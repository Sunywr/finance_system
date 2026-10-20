from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Instrument,
    IPOCalendar,
    MarketRegime,
    ScreenerPreset,
    ScreenerRun,
    StrategySignal,
    Trade,
    Watchlist,
)
from .serializers import (
    DailyBarSerializer,
    IndicatorSnapshotSerializer,
    InstrumentSerializer,
    IPOItemSerializer,
    MarketRegimeSerializer,
    ReportEventSerializer,
    ScreenerPresetSerializer,
    ScreenerRunCreateSerializer,
    ScreenerRunSerializer,
    StrategySignalSerializer,
    TradeCreateSerializer,
    TradeSerializer,
    WatchlistSerializer,
)
from .services import (
    analyze_signals,
    ensure_presets,
    grid_plan,
    indicator_data,
    ipo_list,
    latest_price,
    portfolio_summary,
    refresh_market_regime,
    report_trend,
    sync_all_market_data,
    sync_instrument,
    sync_ipo_calendar,
    sync_reports,
)


@extend_schema_view(
    list=extend_schema(tags=["investments"]),
    create=extend_schema(tags=["investments"]),
    retrieve=extend_schema(tags=["investments"]),
    update=extend_schema(tags=["investments"]),
    partial_update=extend_schema(tags=["investments"]),
    destroy=extend_schema(tags=["investments"]),
)
class InstrumentViewSet(viewsets.ModelViewSet):
    serializer_class = InstrumentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["type", "exchange", "valuation_mode", "is_active"]
    search_fields = ["symbol", "name", "industry"]
    ordering_fields = ["symbol", "name", "created_at"]

    def get_queryset(self):
        return Instrument.objects.filter(owner=self.request.user).select_related("quote")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @extend_schema(summary="标的行情", tags=["investments"])
    @action(detail=True, methods=["get"])
    def quote(self, request, pk=None):
        instrument = self.get_object()
        quote = getattr(instrument, "quote", None)
        price, source, stale = latest_price(instrument)
        return Response(
            {
                "instrument": instrument.id,
                "price": price,
                "source": source,
                "is_stale": stale,
                "quote": InstrumentSerializer(instrument).data.get("quote"),
            }
        )

    @extend_schema(summary="日线数据", tags=["investments"], responses=DailyBarSerializer(many=True))
    @action(detail=True, methods=["get"])
    def bars(self, request, pk=None):
        instrument = self.get_object()
        limit = min(int(request.query_params.get("limit", 300)), 1000)
        bars = instrument.bars.order_by("-trade_date")[:limit]
        bars = sorted(bars, key=lambda item: item.trade_date)
        return Response(DailyBarSerializer(bars, many=True).data)

    @extend_schema(summary="技术指标", tags=["investments"])
    @action(detail=True, methods=["get"])
    def indicators(self, request, pk=None):
        instrument = self.get_object()
        limit = min(int(request.query_params.get("limit", 180)), 500)
        return Response(indicator_data(instrument, limit=limit))

    @extend_schema(summary="同步标行情", tags=["investments"])
    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        instrument = self.get_object()
        return Response(sync_instrument(instrument))

    @extend_schema(summary="定期报告与风向", tags=["investment-intelligence"])
    @action(detail=True, methods=["get"], url_path="reports")
    def reports(self, request, pk=None):
        instrument = self.get_object()
        trend = report_trend(instrument)
        return Response(
            {
                "trend": {
                    "direction": trend["direction"],
                    "avg_revenue_yoy": trend["avg_revenue_yoy"],
                    "avg_profit_yoy": trend["avg_profit_yoy"],
                },
                "upcoming": ReportEventSerializer(trend["upcoming"]).data if trend["upcoming"] else None,
                "items": ReportEventSerializer(instrument.reports.all(), many=True).data,
            }
        )

    @extend_schema(summary="同步定期报告", tags=["investment-intelligence"])
    @action(detail=True, methods=["post"], url_path="sync-reports")
    def sync_reports_action(self, request, pk=None):
        instrument = self.get_object()
        try:
            return Response(sync_reports(instrument))
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

    @extend_schema(summary="策略信号", tags=["investment-intelligence"])
    @action(detail=True, methods=["get", "post"], url_path="signals")
    def signals(self, request, pk=None):
        instrument = self.get_object()
        if request.method == "POST":
            try:
                saved = analyze_signals(instrument)
                return Response(StrategySignalSerializer(saved, many=True).data, status=status.HTTP_201_CREATED)
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(
            StrategySignalSerializer(instrument.signals.order_by("-trade_date", "-confidence")[:30], many=True).data
        )

    @extend_schema(summary="网格降成本测算", tags=["investment-intelligence"])
    @action(detail=True, methods=["get"], url_path="grid-plan")
    def grid_plan_action(self, request, pk=None):
        instrument = self.get_object()
        plan = grid_plan(instrument)
        if not plan:
            return Response({"detail": "日线不足，无法计算网格"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(plan)


@extend_schema_view(
    list=extend_schema(tags=["trades"]),
    create=extend_schema(tags=["trades"]),
    retrieve=extend_schema(tags=["trades"]),
)
class TradeViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filterset_fields = ["account", "instrument", "side", "operation"]
    ordering_fields = ["trade_date", "amount"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return Trade.objects.filter(owner=self.request.user).select_related(
            "account", "instrument", "transaction"
        )

    def get_serializer_class(self):
        if self.action == "create":
            return TradeCreateSerializer
        return TradeSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trade = serializer.save()
        return Response(TradeSerializer(trade).data, status=status.HTTP_201_CREATED)


class HoldingView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="持仓与收益", tags=["investments"])
    def get(self, request):
        account = request.query_params.get("account")
        data = portfolio_summary(request.user)
        if account:
            data["items"] = [row for row in data["items"] if str(row["account"]) == str(account)]
            invested = sum((row["total_buy"] for row in data["items"]), 0)
            total_pnl = sum((row["total_pnl"] for row in data["items"]), 0)
            data["totals"] = {
                "cost": sum((row["cost"] for row in data["items"]), 0),
                "market_value": sum((row["market_value"] for row in data["items"]), 0),
                "unrealized_pnl": sum((row["unrealized_pnl"] for row in data["items"]), 0),
                "realized_pnl": sum((row["realized_pnl"] for row in data["items"]), 0),
                "dividends": sum((row["dividends"] for row in data["items"]), 0),
                "total_pnl": total_pnl,
                "invested": invested,
                "return_rate": (total_pnl / invested * 100) if invested else 0,
                "count": len(data["items"]),
            }
        return Response(data)


@extend_schema_view(
    list=extend_schema(tags=["watchlist"]),
    create=extend_schema(tags=["watchlist"]),
    retrieve=extend_schema(tags=["watchlist"]),
    update=extend_schema(tags=["watchlist"]),
    partial_update=extend_schema(tags=["watchlist"]),
    destroy=extend_schema(tags=["watchlist"]),
)
class WatchlistViewSet(viewsets.ModelViewSet):
    serializer_class = WatchlistSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["instrument"]

    def get_queryset(self):
        return Watchlist.objects.filter(owner=self.request.user).select_related("instrument__quote")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class MarketSyncView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="同步全部行情", tags=["investments"])
    def post(self, request):
        return Response(sync_all_market_data(request.user))


class MarketRegimeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="市场风向", tags=["investment-intelligence"], responses=MarketRegimeSerializer)
    def get(self, request):
        regime = MarketRegime.objects.filter(owner=request.user).first()
        return Response(MarketRegimeSerializer(regime).data if regime else None)

    @extend_schema(summary="刷新市场风向", tags=["investment-intelligence"], responses=MarketRegimeSerializer)
    def post(self, request):
        try:
            regime = refresh_market_regime(request.user)
            return Response(MarketRegimeSerializer(regime).data)
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


@extend_schema_view(
    list=extend_schema(tags=["investment-intelligence"]),
    create=extend_schema(tags=["investment-intelligence"]),
    retrieve=extend_schema(tags=["investment-intelligence"]),
    update=extend_schema(tags=["investment-intelligence"]),
    partial_update=extend_schema(tags=["investment-intelligence"]),
    destroy=extend_schema(tags=["investment-intelligence"]),
)
class ScreenerPresetViewSet(viewsets.ModelViewSet):
    serializer_class = ScreenerPresetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ScreenerPreset.objects.filter(owner=self.request.user)

    def list(self, request, *args, **kwargs):
        ensure_presets(request.user)
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@extend_schema_view(
    list=extend_schema(tags=["investment-intelligence"]),
    retrieve=extend_schema(tags=["investment-intelligence"]),
    create=extend_schema(tags=["investment-intelligence"]),
)
class ScreenerRunViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return ScreenerRun.objects.filter(owner=self.request.user).prefetch_related("results").select_related("preset")

    def get_serializer_class(self):
        if self.action == "create":
            return ScreenerRunCreateSerializer
        return ScreenerRunSerializer

    def create(self, request, *args, **kwargs):
        ensure_presets(request.user)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = serializer.save()
        return Response(ScreenerRunSerializer(run).data, status=status.HTTP_201_CREATED)


class IPOView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="打新日历与资格", tags=["investment-intelligence"], responses=IPOItemSerializer(many=True))
    def get(self, request):
        rows = ipo_list(request.user)
        return Response(IPOItemSerializer(rows, many=True).data)

    @extend_schema(summary="同步打新日历", tags=["investment-intelligence"])
    def post(self, request):
        try:
            return Response(sync_ipo_calendar())
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)


@extend_schema_view(
    list=extend_schema(tags=["investment-intelligence"]),
    retrieve=extend_schema(tags=["investment-intelligence"]),
)
class StrategySignalViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StrategySignalSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["instrument", "signal_type", "trade_date"]

    def get_queryset(self):
        return StrategySignal.objects.filter(owner=self.request.user).select_related("instrument")
