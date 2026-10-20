from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.services import account_balance
from apps.common.utils.dates import add_months, today_local
from apps.common.utils.money import D, money, ZERO

from .models import Loan, LoanSchedule, OffsetPlan


def _monthly_rate(loan):
    return D(loan.annual_rate) / Decimal("100") / Decimal("12")


def _build_rows(principal, annual_rate, months, method):
    principal = money(principal)
    rate = D(annual_rate) / Decimal("100") / Decimal("12")
    rows = []
    remaining = principal
    if method == Loan.RepaymentMethod.EQUAL_PRINCIPAL:
        base = money(principal / months)
        for index in range(1, months + 1):
            principal_due = remaining if index == months else base
            interest_due = money(remaining * rate)
            total_due = principal_due + interest_due
            remaining = money(remaining - principal_due)
            rows.append((principal_due, interest_due, total_due, remaining))
        return rows

    if rate == 0:
        payment = money(principal / months)
        for index in range(1, months + 1):
            principal_due = remaining if index == months else payment
            interest_due = ZERO
            total_due = principal_due
            remaining = money(remaining - principal_due)
            rows.append((principal_due, interest_due, total_due, remaining))
        return rows

    factor = (Decimal("1") + rate) ** months
    payment = money(principal * rate * factor / (factor - Decimal("1")))
    for index in range(1, months + 1):
        interest_due = money(remaining * rate)
        if index == months:
            principal_due = remaining
            total_due = principal_due + interest_due
        else:
            principal_due = money(payment - interest_due)
            if principal_due > remaining:
                principal_due = remaining
            total_due = principal_due + interest_due
        remaining = money(remaining - principal_due)
        rows.append((principal_due, interest_due, total_due, remaining))
    return rows


def _due_date(loan, period_no):
    anchor = loan.first_due_date.replace(day=1)
    return add_months(anchor, period_no - 1, day=loan.payment_day or loan.first_due_date.day)


@transaction.atomic
def generate_schedule(loan, keep_paid=True):
    paid = loan.schedules.filter(status=LoanSchedule.Status.PAID).order_by("period_no")
    paid_count = paid.count()
    if keep_paid and paid_count:
        last_paid = paid.last()
        start_period = last_paid.period_no + 1
        remaining_principal = D(last_paid.remaining_principal)
        loan.schedules.filter(period_no__gte=start_period).delete()
    else:
        loan.schedules.all().delete()
        start_period = 1
        remaining_principal = D(loan.principal)

    periods_left = loan.term_months - start_period + 1
    if periods_left <= 0:
        return list(loan.schedules.all())
    rows = _build_rows(remaining_principal, loan.annual_rate, periods_left, loan.repayment_method)
    schedules = []
    for offset, (principal_due, interest_due, total_due, remaining) in enumerate(rows):
        period_no = start_period + offset
        schedules.append(
            LoanSchedule(
                loan=loan,
                period_no=period_no,
                due_date=_due_date(loan, period_no),
                principal_due=principal_due,
                interest_due=interest_due,
                total_due=total_due,
                remaining_principal=remaining,
                status=LoanSchedule.Status.PENDING,
            )
        )
    LoanSchedule.objects.bulk_create(schedules)
    return list(loan.schedules.order_by("period_no"))


def loan_stats(loan):
    schedules = loan.schedules.all()
    paid = schedules.filter(status=LoanSchedule.Status.PAID)
    paid_principal = D(paid.aggregate(total=Sum("principal_due"))["total"] or 0)
    paid_interest = D(paid.aggregate(total=Sum("interest_due"))["total"] or 0)
    total_interest = D(schedules.aggregate(total=Sum("interest_due"))["total"] or 0)
    next_due = (
        schedules.filter(status__in=[LoanSchedule.Status.PENDING, LoanSchedule.Status.PARTIAL, LoanSchedule.Status.OVERDUE])
        .order_by("due_date")
        .first()
    )
    return {
        "principal": D(loan.principal),
        "total_interest": total_interest,
        "paid_principal": paid_principal,
        "paid_interest": paid_interest,
        "remaining_principal": max(D(loan.principal) - paid_principal, D("0")),
        "paid_periods": paid.count(),
        "term_months": loan.term_months,
        "next_due": next_due,
        "progress": float(paid.count() / loan.term_months) if loan.term_months else 0,
    }


def _month_diff(start, end):
    return max(0, (end.year - start.year) * 12 + (end.month - start.month))


def simulate_offset(loan, use_new_contributions=None, mode=None, monthly_cap=None):
    plan = getattr(loan, "offset_plan", None)
    if not plan or not plan.enabled:
        rows = []
        cash_total = ZERO
        for item in loan.schedules.filter(
            status__in=[LoanSchedule.Status.PENDING, LoanSchedule.Status.PARTIAL, LoanSchedule.Status.OVERDUE]
        ).order_by("period_no"):
            cash_total += D(item.total_due)
            rows.append(
                {
                    "period_no": item.period_no,
                    "due_date": item.due_date,
                    "total_due": D(item.total_due),
                    "pf_offset": ZERO,
                    "cash_due": D(item.total_due),
                    "pf_balance_after": ZERO,
                }
            )
        return {
            "enabled": False,
            "pf_account": None,
            "pf_balance": ZERO,
            "monthly_contribution": ZERO,
            "months_supported": 0,
            "first_cash_due_date": rows[0]["due_date"] if rows else None,
            "cash_total": cash_total,
            "rows": rows,
        }

    use_new = plan.use_new_contributions if use_new_contributions is None else use_new_contributions
    mode = mode or plan.mode
    cap = D(plan.monthly_cap) if monthly_cap is None and plan.monthly_cap is not None else D(monthly_cap) if monthly_cap is not None else None
    pf_account = plan.pf_account
    balance = account_balance(pf_account)
    profile = getattr(pf_account, "pf_profile", None)
    monthly_contribution = D(profile.monthly_total) if (profile and use_new) else ZERO
    start_month = today_local()
    credited_months = 0
    rows = []
    months_supported = 0
    consecutive = True
    first_cash = None
    cash_total = ZERO
    for item in loan.schedules.filter(
        status__in=[LoanSchedule.Status.PENDING, LoanSchedule.Status.PARTIAL, LoanSchedule.Status.OVERDUE]
    ).order_by("period_no"):
        target_months = _month_diff(start_month, item.due_date)
        if monthly_contribution > 0 and target_months > credited_months:
            balance += monthly_contribution * (target_months - credited_months)
            credited_months = target_months
        total_due = D(item.total_due)
        if mode == OffsetPlan.Mode.FULL:
            offset = total_due if balance >= total_due else ZERO
        else:
            cap_value = cap if cap is not None and cap > 0 else total_due
            offset = min(balance, cap_value, total_due)
        cash_due = total_due - offset
        balance -= offset
        cash_total += cash_due
        rows.append(
            {
                "period_no": item.period_no,
                "due_date": item.due_date,
                "total_due": total_due,
                "pf_offset": offset,
                "cash_due": cash_due,
                "pf_balance_after": balance,
            }
        )
        if cash_due == 0 and consecutive:
            months_supported += 1
        else:
            consecutive = False
        if cash_due > 0 and first_cash is None:
            first_cash = item.due_date
    return {
        "enabled": True,
        "pf_account": pf_account.id,
        "pf_balance": account_balance(pf_account),
        "monthly_contribution": monthly_contribution,
        "months_supported": months_supported,
        "first_cash_due_date": first_cash,
        "cash_total": cash_total,
        "rows": rows,
    }
