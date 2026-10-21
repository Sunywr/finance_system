import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from apps.common.utils.crypto import encrypt_text
from .models import ArchiveShard, LegacyRecord, MigrationBatch
from .source import SECRET_WORDS, assert_target, canonical, digest, normalized

FACTS = set(
    """account_account account_accountlabel account_label account_category account_accountbudget
account_budget account_budgetcategory account_asset account_assetcategory account_autoinvestplan
account_balancefix account_bill_review account_bill_review_item account_brand account_creditcard
account_creditcard_prepayment account_debt account_debtcategory account_invest account_investcategory
account_cockpitusersetting account_investrisktemplate account_investstockpolicyconfig account_investstrategy
account_investpolicyresult account_lifetime_return_repair account_presale account_presalecategory
account_stockaccount account_trecord cash_account cash_account_category stock_cash_flow_ledger
stock_cost_basis_anchor stock_holding_plan stock_holding_plan_item stock_holding_plan_stage
stock_trade_discipline_log stock_profit_target stock_allocation_override stock_automation_config
stock_watch_config stock_watch_position_policy stock_watch_grid_plan stock_watch_collection_budget
stock_watch_notify_setting stock_watch_action stock_watch_archive stock_advice_order stock_broker_snapshot
stock_broker_grid_config stock_broker_grid_event stock_reconciliation_version stock_trading_rule
stock_dividend_rotation_config stock_dividend_rotation_target_override stock_discipline_config
stock_robot_position_config stock_bs_model_config stock_bs_runtime_config stock_screen_config
stock_growth_config finance_low_risk_profile finance_low_risk_bucket finance_low_risk_product
finance_low_risk_operation_log finance_low_risk_nav finance_watchlist ff_config ff_config_version
ff_instrument_config ff_asset_bucket_override ff_profit_allocation_ledger ff_trade_discipline_log
ff_holding_annual_review ff_wealth_income_record sim_account sim_position sim_trade
config_items strategy_configs indicator_config kdj_decision_config stock_ai_model_config
income_review income_review_attention investment_cost_review investment_review investment_thesis_revision
investment_trade_plan investment_trade_review investment_trade_tranche investment_holding_lot
investment_instrument investment_transactions investments balance_calibrations auto_invest_plans
assets budgets bills bill_tags debts brands credit_cards presales users""".split()
)
PUBLIC_TABLES = set(
    """stock_daily_bar account_asharestock account_ashare_fundamental
account_ashare_net_profit_yearly stock_selection_calendar stock_selection_quote stock_delisted
stock_sector_daily stock_sector_constituent stock_public_dividend_history_snapshot""".split()
)
SENSITIVE_TABLES = {
    "auth_user",
    "auth_user_groups",
    "auth_user_user_permissions",
    "django_session",
    "stock_ai_model_config",
    "config_items",
    "stock_watch_notify_setting",
}


def is_fact(table):
    return table in FACTS or table.startswith(("mortgage_", "household_", "longterm_"))


def protect(value):
    """Archive private credentials encrypted under the target key; never expose via API."""
    if isinstance(value, (list, tuple)):
        return [protect(v) for v in value]
    if not isinstance(value, dict):
        return normalized(value)
    return {
        k: (
            {"__encrypted__": encrypt_text(canonical(v))}
            if any(w in k.lower() for w in SECRET_WORDS)
            else protect(v)
        )
        for k, v in value.items()
    }


def metadata(row):
    owner = row.get("owner_id_id", row.get("owner_id", row.get("user_id")))
    code = str(row.get("code", row.get("symbol", "")) or "")[:32]
    value = next(
        (
            row.get(k)
            for k in (
                "account_date",
                "trade_date",
                "flow_date",
                "due_date",
                "screen_date",
                "decision_time",
                "created_at",
                "create_at",
                "date",
            )
            if row.get(k)
        ),
        None,
    )
    try:
        day = date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        day = None
    return owner, code, day


def ingest(source, output):
    assert_target()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    root = Path(settings.LEGACY_ARCHIVE_ROOT).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if MigrationBatch.objects.exclude(
        snapshot_sha256=source.config["snapshot_sha256"]
    ).exists():
        raise RuntimeError("A different snapshot requires a fresh rehearsal database")
    batch, _ = MigrationBatch.objects.get_or_create(
        snapshot_sha256=source.config["snapshot_sha256"],
        defaults={
            "source_identity": {
                k: v for k, v in source.config.items() if k not in ("password", "user")
            }
        },
    )
    inventory_path = output / "inventory.json"
    inventory = (
        json.loads(inventory_path.read_text(encoding="utf8"))
        if inventory_path.exists()
        else {}
    )
    # Users must exist before original facts can reference them. Preserve hashes exactly.
    from django.contrib.auth import get_user_model

    User = get_user_model()
    for row in source.all("auth_user"):
        values = {
            k: row[k]
            for k in (
                "username",
                "password",
                "last_login",
                "is_superuser",
                "first_name",
                "last_name",
                "email",
                "is_staff",
                "is_active",
                "date_joined",
            )
        }
        for key in ("last_login", "date_joined"):
            if values[key]:
                from django.utils import timezone
                from datetime import timezone as dt_timezone

                values[key] = timezone.make_aware(values[key], dt_timezone.utc)
        user, created = User.objects.get_or_create(pk=row["id"], defaults=values)
        if not created and (
            user.username != row["username"] or user.password != row["password"]
        ):
            raise RuntimeError("Target user collision")
        if not created:
            User.objects.filter(pk=user.pk).update(
                last_login=values["last_login"], date_joined=values["date_joined"]
            )
    user_ids = set(User.objects.values_list("pk", flat=True))
    # Resolve association-owned rows before archiving. Missing ownership fails
    # closed in the reader rather than granting global household access.
    owner_maps = {}
    for reference in (
        "account_invest",
        "account_account",
        "account_creditcard",
        "account_stockaccount",
        "mortgage_loan",
        "mortgage_housing_fund_account",
        "stock_selection_run",
    ):
        owner_maps[reference] = {
            r["id"]: r.get("owner_id_id", r.get("owner_id", r.get("user_id")))
            for r in source.all(reference)
            if "id" in r
        }
    references = {
        "account_invest_id": "account_invest",
        "invest_id": "account_invest",
        "related_invest_id": "account_invest",
        "account_id_id": "account_account",
        "related_account_id": "account_account",
        "credit_card_id": "account_creditcard",
        "stock_account_id": "account_stockaccount",
        "loan_id": "mortgage_loan",
        "fund_account_id": "mortgage_housing_fund_account",
        "run_id": "stock_selection_run",
    }
    for table in source.tables:
        if table in inventory and inventory[table].get("complete"):
            continue
        count = 0
        semantic = hashlib.sha256()
        sequence = 0
        shard_rows = []
        records = []
        buffer_bytes = 0

        def flush():
            nonlocal sequence, shard_rows, records, buffer_bytes
            if not shard_rows:
                return
            relative = f"{batch.snapshot_sha256[:16]}/{table}/{sequence:06d}.ndjson.gz"
            path = (root / relative).resolve()
            if not path.is_relative_to(root):
                raise RuntimeError("Archive escaped root")
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = hashlib.sha256()
            owners = set()
            days = []
            temp = path.with_suffix(".partial")
            with temp.open("wb") as h, gzip.GzipFile(
                filename="", fileobj=h, mode="wb", mtime=0, compresslevel=6
            ) as z:
                for item in shard_rows:
                    line = (canonical(item) + "\n").encode()
                    raw.update(line)
                    z.write(line)
                    if item["owner_id"] is not None:
                        owners.add(item["owner_id"])
                    if item["business_date"]:
                        days.append(item["business_date"])
            compressed = hashlib.sha256()
            with temp.open("rb") as h:
                for b in iter(lambda: h.read(1024 * 1024), b""):
                    compressed.update(b)
            sha = compressed.hexdigest()
            temp.replace(path)
            with transaction.atomic():
                LegacyRecord.objects.bulk_create(
                    records, ignore_conflicts=True, batch_size=250
                )
                ArchiveShard.objects.update_or_create(
                    batch=batch,
                    table=table,
                    sequence=sequence,
                    defaults=dict(
                        relative_path=relative,
                        rows=len(shard_rows),
                        sha256=sha,
                        raw_sha256=raw.hexdigest(),
                        owner_ids=sorted(owners),
                        min_date=min(days) if days else None,
                        max_date=max(days) if days else None,
                    ),
                )
            sequence += 1
            shard_rows = []
            records = []
            buffer_bytes = 0

        for pk, row in source.rows(table):
            owner, code, day = metadata(row)
            original_hash = digest(row)
            semantic.update((pk + "\t" + original_hash + "\n").encode())
            count += 1
            if owner is None:
                for column, reference in references.items():
                    if row.get(column) in owner_maps[reference]:
                        owner = owner_maps[reference][row[column]]
                        break
            payload = protect(row)
            shard_rows.append(
                dict(
                    source_pk=pk,
                    owner_id=owner,
                    code=code,
                    business_date=str(day) if day else None,
                    sha256=original_hash,
                    payload=payload,
                )
            )
            buffer_bytes += len(canonical(payload).encode())
            if is_fact(table) and table not in SENSITIVE_TABLES:
                records.append(
                    LegacyRecord(
                        batch=batch,
                        table=table,
                        source_pk=pk,
                        owner_id=owner if owner in user_ids else None,
                        business_date=day,
                        code=code,
                        payload=payload,
                        sha256=original_hash,
                    )
                )
            if len(shard_rows) >= 500 or buffer_bytes >= 4 * 1024 * 1024:
                flush()
        flush()
        inventory[table] = dict(
            rows=count,
            shards=sequence,
            semantic_sha256=semantic.hexdigest(),
            classification=(
                "empty"
                if not count
                else (
                    "financial_or_configuration_fact"
                    if is_fact(table)
                    else (
                        "market_history"
                        if table in PUBLIC_TABLES
                        else "archived_original"
                    )
                )
            ),
            online_originals=bool(is_fact(table) and table not in SENSITIVE_TABLES),
            complete=True,
        )
        temp = inventory_path.with_suffix(".partial")
        temp.write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf8"
        )
        temp.replace(inventory_path)
        print(f"Archived {table}: {count} records", flush=True)
    batch.report = {
        "inventory_tables": len(inventory),
        "source_rows": sum(v["rows"] for v in inventory.values()),
        "archive_policy": "All originals immutable; recent 90 days queryable alongside older archive; financial/config facts also online. No source deletion.",
    }
    batch.save(update_fields=["report"])
    return batch, inventory
