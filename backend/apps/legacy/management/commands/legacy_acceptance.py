"""Financial/permission checks in addition to the complete archive verification."""

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone
from rest_framework.test import APIClient
from apps.assets.models import Asset
from apps.debts.models import CreditCard, DebtItem, DebtPayment
from apps.debts.services import card_liability
from apps.investments.models import DailyBar
from apps.insights.models import AIProviderConfig
from apps.common.utils.crypto import decrypt_text
from apps.mortgages.models import Loan
from apps.mortgages.services import loan_stats
from apps.ledger.models import Transaction
from apps.legacy.models import MigrationBatch, SourceMap, Membership, PositionBasis
from apps.legacy.scope import household_owner_ids
from apps.legacy.source import Source, assert_target, money, number


class Command(BaseCommand):
    help = "检查债务、资产、房贷本金、行情、AI 密钥及真实用户权限，私有报告不输出金额或密钥"

    def add_arguments(self, p):
        p.add_argument("--source", required=True)
        p.add_argument("--output", required=True)

    def handle(self, *args, **o):
        assert_target()
        s = Source(o["source"])
        out = Path(o["output"])
        batch = MigrationBatch.objects.get(snapshot_sha256=s.config["snapshot_sha256"])
        maps = {
            (m.table, m.source_pk, m.component): m
            for m in SourceMap.objects.filter(batch=batch)
        }
        errors = []
        checks = {}

        def target(model, table, pk, component="main"):
            return model.objects.get(pk=maps[(table, str(pk), component)].target_pk)

        try:
            for r in s.all("account_asset"):
                a = target(Asset, "account_asset", r["id"])
                if (
                    a.manual_value != money(r["value"])
                    or a.owner_id != r["owner_id_id"]
                ):
                    errors.append({"kind": "asset", "pk": r["id"]})
            checks["assets"] = len(s.all("account_asset"))
            debt_types = {
                r["id"]: r["name"].lower() for r in s.all("account_debtcategory")
            }
            source_debts = s.all("account_debt")
            for r in source_debts:
                d = target(DebtItem, "account_debt", r["id"])
                if (
                    d.amount != money(r["debt_amount"])
                    or d.owner_id != r["owner_id_id"]
                ):
                    errors.append({"kind": "debt", "pk": r["id"]})
                if (r["status"] == 1) != (d.status == "PAID"):
                    errors.append({"kind": "debt_status", "pk": r["id"]})
            checks["debts"] = len(source_debts)
            for r in s.all("account_creditcard"):
                card = target(CreditCard, "account_creditcard", r["id"])
                expected = sum(
                    (
                        money(d["debt_amount"])
                        for d in source_debts
                        if d["status"] == 0
                        and d["credit_card_id"] == r["id"]
                        and debt_types.get(d["debt_type_id"]) == "credit_card"
                    ),
                    Decimal(0),
                )
                if card_liability(card) != expected:
                    errors.append({"kind": "credit_card_open_debt", "pk": r["id"]})
            checks["credit_cards"] = len(s.all("account_creditcard"))
            for r in s.all("mortgage_loan"):
                loan = target(Loan, "mortgage_loan", r["id"])
                if loan_stats(loan)["remaining_principal"] != money(
                    r["remaining_principal"]
                ):
                    errors.append({"kind": "loan_remaining_principal", "pk": r["id"]})
            checks["loan_principal"] = len(s.all("mortgage_loan"))
            for m in SourceMap.objects.filter(batch=batch, component="payment"):
                d = DebtPayment.objects.get(pk=m.target_pk)
                txn = target(Transaction, "account_account", m.source_pk, "expenditure")
                if d.amount != txn.amount or d.transaction_id != txn.pk:
                    errors.append({"kind": "payment_link", "pk": m.source_pk})
            checks["linked_payments"] = DebtPayment.objects.count()
            for r in s.all("stock_ai_model_config"):
                p = target(AIProviderConfig, "stock_ai_model_config", r["id"])
                if decrypt_text(p.api_key_encrypted) != r["api_key"] or p.enabled:
                    errors.append({"kind": "provider_encryption", "pk": r["id"]})
            checks["reencrypted_ai_providers"] = len(s.all("stock_ai_model_config"))
            for b in PositionBasis.objects.filter(
                batch=batch,
                is_active=True,
                instrument__type__in=["STOCK", "ETF", "CONVERTIBLE_BOND"],
            ).select_related("instrument"):
                original = s.query(
                    "SELECT date,close FROM stock_daily_bar WHERE code=%s ORDER BY date",
                    [b.instrument.symbol],
                )
                actual = dict(
                    DailyBar.objects.filter(instrument=b.instrument).values_list(
                        "trade_date", "close"
                    )
                )
                if len(original) != len(actual) or any(
                    r["date"] not in actual
                    or abs(number(r["close"]) - actual[r["date"]])
                    > Decimal(".000000005")
                    for r in original
                ):
                    errors.append(
                        {
                            "kind": "necessary_price_history",
                            "source_invest_id": b.source_invest_id,
                        }
                    )
            checks["native_daily_bars"] = DailyBar.objects.count()
            permissions = []
            for u in get_user_model().objects.filter(is_active=True):
                expected_groups = {
                    r["household_id"]
                    for r in s.all("household_member")
                    if r["user_id"] == u.pk and r["status"] == "active"
                }
                expected_owners = {
                    r["user_id"]
                    for r in s.all("household_member")
                    if r["household_id"] in expected_groups and r["status"] == "active"
                } or {u.pk}
                if set(household_owner_ids(u)) != expected_owners:
                    errors.append({"kind": "household_permission", "user_id": u.pk})
                c = APIClient()
                c.force_authenticate(u)
                for path in [
                    "/api/v1/household/summary",
                    "/api/v1/history/types",
                    "/api/v1/history/records?table=account_account&page_size=5",
                    "/api/v1/holdings",
                ]:
                    r = c.get(path, HTTP_HOST="localhost")
                    if r.status_code != 200:
                        errors.append(
                            {
                                "kind": "real_data_api",
                                "user_id": u.pk,
                                "path": path,
                                "status": r.status_code,
                            }
                        )
                    elif "history/records" in path and any(
                        x["owner_id"] not in expected_owners for x in r.data["results"]
                    ):
                        errors.append({"kind": "archive_scope_leak", "user_id": u.pk})
                permissions.append(
                    {
                        "user_id": u.pk,
                        "expected_owner_ids": sorted(expected_owners),
                        "superuser_global_bypass": False,
                    }
                )
            checks["real_users_checked"] = len(permissions)
            issues = list(
                batch.migrationissue_set.values(
                    "table", "source_pk", "reason", "details"
                )
            )
            report = {
                "checks": checks,
                "permissions": permissions,
                "errors": errors,
                "passed": not errors,
                "source_exception_summary": dict(Counter(x["reason"] for x in issues)),
                "source_exception_count": len(issues),
            }
            (out / "acceptance.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
            )
            self.stdout.write(
                json.dumps(
                    {
                        "passed": not errors,
                        "checks": checks,
                        "errors": len(errors),
                        "source_exception_count": len(issues),
                    }
                )
            )
        finally:
            s.close()
