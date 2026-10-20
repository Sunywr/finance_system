from django.contrib import admin

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
    TradingDay,
    Watchlist,
)

admin.site.register(
    [
        Instrument,
        Trade,
        Quote,
        DailyBar,
        IndicatorSnapshot,
        Watchlist,
        TradingDay,
        ReportEvent,
        MarketRegime,
        ScreenerPreset,
        ScreenerRun,
        ScreenerResult,
        IPOCalendar,
        StrategySignal,
    ]
)
