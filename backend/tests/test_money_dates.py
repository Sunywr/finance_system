from datetime import date
from decimal import Decimal

from apps.common.utils.dates import add_months, due_date_for_period, next_payday, statement_period_for
from apps.common.utils.money import money, split_money


def test_split_money_keeps_total_exact():
    parts = split_money(Decimal("1000"), 3)
    assert parts == [Decimal("333.33"), Decimal("333.33"), Decimal("333.34")]
    assert sum(parts) == Decimal("1000.00")


def test_money_rounds_half_up():
    assert money("1.005") == Decimal("1.01")


def test_add_months_clamps_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_statement_period_wraps_month():
    assert statement_period_for(date(2026, 10, 4), 5, 4) == (date(2026, 9, 5), date(2026, 10, 4))
    assert statement_period_for(date(2026, 10, 5), 5, 4) == (date(2026, 10, 5), date(2026, 11, 4))
    assert statement_period_for(date(2026, 10, 19), 5, 4) == (date(2026, 10, 5), date(2026, 11, 4))


def test_due_date_rule():
    assert due_date_for_period(date(2026, 10, 4), 20) == date(2026, 10, 20)
    assert due_date_for_period(date(2026, 11, 4), 1) == date(2026, 12, 1)
    assert due_date_for_period(date(2026, 2, 28), 31) == date(2026, 3, 31)


def test_next_payday():
    assert next_payday(date(2026, 10, 9), 10) == date(2026, 10, 10)
    assert next_payday(date(2026, 10, 11), 10) == date(2026, 11, 10)
    assert next_payday(date(2026, 10, 19), 31) == date(2026, 10, 31)
