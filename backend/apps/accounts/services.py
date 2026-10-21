from decimal import Decimal

from django.db.models import Q, Sum

from apps.common.utils.dates import day_end
from apps.common.utils.money import D

from .models import Account


def balance_breakdown(account, as_of=None):
    # Imported lazily to keep model import graph acyclic.
    from apps.ledger.models import Transaction

    qs = Transaction.objects.filter(account=account, status=Transaction.Status.POSTED)
    basis = getattr(account, "imported_balance", None)
    use_basis = basis is not None and (as_of is None or day_end(as_of) >= basis.as_of)
    if use_basis:
        qs = qs.filter(occurred_at__gt=basis.as_of).exclude(source="LEGACY")
    if as_of:
        qs = qs.filter(occurred_at__lte=day_end(as_of))
    agg = qs.aggregate(
        income=Sum("amount", filter=Q(type=Transaction.Type.INCOME)),
        refund=Sum("amount", filter=Q(type=Transaction.Type.REFUND)),
        expense=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
        transfer_in=Sum("amount", filter=Q(type=Transaction.Type.TRANSFER_IN)),
        transfer_out=Sum("amount", filter=Q(type=Transaction.Type.TRANSFER_OUT)),
    )
    income = D(agg["income"] or 0)
    refund = D(agg["refund"] or 0)
    expense = D(agg["expense"] or 0)
    transfer_in = D(agg["transfer_in"] or 0)
    transfer_out = D(agg["transfer_out"] or 0)
    opening = D(basis.balance) if use_basis else D(account.opening_balance)
    current = opening + income + refund - expense + transfer_in - transfer_out
    return {
        "opening_balance": opening,
        "income": income,
        "refund": refund,
        "expense": expense,
        "transfer_in": transfer_in,
        "transfer_out": transfer_out,
        "current_balance": current,
    }


def account_balance(account, as_of=None):
    return balance_breakdown(account, as_of)["current_balance"]


def balances_for_owner(owner, as_of=None):
    from apps.ledger.models import Transaction

    accounts = list(Account.objects.filter(owner=owner))
    mapping = {account.id: D(account.opening_balance) for account in accounts}
    qs = Transaction.objects.filter(
        owner=owner, status=Transaction.Status.POSTED, account__isnull=False
    )
    if as_of:
        qs = qs.filter(occurred_at__lte=day_end(as_of))
    rows = qs.values("account_id").annotate(
        income=Sum("amount", filter=Q(type=Transaction.Type.INCOME)),
        refund=Sum("amount", filter=Q(type=Transaction.Type.REFUND)),
        expense=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
        transfer_in=Sum("amount", filter=Q(type=Transaction.Type.TRANSFER_IN)),
        transfer_out=Sum("amount", filter=Q(type=Transaction.Type.TRANSFER_OUT)),
    )
    for row in rows:
        account_id = row["account_id"]
        mapping[account_id] = (
            mapping.get(account_id, D(0))
            + D(row["income"] or 0)
            + D(row["refund"] or 0)
            - D(row["expense"] or 0)
            + D(row["transfer_in"] or 0)
            - D(row["transfer_out"] or 0)
        )
    from apps.legacy.models import AccountBalanceBasis

    for basis in AccountBalanceBasis.objects.filter(
        account__owner=owner
    ).select_related("account"):
        if as_of is None or day_end(as_of) >= basis.as_of:
            mapping[basis.account_id] = account_balance(basis.account, as_of)
    return mapping


def cash_balance(owner, as_of=None):
    mapping = balances_for_owner(owner, as_of)
    total = Decimal("0")
    for account in Account.objects.filter(
        owner=owner,
        is_active=True,
        type__in=[
            Account.Type.SAVINGS,
            Account.Type.ALIPAY,
            Account.Type.WECHAT,
            Account.Type.WALLET,
        ],
    ):
        total += mapping.get(account.id, D(account.opening_balance))
    return total


def assert_can_debit(account, amount):
    from rest_framework.exceptions import ValidationError

    amount = D(amount)
    if account.allow_negative:
        return
    current = account_balance(account)
    if current < amount:
        raise ValidationError(
            {"detail": f"账户「{account.name}」余额不足，当前 {current}，需要 {amount}"}
        )
