import gzip
import hashlib
import json
from datetime import date, datetime, timedelta, timezone as utc
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.accounts.services import account_balance
from apps.debts.models import CreditCard, DebtItem
from apps.debts.services import card_liability, settle_debt
from apps.investments.models import Instrument, Trade
from apps.investments.services import holdings, create_trade
from apps.ledger.models import Transaction
from apps.legacy.archive import page, path_for, redact
from apps.legacy.ingest import protect
from apps.legacy.models import (
    ArchiveShard,
    Household,
    Membership,
    MigrationBatch,
    PositionBasis,
    AccountBalanceBasis,
)
from apps.legacy.project import Projector
from apps.legacy.scope import household_owner_ids
from apps.legacy.source import business_time, canonical, digest
from apps.legacy.verify import unprotect

pytestmark = pytest.mark.django_db


@pytest.fixture
def batch():
    return MigrationBatch.objects.create(
        snapshot_sha256="a" * 64,
        source_identity={"snapshot_finished_at": "2026-10-21T03:00:00+00:00"},
    )


def test_household_scope_never_gives_superuser_global_access(user):
    U = get_user_model()
    peer = U.objects.create_user(username="peer")
    admin = U.objects.create_superuser(username="root", password="test")
    h = Household.objects.create(name="family", manager=user)
    Membership.objects.create(household=h, user=user, role="manager")
    Membership.objects.create(household=h, user=peer, role="viewer")
    assert household_owner_ids(user) == sorted([user.pk, peer.pk])
    assert household_owner_ids(admin) == [admin.pk]
    peer.is_active = False
    peer.save()
    assert household_owner_ids(user) == [user.pk]


def test_archive_owner_filter_cursor_and_integrity(user, batch, tmp_path, settings):
    settings.LEGACY_ARCHIVE_ROOT = tmp_path
    records = [
        {
            "source_pk": str(n),
            "owner_id": owner,
            "code": "600000",
            "business_date": "2026-01-01",
            "payload": {"note": "safe"},
            "sha256": "x",
        }
        for n, owner in enumerate([user.pk, 999, user.pk])
    ]
    raw = "".join(canonical(r) + "\n" for r in records).encode()
    path = tmp_path / "test.gz"
    path.write_bytes(gzip.compress(raw, mtime=0))
    ArchiveShard.objects.create(
        batch=batch,
        table="account_account",
        sequence=0,
        relative_path="test.gz",
        rows=3,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        owner_ids=[user.pk, 999],
    )
    one = page(user, {"table": "account_account", "page_size": "1"})
    assert [x["source_pk"] for x in one["results"]] == ["0"]
    two = page(
        user,
        {"table": "account_account", "page_size": "1", "cursor": one["next_cursor"]},
    )
    assert [x["source_pk"] for x in two["results"]] == ["2"]
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        page(
            user,
            {
                "table": "account_account",
                "code": "changed",
                "cursor": one["next_cursor"],
            },
        )
    path.write_bytes(b"corrupt")
    with pytest.raises(ValidationError):
        page(user, {"table": "account_account"})


def test_archive_secrets_roundtrip_and_redaction():
    value = {
        "api_key": "private",
        "nested": [{"authorization": "Bearer private"}],
        "number": -0.0,
    }
    protected = protect(value)
    assert unprotect(protected) == value
    assert "private" not in json.dumps(protected)
    assert "private" not in json.dumps(redact(protected))


def test_archive_rejects_path_escape(batch, tmp_path, settings):
    settings.LEGACY_ARCHIVE_ROOT = tmp_path
    shard = ArchiveShard(relative_path="../secret")
    with pytest.raises(RuntimeError):
        path_for(shard)


def test_shanghai_wall_time_is_not_moved_to_next_day():
    value = business_time("2026-12-31 23:30:00")
    assert value.astimezone(utc.utc).isoformat() == "2026-12-31T15:30:00+00:00"
    assert timezone.localtime(value).date().isoformat() == "2026-12-31"


def test_mysql_time_keeps_negative_and_fractional_duration():
    value = {"time": timedelta(hours=-30, microseconds=123)}
    assert (
        json.loads(canonical(value))["time"]["__mysql_time_microseconds__"]
        == -108000000000 + 123
    )


def test_imported_balance_does_not_count_historical_cash_twice(
    user, batch, savings, categories
):
    cutoff = timezone.now()
    AccountBalanceBasis.objects.create(
        account=savings,
        batch=batch,
        as_of=cutoff,
        balance=200,
        available=150,
        frozen=50,
    )
    Transaction.objects.create(
        owner=user,
        category=categories["餐饮"],
        txn_no="old",
        type="EXPENSE",
        amount=70,
        account=savings,
        occurred_at=cutoff - timedelta(days=1),
    )
    Transaction.objects.create(
        owner=user,
        category=categories["餐饮"],
        txn_no="new",
        type="EXPENSE",
        amount=20,
        account=savings,
        occurred_at=cutoff + timedelta(seconds=1),
    )
    assert account_balance(savings) == 180


def test_snapshot_is_not_a_fabricated_buy_and_later_sale_advances_it(
    user, batch, categories
):
    a = Account.objects.create(
        owner=user, name="broker", type="STOCK", opening_balance=10000
    )
    i = Instrument.objects.create(
        owner=user, symbol="113001", name="bond", type="CONVERTIBLE_BOND"
    )
    cutoff = timezone.now() - timedelta(days=1)
    PositionBasis.objects.create(
        batch=batch,
        source_invest_id=1,
        owner=user,
        account=a,
        instrument=i,
        as_of=cutoff,
        quantity=100,
        cost=9000,
        market_value=10000,
        profit=1100,
        price=100,
        cost_anchor={"verified_total_cost": 9000},
    )
    before = holdings(user)[0]
    assert before["cost"] == 9000 and before["total_pnl"] == 1100
    assert Trade.objects.count() == 0
    assert before["realized_pnl"] is None
    sold = create_trade(
        owner=user,
        account=a,
        instrument=i,
        side="SELL",
        operation="REDUCE",
        quantity=20,
        price=100,
        trade_date=timezone.now(),
    )
    after = holdings(user)[0]
    assert after["quantity"] == 80 and after["cost"] == 7200
    assert sold.realized_pnl == 200 and after["total_pnl"] == 1100


def test_imported_credit_debt_can_be_paid_without_inventing_statement(
    user, batch, savings
):
    card = CreditCard.objects.create(owner=user, name="old card")
    debt = DebtItem.objects.create(
        owner=user,
        kind="CREDIT_CARD",
        legacy_card=card,
        title="old debt",
        due_date=timezone.localdate(),
        amount=100,
        status="PENDING",
    )
    assert card_liability(card) == 100
    settle_debt(owner=user, debt_item=debt, amount=40, account=savings)
    debt.refresh_from_db()
    assert debt.paid_amount == 40 and debt.bill_id is None
    assert card_liability(card) == 60
    assert Transaction.objects.get(source="DEBT_PAYMENT").type == "TRANSFER_OUT"


def test_split_income_expense_zero_and_idempotency(user, batch, settings):
    settings.MIGRATION_REHEARSAL = True
    from unittest.mock import patch
    from apps.ledger.models import Category

    category = Category.objects.create(owner=user, name="legacy")
    from apps.legacy.models import SourceMap

    SourceMap.objects.create(
        batch=batch,
        table="account_category",
        source_pk="1",
        component=str(user.pk),
        target_model="ledger.Category",
        target_pk=category.pk,
        sha256="x",
    )
    base = dict(
        id=1,
        owner_id_id=user.pk,
        account_type_id=1,
        account_date=datetime(2026, 1, 1),
        income=3.5,
        expenditure=2,
        is_cash=1,
        credit_card_id=None,
        debt_id=None,
        asset_id=None,
        invest_id=None,
        refund_of_id=None,
        description="both",
        remark="",
        cash_account_id=None,
        stock_account_id=None,
        transfer_id=None,
    )
    zero = dict(base, id=2, income=0, expenditure=None)

    class FixtureSource:
        def all(self, t):
            return (
                [base, zero]
                if t == "account_account"
                else [dict(id=1, name="general")] if t == "account_category" else []
            )

    with patch("apps.legacy.project.assert_target"):
        p = Projector(FixtureSource(), batch)
        p.ledger()
        p.ledger()
    assert Transaction.objects.count() == 3
    assert list(
        Transaction.objects.filter(source_id=1)
        .order_by("id")
        .values_list("amount", flat=True)
    ) == [Decimal("3.50"), Decimal("2")]
    assert Transaction.objects.get(source_id=2).type == "NOTE"


def test_history_requires_authentication():
    assert APIClient().get("/api/v1/history/types").status_code == 401


def test_source_limitation_is_recorded_and_idempotent(batch):
    from unittest.mock import patch

    class FixtureSource:
        pass

    with patch("apps.legacy.project.assert_target"):
        p = Projector(FixtureSource(), batch)
        p.issue("account_account", 1, "original association absent")
        p.issue("account_account", 1, "original association absent")
    assert batch.migrationissue_set.count() == 1
    assert batch.migrationissue_set.get().severity == "SOURCE_LIMITATION"


def test_provider_key_is_reencrypted_without_argument_collision(user, batch):
    from unittest.mock import patch
    from apps.insights.models import AIProviderConfig
    from apps.common.utils.crypto import decrypt_text

    class FixtureSource:
        def all(self, t):
            return (
                [
                    dict(
                        id=1,
                        owner_id=user.pk,
                        config_name="source",
                        base_url="https://example.com/v1",
                        api_key="private-test-key",
                        model_name="model",
                    )
                ]
                if t == "stock_ai_model_config"
                else []
            )

    with patch("apps.legacy.project.assert_target"):
        Projector(FixtureSource(), batch).subjects()
    config = AIProviderConfig.objects.get()
    assert config.api_key_encrypted != "private-test-key"
    assert decrypt_text(config.api_key_encrypted) == "private-test-key"
    assert config.enabled is False


def test_auto_plan_default_and_account_filter_preserve_unknown_totals(user, batch):
    a = Account.objects.create(owner=user, name="broker", type="STOCK")
    i = Instrument.objects.create(
        owner=user, symbol="600000", name="test", type="STOCK"
    )
    PositionBasis.objects.create(
        batch=batch,
        source_invest_id=1,
        owner=user,
        account=a,
        instrument=i,
        as_of=timezone.now(),
        quantity=10,
        cost=90,
        market_value=100,
        profit=10,
        price=10,
        is_auto_plan=True,
    )
    assert holdings(user) == []
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(f"/api/v1/holdings?account={a.pk}&include_auto_plans=1")
    assert response.status_code == 200
    assert response.data["totals"]["market_value"] == 100
    assert response.data["totals"]["realized_pnl"] is None
    assert client.get("/api/v1/holdings?account=bad").status_code == 400


def test_rehearsal_cannot_start_scheduler(settings):
    from django.core.management import call_command, CommandError

    settings.MIGRATION_REHEARSAL = True
    with pytest.raises(CommandError):
        call_command("run_scheduler")


def test_imported_loan_balance_uses_original_principal_then_only_new_payments(
    user, batch
):
    from apps.mortgages.models import Loan, LoanSchedule
    from apps.mortgages.services import loan_stats
    from apps.legacy.models import LoanBalanceBasis

    loan = Loan.objects.create(
        owner=user,
        name="original loan",
        loan_type="COMMERCIAL",
        principal=10000,
        annual_rate=3,
        term_months=2,
        first_due_date=date(2026, 1, 1),
    )
    for period, status in [(1, "PAID"), (2, "PENDING")]:
        LoanSchedule.objects.create(
            loan=loan,
            period_no=period,
            due_date=date(2026, period, 1),
            principal_due=100,
            interest_due=10,
            total_due=110,
            status=status,
        )
    LoanBalanceBasis.objects.create(
        loan=loan,
        batch=batch,
        as_of=timezone.now(),
        remaining_principal=8500,
        paid_periods=[1],
    )
    assert loan_stats(loan)["remaining_principal"] == 8500
    loan.schedules.filter(period_no=2).update(status="PAID")
    assert loan_stats(loan)["remaining_principal"] == 8400


def test_import_target_rejects_other_instance_and_enabled_events(tmp_path, settings):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch
    from apps.legacy.source import assert_target

    settings.MIGRATION_REHEARSAL = True
    settings.MIGRATION_INSTANCE_FILE = tmp_path / "instance.json"
    settings.MIGRATION_INSTANCE_FILE.write_text(
        json.dumps({"uuid": "owned", "root": {"port": 58924}})
    )
    cursor = MagicMock()
    fake = SimpleNamespace(
        settings_dict={
            "ENGINE": "django.db.backends.mysql",
            "HOST": "127.0.0.1",
            "NAME": "finance_rehearsal",
            "PORT": "58924",
        },
        cursor=MagicMock(),
    )
    fake.cursor.return_value.__enter__.return_value = cursor
    with patch("apps.legacy.source.connection", fake):
        cursor.fetchone.return_value = ("other", "OFF")
        with pytest.raises(RuntimeError, match="identity"):
            assert_target()
        cursor.fetchone.return_value = ("owned", "ON")
        with pytest.raises(RuntimeError, match="scheduler"):
            assert_target()
        cursor.fetchone.return_value = ("owned", "OFF")
        assert_target()
        fake.settings_dict["PORT"] = "3306"
        with pytest.raises(RuntimeError, match="port"):
            assert_target()
