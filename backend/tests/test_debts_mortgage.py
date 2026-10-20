from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.models import Account
from apps.common.utils.dates import add_months, today_local
from apps.debts.models import DebtItem, RecurringDebt
from apps.debts.services import create_recurring_items
from apps.mortgages.models import Loan, OffsetPlan
from apps.mortgages.services import generate_schedule, loan_stats, simulate_offset

pytestmark = pytest.mark.django_db


def test_recurring_debt_generates_periods(user):
    recurring = RecurringDebt.objects.create(
        owner=user,
        name="保险",
        amount="300",
        periods=3,
        interval_months=1,
        first_due_date=date(2026, 1, 31),
        due_day=31,
        auto_pay=False,
    )
    items = create_recurring_items(recurring)
    assert len(items) == 3
    assert items[0].due_date == date(2026, 1, 31)
    assert items[1].due_date == date(2026, 2, 28)
    assert items[2].due_date == date(2026, 3, 31)


def test_equal_installment_schedule_totals(user, savings):
    loan = Loan.objects.create(
        owner=user,
        name="房贷",
        loan_type=Loan.LoanType.COMMERCIAL,
        principal="120000",
        annual_rate="4.8",
        term_months=12,
        repayment_method=Loan.RepaymentMethod.EQUAL_INSTALLMENT,
        first_due_date=add_months(today_local(), 1, day=10),
        payment_day=10,
        repayment_account=savings,
    )
    generate_schedule(loan)
    schedules = list(loan.schedules.order_by("period_no"))
    assert len(schedules) == 12
    assert sum(item.principal_due for item in schedules) == Decimal("120000.00")
    assert schedules[-1].remaining_principal == Decimal("0.00")
    stats = loan_stats(loan)
    assert stats["remaining_principal"] == Decimal("120000.00")


def test_equal_principal_schedule_totals(user, savings):
    loan = Loan.objects.create(
        owner=user,
        name="公积金贷",
        loan_type=Loan.LoanType.PROVIDENT_FUND,
        principal="120000",
        annual_rate="3.1",
        term_months=12,
        repayment_method=Loan.RepaymentMethod.EQUAL_PRINCIPAL,
        first_due_date=add_months(today_local(), 1, day=10),
        payment_day=10,
        repayment_account=savings,
    )
    generate_schedule(loan)
    schedules = list(loan.schedules.order_by("period_no"))
    assert sum(item.principal_due for item in schedules) == Decimal("120000.00")
    assert schedules[0].principal_due == Decimal("10000.00")
    assert schedules[-1].remaining_principal == Decimal("0.00")


def test_pf_offset_simulation(user, savings):
    pf = Account.objects.create(
        owner=user, name="公积金", type=Account.Type.PROVIDENT_FUND_MAIN, opening_balance="20000"
    )
    loan = Loan.objects.create(
        owner=user,
        name="房贷",
        loan_type=Loan.LoanType.COMMERCIAL,
        principal="120000",
        annual_rate="4.8",
        term_months=12,
        repayment_method=Loan.RepaymentMethod.EQUAL_INSTALLMENT,
        first_due_date=add_months(today_local(), 1, day=10),
        payment_day=10,
        repayment_account=savings,
    )
    generate_schedule(loan)
    OffsetPlan.objects.create(
        loan=loan,
        pf_account=pf,
        enabled=True,
        mode=OffsetPlan.Mode.FULL,
        use_new_contributions=False,
    )
    result = simulate_offset(loan)
    assert result["enabled"] is True
    assert result["months_supported"] >= 1
    assert result["first_cash_due_date"] is not None
    assert result["pf_balance"] == 20000


def test_pf_offset_zero_balance_first_cash_immediately(user, savings):
    pf = Account.objects.create(
        owner=user, name="公积金", type=Account.Type.PROVIDENT_FUND_MAIN, opening_balance="0"
    )
    loan = Loan.objects.create(
        owner=user,
        name="房贷",
        loan_type=Loan.LoanType.COMMERCIAL,
        principal="120000",
        annual_rate="4.8",
        term_months=12,
        repayment_method=Loan.RepaymentMethod.EQUAL_INSTALLMENT,
        first_due_date=add_months(today_local(), 1, day=10),
        payment_day=10,
        repayment_account=savings,
    )
    generate_schedule(loan)
    OffsetPlan.objects.create(
        loan=loan,
        pf_account=pf,
        enabled=True,
        mode=OffsetPlan.Mode.FULL,
        use_new_contributions=False,
    )
    result = simulate_offset(loan)
    assert result["months_supported"] == 0
    assert result["first_cash_due_date"] == loan.schedules.order_by("due_date").first().due_date
