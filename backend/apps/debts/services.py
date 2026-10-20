import logging
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Account
from apps.accounts.services import account_balance
from apps.common.utils.dates import add_months, today_local
from apps.common.utils.money import D, money
from apps.ledger.models import Category, InstallmentPeriod, InstallmentPlan, Transaction
from apps.mortgages.models import Loan, LoanSchedule

from .cycles import card_period_for, next_period_start, period_by_start, period_due_date
from .models import CreditCard, CreditCardBill, DebtItem, DebtPayment, RecurringDebt

logger = logging.getLogger(__name__)


def _day_start(value):
    return timezone.make_aware(datetime.combine(value, time.min))


def _day_end(value):
    return timezone.make_aware(datetime.combine(value, time.max))


def get_or_create_bill(card, period_start, period_end, status=None):
    today = today_local()
    if status is None:
        status = CreditCardBill.Status.CLOSED if period_end < today else CreditCardBill.Status.OPEN
    bill, created = CreditCardBill.objects.get_or_create(
        owner=card.owner,
        card=card,
        period_start=period_start,
        period_end=period_end,
        defaults={
            "due_date": period_due_date(card, period_end),
            "status": status,
            "generated_at": timezone.now() if status == CreditCardBill.Status.CLOSED else None,
        },
    )
    return bill


def compute_bill_totals(card, period_start, period_end):
    qs = Transaction.objects.filter(
        owner=card.owner,
        credit_card=card,
        status=Transaction.Status.POSTED,
        occurred_at__gte=_day_start(period_start),
        occurred_at__lte=_day_end(period_end),
        exclude_from_card_bill=False,
    )
    agg = qs.aggregate(
        expense=Sum("amount", filter=Q(type=Transaction.Type.EXPENSE)),
        refund=Sum("amount", filter=Q(type=Transaction.Type.REFUND)),
    )
    normal_total = D(agg["expense"] or 0) - D(agg["refund"] or 0)
    installment_total = D(
        InstallmentPeriod.objects.filter(
            plan__credit_card=card,
            bill_period_start=period_start,
            bill_period_end=period_end,
        )
        .exclude(status=InstallmentPeriod.Status.CANCELLED)
        .aggregate(total=Sum("amount"))["total"]
        or 0
    )
    total = normal_total + installment_total
    min_payment = money(max(total, D("0")) * D(card.min_payment_rate))
    return {
        "normal_total": normal_total,
        "installment_total": installment_total,
        "refund_total": D(agg["refund"] or 0),
        "total_amount": total,
        "min_payment": min_payment,
    }


def _sync_bill_debt(bill):
    debt = DebtItem.objects.select_for_update().filter(bill=bill).first()
    if bill.total_amount <= 0:
        if debt and debt.status not in (DebtItem.Status.PAID, DebtItem.Status.CANCELLED):
            debt.status = DebtItem.Status.CANCELLED
            debt.save(update_fields=["status", "updated_at"])
        return debt
    title = f"{bill.card.name} {bill.period_start:%m-%d}~{bill.period_end:%m-%d}账单"
    if debt:
        paid = D(debt.paid_amount)
        discount = D(debt.discount_amount)
        target_amount = max(D(bill.total_amount), paid + discount)
        debt.title = title
        debt.due_date = bill.due_date
        debt.amount = target_amount
        debt.refresh_status()
        return debt
    return DebtItem.objects.create(
        owner=bill.owner,
        kind=DebtItem.Kind.CREDIT_CARD,
        bill=bill,
        title=title,
        due_date=bill.due_date,
        amount=D(bill.total_amount),
        status=DebtItem.Status.OVERDUE if bill.due_date < today_local() else DebtItem.Status.PENDING,
    )


def refresh_bill(bill, close=False):
    totals = compute_bill_totals(bill.card, bill.period_start, bill.period_end)
    bill.normal_total = totals["normal_total"]
    bill.installment_total = totals["installment_total"]
    bill.refund_total = totals["refund_total"]
    bill.total_amount = totals["total_amount"]
    bill.min_payment = totals["min_payment"]
    if close or bill.period_end < today_local():
        bill.status = CreditCardBill.Status.CLOSED
        bill.generated_at = bill.generated_at or timezone.now()
    bill.save()
    InstallmentPeriod.objects.filter(
        plan__credit_card=bill.card,
        bill_period_start=bill.period_start,
        bill_period_end=bill.period_end,
    ).exclude(status__in=[InstallmentPeriod.Status.PAID, InstallmentPeriod.Status.CANCELLED]).update(
        status=InstallmentPeriod.Status.BILLED, bill=bill
    )
    if bill.status == CreditCardBill.Status.CLOSED:
        _sync_bill_debt(bill)
    return bill


def assert_card_period_editable(card, occurred_at):
    period_start, period_end = card_period_for(card, occurred_at)
    bill = CreditCardBill.objects.filter(card=card, period_start=period_start, period_end=period_end).first()
    if not bill or bill.status != CreditCardBill.Status.CLOSED:
        return
    debt = getattr(bill, "debt_item", None)
    if debt and (debt.status == DebtItem.Status.PAID or D(debt.paid_amount) > 0):
        raise ValidationError({"detail": "该账单周期已还款，不能修改此流水"})


def refresh_bill_for_card_date(card, occurred_at):
    period_start, period_end = card_period_for(card, occurred_at)
    status = CreditCardBill.Status.CLOSED if period_end < today_local() else CreditCardBill.Status.OPEN
    bill = get_or_create_bill(card, period_start, period_end, status=status)
    if period_end < today_local() and bill.status == CreditCardBill.Status.OPEN:
        bill.status = CreditCardBill.Status.CLOSED
    return refresh_bill(bill, close=period_end < today_local())


def generate_due_bills(owner=None, as_of=None, history_months=6):
    as_of = as_of or today_local()
    cards = CreditCard.objects.filter(is_active=True).select_related("owner")
    if owner is not None:
        cards = cards.filter(owner=owner)
    stats = {"closed": 0, "open": 0, "cards": 0}
    for card in cards:
        stats["cards"] += 1
        current_start, _ = card_period_for(card, as_of)
        cursor = add_months(current_start, -history_months, day=card.statement_start_day)
        while cursor <= current_start:
            start, end = period_by_start(card, cursor)
            if end < as_of:
                bill = get_or_create_bill(card, start, end, status=CreditCardBill.Status.CLOSED)
                bill.status = CreditCardBill.Status.CLOSED
                refresh_bill(bill, close=True)
                stats["closed"] += 1
            cursor = next_period_start(card, cursor)
        open_start, open_end = card_period_for(card, as_of)
        open_bill = get_or_create_bill(card, open_start, open_end, status=CreditCardBill.Status.OPEN)
        refresh_bill(open_bill)
        stats["open"] += 1
    return stats


def create_recurring_items(recurring):
    if recurring.periods <= 0:
        return []
    items = []
    for index in range(1, recurring.periods + 1):
        due_date = add_months(
            recurring.first_due_date.replace(day=1),
            (index - 1) * recurring.interval_months,
            day=recurring.due_day,
        )
        item, _ = DebtItem.objects.get_or_create(
            owner=recurring.owner,
            recurring_debt=recurring,
            period_no=index,
            defaults={
                "kind": DebtItem.Kind.PERIODIC,
                "title": recurring.name,
                "due_date": due_date,
                "amount": recurring.amount,
                "status": DebtItem.Status.OVERDUE if due_date < today_local() else DebtItem.Status.PENDING,
            },
        )
        if item.status not in (DebtItem.Status.PAID, DebtItem.Status.CANCELLED):
            item.due_date = due_date
            item.amount = recurring.amount
            item.title = recurring.name
            item.refresh_status()
        items.append(item)
    recurring.items.filter(period_no__gt=recurring.periods).exclude(
        status__in=[DebtItem.Status.PAID, DebtItem.Status.CANCELLED]
    ).update(status=DebtItem.Status.CANCELLED)
    return items


def generate_mortgage_items(loan, months_ahead=12):
    if loan.status != Loan.Status.ACTIVE:
        return []
    cutoff = add_months(today_local(), months_ahead)
    schedules = loan.schedules.filter(
        status__in=[LoanSchedule.Status.PENDING, LoanSchedule.Status.PARTIAL, LoanSchedule.Status.OVERDUE],
        due_date__lte=cutoff,
    ).select_related("loan")
    items = []
    for schedule in schedules:
        item, _ = DebtItem.objects.get_or_create(
            owner=loan.owner,
            loan_schedule=schedule,
            defaults={
                "kind": DebtItem.Kind.MORTGAGE,
                "title": f"{loan.name} 第{schedule.period_no}期",
                "period_no": schedule.period_no,
                "due_date": schedule.due_date,
                "amount": schedule.total_due,
                "status": DebtItem.Status.OVERDUE
                if schedule.due_date < today_local()
                else DebtItem.Status.PENDING,
            },
        )
        if item.status not in (DebtItem.Status.PAID, DebtItem.Status.CANCELLED):
            item.due_date = schedule.due_date
            item.amount = schedule.total_due
            item.title = f"{loan.name} 第{schedule.period_no}期"
            item.refresh_status()
        items.append(item)
    return items


def generate_all_debt_items(owner=None, as_of=None):
    stats = {"recurring": 0, "mortgage": 0}
    recurring_qs = RecurringDebt.objects.filter(status=RecurringDebt.Status.ACTIVE)
    loans = Loan.objects.filter(status=Loan.Status.ACTIVE)
    if owner is not None:
        recurring_qs = recurring_qs.filter(owner=owner)
        loans = loans.filter(owner=owner)
    for recurring in recurring_qs:
        stats["recurring"] += len(create_recurring_items(recurring))
    for loan in loans:
        stats["mortgage"] += len(generate_mortgage_items(loan))
    return stats


def mark_overdue(as_of=None):
    as_of = as_of or today_local()
    updated = DebtItem.objects.filter(
        due_date__lt=as_of,
        status__in=[DebtItem.Status.PENDING, DebtItem.Status.PARTIAL],
    ).update(status=DebtItem.Status.OVERDUE)
    return updated


def _category_for_debt(owner, item):
    if item.kind == DebtItem.Kind.MORTGAGE:
        return _get_or_create_general(owner, "房贷")
    if item.recurring_debt_id and item.recurring_debt.category_id:
        category = Category.objects.filter(id=item.recurring_debt.category_id, owner=owner).first()
        if category:
            return category
    return _get_or_create_general(owner, "债务支出")


def _get_or_create_general(owner, name):
    category = Category.objects.filter(owner=owner, name=name, kind=Category.Kind.GENERAL).first()
    if category:
        return category
    return Category.objects.create(owner=owner, name=name, kind=Category.Kind.GENERAL)


def _validate_settlement_channel(item, channel, account, credit_card):
    if item.kind == DebtItem.Kind.CREDIT_CARD:
        if channel not in (
            DebtPayment.Channel.CASH,
            DebtPayment.Channel.ALIPAY,
            DebtPayment.Channel.WECHAT,
        ):
            raise ValidationError({"channel": "信用卡还款只能使用储蓄卡、支付宝或微信"})
        if not account or account.owner_id != item.owner_id:
            raise ValidationError({"account": "请选择还款账户"})
        if account.type not in (Account.Type.SAVINGS, Account.Type.ALIPAY, Account.Type.WECHAT):
            raise ValidationError({"account": "信用卡还款账户类型不正确"})
        return
    if item.kind == DebtItem.Kind.MORTGAGE and channel not in (
        DebtPayment.Channel.CASH,
        DebtPayment.Channel.PROVIDENT_FUND,
    ):
        raise ValidationError({"channel": "房贷只支持现金或公积金支付"})
    if channel == DebtPayment.Channel.CREDIT_CARD:
        if not credit_card or credit_card.owner_id != item.owner_id:
            raise ValidationError({"credit_card": "请选择信用卡"})
        if account:
            raise ValidationError({"account": "信用卡支付不能同时选择资金账户"})
        return
    if not account or account.owner_id != item.owner_id:
        raise ValidationError({"account": "请选择支付账户"})
    expected = {
        DebtPayment.Channel.CASH: Account.Type.SAVINGS,
        DebtPayment.Channel.PROVIDENT_FUND: {Account.Type.PROVIDENT_FUND_MAIN, Account.Type.PROVIDENT_FUND_SUPP},
        DebtPayment.Channel.ALIPAY: Account.Type.ALIPAY,
        DebtPayment.Channel.WECHAT: Account.Type.WECHAT,
    }[channel]
    if isinstance(expected, set):
        if account.type not in expected:
            raise ValidationError({"account": "支付账户类型不匹配"})
    elif account.type != expected:
        raise ValidationError({"account": "支付账户类型不匹配"})


def _mark_debt_paid_side_effects(item):
    if item.kind == DebtItem.Kind.MORTGAGE and item.loan_schedule_id:
        schedule = item.loan_schedule
        if item.status == DebtItem.Status.PAID:
            schedule.status = LoanSchedule.Status.PAID
        elif D(item.paid_amount) > 0:
            schedule.status = LoanSchedule.Status.PARTIAL
        elif schedule.due_date < today_local():
            schedule.status = LoanSchedule.Status.OVERDUE
        schedule.save(update_fields=["status", "updated_at"])
        loan = schedule.loan
        if loan.schedules.exclude(status=LoanSchedule.Status.PAID).count() == 0:
            loan.status = Loan.Status.SETTLED
            loan.save(update_fields=["status", "updated_at"])
    if item.kind == DebtItem.Kind.CREDIT_CARD and item.bill_id and item.status == DebtItem.Status.PAID:
        item.bill.installment_periods.exclude(status=InstallmentPeriod.Status.CANCELLED).update(
            status=InstallmentPeriod.Status.PAID
        )
        for plan in item.bill.card.installment_plans.filter(status=InstallmentPlan.Status.ACTIVE):
            if not plan.period_rows.exclude(status=InstallmentPeriod.Status.PAID).exists():
                plan.status = InstallmentPlan.Status.COMPLETED
                plan.save(update_fields=["status", "updated_at"])


@db_transaction.atomic
def settle_debt(
    *,
    owner,
    debt_item,
    amount,
    discount=Decimal("0"),
    channel=DebtPayment.Channel.CASH,
    account=None,
    credit_card=None,
    paid_at=None,
    note="",
    idempotency_key=None,
):
    from apps.ledger.services import create_transaction, system_category

    pay_amount = money(amount)
    discount = money(discount)
    if pay_amount < 0 or discount < 0:
        raise ValidationError({"amount": "还款金额和减免金额不能为负"})
    if pay_amount == 0 and discount == 0:
        raise ValidationError({"amount": "还款金额和减免金额不能同时为 0"})
    if idempotency_key:
        existing = DebtPayment.objects.filter(owner=owner, idempotency_key=idempotency_key).first()
        if existing:
            return existing
    item = (
        DebtItem.objects.select_for_update()
        .select_related("bill", "recurring_debt", "loan_schedule__loan")
        .get(id=debt_item.id, owner=owner)
    )
    if item.status == DebtItem.Status.CANCELLED:
        raise ValidationError({"detail": "债务项已取消"})
    if item.status == DebtItem.Status.PAID:
        raise ValidationError({"detail": "债务项已结清"})
    payable = max(D(item.amount) - D(item.discount_amount) - D(item.paid_amount), D("0"))
    if pay_amount + discount > payable:
        raise ValidationError({"amount": f"还款金额加减免金额不能超过应付金额 {payable}"})
    _validate_settlement_channel(item, channel, account, credit_card)
    paid_at = paid_at or timezone.now()

    payment = DebtPayment.objects.create(
        owner=owner,
        debt_item=item,
        amount=pay_amount,
        discount_amount=discount,
        channel=channel,
        account=account,
        credit_card=credit_card,
        paid_at=paid_at,
        idempotency_key=idempotency_key,
        note=note or "",
    )

    txn = None
    if pay_amount > 0:
        if item.kind == DebtItem.Kind.CREDIT_CARD:
            txn = create_transaction(
                owner=owner,
                txn_type=Transaction.Type.TRANSFER_OUT,
                category=system_category(owner, Category.Kind.TRANSFER),
                amount=pay_amount,
                occurred_at=paid_at,
                settlement_channel=channel,
                account=account,
                credit_card=item.bill.card,
                note=note or f"信用卡还款：{item.bill.card.name}",
                source=Transaction.Source.DEBT_PAYMENT,
                source_id=item.id,
                idempotency_key=f"debtpay:{payment.id}",
                skip_bill_refresh=True,
                allow_card_reference=True,
            )
        else:
            txn = create_transaction(
                owner=owner,
                txn_type=Transaction.Type.EXPENSE,
                category=_category_for_debt(owner, item),
                amount=pay_amount,
                occurred_at=paid_at,
                settlement_channel=Transaction.SettlementChannel.CREDIT_CARD
                if channel == DebtPayment.Channel.CREDIT_CARD
                else channel,
                account=account,
                credit_card=credit_card,
                note=note or f"债务还款：{item.title}",
                source=Transaction.Source.DEBT_PAYMENT,
                source_id=item.id,
                idempotency_key=f"debtpay:{payment.id}",
            )
    if txn:
        payment.transaction_id = txn.id
        payment.save(update_fields=["transaction_id", "updated_at"])
    item.paid_amount = D(item.paid_amount) + pay_amount
    item.discount_amount = D(item.discount_amount) + discount
    item.refresh_status()
    _mark_debt_paid_side_effects(item)
    return payment


def auto_settle_due_items(owner=None, as_of=None):
    as_of = as_of or today_local()
    qs = DebtItem.objects.filter(
        due_date__lte=as_of,
        status__in=[DebtItem.Status.PENDING, DebtItem.Status.PARTIAL, DebtItem.Status.OVERDUE],
    ).select_related("loan_schedule__loan__offset_plan__pf_account", "recurring_debt")
    if owner is not None:
        qs = qs.filter(owner=owner)
    stats = {"settled": 0, "failed": 0}
    for item in qs:
        try:
            payable = max(D(item.amount) - D(item.discount_amount) - D(item.paid_amount), D("0"))
            if payable <= 0:
                continue
            if item.kind == DebtItem.Kind.MORTGAGE and item.loan_schedule_id:
                loan = item.loan_schedule.loan
                plan = getattr(loan, "offset_plan", None)
                remaining = payable
                if plan and plan.enabled:
                    pf_balance = account_balance(plan.pf_account)
                    if plan.mode == "FULL":
                        offset = payable if pf_balance >= payable else D("0")
                    else:
                        cap = D(plan.monthly_cap) if plan.monthly_cap is not None else payable
                        offset = min(pf_balance, cap, payable)
                    if offset > 0:
                        settle_debt(
                            owner=item.owner,
                            debt_item=item,
                            amount=offset,
                            channel=DebtPayment.Channel.PROVIDENT_FUND,
                            account=plan.pf_account,
                            idempotency_key=f"auto-pf:{item.id}:{as_of.isoformat()}",
                            note="公积金自动冲还",
                        )
                        remaining = payable - offset
                        stats["settled"] += 1
                    if remaining > 0 and plan.auto_pay_cash and loan.repayment_account_id:
                        settle_debt(
                            owner=item.owner,
                            debt_item=item,
                            amount=remaining,
                            channel=DebtPayment.Channel.CASH,
                            account=loan.repayment_account,
                            idempotency_key=f"auto-cash:{item.id}:{as_of.isoformat()}",
                            note="房贷现金差额自动扣款",
                        )
                        stats["settled"] += 1
                elif loan.auto_settle and loan.repayment_account_id:
                    settle_debt(
                        owner=item.owner,
                        debt_item=item,
                        amount=remaining,
                        channel=DebtPayment.Channel.CASH,
                        account=loan.repayment_account,
                        idempotency_key=f"auto-cash:{item.id}:{as_of.isoformat()}",
                        note="房贷自动扣款",
                    )
                    stats["settled"] += 1
            elif item.kind == DebtItem.Kind.PERIODIC and item.recurring_debt and item.recurring_debt.auto_pay:
                recurring = item.recurring_debt
                channel = recurring.payment_channel or DebtPayment.Channel.CASH
                if channel == DebtPayment.Channel.CREDIT_CARD:
                    if recurring.credit_card_id:
                        settle_debt(
                            owner=item.owner,
                            debt_item=item,
                            amount=payable,
                            channel=channel,
                            credit_card=recurring.credit_card,
                            idempotency_key=f"auto:{item.id}:{as_of.isoformat()}",
                            note="周期债务自动支付",
                        )
                        stats["settled"] += 1
                elif recurring.account_id:
                    settle_debt(
                        owner=item.owner,
                        debt_item=item,
                        amount=payable,
                        channel=channel,
                        account=recurring.account,
                        idempotency_key=f"auto:{item.id}:{as_of.isoformat()}",
                        note="周期债务自动支付",
                    )
                stats["settled"] += 1
        except Exception as exc:  # keep one failing item from blocking the batch
            logger.exception("auto settle failed for debt item %s", item.id)
            stats["failed"] += 1
    return stats


def card_liability(card):
    unpaid_items = DebtItem.objects.filter(
        owner=card.owner,
        kind=DebtItem.Kind.CREDIT_CARD,
        bill__card=card,
        status__in=[DebtItem.Status.PENDING, DebtItem.Status.PARTIAL, DebtItem.Status.OVERDUE],
    )
    unpaid = sum(
        (max(D(item.amount) - D(item.discount_amount) - D(item.paid_amount), D("0")) for item in unpaid_items),
        D("0"),
    )
    open_bill_total = (
        CreditCardBill.objects.filter(owner=card.owner, card=card, status=CreditCardBill.Status.OPEN).aggregate(
            total=Sum("total_amount")
        )["total"]
        or 0
    )
    future_installment = (
        InstallmentPeriod.objects.filter(
            owner=card.owner,
            plan__credit_card=card,
            status=InstallmentPeriod.Status.PENDING,
            bill__isnull=True,
        ).aggregate(total=Sum("principal_part"))["total"]
        or 0
    )
    return unpaid + D(open_bill_total) + D(future_installment)


def card_summary(card):
    today = today_local()
    start, end = card_period_for(card, today)
    bill = get_or_create_bill(card, start, end, status=CreditCardBill.Status.OPEN)
    refresh_bill(bill)
    next_due = (
        DebtItem.objects.filter(
            owner=card.owner,
            bill__card=card,
            status__in=[DebtItem.Status.PENDING, DebtItem.Status.PARTIAL, DebtItem.Status.OVERDUE],
        )
        .order_by("due_date")
        .first()
    )
    liability = card_liability(card)
    return {
        "card": card,
        "current_period_start": start,
        "current_period_end": end,
        "current_due_date": bill.due_date,
        "current_normal_total": bill.normal_total,
        "current_installment_total": bill.installment_total,
        "current_refund_total": bill.refund_total,
        "current_total": bill.total_amount,
        "current_min_payment": bill.min_payment,
        "credit_limit": D(card.credit_limit),
        "used_credit": liability,
        "available_credit": D(card.credit_limit) - liability,
        "next_due": next_due,
    }


def unpaid_debt_total(owner):
    total = Decimal("0")
    for item in DebtItem.objects.filter(
        owner=owner,
        status__in=[DebtItem.Status.PENDING, DebtItem.Status.PARTIAL, DebtItem.Status.OVERDUE],
    ):
        total += max(D(item.amount) - D(item.discount_amount) - D(item.paid_amount), D("0"))
    return total
