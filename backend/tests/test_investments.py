from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.models import Account
from apps.investments.models import DailyBar, Instrument, IPOCalendar, Quote, ReportEvent
from apps.investments.services import (
    analyze_signals,
    create_trade,
    grid_plan,
    holdings,
    indicator_data,
    ipo_list,
    portfolio_summary,
    report_trend,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def stock_account(user):
    return Account.objects.create(
        owner=user, name="股票账户", type=Account.Type.STOCK, opening_balance="100000"
    )


@pytest.fixture
def stock(user):
    return Instrument.objects.create(
        owner=user, symbol="600000", name="测试股票", type=Instrument.Type.STOCK,
        exchange=Instrument.Exchange.SH, valuation_mode=Instrument.ValuationMode.MARKET,
    )


def test_weighted_average_cost_and_realized_pnl(user, categories, stock_account, stock):
    Quote.objects.create(instrument=stock, price="12", prev_close="11", change_pct="9.09")
    create_trade(
        owner=user, account=stock_account, instrument=stock, side="BUY", operation="OPEN",
        quantity="100", price="10", fee="5", trade_date=timezone.now() - timedelta(days=10),
    )
    create_trade(
        owner=user, account=stock_account, instrument=stock, side="SELL", operation="REDUCE",
        quantity="40", price="12", fee="5", trade_date=timezone.now() - timedelta(days=5),
    )
    rows = holdings(user)
    assert len(rows) == 1
    row = rows[0]
    assert row["quantity"] == 60
    assert row["cost"] == 603
    assert row["realized_pnl"] == 73
    assert row["last_price"] == 12
    assert row["since_last_trade_return"] == 0
    summary = portfolio_summary(user)
    assert summary["totals"]["market_value"] == 720
    assert summary["totals"]["total_pnl"] == 190


def _bars(stock, days=120):
    today = timezone.localdate()
    bars = []
    for index in range(days):
        price = 10 + index * 0.05
        bars.append(
            DailyBar(
                instrument=stock,
                trade_date=today - timedelta(days=days - 1 - index),
                open=price,
                high=price + 0.2,
                low=price - 0.2,
                close=price,
                volume=1000 + index,
                amount=10000,
            )
        )
    DailyBar.objects.bulk_create(bars)
    return bars


def test_indicator_calculation(user, stock):
    _bars(stock)
    data = indicator_data(stock, limit=10)
    assert len(data["items"]) == 10
    latest = data["latest"]
    assert latest["ma20"] is not None
    assert latest["macd_dif"] is not None
    assert latest["kdj_k"] is not None
    assert "above_ma20" in data["signals"]


def test_grid_and_signals(user, stock):
    _bars(stock)
    stock.dividend_yield = "4.0"
    stock.save(update_fields=["dividend_yield"])
    plan = grid_plan(stock)
    assert plan is not None
    assert plan["buy_price"] < plan["sell_price"]
    saved = analyze_signals(stock)
    types = {signal.signal_type for signal in saved}
    assert "GRID" in types
    assert "DIVIDEND" in types


def test_report_trend(user, stock):
    ReportEvent.objects.create(
        instrument=stock,
        report_type="Q1",
        period_end=timezone.localdate() - timedelta(days=120),
        status=ReportEvent.Status.RELEASED,
        revenue_yoy="10",
        profit_yoy="12",
    )
    ReportEvent.objects.create(
        instrument=stock,
        report_type="H1",
        period_end=timezone.localdate() - timedelta(days=30),
        status=ReportEvent.Status.RELEASED,
        revenue_yoy="8",
        profit_yoy="9",
    )
    trend = report_trend(stock)
    assert trend["direction"] == "向好"
    assert trend["avg_profit_yoy"] == 10.5


def test_ipo_list_eligibility(user):
    IPOCalendar.objects.create(
        code="301999",
        name="测试新股",
        apply_date=timezone.localdate(),
        requirement_market_value="10000",
    )
    rows = ipo_list(user)
    assert rows
    assert rows[0]["eligible"] is False
    assert rows[0]["stock_market_value"] == 0
