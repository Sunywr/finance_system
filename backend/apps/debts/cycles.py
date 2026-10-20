from datetime import date

from apps.common.utils.dates import add_months, clamp_day, due_date_for_period, statement_period_for


def card_period_for(card, value):
    return statement_period_for(value, card.statement_start_day, card.statement_end_day)


def period_due_date(card, period_end):
    return due_date_for_period(period_end, card.due_day)


def next_period_start(card, period_start):
    return add_months(period_start, 1, day=card.statement_start_day)


def period_by_start(card, period_start):
    start = clamp_day(period_start.year, period_start.month, card.statement_start_day)
    end_year, end_month = start.year, start.month
    if card.statement_start_day <= card.statement_end_day:
        end = clamp_day(end_year, end_month, card.statement_end_day)
    else:
        shift = add_months(start, 1, day=card.statement_end_day)
        end = shift
    return start, end
