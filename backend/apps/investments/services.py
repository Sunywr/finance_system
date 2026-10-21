import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Account
from apps.common.utils.money import D, money, percent
from apps.ledger.models import Category, Transaction
from apps.ledger.services import (
    channel_for_account,
    create_transaction,
    system_category,
)

from apps.common.utils.dates import today_local

from .indicators import build_indicator_rows, latest_signals
from .market import (
    fetch_bars,
    fetch_index_bars,
    fetch_ipo_calendar,
    fetch_quote,
    fetch_report_appointments,
    fetch_reports,
    fetch_spot_universe,
)
from .models import (
    DailyBar,
    IndicatorSnapshot,
    Instrument,
    IPOCalendar,
    MarketRegime,
    Quote,
    ReportEvent,
    ScreenerPreset,
    ScreenerResult,
    ScreenerRun,
    StrategySignal,
    Trade,
)

logger = logging.getLogger(__name__)


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


TRADABLE_ACCOUNTS = {
    Instrument.Type.CONVERTIBLE_BOND: {Account.Type.STOCK},
    Instrument.Type.GOLD: {Account.Type.STOCK, Account.Type.WEALTH},
    Instrument.Type.STOCK: {Account.Type.STOCK},
    Instrument.Type.ETF: {Account.Type.STOCK, Account.Type.WEALTH},
    Instrument.Type.OTC_FUND: {
        Account.Type.STOCK,
        Account.Type.WEALTH,
        Account.Type.ALIPAY,
        Account.Type.WECHAT,
    },
    Instrument.Type.WEALTH: {
        Account.Type.STOCK,
        Account.Type.WEALTH,
        Account.Type.ALIPAY,
        Account.Type.WECHAT,
    },
}


def _validate_account(account, instrument):
    allowed = TRADABLE_ACCOUNTS.get(instrument.type, set())
    if account.type not in allowed:
        raise ValidationError({"account": "该账户不能交易此类型标的"})
    if account.type in (
        Account.Type.ALIPAY,
        Account.Type.WECHAT,
    ) and instrument.type not in (
        Instrument.Type.WEALTH,
        Instrument.Type.OTC_FUND,
    ):
        raise ValidationError({"account": "支付宝/微信账户只能购买理财或场外基金"})


def _category_for(instrument, owner):
    kind = (
        Category.Kind.STOCK
        if instrument.type
        in (
            Instrument.Type.STOCK,
            Instrument.Type.ETF,
            Instrument.Type.CONVERTIBLE_BOND,
        )
        else Category.Kind.INVESTMENT
    )
    return system_category(owner, kind)


def _position_state(trades):
    quantity = D("0")
    cost = D("0")
    realized = D("0")
    dividends = D("0")
    total_buy = D("0")
    realized_cost = D("0")
    first_trade = None
    last_trade = None
    for trade in trades:
        first_trade = first_trade or trade
        last_trade = trade
        if trade.side == Trade.Side.BUY:
            quantity += D(trade.quantity)
            cost += D(trade.amount)
            total_buy += D(trade.amount)
        elif trade.side == Trade.Side.SELL:
            sell_qty = min(quantity, D(trade.quantity))
            avg = cost / quantity if quantity > 0 else D("0")
            cost_removed = avg * sell_qty
            realized += D(trade.amount) - cost_removed
            cost -= cost_removed
            quantity -= sell_qty
            realized_cost += cost_removed
        elif trade.side == Trade.Side.DIVIDEND:
            dividends += D(trade.amount)
    return {
        "quantity": quantity,
        "cost": cost,
        "realized": realized,
        "dividends": dividends,
        "total_buy": total_buy,
        "realized_cost": realized_cost,
        "first_trade": first_trade,
        "last_trade": last_trade,
        "avg_cost": (cost / quantity) if quantity > 0 else D("0"),
    }


def _current_trade_state(owner, account, instrument):
    from apps.legacy.positions import imported_holdings

    _, imported = imported_holdings(owner, account.id)
    row = next((r for r in imported if r["instrument"] == instrument.id), None)
    if row is not None:
        return {"quantity": row["quantity"], "avg_cost": row["avg_cost"]}
    return _position_state(
        Trade.objects.filter(
            owner=owner, account=account, instrument=instrument
        ).order_by("trade_date", "id")
    )


def create_trade(
    *,
    owner,
    account,
    instrument,
    side,
    operation,
    quantity=Decimal("0"),
    price=Decimal("0"),
    fee=Decimal("0"),
    trade_date=None,
    amount=None,
    note="",
):
    if account.owner_id != owner.id:
        raise ValidationError({"account": "账户不存在"})
    if instrument.owner_id != owner.id:
        raise ValidationError({"instrument": "标的不存在"})
    if not instrument.is_active:
        raise ValidationError({"instrument": "标的已停用"})
    _validate_account(account, instrument)
    from apps.legacy.models import PositionBasis

    imported_basis = PositionBasis.objects.filter(
        owner=owner, account=account, instrument=instrument, is_active=True
    )
    if (
        instrument.valuation_mode != Instrument.ValuationMode.MARKET
        and imported_basis.exists()
    ):
        if sum((b.quantity for b in imported_basis), D("0")) == 0 and any(
            b.cost != 0 for b in imported_basis
        ):
            raise ValidationError(
                {"quantity": "历史持仓没有可核实的份额，请先核实份额与估值后再交易"}
            )
    quantity = D(quantity)
    price = D(price)
    fee = money(fee)
    trade_date = trade_date or timezone.now()
    if fee < 0:
        raise ValidationError({"fee": "费用不能为负"})
    total = D("0")
    txn_type = Transaction.Type.EXPENSE
    level_operation = operation
    if side == Trade.Side.BUY:
        if quantity <= 0 or price <= 0:
            raise ValidationError({"quantity": "买入数量和价格必须大于 0"})
        if level_operation not in (Trade.Operation.OPEN, Trade.Operation.ADD):
            level_operation = Trade.Operation.OPEN
        total = money(quantity * price + fee)
        txn_type = Transaction.Type.EXPENSE
    elif side == Trade.Side.SELL:
        if quantity <= 0 or price <= 0:
            raise ValidationError({"quantity": "卖出数量和价格必须大于 0"})
        state = _current_trade_state(owner, account, instrument)
        if D(state["quantity"]) < quantity:
            raise ValidationError(
                {"quantity": f"持仓不足，当前持仓 {state['quantity']}"}
            )
        level_operation = Trade.Operation.REDUCE
        total = money(quantity * price - fee)
        if total <= 0:
            raise ValidationError({"amount": "卖出金额必须大于 0"})
        txn_type = Transaction.Type.INCOME
    elif side == Trade.Side.DIVIDEND:
        level_operation = Trade.Operation.DIVIDEND
        total = money(amount if amount is not None else quantity * price)
        if total <= 0:
            raise ValidationError({"amount": "分红金额必须大于 0"})
        txn_type = Transaction.Type.INCOME
    else:
        raise ValidationError({"side": "交易方向不正确"})

    with db_transaction.atomic():
        txn = create_transaction(
            owner=owner,
            txn_type=txn_type,
            category=_category_for(instrument, owner),
            amount=total,
            occurred_at=trade_date,
            settlement_channel=channel_for_account(account),
            account=account,
            operation=level_operation,
            note=note or f"{instrument.name} {side}",
            source=Transaction.Source.INVESTMENT,
        )
        realized = None
        if side == Trade.Side.SELL:
            state = _current_trade_state(owner, account, instrument)
            avg = state["avg_cost"]
            realized = money(total - avg * quantity)
        trade = Trade.objects.create(
            owner=owner,
            account=account,
            instrument=instrument,
            transaction=txn,
            side=side,
            operation=level_operation,
            trade_date=trade_date,
            quantity=quantity,
            price=price,
            fee=fee,
            amount=total,
            realized_pnl=realized,
            note=note or "",
        )
    return trade


def latest_price(instrument):
    quote = getattr(instrument, "quote", None)
    if quote and D(quote.price) > 0:
        return D(quote.price), "quote", bool(quote.is_stale)
    bar = instrument.bars.order_by("-trade_date").first()
    if bar:
        return D(bar.close), "bar", True
    trade = instrument.trades.order_by("-trade_date").first()
    if trade:
        return D(trade.price), "trade", True
    return D("0"), "none", True


def holdings(owner, account_id=None, include_auto_plans=False):
    from apps.legacy.positions import imported_holdings

    imported_keys, imported_rows = imported_holdings(owner, account_id, include_auto_plans)
    qs = Trade.objects.filter(owner=owner).select_related(
        "account", "instrument", "transaction"
    )
    if account_id:
        qs = qs.filter(account_id=account_id)
    grouped = {}
    for trade in qs.order_by("account_id", "instrument_id", "trade_date", "id"):
        grouped.setdefault((trade.account_id, trade.instrument_id), []).append(trade)
    today = timezone.localdate()
    rows = []
    for (account_id_value, instrument_id), trades in grouped.items():
        if (account_id_value, instrument_id) in imported_keys:
            continue
        instrument = trades[0].instrument
        account = trades[0].account
        state = _position_state(trades)
        quote = getattr(instrument, "quote", None)
        price, price_source, stale = latest_price(instrument)
        if instrument.valuation_mode == Instrument.ValuationMode.ACCRUAL:
            days = (
                max((today - state["first_trade"].trade_date.date()).days, 0)
                if state["first_trade"]
                else 0
            )
            estimated_value = D(state["cost"]) * (
                Decimal("1")
                + D(instrument.annual_rate)
                / Decimal("100")
                * Decimal(days)
                / Decimal("365")
            )
            market_value = money(estimated_value)
            price = (
                money(market_value / state["quantity"])
                if state["quantity"] > 0
                else D("0")
            )
        else:
            market_value = money(state["quantity"] * price)
        unrealized = market_value - D(state["cost"])
        total_pnl = unrealized + D(state["realized"]) + D(state["dividends"])
        last_trade = state["last_trade"]
        price_trade = next(
            (trade for trade in reversed(trades) if trade.side != Trade.Side.DIVIDEND),
            None,
        )
        since_return = None
        days_since = None
        if price_trade and D(price_trade.price) > 0:
            since_return = (
                (price - D(price_trade.price)) / D(price_trade.price) * Decimal("100")
            )
            days_since = max((today - price_trade.trade_date.date()).days, 0)
        rows.append(
            {
                "account": account.id,
                "account_name": account.name,
                "instrument": instrument.id,
                "symbol": instrument.symbol,
                "name": instrument.name,
                "instrument_type": instrument.type,
                "valuation_mode": instrument.valuation_mode,
                "quantity": state["quantity"],
                "avg_cost": state["avg_cost"].quantize(Decimal("0.0001")),
                "cost": money(state["cost"]),
                "total_buy": money(state["total_buy"]),
                "market_value": market_value,
                "unrealized_pnl": money(unrealized),
                "realized_pnl": money(state["realized"]),
                "dividends": money(state["dividends"]),
                "total_pnl": money(total_pnl),
                "return_rate": percent(total_pnl, state["total_buy"]),
                "position_return_rate": percent(unrealized, state["cost"]),
                "last_price": price,
                "price_source": price_source,
                "is_stale": stale,
                "last_trade_date": price_trade.trade_date if price_trade else None,
                "last_trade_price": price_trade.price if price_trade else None,
                "since_last_trade_return": (
                    since_return.quantize(Decimal("0.01"))
                    if since_return is not None
                    else None
                ),
                "days_since_last_trade": days_since,
                "quote_change_pct": quote.change_pct if quote else None,
            }
        )
    rows.extend(imported_rows)
    rows.sort(key=lambda item: (-float(item["market_value"]), item["symbol"]))
    return rows


def portfolio_summary(owner, include_auto_plans=False, account_id=None):
    rows = holdings(owner, account_id=account_id, include_auto_plans=include_auto_plans)
    totals = {
        "cost": sum((D(row["cost"]) for row in rows), D("0")),
        "market_value": sum((D(row["market_value"]) for row in rows), D("0")),
        "unrealized_pnl": sum((D(row["unrealized_pnl"]) for row in rows), D("0")),
        "realized_pnl": (
            None
            if any(row["realized_pnl"] is None for row in rows)
            else sum((D(row["realized_pnl"]) for row in rows), D("0"))
        ),
        "dividends": (
            None
            if any(row["dividends"] is None for row in rows)
            else sum((D(row["dividends"]) for row in rows), D("0"))
        ),
        "total_pnl": sum((D(row["total_pnl"]) for row in rows), D("0")),
    }
    invested = (
        None
        if any(row["total_buy"] is None for row in rows)
        else sum((D(row["total_buy"]) for row in rows), D("0"))
    )
    totals["invested"] = invested
    totals["return_rate"] = (
        percent(totals["total_pnl"], invested) if invested is not None else None
    )
    totals["count"] = len(rows)
    by_account = {}
    for row in rows:
        bucket = by_account.setdefault(
            row["account"],
            {
                "account": row["account"],
                "account_name": row["account_name"],
                "market_value": D("0"),
                "total_pnl": D("0"),
            },
        )
        bucket["market_value"] += D(row["market_value"])
        bucket["total_pnl"] += D(row["total_pnl"])
    return {"totals": totals, "by_account": list(by_account.values()), "items": rows}


def _bar_rows(instrument, limit=300):
    bars = list(instrument.bars.order_by("-trade_date")[:limit])
    bars.reverse()
    return [
        {
            "trade_date": bar.trade_date,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "amount": bar.amount,
        }
        for bar in bars
    ]


def indicator_data(instrument, limit=180):
    rows = _bar_rows(instrument, limit=max(limit, 120))
    computed = build_indicator_rows(rows)
    signals = latest_signals(rows, computed)
    return {
        "items": computed[-limit:],
        "signals": signals,
        "latest": computed[-1] if computed else None,
    }


def sync_instrument(instrument, days=300):
    if (
        instrument.valuation_mode != Instrument.ValuationMode.MARKET
        or instrument.exchange == Instrument.Exchange.OTC
    ):
        return {
            "instrument": instrument.id,
            "status": "skipped",
            "reason": "非行情估值标的",
        }
    try:
        quote_data = fetch_quote(instrument)
        if quote_data:
            Quote.objects.update_or_create(
                instrument=instrument,
                defaults={
                    "price": quote_data["price"],
                    "prev_close": quote_data["prev_close"],
                    "change_pct": quote_data["change_pct"],
                    "open": quote_data["open"],
                    "high": quote_data["high"],
                    "low": quote_data["low"],
                    "volume": quote_data["volume"],
                    "amount": quote_data["amount"],
                    "pe": quote_data.get("pe"),
                    "pb": quote_data.get("pb"),
                    "market_cap": quote_data.get("market_cap"),
                    "source": quote_data.get("source", "eastmoney"),
                    "is_stale": False,
                },
            )
        bar_rows = fetch_bars(instrument, limit=days)
        created = 0
        updated = 0
        if bar_rows:
            dates = [row["trade_date"] for row in bar_rows]
            existing = {
                bar.trade_date: bar
                for bar in instrument.bars.filter(trade_date__in=dates)
            }
            to_create = []
            to_update = []
            for row in bar_rows:
                trade_date_value = date.fromisoformat(row["trade_date"])
                if trade_date_value in existing:
                    bar = existing[trade_date_value]
                    bar.open = row["open"]
                    bar.high = row["high"]
                    bar.low = row["low"]
                    bar.close = row["close"]
                    bar.volume = row["volume"]
                    bar.amount = row["amount"]
                    to_update.append(bar)
                else:
                    to_create.append(
                        DailyBar(
                            instrument=instrument,
                            trade_date=trade_date_value,
                            open=row["open"],
                            high=row["high"],
                            low=row["low"],
                            close=row["close"],
                            volume=row["volume"],
                            amount=row["amount"],
                        )
                    )
            if to_create:
                DailyBar.objects.bulk_create(to_create)
                created = len(to_create)
            if to_update:
                DailyBar.objects.bulk_update(
                    to_update, ["open", "high", "low", "close", "volume", "amount"]
                )
                updated = len(to_update)
        rows = _bar_rows(instrument, limit=max(days, 120))
        computed = build_indicator_rows(rows)
        if computed:
            latest = computed[-1]
            signals = latest_signals(rows, computed)
            IndicatorSnapshot.objects.update_or_create(
                instrument=instrument,
                trade_date=latest["trade_date"],
                defaults={
                    "ma5": latest["ma5"],
                    "ma10": latest["ma10"],
                    "ma20": latest["ma20"],
                    "ma60": latest["ma60"],
                    "macd_dif": latest["macd_dif"],
                    "macd_dea": latest["macd_dea"],
                    "macd_hist": latest["macd_hist"],
                    "kdj_k": latest["kdj_k"],
                    "kdj_d": latest["kdj_d"],
                    "kdj_j": latest["kdj_j"],
                    "rsi6": latest["rsi6"],
                    "rsi12": latest["rsi12"],
                    "rsi24": latest["rsi24"],
                    "boll_upper": latest["boll_upper"],
                    "boll_mid": latest["boll_mid"],
                    "boll_lower": latest["boll_lower"],
                    "signals": signals,
                },
            )
        return {
            "instrument": instrument.id,
            "status": "ok",
            "bars_created": created,
            "bars_updated": updated,
            "quote": bool(quote_data),
        }
    except Exception as exc:
        logger.exception("sync instrument failed: %s", instrument.symbol)
        quote = getattr(instrument, "quote", None)
        if quote:
            quote.is_stale = True
            quote.save(update_fields=["is_stale", "updated_at"])
        return {"instrument": instrument.id, "status": "error", "error": str(exc)}


def sync_all_market_data(owner):
    instruments = Instrument.objects.filter(
        owner=owner, is_active=True, valuation_mode=Instrument.ValuationMode.MARKET
    ).exclude(exchange=Instrument.Exchange.OTC)
    stats = {"total": 0, "ok": 0, "error": 0, "skipped": 0}
    for instrument in instruments:
        result = sync_instrument(instrument)
        stats["total"] += 1
        stats[result["status"]] = stats.get(result["status"], 0) + 1
    return stats


DEFAULT_PRESETS = [
    {
        "name": "股息价值",
        "description": "低估值、高股息、长期趋势向上，适合稳持吃股息",
        "criteria": {
            "max_pe": 20,
            "max_pb": 3,
            "min_dividend_yield": 3,
            "min_market_cap": 100,
            "technical": ["above_ma60"],
            "limit": 20,
        },
    },
    {
        "name": "低估值",
        "description": "PE/PB 双低，适合价值观察",
        "criteria": {"max_pe": 15, "max_pb": 1.5, "min_market_cap": 50, "limit": 20},
    },
    {
        "name": "趋势突破",
        "description": "站上 MA20/MA60，量能活跃",
        "criteria": {
            "min_turnover": 1,
            "technical": ["above_ma20", "above_ma60"],
            "limit": 20,
        },
    },
    {
        "name": "超跌反弹",
        "description": "KDJ 超卖且估值不过高，寻找 B 点",
        "criteria": {
            "max_pe": 40,
            "technical": ["kdj_oversold"],
            "limit": 20,
        },
    },
]


def ensure_presets(owner):
    for index, preset in enumerate(DEFAULT_PRESETS):
        ScreenerPreset.objects.get_or_create(
            owner=owner,
            name=preset["name"],
            defaults={
                "description": preset["description"],
                "criteria": preset["criteria"],
                "is_default": index == 0,
            },
        )


def _exchange_for_symbol(symbol):
    if symbol.startswith("6"):
        return Instrument.Exchange.SH
    if symbol.startswith(("0", "3")):
        return Instrument.Exchange.SZ
    if symbol.startswith(("8", "4", "9")):
        return Instrument.Exchange.BJ
    return Instrument.Exchange.SH


def _technical_signals(symbol, exchange):
    fake = Instrument(
        symbol=symbol, exchange=exchange, name="", type=Instrument.Type.STOCK
    )
    rows = fetch_bars(fake, 160)
    computed = build_indicator_rows(rows)
    return latest_signals(rows, computed)


def run_screener(owner, criteria=None, preset=None):
    merged = {"max_pages": 10, "limit": 20, "technical_check_limit": 15}
    if preset:
        merged.update(preset.criteria or {})
    if criteria:
        merged.update(criteria)
    run = ScreenerRun.objects.create(owner=owner, preset=preset, criteria=merged)
    try:
        try:
            universe = fetch_spot_universe(max_pages=int(merged.get("max_pages", 10)))
        except Exception:
            universe = fetch_spot_universe(max_pages=5)
        dividend_map = {
            item.symbol: D(item.dividend_yield)
            for item in Instrument.objects.filter(
                owner=owner, type=Instrument.Type.STOCK
            )
            if item.dividend_yield is not None
        }
        instrument_map = {
            item.symbol: item
            for item in Instrument.objects.filter(
                owner=owner, type=Instrument.Type.STOCK
            )
        }
        industries = [item for item in (merged.get("industries") or []) if item]
        min_price = (
            D(merged.get("min_price")) if merged.get("min_price") is not None else None
        )
        max_price = (
            D(merged.get("max_price")) if merged.get("max_price") is not None else None
        )
        max_pe = D(merged.get("max_pe")) if merged.get("max_pe") is not None else None
        min_pe = D(merged.get("min_pe")) if merged.get("min_pe") is not None else None
        max_pb = D(merged.get("max_pb")) if merged.get("max_pb") is not None else None
        min_cap = (
            D(merged.get("min_market_cap"))
            if merged.get("min_market_cap") is not None
            else None
        )
        max_cap = (
            D(merged.get("max_market_cap"))
            if merged.get("max_market_cap") is not None
            else None
        )
        min_turnover = (
            D(merged.get("min_turnover"))
            if merged.get("min_turnover") is not None
            else None
        )
        min_volume_ratio = (
            D(merged.get("min_volume_ratio"))
            if merged.get("min_volume_ratio") is not None
            else None
        )
        min_dividend = (
            D(merged.get("min_dividend_yield"))
            if merged.get("min_dividend_yield")
            else None
        )
        technical = set(merged.get("technical") or [])

        candidates = []
        for item in universe:
            price = D(item["price"])
            pe = D(item["pe"]) if item.get("pe") is not None else None
            pb = D(item["pb"]) if item.get("pb") is not None else None
            market_cap_yi = (
                D(item["market_cap"]) / Decimal("100000000")
                if item.get("market_cap")
                else None
            )
            dividend = dividend_map.get(item["symbol"])
            if min_price is not None and price < min_price:
                continue
            if max_price is not None and price > max_price:
                continue
            if max_pe is not None and (pe is None or pe <= 0 or pe > max_pe):
                continue
            if min_pe is not None and (pe is None or pe < min_pe):
                continue
            if max_pb is not None and (pb is None or pb <= 0 or pb > max_pb):
                continue
            if min_cap is not None and (
                market_cap_yi is None or market_cap_yi < min_cap
            ):
                continue
            if max_cap is not None and (
                market_cap_yi is None or market_cap_yi > max_cap
            ):
                continue
            if min_turnover is not None and D(item.get("turnover") or 0) < min_turnover:
                continue
            if (
                min_volume_ratio is not None
                and D(item.get("volume_ratio") or 0) < min_volume_ratio
            ):
                continue
            if min_dividend is not None and (
                dividend is None or dividend < min_dividend
            ):
                continue
            if industries and item.get("industry") not in industries:
                continue
            score = Decimal("50")
            reasons = []
            if pe is not None and pe > 0:
                score += max(Decimal("0"), Decimal("25") - pe)
                reasons.append(f"PE {pe}")
            if pb is not None and pb > 0:
                score += max(Decimal("0"), Decimal("4") - pb) * 5
                reasons.append(f"PB {pb}")
            if dividend is not None:
                score += dividend * 8
                reasons.append(f"股息率 {dividend}%")
            if market_cap_yi is not None:
                reasons.append(f"市值 {market_cap_yi.quantize(Decimal('0.01'))}亿")
            if item.get("change_60d") is not None:
                change_60 = D(item["change_60d"])
                score += max(Decimal("-15"), min(Decimal("15"), -change_60)) * Decimal(
                    "0.5"
                )
            candidates.append(
                {
                    **item,
                    "market_cap_yi": market_cap_yi,
                    "dividend": dividend,
                    "score": score,
                    "reasons": reasons,
                }
            )
        candidates.sort(key=lambda item: item["score"], reverse=True)
        if technical:
            checked = []
            for item in candidates[: int(merged.get("technical_check_limit", 15))]:
                try:
                    signals = _technical_signals(
                        item["symbol"], _exchange_for_symbol(item["symbol"])
                    )
                except Exception:
                    continue
                if all(bool(signals.get(key)) for key in technical):
                    for key in technical:
                        item["reasons"].append(key)
                    item["signals"] = signals
                    checked.append(item)
            candidates = checked
        limit = int(merged.get("limit", 20))
        for item in candidates[:limit]:
            ScreenerResult.objects.create(
                run=run,
                instrument=instrument_map.get(item["symbol"]),
                symbol=item["symbol"],
                name=item["name"],
                industry=item.get("industry") or "",
                price=item["price"],
                change_pct=item.get("change_pct"),
                pe=item.get("pe"),
                pb=item.get("pb"),
                market_cap=item.get("market_cap"),
                dividend_yield=item.get("dividend"),
                score=item["score"].quantize(Decimal("0.01")),
                reasons=item["reasons"],
                metrics={
                    "market_cap_yi": str(item.get("market_cap_yi") or ""),
                    "change_60d": str(item.get("change_60d") or ""),
                    "turnover": str(item.get("turnover") or ""),
                    "volume_ratio": str(item.get("volume_ratio") or ""),
                    "signals": item.get("signals", {}),
                },
            )
        run.status = ScreenerRun.Status.SUCCESS
        run.universe_size = len(universe)
        run.result_count = min(len(candidates), limit)
        run.finished_at = timezone.now()
        run.save()
    except Exception as exc:
        logger.exception("screener failed")
        run.status = ScreenerRun.Status.FAILED
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save()
    return run


def refresh_market_regime(owner):
    today = today_local()
    try:
        universe = fetch_spot_universe(max_pages=5)
    except Exception:
        last = MarketRegime.objects.filter(owner=owner).first()
        if last:
            return last
        raise
    advance = sum(1 for item in universe if D(item.get("change_pct") or 0) > 0)
    decline = sum(1 for item in universe if D(item.get("change_pct") or 0) < 0)
    total = max(advance + decline, 1)
    breadth = Decimal(advance) / Decimal(total)
    bars = fetch_index_bars("000300", "SH", 180)
    computed = build_indicator_rows(bars)
    latest = computed[-1] if computed else {}
    close = D(latest.get("close")) if latest.get("close") is not None else None
    ma20 = D(latest.get("ma20")) if latest.get("ma20") is not None else None
    ma60 = D(latest.get("ma60")) if latest.get("ma60") is not None else None

    sectors = {}
    for item in universe:
        name = item.get("industry") or "其他"
        bucket = sectors.setdefault(
            name, {"name": name, "count": 0, "sum": Decimal("0"), "advance": 0}
        )
        bucket["count"] += 1
        bucket["sum"] += D(item.get("change_pct") or 0)
        if D(item.get("change_pct") or 0) > 0:
            bucket["advance"] += 1
    sector_rows = []
    for bucket in sectors.values():
        if bucket["count"] < 3:
            continue
        avg = bucket["sum"] / bucket["count"]
        sector_rows.append(
            {
                "name": bucket["name"],
                "avg_change": avg.quantize(Decimal("0.01")),
                "count": bucket["count"],
                "advance_ratio": (
                    Decimal(bucket["advance"]) / bucket["count"] * 100
                ).quantize(Decimal("0.01")),
            }
        )
    sector_rows.sort(key=lambda item: item["avg_change"], reverse=True)
    sector_rows = sector_rows[:10] + sector_rows[-3:]

    score = Decimal("0")
    if close is not None and ma20 is not None:
        score += Decimal("30") if close > ma20 else Decimal("-30")
    if ma20 is not None and ma60 is not None:
        score += Decimal("20") if ma20 > ma60 else Decimal("-20")
    score += (breadth - Decimal("0.5")) * Decimal("80")
    if len(computed) >= 2 and computed[-2].get("close"):
        prev = D(computed[-2]["close"])
        if prev:
            score += (D(computed[-1]["close"]) / prev - 1) * 100 * 2
    score = max(Decimal("-100"), min(Decimal("100"), score))
    regime = (
        MarketRegime.Regime.BULL
        if score >= 20
        else MarketRegime.Regime.BEAR if score <= -20 else MarketRegime.Regime.NEUTRAL
    )
    explanation = (
        f"沪深300 {close or '—'}，MA20 {ma20 or '—'}，MA60 {ma60 or '—'}；"
        f"上涨 {advance} 家、下跌 {decline} 家，宽度 {float(breadth):.2%}；"
        f"综合评分 {score:.2f}，判定为 {dict(MarketRegime.Regime.choices)[regime]}。"
    )
    record, _ = MarketRegime.objects.update_or_create(
        owner=owner,
        trade_date=today,
        defaults={
            "regime": regime,
            "score": score,
            "index_close": close,
            "ma20": ma20,
            "ma60": ma60,
            "advance_count": advance,
            "decline_count": decline,
            "breadth_ratio": breadth,
            "sectors": _jsonable(sector_rows),
            "explanation": explanation,
        },
    )
    return record


def sync_reports(instrument):
    merged = {}
    for row in fetch_report_appointments(instrument):
        key = (row["report_type"], row["period_end"])
        merged.setdefault(key, {}).update(
            {
                "disclosure_date": row.get("disclosure_date"),
                "actual_date": row.get("actual_date"),
            }
        )
    for row in fetch_reports(instrument):
        key = (row["report_type"], row["period_end"])
        merged.setdefault(key, {}).update(
            {
                "actual_date": row.get("actual_date"),
                "revenue": row.get("revenue"),
                "net_profit": row.get("net_profit"),
                "revenue_yoy": row.get("revenue_yoy"),
                "profit_yoy": row.get("profit_yoy"),
                "roe": row.get("roe"),
                "eps": row.get("eps"),
                "summary": row.get("summary", ""),
            }
        )
    count = 0
    for (report_type, period_end), data in merged.items():
        released = (
            data.get("actual_date") is not None or data.get("revenue") is not None
        )
        ReportEvent.objects.update_or_create(
            instrument=instrument,
            report_type=report_type,
            period_end=period_end,
            defaults={
                **data,
                "status": (
                    ReportEvent.Status.RELEASED
                    if released
                    else ReportEvent.Status.SCHEDULED
                ),
                "source": "eastmoney",
            },
        )
        count += 1
    return {"instrument": instrument.id, "count": count}


def report_trend(instrument):
    events = list(instrument.reports.order_by("-period_end")[:4])
    released = [
        event for event in events if event.status == ReportEvent.Status.RELEASED
    ]
    revenue_yoy = [
        D(event.revenue_yoy) for event in released if event.revenue_yoy is not None
    ]
    profit_yoy = [
        D(event.profit_yoy) for event in released if event.profit_yoy is not None
    ]
    avg_revenue = sum(revenue_yoy, D("0")) / len(revenue_yoy) if revenue_yoy else None
    avg_profit = sum(profit_yoy, D("0")) / len(profit_yoy) if profit_yoy else None
    if avg_profit is not None and avg_revenue is not None:
        if avg_profit > 0 and avg_revenue > 0:
            direction = "向好"
        elif avg_profit < 0 or avg_revenue < 0:
            direction = "承压"
        else:
            direction = "分化"
    else:
        direction = "数据不足"
    upcoming = (
        instrument.reports.filter(status=ReportEvent.Status.SCHEDULED)
        .order_by("disclosure_date")
        .first()
    )
    return {
        "direction": direction,
        "avg_revenue_yoy": avg_revenue,
        "avg_profit_yoy": avg_profit,
        "latest_reports": events,
        "upcoming": upcoming,
    }


def sync_ipo_calendar():
    rows = fetch_ipo_calendar(100)
    count = 0
    for row in rows:
        if not row.get("apply_date"):
            continue
        IPOCalendar.objects.update_or_create(
            code=row["code"],
            apply_date=row["apply_date"],
            defaults={
                "name": row["name"],
                "market": row.get("market", ""),
                "apply_code": row.get("apply_code", ""),
                "listing_date": row.get("listing_date"),
                "issue_price": row.get("issue_price"),
                "issue_num": row.get("issue_num"),
                "online_apply_upper": row.get("online_apply_upper"),
                "requirement_market_value": row.get("requirement_market_value"),
                "status": row.get("status", ""),
                "source": "eastmoney",
            },
        )
        count += 1
    return {"count": count}


def ipo_list(owner):
    rows = list(IPOCalendar.objects.all()[:100])
    stock_market_value = sum(
        (
            D(row["market_value"])
            for row in holdings(owner)
            if row["instrument_type"] == Instrument.Type.STOCK
        ),
        D("0"),
    )
    result = []
    for row in rows:
        required = (
            D(row.requirement_market_value)
            if row.requirement_market_value is not None
            else None
        )
        required_yuan = (
            required * 10000 if required is not None and required < 100000 else required
        )
        eligible = (
            None if required_yuan is None else stock_market_value >= required_yuan
        )
        result.append(
            {
                "id": row.id,
                "code": row.code,
                "name": row.name,
                "market": row.market,
                "apply_code": row.apply_code,
                "apply_date": row.apply_date,
                "listing_date": row.listing_date,
                "issue_price": row.issue_price,
                "issue_num": row.issue_num,
                "online_apply_upper": row.online_apply_upper,
                "requirement_market_value": required_yuan,
                "status": row.status,
                "eligible": eligible,
                "stock_market_value": stock_market_value,
            }
        )
    return result


def grid_plan(instrument):
    bars = list(instrument.bars.order_by("-trade_date")[:60])
    if len(bars) < 20:
        return None
    bars.reverse()
    highs = [D(bar.high) for bar in bars]
    lows = [D(bar.low) for bar in bars]
    closes = [D(bar.close) for bar in bars]
    high = max(highs)
    low = min(lows)
    current = closes[-1]
    if high <= low or current <= 0:
        return None
    step = (high - low) / 5
    buy_price = max(low, current - step)
    sell_price = min(high, current + step)
    if sell_price <= buy_price:
        return None
    bands = [money(low + step * index) for index in range(6)]
    return {
        "low": low,
        "high": high,
        "current": current,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "step": step,
        "bands": bands,
        "potential_reduction_pct": (
            (sell_price - buy_price) / buy_price * 100
        ).quantize(Decimal("0.01")),
        "note": "高抛低吸/网格仅做成本测算，不构成交易建议",
    }


def analyze_signals(instrument):
    data = indicator_data(instrument, limit=180)
    if not data.get("latest"):
        sync_instrument(instrument)
        data = indicator_data(instrument, limit=180)
    latest = data.get("latest") or {}
    signals = data.get("signals") or {}
    close = D(latest.get("close")) if latest.get("close") is not None else D("0")
    ma20 = D(latest.get("ma20")) if latest.get("ma20") is not None else None
    ma60 = D(latest.get("ma60")) if latest.get("ma60") is not None else None
    rsi6 = D(latest.get("rsi6")) if latest.get("rsi6") is not None else None
    kdj_j = D(latest.get("kdj_j")) if latest.get("kdj_j") is not None else None
    boll_upper = (
        D(latest.get("boll_upper")) if latest.get("boll_upper") is not None else None
    )
    macd_ok = (
        latest.get("macd_dif") is not None
        and latest.get("macd_dea") is not None
        and D(latest["macd_dif"]) >= D(latest["macd_dea"])
    )
    results = []
    today = today_local()
    if (
        close > 0
        and ma20
        and close > ma20 * Decimal("0.97")
        and close < ma20 * Decimal("1.03")
    ):
        if (ma60 is None or close > ma60) and (
            macd_ok
            or (latest.get("kdj_k") is not None and D(latest["kdj_k"]) < 30)
            or signals.get("macd_golden_cross")
        ):
            results.append(
                {
                    "signal_type": StrategySignal.Type.BUY_POINT,
                    "price_low": close * Decimal("0.98"),
                    "price_high": close * Decimal("1.01"),
                    "confidence": 70,
                    "reasons": [
                        "回踩 MA20 附近",
                        "趋势未破 MA60",
                        "MACD/KDJ 出现低吸条件",
                    ],
                    "metrics": _jsonable(latest),
                }
            )
    if close > 0 and (
        (boll_upper and close >= boll_upper * Decimal("0.99"))
        or (rsi6 is not None and rsi6 > 72)
        or (kdj_j is not None and kdj_j > 100)
    ):
        if signals.get("macd_death_cross") or (ma20 and close < ma20):
            results.append(
                {
                    "signal_type": StrategySignal.Type.SELL_POINT,
                    "price_low": close * Decimal("0.98"),
                    "price_high": close * Decimal("1.05"),
                    "confidence": 65,
                    "reasons": ["触及布林上轨/超买", "MACD 死叉或跌破 MA20"],
                    "metrics": _jsonable(latest),
                }
            )
    if (
        instrument.dividend_yield is not None
        and D(instrument.dividend_yield) >= 3
        and (ma60 is None or close > ma60)
    ):
        results.append(
            {
                "signal_type": StrategySignal.Type.DIVIDEND,
                "price_low": close * Decimal("0.95"),
                "price_high": close * Decimal("1.02"),
                "confidence": 60,
                "reasons": [f"股息率 {instrument.dividend_yield}%", "趋势在 MA60 上方"],
                "metrics": {"dividend_yield": str(instrument.dividend_yield)},
            }
        )
    grid = grid_plan(instrument)
    if grid:
        results.append(
            {
                "signal_type": StrategySignal.Type.GRID,
                "price_low": grid["buy_price"],
                "price_high": grid["sell_price"],
                "confidence": 50,
                "reasons": ["基于近 60 日高低点的网格测算"],
                "metrics": _jsonable(grid),
            }
        )
    saved = []
    for item in results:
        signal, _ = StrategySignal.objects.update_or_create(
            owner=instrument.owner,
            instrument=instrument,
            trade_date=today,
            signal_type=item["signal_type"],
            defaults={
                "price_low": item["price_low"],
                "price_high": item["price_high"],
                "confidence": item["confidence"],
                "reasons": item["reasons"],
                "metrics": item["metrics"],
            },
        )
        saved.append(signal)
    return saved
