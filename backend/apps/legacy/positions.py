"""Project imported position states forward; never replay incomplete history as truth."""

from collections import defaultdict
from decimal import Decimal
from django.utils import timezone
from apps.common.utils.money import money, percent
from .models import PositionBasis


def imported_holdings(owner, account_id=None, include_auto_plans=False):
    from apps.investments.models import Trade

    qs = PositionBasis.objects.filter(owner=owner).select_related(
        "account", "instrument", "instrument__quote"
    )
    if account_id:
        qs = qs.filter(account_id=account_id)
    grouped = defaultdict(list)
    for b in qs:
        grouped[(b.account_id, b.instrument_id)].append(b)
    future_by_group = defaultdict(list)
    if grouped:
        cutoff = min(b.as_of for bases in grouped.values() for b in bases)
        future = Trade.objects.filter(
            owner=owner, legacy_batch__isnull=True, trade_date__gt=cutoff
        ).order_by("trade_date", "pk")
        if account_id:
            future = future.filter(account_id=account_id)
        for t in future:
            future_by_group[(t.account_id, t.instrument_id)].append(t)
    result = []
    for key, bases in grouped.items():
        cutoff = max(b.as_of for b in bases)
        active = [
            b
            for b in bases
            if b.is_active and (include_auto_plans or not b.is_auto_plan)
        ]
        trades = [t for t in future_by_group[key] if t.trade_date > cutoff]
        if not active and not trades:
            continue
        qty = sum((b.quantity for b in active), Decimal(0))
        cost = sum((b.cost for b in active), Decimal(0))
        initial_cost = cost
        initial_market = sum((b.market_value for b in active), Decimal(0))
        initial_profit = sum((b.profit for b in active), Decimal(0))
        realized = Decimal(0)
        dividends = Decimal(0)
        for t in trades:
            if t.side == "BUY":
                qty += t.quantity
                cost += t.amount
            elif t.side == "SELL":
                if t.quantity > qty:
                    raise ValueError("Imported position cannot cover this sale")
                removed = cost / qty * t.quantity if qty else Decimal(0)
                cost -= removed
                qty -= t.quantity
                realized += t.amount - removed
            else:
                dividends += t.amount
        b = bases[0]
        inst = b.instrument
        quote = getattr(inst, "quote", None)
        price = quote.price if quote and quote.price > 0 else b.price
        market = (
            money(qty * price)
            if trades or (quote and quote.price > 0)
            else money(initial_market)
        )
        pnl = money(
            initial_profit
            + market
            - initial_market
            - (cost - initial_cost)
            + realized
            + dividends
        )
        last = next((t for t in reversed(trades) if t.side != "DIVIDEND"), None)
        result.append(
            dict(
                account=b.account_id,
                account_name=b.account.name,
                instrument=b.instrument_id,
                symbol=inst.symbol,
                name=inst.name,
                instrument_type=inst.type,
                valuation_mode=inst.valuation_mode,
                quantity=qty,
                avg_cost=cost / qty if qty else None,
                cost=money(cost),
                total_buy=None,
                market_value=market,
                unrealized_pnl=money(market - cost),
                realized_pnl=None,
                dividends=None,
                total_pnl=pnl,
                return_rate=None,
                position_return_rate=percent(market - cost, cost) if cost > 0 else None,
                last_price=price,
                price_source="quote" if quote else "imported_snapshot",
                is_stale=True if quote is None else quote.is_stale,
                last_trade_date=last.trade_date if last else None,
                last_trade_price=last.price if last else None,
                since_last_trade_return=(
                    percent(price - last.price, last.price) if last else None
                ),
                days_since_last_trade=(
                    (
                        timezone.localdate()
                        - timezone.localtime(last.trade_date).date()
                    ).days
                    if last
                    else None
                ),
                quote_change_pct=quote.change_pct if quote else None,
                basis_as_of=cutoff,
                legacy_profit=money(initial_profit),
                historical_realized_status="not_independently_reconciled",
                attribution_verified=all(b.attribution_verified for b in active),
                cost_anchor_count=sum(bool(b.cost_anchor) for b in active),
            )
        )
    return set(grouped), result
