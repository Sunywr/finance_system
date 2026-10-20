from rest_framework import serializers

from apps.accounts.models import Account

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
    Watchlist,
)
from .services import create_trade, latest_price


class QuoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quote
        fields = [
            "price",
            "prev_close",
            "change_pct",
            "open",
            "high",
            "low",
            "volume",
            "amount",
            "pe",
            "pb",
            "market_cap",
            "dividend_yield",
            "source",
            "is_stale",
            "updated_at",
        ]


class InstrumentSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    exchange_label = serializers.CharField(source="get_exchange_display", read_only=True)
    quote = serializers.SerializerMethodField()
    latest_price = serializers.SerializerMethodField()

    class Meta:
        model = Instrument
        fields = [
            "id",
            "symbol",
            "name",
            "type",
            "type_label",
            "exchange",
            "exchange_label",
            "industry",
            "valuation_mode",
            "annual_rate",
            "dividend_yield",
            "is_active",
            "data_source",
            "note",
            "quote",
            "latest_price",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "quote", "latest_price", "created_at", "updated_at"]

    def get_quote(self, obj):
        quote = getattr(obj, "quote", None)
        return QuoteSerializer(quote).data if quote else None

    def get_latest_price(self, obj):
        return latest_price(obj)[0]

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            symbol = attrs.get("symbol", getattr(self.instance, "symbol", None))
            type_value = attrs.get("type", getattr(self.instance, "type", None))
            qs = Instrument.objects.filter(owner=request.user, symbol=symbol, type=type_value)
            if self.instance:
                qs = qs.exclude(id=self.instance.id)
            if qs.exists():
                raise serializers.ValidationError("同一代码和类型的标的已存在")
        if attrs.get("type") == Instrument.Type.WEALTH and "valuation_mode" not in attrs:
            attrs["valuation_mode"] = Instrument.ValuationMode.ACCRUAL
        return attrs


class TradeSerializer(serializers.ModelSerializer):
    instrument_symbol = serializers.CharField(source="instrument.symbol", read_only=True)
    instrument_name = serializers.CharField(source="instrument.name", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    side_label = serializers.CharField(source="get_side_display", read_only=True)
    operation_label = serializers.CharField(source="get_operation_display", read_only=True)
    transaction_no = serializers.CharField(source="transaction.txn_no", read_only=True)

    class Meta:
        model = Trade
        fields = [
            "id",
            "account",
            "account_name",
            "instrument",
            "instrument_symbol",
            "instrument_name",
            "transaction",
            "transaction_no",
            "side",
            "side_label",
            "operation",
            "operation_label",
            "trade_date",
            "quantity",
            "price",
            "fee",
            "amount",
            "realized_pnl",
            "note",
            "created_at",
        ]
        read_only_fields = ["id", "transaction", "amount", "realized_pnl", "created_at"]


class TradeCreateSerializer(serializers.Serializer):
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none())
    instrument = serializers.PrimaryKeyRelatedField(queryset=Instrument.objects.none())
    side = serializers.ChoiceField(choices=Trade.Side.choices)
    operation = serializers.ChoiceField(choices=Trade.Operation.choices, required=False, allow_blank=True)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=6, required=False, default=0)
    price = serializers.DecimalField(max_digits=18, decimal_places=4, required=False, default=0)
    fee = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=0)
    trade_date = serializers.DateTimeField(required=False)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            user = request.user
            self.fields["account"].queryset = Account.objects.filter(
                owner=user,
                is_active=True,
                type__in=[
                    Account.Type.STOCK,
                    Account.Type.WEALTH,
                    Account.Type.ALIPAY,
                    Account.Type.WECHAT,
                ],
            )
            self.fields["instrument"].queryset = Instrument.objects.filter(owner=user, is_active=True)

    def validate(self, attrs):
        side = attrs["side"]
        if side == Trade.Side.DIVIDEND:
            if not attrs.get("amount") and not (attrs.get("quantity") and attrs.get("price")):
                raise serializers.ValidationError({"amount": "分红需要填写金额"})
        else:
            if not attrs.get("quantity") or not attrs.get("price"):
                raise serializers.ValidationError({"quantity": "买入/卖出需要填写数量和价格"})
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        return create_trade(owner=request.user, **validated_data)


class WatchlistSerializer(serializers.ModelSerializer):
    instrument_symbol = serializers.CharField(source="instrument.symbol", read_only=True)
    instrument_name = serializers.CharField(source="instrument.name", read_only=True)
    latest_price = serializers.SerializerMethodField()

    class Meta:
        model = Watchlist
        fields = [
            "id",
            "instrument",
            "instrument_symbol",
            "instrument_name",
            "note",
            "target_buy_price",
            "target_sell_price",
            "latest_price",
            "created_at",
        ]
        read_only_fields = ["id", "latest_price", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["instrument"].queryset = Instrument.objects.filter(owner=request.user, is_active=True)

    def get_latest_price(self, obj):
        return latest_price(obj.instrument)[0]


class DailyBarSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyBar
        fields = ["trade_date", "open", "high", "low", "close", "volume", "amount"]


class IndicatorSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorSnapshot
        fields = [
            "trade_date",
            "ma5",
            "ma10",
            "ma20",
            "ma60",
            "macd_dif",
            "macd_dea",
            "macd_hist",
            "kdj_k",
            "kdj_d",
            "kdj_j",
            "rsi6",
            "rsi12",
            "rsi24",
            "boll_upper",
            "boll_mid",
            "boll_lower",
            "signals",
        ]


class ReportEventSerializer(serializers.ModelSerializer):
    report_type_label = serializers.CharField(source="get_report_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ReportEvent
        fields = [
            "id",
            "report_type",
            "report_type_label",
            "period_end",
            "disclosure_date",
            "actual_date",
            "status",
            "status_label",
            "revenue",
            "net_profit",
            "revenue_yoy",
            "profit_yoy",
            "roe",
            "eps",
            "summary",
            "source",
        ]


class MarketRegimeSerializer(serializers.ModelSerializer):
    regime_label = serializers.CharField(source="get_regime_display", read_only=True)

    class Meta:
        model = MarketRegime
        fields = [
            "id",
            "trade_date",
            "regime",
            "regime_label",
            "score",
            "index_symbol",
            "index_close",
            "ma20",
            "ma60",
            "advance_count",
            "decline_count",
            "breadth_ratio",
            "sectors",
            "explanation",
            "created_at",
        ]


class ScreenerPresetSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScreenerPreset
        fields = ["id", "name", "description", "criteria", "is_default", "created_at"]
        read_only_fields = ["id", "created_at"]


class ScreenerResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScreenerResult
        fields = [
            "id",
            "symbol",
            "name",
            "industry",
            "price",
            "change_pct",
            "pe",
            "pb",
            "market_cap",
            "dividend_yield",
            "score",
            "reasons",
            "metrics",
        ]


class ScreenerRunSerializer(serializers.ModelSerializer):
    preset_name = serializers.CharField(source="preset.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    results = ScreenerResultSerializer(many=True, read_only=True)

    class Meta:
        model = ScreenerRun
        fields = [
            "id",
            "preset",
            "preset_name",
            "criteria",
            "status",
            "status_label",
            "universe_size",
            "result_count",
            "error",
            "started_at",
            "finished_at",
            "results",
        ]


class ScreenerRunCreateSerializer(serializers.Serializer):
    preset = serializers.PrimaryKeyRelatedField(
        queryset=ScreenerPreset.objects.none(), required=False, allow_null=True
    )
    criteria = serializers.JSONField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["preset"].queryset = ScreenerPreset.objects.filter(owner=request.user)

    def create(self, validated_data):
        request = self.context["request"]
        from .services import run_screener

        return run_screener(
            owner=request.user,
            criteria=validated_data.get("criteria"),
            preset=validated_data.get("preset"),
        )


class IPOItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()
    market = serializers.CharField()
    apply_code = serializers.CharField()
    apply_date = serializers.DateField(allow_null=True)
    listing_date = serializers.DateField(allow_null=True)
    issue_price = serializers.DecimalField(max_digits=18, decimal_places=4, allow_null=True)
    issue_num = serializers.DecimalField(max_digits=24, decimal_places=2, allow_null=True)
    online_apply_upper = serializers.DecimalField(max_digits=24, decimal_places=2, allow_null=True)
    requirement_market_value = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    status = serializers.CharField()
    eligible = serializers.BooleanField(allow_null=True)
    stock_market_value = serializers.DecimalField(max_digits=18, decimal_places=2)


class StrategySignalSerializer(serializers.ModelSerializer):
    signal_type_label = serializers.CharField(source="get_signal_type_display", read_only=True)
    instrument_symbol = serializers.CharField(source="instrument.symbol", read_only=True)
    instrument_name = serializers.CharField(source="instrument.name", read_only=True)

    class Meta:
        model = StrategySignal
        fields = [
            "id",
            "instrument",
            "instrument_symbol",
            "instrument_name",
            "trade_date",
            "signal_type",
            "signal_type_label",
            "price_low",
            "price_high",
            "confidence",
            "reasons",
            "metrics",
            "created_at",
        ]

