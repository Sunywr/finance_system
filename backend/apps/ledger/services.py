import logging
import secrets
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Account
from apps.accounts.services import account_balance
from apps.common.utils.dates import (
    add_months,
    due_date_for_period,
    statement_period_for,
    today_local,
)
from apps.common.utils.money import D, money, split_money
from apps.debts.cycles import (
    card_period_for,
    next_period_start,
    period_by_start,
    period_due_date,
)

from .models import (
    AccountTransfer,
    Category,
    InstallmentPeriod,
    InstallmentPlan,
    Tag,
    Transaction,
)

logger = logging.getLogger(__name__)

CHANNEL_BY_ACCOUNT_TYPE = {
    Account.Type.SAVINGS: Transaction.SettlementChannel.CASH,
    Account.Type.PROVIDENT_FUND_MAIN: Transaction.SettlementChannel.PROVIDENT_FUND,
    Account.Type.PROVIDENT_FUND_SUPP: Transaction.SettlementChannel.PROVIDENT_FUND,
    Account.Type.STOCK: Transaction.SettlementChannel.STOCK,
    Account.Type.WEALTH: Transaction.SettlementChannel.WEALTH,
    Account.Type.ALIPAY: Transaction.SettlementChannel.ALIPAY,
    Account.Type.WECHAT: Transaction.SettlementChannel.WECHAT,
    Account.Type.WALLET: Transaction.SettlementChannel.WALLET,
}

EXPECTED_ACCOUNT_TYPES = {
    Transaction.SettlementChannel.CASH: {Account.Type.SAVINGS},
    Transaction.SettlementChannel.PROVIDENT_FUND: {
        Account.Type.PROVIDENT_FUND_MAIN,
        Account.Type.PROVIDENT_FUND_SUPP,
    },
    Transaction.SettlementChannel.ALIPAY: {Account.Type.ALIPAY},
    Transaction.SettlementChannel.WECHAT: {Account.Type.WECHAT},
    Transaction.SettlementChannel.STOCK: {Account.Type.STOCK},
    Transaction.SettlementChannel.WEALTH: {Account.Type.WEALTH},
    Transaction.SettlementChannel.WALLET: {Account.Type.WALLET},
}


def channel_for_account(account):
    try:
        return CHANNEL_BY_ACCOUNT_TYPE[account.type]
    except KeyError as exc:
        raise ValidationError(
            {"detail": f"账户「{account.name}」不支持作为资金账户"}
        ) from exc


def generate_txn_no():
    return f"TX{timezone.localtime():%Y%m%d%H%M%S}{secrets.token_hex(3).upper()}"


def get_or_create_category(owner, name, kind=Category.Kind.GENERAL, parent=None):
    category = Category.objects.filter(
        owner=owner, name=name, kind=kind, parent=parent
    ).first()
    if category:
        return category
    return Category.objects.create(owner=owner, name=name, kind=kind, parent=parent)


def system_category(owner, kind):
    category = Category.objects.filter(
        owner=owner, kind=kind, is_system=True, is_active=True
    ).first()
    if category:
        return category
    name = dict(Category.Kind.choices).get(kind, kind)
    return Category.objects.create(owner=owner, name=name, kind=kind, is_system=True)


def _validate_category(owner, category, txn_type, operation):
    if category.owner_id != owner.id:
        raise ValidationError({"category": "分类不存在"})
    if not category.is_active:
        raise ValidationError({"category": "分类已停用"})
    if category.kind == Category.Kind.REFUND and txn_type != Transaction.Type.REFUND:
        raise ValidationError({"category": "退款分类只能用于退款流水"})
    if txn_type == Transaction.Type.REFUND and category.kind != Category.Kind.REFUND:
        raise ValidationError({"category": "退款流水必须使用退款分类"})
    if (
        category.kind in (Category.Kind.INVESTMENT, Category.Kind.STOCK)
        and operation == Transaction.Operation.NONE
    ):
        raise ValidationError(
            {"operation": "投资/股票流水必须选择建仓、加仓、减仓或分红操作"}
        )
    if operation != Transaction.Operation.NONE and category.kind not in (
        Category.Kind.INVESTMENT,
        Category.Kind.STOCK,
    ):
        raise ValidationError({"operation": "只有投资/股票分类可以设置投资操作"})


def _validate_channel(owner, channel, account, credit_card, allow_card_reference=False):
    if channel == Transaction.SettlementChannel.CREDIT_CARD:
        if not credit_card or credit_card.owner_id != owner.id:
            raise ValidationError({"credit_card": "请选择信用卡"})
        if account is not None:
            raise ValidationError({"account": "信用卡支付不能同时选择资金账户"})
        return
    if not account or account.owner_id != owner.id:
        raise ValidationError({"account": "请选择资金账户"})
    if credit_card is not None and not allow_card_reference:
        raise ValidationError({"credit_card": "非信用卡支付不能选择信用卡"})
    expected = EXPECTED_ACCOUNT_TYPES.get(channel)
    if not expected or account.type not in expected:
        raise ValidationError({"settlement_channel": "支付渠道与账户类型不匹配"})


def _check_balance(account, amount):
    if account is None or account.allow_negative:
        return
    current = account_balance(account)
    if current < amount:
        raise ValidationError(
            {"detail": f"账户「{account.name}」余额不足，当前 {current}，需要 {amount}"}
        )


def _validate_refund(owner, original, amount):
    if not original or original.owner_id != owner.id:
        raise ValidationError({"refund_of": "请选择原支出流水"})
    if original.status != Transaction.Status.POSTED:
        raise ValidationError({"refund_of": "原流水已作废"})
    if original.type != Transaction.Type.EXPENSE:
        raise ValidationError({"refund_of": "只能对支出流水发起退款"})
    refunded = (
        Transaction.objects.filter(
            refund_of=original, status=Transaction.Status.POSTED
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    if D(refunded) + D(amount) > D(original.amount):
        raise ValidationError({"amount": "累计退款金额不能超过原支出金额"})


def _assert_card_period_editable(card, occurred_at):
    from apps.debts.services import assert_card_period_editable

    assert_card_period_editable(card, occurred_at)


def _refresh_card_bill(card, occurred_at):
    if not card:
        return
    from apps.debts.services import refresh_bill_for_card_date

    refresh_bill_for_card_date(card, occurred_at)


@db_transaction.atomic
def create_transaction(
    *,
    owner,
    txn_type,
    category,
    amount,
    occurred_at=None,
    settlement_channel=Transaction.SettlementChannel.CASH,
    account=None,
    credit_card=None,
    operation=Transaction.Operation.NONE,
    note="",
    tags=None,
    refund_of=None,
    asset=None,
    asset_amount=None,
    transfer=None,
    source=Transaction.Source.MANUAL,
    source_id=None,
    idempotency_key=None,
    exclude_from_card_bill=False,
    check_balance=True,
    skip_bill_refresh=False,
    allow_card_reference=False,
):
    amount = money(amount)
    if amount <= 0:
        raise ValidationError({"amount": "金额必须大于 0"})
    occurred_at = occurred_at or timezone.now()
    if idempotency_key:
        existing = Transaction.objects.filter(
            owner=owner, idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing

    _validate_category(owner, category, txn_type, operation)
    _validate_channel(
        owner, settlement_channel, account, credit_card, allow_card_reference
    )
    if (
        txn_type not in (Transaction.Type.INCOME, Transaction.Type.REFUND)
        and check_balance
    ):
        if settlement_channel != Transaction.SettlementChannel.CREDIT_CARD:
            _check_balance(account, amount)
    if txn_type == Transaction.Type.REFUND:
        _validate_refund(owner, refund_of, amount)
    elif refund_of:
        raise ValidationError({"refund_of": "只有退款流水可以关联原流水"})
    if asset and asset.owner_id != owner.id:
        raise ValidationError({"asset": "资产不存在"})
    if asset:
        if asset_amount is None:
            asset_amount = amount if txn_type == Transaction.Type.EXPENSE else D("0")
        asset_amount = money(asset_amount)
        if asset_amount < 0 or asset_amount > amount:
            raise ValidationError({"asset_amount": "资产金额必须在 0 到流水金额之间"})
    else:
        asset_amount = D("0")
    if credit_card:
        _assert_card_period_editable(credit_card, occurred_at)

    txn = Transaction.objects.create(
        owner=owner,
        txn_no=generate_txn_no(),
        type=txn_type,
        category=category,
        occurred_at=occurred_at,
        amount=amount,
        settlement_channel=settlement_channel,
        account=account,
        credit_card=credit_card,
        operation=operation,
        note=note or "",
        transfer=transfer,
        refund_of=refund_of,
        asset=asset,
        asset_amount=asset_amount,
        source=source,
        source_id=source_id,
        idempotency_key=idempotency_key,
        exclude_from_card_bill=exclude_from_card_bill,
    )
    if tags:
        tag_ids = []
        for tag in tags:
            if isinstance(tag, Tag):
                if tag.owner_id != owner.id:
                    raise ValidationError({"tags": "标签不存在"})
                tag_ids.append(tag.id)
            else:
                tag_obj, _ = Tag.objects.get_or_create(
                    owner=owner, name=str(tag), defaults={"color": "#909399"}
                )
                tag_ids.append(tag_obj.id)
        txn.tags.set(tag_ids)
    if not skip_bill_refresh:
        _refresh_card_bill(credit_card, occurred_at)
    return txn


@db_transaction.atomic
def update_transaction(txn, *, data, tags=None):
    if txn.status != Transaction.Status.POSTED:
        raise ValidationError({"detail": "已作废流水不能修改"})
    if txn.source != Transaction.Source.MANUAL:
        raise ValidationError(
            {"detail": "系统生成流水不能直接修改，请通过对应业务操作处理"}
        )
    old_account = txn.account
    old_card = txn.credit_card
    old_occurred = txn.occurred_at

    txn_type = data.get("type", txn.type)
    category = data.get("category", txn.category)
    amount = money(data.get("amount", txn.amount))
    occurred_at = data.get("occurred_at", txn.occurred_at)
    settlement_channel = data.get("settlement_channel", txn.settlement_channel)
    account = data.get("account", txn.account)
    credit_card = data.get("credit_card", txn.credit_card)
    operation = data.get("operation", txn.operation)
    note = data.get("note", txn.note)
    refund_of = data.get("refund_of", txn.refund_of)
    asset = data.get("asset", txn.asset)
    asset_amount = data.get("asset_amount", txn.asset_amount)
    exclude = data.get("exclude_from_card_bill", txn.exclude_from_card_bill)

    if amount <= 0:
        raise ValidationError({"amount": "金额必须大于 0"})
    _validate_category(txn.owner, category, txn_type, operation)
    _validate_channel(txn.owner, settlement_channel, account, credit_card)
    if asset and asset.owner_id != txn.owner_id:
        raise ValidationError({"asset": "资产不存在"})
    if asset:
        asset_amount = money(asset_amount)
        if asset_amount < 0 or asset_amount > amount:
            raise ValidationError({"asset_amount": "资产金额必须在 0 到流水金额之间"})
    else:
        asset_amount = D("0")
    if old_card:
        _assert_card_period_editable(old_card, old_occurred)
    if credit_card:
        _assert_card_period_editable(credit_card, occurred_at)
    if txn_type not in (Transaction.Type.INCOME, Transaction.Type.REFUND):
        if settlement_channel != Transaction.SettlementChannel.CREDIT_CARD:
            _check_balance(account, amount)

    txn.type = txn_type
    txn.category = category
    txn.amount = amount
    txn.occurred_at = occurred_at
    txn.settlement_channel = settlement_channel
    txn.account = account
    txn.credit_card = credit_card
    txn.operation = operation
    txn.note = note or ""
    txn.refund_of = refund_of
    txn.asset = asset
    txn.asset_amount = asset_amount
    txn.exclude_from_card_bill = exclude
    txn.save()
    if tags is not None:
        txn.tags.set(tags)
    if old_card_id := (old_card.id if old_card else None):
        _refresh_card_bill(old_card, old_occurred)
    if credit_card:
        _refresh_card_bill(credit_card, occurred_at)
    return txn


@db_transaction.atomic
def void_transaction(txn, reason=""):
    if txn.status != Transaction.Status.POSTED:
        raise ValidationError({"detail": "流水已作废"})
    if txn.source != Transaction.Source.MANUAL:
        raise ValidationError(
            {"detail": "系统生成流水不能直接作废，请通过对应业务操作处理"}
        )
    if txn.refunds.filter(status=Transaction.Status.POSTED).exists():
        raise ValidationError({"detail": "该流水已有退款记录，不能作废"})
    if txn.transfer_id:
        related = Transaction.objects.filter(
            transfer=txn.transfer, status=Transaction.Status.POSTED
        )
        for item in related:
            item.status = Transaction.Status.VOID
            item.voided_at = timezone.now()
            item.void_reason = reason or "转账作废"
            item.save(
                update_fields=["status", "voided_at", "void_reason", "updated_at"]
            )
        return txn
    if txn.installment_plan_id:
        raise ValidationError({"detail": "分期购买流水不能直接作废，请先取消分期计划"})
    if txn.credit_card_id:
        _assert_card_period_editable(txn.credit_card, txn.occurred_at)
    txn.status = Transaction.Status.VOID
    txn.voided_at = timezone.now()
    txn.void_reason = reason or ""
    txn.save(update_fields=["status", "voided_at", "void_reason", "updated_at"])
    _refresh_card_bill(txn.credit_card, txn.occurred_at)
    return txn


@db_transaction.atomic
def create_refund(
    *,
    owner,
    original,
    amount,
    occurred_at=None,
    note="",
    cancel_installment=False,
    asset=None,
):
    amount = money(amount)
    if amount <= 0:
        raise ValidationError({"amount": "退款金额必须大于 0"})
    _validate_refund(owner, original, amount)
    if original.installment_plan_id:
        if not cancel_installment:
            raise ValidationError({"detail": "原流水为分期购买，请先取消后续分期期次"})
        plan = original.installment_plan
        plan.period_rows.filter(
            status__in=[
                InstallmentPeriod.Status.PENDING,
                InstallmentPeriod.Status.BILLED,
            ]
        ).update(status=InstallmentPeriod.Status.CANCELLED)
        plan.status = InstallmentPlan.Status.CANCELLED
        plan.save(update_fields=["status", "updated_at"])
    category = system_category(owner, Category.Kind.REFUND)
    return create_transaction(
        owner=owner,
        txn_type=Transaction.Type.REFUND,
        category=category,
        amount=amount,
        occurred_at=occurred_at or timezone.now(),
        settlement_channel=original.settlement_channel,
        account=original.account,
        credit_card=original.credit_card,
        note=note or f"退款：{original.txn_no}",
        refund_of=original,
        asset=asset,
        asset_amount=amount if asset else None,
        source=Transaction.Source.REFUND,
        source_id=original.id,
        exclude_from_card_bill=bool(original.installment_plan_id),
    )


@db_transaction.atomic
def create_transfer(
    *,
    owner,
    from_account,
    to_account,
    amount,
    fee=D("0"),
    occurred_at=None,
    note="",
    idempotency_key=None,
):
    amount = money(amount)
    fee = money(fee)
    if amount <= 0:
        raise ValidationError({"amount": "转账金额必须大于 0"})
    if fee < 0:
        raise ValidationError({"fee": "手续费不能为负"})
    if from_account.owner_id != owner.id or to_account.owner_id != owner.id:
        raise ValidationError({"detail": "账户不存在"})
    if from_account.id == to_account.id:
        raise ValidationError({"to_account": "转出和转入账户不能相同"})
    if from_account.currency != to_account.currency:
        raise ValidationError({"detail": "暂不支持跨币种转账"})
    if idempotency_key:
        existing = AccountTransfer.objects.filter(
            owner=owner, idempotency_key=idempotency_key
        ).first()
        if existing:
            return existing
    _check_balance(from_account, amount + fee)
    transfer = AccountTransfer.objects.create(
        owner=owner,
        from_account=from_account,
        to_account=to_account,
        amount=amount,
        fee=fee,
        occurred_at=occurred_at or timezone.now(),
        note=note or "",
        idempotency_key=idempotency_key,
    )
    category = system_category(owner, Category.Kind.TRANSFER)
    out_txn = create_transaction(
        owner=owner,
        txn_type=Transaction.Type.TRANSFER_OUT,
        category=category,
        amount=amount + fee,
        occurred_at=transfer.occurred_at,
        settlement_channel=channel_for_account(from_account),
        account=from_account,
        note=note or f"转账至 {to_account.name}",
        transfer=transfer,
        source=Transaction.Source.TRANSFER,
        source_id=transfer.id,
        idempotency_key=f"{idempotency_key}:out" if idempotency_key else None,
        check_balance=False,
    )
    in_txn = create_transaction(
        owner=owner,
        txn_type=Transaction.Type.TRANSFER_IN,
        category=category,
        amount=amount,
        occurred_at=transfer.occurred_at,
        settlement_channel=channel_for_account(to_account),
        account=to_account,
        note=note or f"来自 {from_account.name} 的转账",
        transfer=transfer,
        source=Transaction.Source.TRANSFER,
        source_id=transfer.id,
        idempotency_key=f"{idempotency_key}:in" if idempotency_key else None,
        check_balance=False,
    )
    transfer.out_transaction_id = out_txn.id
    transfer.in_transaction_id = in_txn.id
    transfer.save(
        update_fields=["out_transaction_id", "in_transaction_id", "updated_at"]
    )
    return transfer


def preview_installment(
    *,
    card,
    principal,
    periods,
    fee_mode=InstallmentPlan.FeeMode.NONE,
    fee_rate=Decimal("0"),
    purchase_at=None,
):
    principal = money(principal)
    periods = int(periods)
    fee_rate = D(fee_rate)
    if principal <= 0:
        raise ValidationError({"principal": "分期本金必须大于 0"})
    if periods < 1 or periods > 60:
        raise ValidationError({"periods": "分期期数必须在 1-60 之间"})
    if fee_mode == InstallmentPlan.FeeMode.NONE:
        total_fee = D("0")
    elif fee_mode == InstallmentPlan.FeeMode.FLAT:
        total_fee = money(principal * fee_rate / Decimal("100"))
    else:
        total_fee = money(principal * fee_rate / Decimal("100") * periods)
    principal_parts = split_money(principal, periods)
    fee_parts = split_money(total_fee, periods)
    purchase_cycle_start, _ = card_period_for(card, purchase_at or today_local())
    first_start = next_period_start(card, purchase_cycle_start)
    rows = []
    for index in range(periods):
        start = add_months(first_start, index, day=card.statement_start_day)
        _, end = period_by_start(card, start)
        due = period_due_date(card, end)
        rows.append(
            {
                "period_no": index + 1,
                "bill_period_start": start,
                "bill_period_end": end,
                "due_date": due,
                "principal_part": principal_parts[index],
                "fee_part": fee_parts[index],
                "amount": principal_parts[index] + fee_parts[index],
            }
        )
    return {
        "principal": principal,
        "periods": periods,
        "total_fee": total_fee,
        "per_period_amount": rows[0]["amount"] if rows else D("0"),
        "first_period_start": first_start,
        "rows": rows,
    }


@db_transaction.atomic
def create_installment_purchase(
    *,
    owner,
    card,
    principal,
    periods,
    occurred_at,
    category,
    note="",
    fee_mode=InstallmentPlan.FeeMode.NONE,
    fee_rate=Decimal("0"),
    asset=None,
):
    if card.owner_id != owner.id:
        raise ValidationError({"credit_card": "信用卡不存在"})
    preview = preview_installment(
        card=card,
        principal=principal,
        periods=periods,
        fee_mode=fee_mode,
        fee_rate=fee_rate,
        purchase_at=occurred_at,
    )
    parent = create_transaction(
        owner=owner,
        txn_type=Transaction.Type.EXPENSE,
        category=category,
        amount=preview["principal"],
        occurred_at=occurred_at,
        settlement_channel=Transaction.SettlementChannel.CREDIT_CARD,
        credit_card=card,
        note=note,
        asset=asset,
        source=Transaction.Source.INSTALLMENT,
        exclude_from_card_bill=True,
    )
    plan = InstallmentPlan.objects.create(
        owner=owner,
        purchase_transaction_id=parent.id,
        credit_card=card,
        principal=preview["principal"],
        periods=preview["periods"],
        fee_mode=fee_mode,
        fee_rate=D(fee_rate),
        total_fee=preview["total_fee"],
        per_period_amount=preview["per_period_amount"],
        first_period_start=preview["first_period_start"],
    )
    parent.installment_plan = plan
    parent.save(update_fields=["installment_plan", "updated_at"])
    periods_to_create = [
        InstallmentPeriod(
            owner=owner,
            plan=plan,
            period_no=row["period_no"],
            bill_period_start=row["bill_period_start"],
            bill_period_end=row["bill_period_end"],
            due_date=row["due_date"],
            principal_part=row["principal_part"],
            fee_part=row["fee_part"],
            amount=row["amount"],
        )
        for row in preview["rows"]
    ]
    InstallmentPeriod.objects.bulk_create(periods_to_create)
    return parent, plan


def installment_remaining_principal(owner):
    total = (
        InstallmentPeriod.objects.filter(
            owner=owner,
            plan__status=InstallmentPlan.Status.ACTIVE,
        )
        .exclude(
            status__in=[
                InstallmentPeriod.Status.PAID,
                InstallmentPeriod.Status.CANCELLED,
            ]
        )
        .aggregate(total=Sum("principal_part"))["total"]
        or 0
    )
    return D(total)


def active_installment_periods(owner):
    return InstallmentPeriod.objects.filter(owner=owner).exclude(
        status__in=[InstallmentPeriod.Status.PAID, InstallmentPeriod.Status.CANCELLED]
    )
