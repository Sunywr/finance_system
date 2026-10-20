from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    HoldingView,
    IPOView,
    InstrumentViewSet,
    MarketRegimeView,
    MarketSyncView,
    ScreenerPresetViewSet,
    ScreenerRunViewSet,
    StrategySignalViewSet,
    TradeViewSet,
    WatchlistViewSet,
)

router = DefaultRouter()
router.register("instruments", InstrumentViewSet, basename="instrument")
router.register("trades", TradeViewSet, basename="trade")
router.register("watchlist", WatchlistViewSet, basename="watchlist")
router.register("screener/presets", ScreenerPresetViewSet, basename="screener-preset")
router.register("screener/runs", ScreenerRunViewSet, basename="screener-run")
router.register("signals", StrategySignalViewSet, basename="strategy-signal")

urlpatterns = [
    path("holdings", HoldingView.as_view(), name="holdings"),
    path("market/sync", MarketSyncView.as_view(), name="market-sync"),
    path("market/regime", MarketRegimeView.as_view(), name="market-regime"),
    path("ipo", IPOView.as_view(), name="ipo-calendar"),
    path("", include(router.urls)),
]
