import gzip
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.utils import timezone
from apps.accounts.models import Account
from apps.accounts.services import account_balance
from apps.assets.models import Asset
from apps.investments.services import portfolio_summary
from apps.ledger.models import Transaction
from apps.mortgages.models import LoanSchedule
from apps.common.utils.crypto import decrypt_text
from .archive import path_for
from .models import ArchiveShard, LegacyRecord, MigrationIssue, PositionBasis, SourceMap
from .source import canonical, digest, money, number, normalized


def unprotect(v):
    if isinstance(v, list):
        return [unprotect(x) for x in v]
    if not isinstance(v, dict):
        return v
    if "__encrypted__" in v:
        plain = decrypt_text(v["__encrypted__"])
        if not plain:
            raise ValueError("Cannot decrypt protected archive field")
        return json.loads(plain)
    return {k: unprotect(x) for k, x in v.items()}


def verify(source, batch, output):
    inventory = json.loads((Path(output) / "inventory.json").read_text(encoding="utf8"))
    errors = []
    counts = {}
    archive_bytes = 0
    archive_rows = 0
    for table, entry in inventory.items():
        semantic = hashlib.sha256()
        count = 0
        for shard in ArchiveShard.objects.filter(batch=batch, table=table).order_by(
            "sequence"
        ):
            path = path_for(shard)
            sha = hashlib.sha256()
            raw = hashlib.sha256()
            with path.open("rb") as h:
                for b in iter(lambda: h.read(1024 * 1024), b""):
                    sha.update(b)
            if sha.hexdigest() != shard.sha256:
                errors.append(
                    {
                        "kind": "archive_file_hash",
                        "table": table,
                        "shard": shard.sequence,
                    }
                )
            archive_bytes += path.stat().st_size
            with gzip.open(path, "rb") as h:
                for line in h:
                    raw.update(line)
                    r = json.loads(line)
                    count += 1
                    if digest(unprotect(r["payload"])) != r["sha256"]:
                        errors.append(
                            {
                                "kind": "archive_row_hash",
                                "table": table,
                                "pk": r["source_pk"],
                            }
                        )
                    semantic.update(
                        (r["source_pk"] + "\t" + r["sha256"] + "\n").encode()
                    )
            if raw.hexdigest() != shard.raw_sha256:
                errors.append(
                    {
                        "kind": "archive_raw_hash",
                        "table": table,
                        "shard": shard.sequence,
                    }
                )
        if count != entry["rows"] or semantic.hexdigest() != entry["semantic_sha256"]:
            errors.append({"kind": "archive_table_hash", "table": table})
        archive_rows += count
        if (
            entry["online_originals"]
            and LegacyRecord.objects.filter(batch=batch, table=table).count() != count
        ):
            errors.append({"kind": "online_fact_count", "table": table})
    if set(source.tables) != set(inventory):
        errors.append({"kind": "table_coverage"})
    maps = {
        (m.table, m.source_pk, m.component): m
        for m in SourceMap.objects.filter(batch=batch)
    }
    txns = {t.pk: t for t in Transaction.objects.filter(source="LEGACY")}
    expected = defaultdict(lambda: Decimal(0))
    actual = defaultdict(lambda: Decimal(0))
    target_ids = set()
    for r in source.all("account_account"):
        components = [k for k in ("income", "expenditure") if number(r[k]) != 0] or [
            "note"
        ]
        for component in components:
            m = maps.get(("account_account", str(r["id"]), component))
            t = txns.get(m.target_pk) if m else None
            if not t:
                errors.append(
                    {
                        "kind": "missing_ledger_component",
                        "pk": r["id"],
                        "component": component,
                    }
                )
                continue
            target_ids.add(t.pk)
            day = timezone.localtime(t.occurred_at).replace(tzinfo=None)
            if day != r["account_date"]:
                errors.append({"kind": "business_time_shift", "pk": r["id"]})
            if t.owner_id != r["owner_id_id"]:
                errors.append({"kind": "owner_changed", "pk": r["id"]})
            value = money(r.get(component, 0)) if component != "note" else Decimal(0)
            if value != t.amount:
                errors.append(
                    {"kind": "ledger_amount", "pk": r["id"], "component": component}
                )
            key = f'{r["owner_id_id"]}:{r["account_date"]:%Y-%m}:{component}'
            expected[key] += value
            actual[key] += t.amount
    if target_ids != set(txns):
        errors.append({"kind": "unexpected_legacy_transactions"})
    for key in expected:
        if expected[key] != actual[key]:
            errors.append({"kind": "monthly_total", "key": key})
    cash_results = []
    flows = source.all("account_account")
    for r in source.all("cash_account"):
        m = maps[("cash_account", str(r["id"]), "main")]
        a = Account.objects.get(pk=m.target_pk)
        original = money(
            number(r["opening_balance"])
            + sum(
                (
                    number(x["income"]) - number(x["expenditure"])
                    for x in flows
                    if x.get("cash_account_id") == r["id"]
                ),
                Decimal(0),
            )
        )
        actual_balance = money(account_balance(a))
        same = original == actual_balance
        cash_results.append({"source_account_id": r["id"], "match": same})
        if not same:
            errors.append(
                {
                    "kind": "cash_account_balance",
                    "pk": r["id"],
                    "expected": str(original),
                    "actual": str(actual_balance),
                }
            )
    position_results = []
    auto_ids = {r["invest_id"] for r in source.all("account_autoinvestplan")}
    for r in source.all("account_invest"):
        b = PositionBasis.objects.get(batch=batch, source_invest_id=r["id"])
        for old, new in [
            ("share", "quantity"),
            ("cost", "cost"),
            ("value", "market_value"),
            ("profit", "profit"),
            ("price", "price"),
        ]:
            if abs(number(r[old]) - getattr(b, new)) > Decimal(".000000005"):
                errors.append({"kind": "position_fact", "pk": r["id"], "field": old})
    for u in get_user_model().objects.all():
        rows = [
            r
            for r in source.all("account_invest")
            if r["owner_id_id"] == u.pk and r["status"] == 0 and r["id"] not in auto_ids
        ]
        p = portfolio_summary(u)["totals"]
        for old, new in [
            ("cost", "cost"),
            ("value", "market_value"),
            ("profit", "total_pnl"),
        ]:
            source_value = money(sum((number(r[old]) for r in rows), Decimal(0)))
            if abs(source_value - p[new]) > Decimal(".01"):
                errors.append(
                    {
                        "kind": "portfolio_total",
                        "owner": u.pk,
                        "field": new,
                        "expected": str(source_value),
                        "actual": str(p[new]),
                    }
                )
        position_results.append(
            {"owner_id": u.pk, "active_source_positions": len(rows)}
        )
    for r in source.all("mortgage_repayment_plan"):
        m = maps[("mortgage_repayment_plan", str(r["id"]), "main")]
        s = LoanSchedule.objects.get(pk=m.target_pk)
        for old, new in [
            ("principal_due", "principal_due"),
            ("interest_due", "interest_due"),
            ("payment_due", "total_due"),
            ("closing_principal", "remaining_principal"),
        ]:
            if money(r[old]) != getattr(s, new):
                errors.append(
                    {"kind": "mortgage_schedule", "pk": r["id"], "field": old}
                )
    password_checks = []
    for r in source.all("auth_user"):
        u = get_user_model().objects.get(pk=r["id"])
        same = u.password == r["password"]
        try:
            algorithm = identify_hasher(u.password).algorithm
        except ValueError:
            algorithm = "unsupported"
            same = False
        password_checks.append(
            {"user_id": u.pk, "hash_preserved": same, "algorithm": algorithm}
        )
        if not same:
            errors.append({"kind": "password_hash", "user_id": u.pk})
    issues = list(
        MigrationIssue.objects.filter(batch=batch).values(
            "severity", "table", "source_pk", "reason", "details"
        )
    )
    report = dict(
        snapshot_sha256=batch.snapshot_sha256,
        table_coverage=len(inventory),
        archive_rows=archive_rows,
        archive_bytes=archive_bytes,
        ledger_rows=len(flows),
        native_ledger_components=len(target_ids),
        monthly_groups=len(expected),
        monthly_totals_match=expected == actual,
        cash_accounts=cash_results,
        positions=position_results,
        passwords=password_checks,
        source_limitations=issues,
        migration_errors=errors,
        migration_integrity_passed=not errors,
        full_replacement_ready=False,
        limitations=[
            "Native holdings preserve the persisted snapshot; confirmed cost-book overrides and full historical realized/yearly profit still require equivalence validation.",
            "Budget/presale/automatic-investment and multi-fund offset originals are queryable; their complete workflows are listed in the replacement assessment.",
            "Archived source facts and original limitations are not treated as corrected by the import.",
        ],
    )
    (Path(output) / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf8"
    )
    batch.report.update(
        verification={
            k: v
            for k, v in report.items()
            if k not in ("source_limitations", "cash_accounts", "passwords")
        }
    )
    batch.state = "VERIFIED" if not errors else "NEEDS_REVIEW"
    batch.save(update_fields=["report", "state"])
    return {
        "migration_integrity_passed": not errors,
        "migration_errors": len(errors),
        "source_limitations": len(issues),
        "archive_rows": archive_rows,
        "full_replacement_ready": False,
    }
