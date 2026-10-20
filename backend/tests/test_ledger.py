from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.accounts.services import account_balance
from apps.debts.cycles import card_period_for
from apps.debts.services import compute_bill_totals, settle_debt
from apps.ledger.models import Transaction
from apps.ledger.services import (
    create_installment_purchase,
    create_refund,
    create_transaction,
    create_transfer,
    preview_installment,
)

pytestmark = pytest.mark.django_db


def aware(dt):
    return timezone.make_aware(dt)


def test_transfer_creates_two_legs_and_updates_balances(user, categories, savings, alipay):
    transfer = create_transfer(
        owner=user,
        from_account=savings,
        to_account=alipay,
        amount="1000",
        fee="10",
        occurred_at=timezone.now(),
    )
    assert Transaction.objects.filter(transfer=transfer).count() == 2
    assert account_balance(savings) == 8990
    assert account_balance(alipay) == 1000


def test_refund_requires_original_and_respects_limit(user, categories, savings):
    original = create_transaction(
        owner=user,
        txn_type=Transaction.Type.EXPENSE,
        category=categories["餐饮"],
        amount="100",
        settlement_channel=Transaction.SettlementChannel.CASH,
        account=savings,
        occurred_at=timezone.now(),
    )
    refund = create_refund(owner=user, original=original, amount="30")
    assert refund.type == Transaction.Type.REFUND
    assert account_balance(savings) == 9930
    with pytest.raises(Exception):
        create_refund(owner=user, original=original, amount="80")


def test_installment_preview_and_parent_excluded_from_bill(user, categories, card):
    from decimal import Decimal

    preview = preview_installment(card=card, principal="1000", periods=3)
    assert preview["rows"][-1]["amount"] == Decimal("333.34")
    assert sum(row["amount"] for row in preview["rows"]) == 1000
    parent, plan = create_installment_purchase(
        owner=user,
        card=card,
        principal="1200",
        periods=3,
        occurred_at=timezone.now(),
        category=categories["购物"],
    )
    assert plan.period_rows.count() == 3
    assert parent.exclude_from_card_bill is True
    start, end = card_period_for(card, timezone.now())
    totals = compute_bill_totals(card, start, end)
    assert totals["total_amount"] == 0
    first = plan.period_rows.order_by("period_no").first()
    first_totals = compute_bill_totals(card, first.bill_period_start, first.bill_period_end)
    assert first_totals["installment_total"] == 400


def test_closed_card_bill_creates_debt_and_payment_with_discount(user, categories, card, savings):
    start, end = card_period_for(card, timezone.now() - timedelta(days=40))
    occurred = aware(datetime.combine(start + timedelta(days=2), datetime.min.time()))
    txn = create_transaction(
        owner=user,
        txn_type=Transaction.Type.EXPENSE,
        category=categories["购物"],
        amount="500",
        settlement_channel=Transaction.SettlementChannel.CREDIT_CARD,
        credit_card=card,
        occurred_at=occurred,
    )
    card.refresh_from_db()
    from apps.debts.models import DebtItem

    debt = DebtItem.objects.filter(bill__card=card).first()
    assert debt is not None
    assert debt.amount == 500
    payment = settle_debt(
        owner=user,
        debt_item=debt,
        amount="400",
        discount="100",
        channel="CASH",
        account=savings,
        idempotency_key="pay-1",
    )
    debt.refresh_from_db()
    assert payment.amount == 400
    assert debt.status == DebtItem.Status.PAID
    assert account_balance(savings) == 9600
    txn.refresh_from_db()
    assert txn.status == Transaction.Status.POSTED
