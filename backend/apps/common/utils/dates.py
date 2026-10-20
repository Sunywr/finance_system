import calendar
from datetime import date, datetime, time, timedelta

from django.utils import timezone


def today_local():
    return timezone.localdate()


def as_date(value):
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    if isinstance(value, datetime):
        return timezone.localtime(value).date() if timezone.is_aware(value) else value.date()
    return value


def day_start(value):
    """Timezone-aware start of day, safe for MySQL where CONVERT_TZ may be unavailable."""
    return timezone.make_aware(datetime.combine(as_date(value), time.min))


def day_end(value):
    """Timezone-aware end of day (inclusive)."""
    return timezone.make_aware(datetime.combine(as_date(value), time.max))


def last_day_of_month(year, month):
    return calendar.monthrange(year, month)[1]


def clamp_day(year, month, day):
    day = int(day)
    return date(year, month, min(max(day, 1), last_day_of_month(year, month)))


def add_months(value, months, day=None):
    value = as_date(value)
    total = value.year * 12 + (value.month - 1) + int(months)
    year, month = divmod(total, 12)
    month += 1
    if day is None:
        day = value.day
    return clamp_day(year, month, day)


def month_bounds(value):
    value = as_date(value)
    return value.replace(day=1), date(value.year, value.month, last_day_of_month(value.year, value.month))


def _period_for_anchor(anchor, start_day, end_day):
    start = clamp_day(anchor.year, anchor.month, start_day)
    end_anchor = anchor if start_day <= end_day else add_months(anchor, 1)
    end = clamp_day(end_anchor.year, end_anchor.month, end_day)
    return start, end


def statement_period_for(value, start_day, end_day):
    """Return the inclusive statement period containing `value`.

    Periods are anchored on `start_day` every month. If the configured
    start/end leave a gap, the next upcoming period is returned.
    """
    target = as_date(value)
    base = date(target.year, target.month, 1)
    candidates = [_period_for_anchor(add_months(base, offset), start_day, end_day) for offset in (-1, 0, 1)]
    for start, end in candidates:
        if start <= target <= end:
            return start, end
    upcoming = sorted((item for item in candidates if item[0] > target), key=lambda item: item[0])
    if upcoming:
        return upcoming[0]
    return candidates[-1]


def due_date_for_period(period_end, due_day):
    """First `due_day` strictly after the period end; otherwise use next month."""
    period_end = as_date(period_end)
    if int(due_day) > period_end.day:
        candidate = clamp_day(period_end.year, period_end.month, due_day)
        if candidate > period_end:
            return candidate
    return add_months(period_end.replace(day=1), 1, day=due_day)


def next_payday(value, payday):
    value = as_date(value)
    candidate = clamp_day(value.year, value.month, payday)
    if candidate >= value:
        return candidate
    return add_months(value.replace(day=1), 1, day=payday)


def days_until(target, start=None):
    start = as_date(start or today_local())
    target = as_date(target)
    return (target - start).days


def date_range(start, end):
    start = as_date(start)
    end = as_date(end)
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def period_label(start, end):
    return f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d}"
