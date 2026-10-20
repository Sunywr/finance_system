from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def D(value, default=ZERO):
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def money(value):
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)


def split_money(total, parts):
    """Split an amount into `parts` cent-exact pieces; remainder goes to the last piece."""
    total = money(total)
    parts = int(parts)
    if parts <= 0:
        raise ValueError("parts must be positive")
    if parts == 1:
        return [total]
    base = money(total / parts)
    values = [base for _ in range(parts - 1)]
    values.append(total - base * (parts - 1))
    return values


def split_principal(total, parts):
    return split_money(total, parts)


def safe_div(numerator, denominator, default=ZERO):
    numerator = D(numerator)
    denominator = D(denominator)
    if denominator == 0:
        return default
    return numerator / denominator


def percent(numerator, denominator, places=2):
    value = safe_div(numerator, denominator) * Decimal("100")
    return value.quantize(CENT if places == 2 else Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def sum_money(values):
    return sum((D(value) for value in values), ZERO)
