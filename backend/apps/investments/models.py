from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import OwnedModel, TimeStampedModel
from apps.common.utils.money import D


class Instrument(OwnedModel):
    class Type(models.TextChoices):
        STOCK = "STOCK", "股票"
        ETF = "ETF", "场内基金"
        OTC_FUND = "OTC_FUND", "场外基金"
        WEALTH = "WEALTH", "理财"
        CONVERTIBLE_BOND = "CONVERTIBLE_BOND", "可转债"
        GOLD = "GOLD", "黄金"

    class Exchange(models.TextChoices):
        SH = "SH", "上交所"
        SZ = "SZ", "深交所"
        BJ = "BJ", "北交所"
        OTC = "OTC", "场外"

    class ValuationMode(models.TextChoices):
        MARKET = "MARKET", "行情估值"
        ACCRUAL = "ACCRUAL", "收益累计"
        YIELD_PER_10000 = "YIELD_PER_10000", "万份收益"
        MANUAL = "MANUAL", "手工估值"

    symbol = models.CharField(max_length=32, verbose_name="代码")
    name = models.CharField(max_length=80, verbose_name="名称")
    type = models.CharField(
        max_length=20, choices=Type.choices, verbose_name="标的类型"
    )
    exchange = models.CharField(
        max_length=10,
        choices=Exchange.choices,
        default=Exchange.SH,
        verbose_name="市场",
    )
    industry = models.CharField(
        max_length=60, blank=True, default="", verbose_name="行业"
    )
    valuation_mode = models.CharField(
        max_length=20,
        choices=ValuationMode.choices,
        default=ValuationMode.MARKET,
        verbose_name="估值方式",
    )
    annual_rate = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="年化收益率(%)",
    )
    dividend_yield = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True, verbose_name="股息率(%)"
    )
    is_active = models.BooleanField(default=True, verbose_name="启用")
    data_source = models.CharField(
        max_length=30, default="eastmoney", verbose_name="数据源"
    )
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["type", "symbol"]
        verbose_name = "投资标的"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "symbol", "type"], name="uniq_instrument"
            )
        ]
        indexes = [models.Index(fields=["owner", "type", "is_active"])]

    def __str__(self):
        return f"{self.symbol} {self.name}"


class Trade(OwnedModel):
    legacy_batch = models.ForeignKey(
        "legacy.MigrationBatch",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="imported_trades",
    )

    class Side(models.TextChoices):
        BUY = "BUY", "买入"
        SELL = "SELL", "卖出"
        DIVIDEND = "DIVIDEND", "分红"

    class Operation(models.TextChoices):
        OPEN = "OPEN", "建仓"
        ADD = "ADD", "加仓"
        REDUCE = "REDUCE", "减仓"
        DIVIDEND = "DIVIDEND", "分红"

    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="trades",
        verbose_name="投资账户",
    )
    instrument = models.ForeignKey(
        Instrument, on_delete=models.PROTECT, related_name="trades", verbose_name="标的"
    )
    transaction = models.OneToOneField(
        "ledger.Transaction",
        on_delete=models.PROTECT,
        related_name="trade",
        verbose_name="资金流水",
        null=True,
        blank=True,
    )
    side = models.CharField(max_length=20, choices=Side.choices, verbose_name="方向")
    operation = models.CharField(
        max_length=20, choices=Operation.choices, verbose_name="操作"
    )
    trade_date = models.DateTimeField(default=timezone.now, verbose_name="交易时间")
    quantity = models.DecimalField(
        max_digits=24, decimal_places=8, default=D("0"), verbose_name="数量"
    )
    price = models.DecimalField(
        max_digits=24, decimal_places=8, default=D("0"), verbose_name="价格/净值"
    )
    fee = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="费用"
    )
    amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="金额"
    )
    realized_pnl = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="已实现盈亏",
    )
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["-trade_date", "-id"]
        verbose_name = "投资交易"
        verbose_name_plural = verbose_name
        indexes = [models.Index(fields=["owner", "account", "trade_date"])]

    def __str__(self):
        return f"{self.instrument} {self.side} {self.quantity}"


class Quote(TimeStampedModel):
    instrument = models.OneToOneField(
        Instrument, on_delete=models.CASCADE, related_name="quote", verbose_name="标的"
    )
    price = models.DecimalField(
        max_digits=18, decimal_places=4, default=D("0"), verbose_name="最新价"
    )
    prev_close = models.DecimalField(
        max_digits=18, decimal_places=4, default=D("0"), verbose_name="昨收"
    )
    change_pct = models.DecimalField(
        max_digits=12, decimal_places=4, default=D("0"), verbose_name="涨跌幅(%)"
    )
    open = models.DecimalField(
        max_digits=18, decimal_places=4, default=D("0"), verbose_name="开盘"
    )
    high = models.DecimalField(
        max_digits=18, decimal_places=4, default=D("0"), verbose_name="最高"
    )
    low = models.DecimalField(
        max_digits=18, decimal_places=4, default=D("0"), verbose_name="最低"
    )
    volume = models.DecimalField(
        max_digits=24, decimal_places=2, default=D("0"), verbose_name="成交量"
    )
    amount = models.DecimalField(
        max_digits=24, decimal_places=2, default=D("0"), verbose_name="成交额"
    )
    pe = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name="市盈率"
    )
    pb = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name="市净率"
    )
    market_cap = models.DecimalField(
        max_digits=24, decimal_places=2, null=True, blank=True, verbose_name="总市值"
    )
    dividend_yield = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="股息率(%)"
    )
    source = models.CharField(max_length=30, default="eastmoney", verbose_name="来源")
    is_stale = models.BooleanField(default=False, verbose_name="已过期")

    class Meta:
        verbose_name = "最新行情"
        verbose_name_plural = verbose_name


class DailyBar(TimeStampedModel):
    instrument = models.ForeignKey(
        Instrument, on_delete=models.CASCADE, related_name="bars", verbose_name="标的"
    )
    trade_date = models.DateField(verbose_name="交易日")
    open = models.DecimalField(max_digits=24, decimal_places=8, default=D("0"))
    high = models.DecimalField(max_digits=24, decimal_places=8, default=D("0"))
    low = models.DecimalField(max_digits=24, decimal_places=8, default=D("0"))
    close = models.DecimalField(max_digits=24, decimal_places=8, default=D("0"))
    volume = models.DecimalField(max_digits=24, decimal_places=2, default=D("0"))
    amount = models.DecimalField(max_digits=24, decimal_places=2, default=D("0"))

    class Meta:
        ordering = ["instrument", "trade_date"]
        verbose_name = "日线"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "trade_date"], name="uniq_daily_bar"
            )
        ]
        indexes = [models.Index(fields=["instrument", "trade_date"])]


class IndicatorSnapshot(TimeStampedModel):
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="indicators",
        verbose_name="标的",
    )
    trade_date = models.DateField(verbose_name="交易日")
    ma5 = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    ma10 = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    ma20 = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    ma60 = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    macd_dif = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    macd_dea = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    macd_hist = models.DecimalField(
        max_digits=18, decimal_places=6, null=True, blank=True
    )
    kdj_k = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    kdj_d = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    kdj_j = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    rsi6 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    rsi12 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    rsi24 = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    boll_upper = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    boll_mid = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    boll_lower = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    signals = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-trade_date"]
        verbose_name = "技术指标"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "trade_date"], name="uniq_indicator"
            )
        ]


class Watchlist(OwnedModel):
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="watchlist_entries",
        verbose_name="标的",
    )
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")
    target_buy_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="目标买入价",
    )
    target_sell_price = models.DecimalField(
        max_digits=18,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="目标卖出价",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "自选"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "instrument"], name="uniq_watchlist"
            )
        ]


class TradingDay(models.Model):
    trade_date = models.DateField(unique=True, verbose_name="日期")
    is_open = models.BooleanField(default=True, verbose_name="是否交易日")

    class Meta:
        ordering = ["trade_date"]
        verbose_name = "交易日"
        verbose_name_plural = verbose_name


class ReportEvent(TimeStampedModel):
    class ReportType(models.TextChoices):
        Q1 = "Q1", "一季报"
        H1 = "H1", "半年报"
        Q3 = "Q3", "三季报"
        ANNUAL = "ANNUAL", "年报"

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "待披露"
        RELEASED = "RELEASED", "已披露"

    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="reports",
        verbose_name="标的",
    )
    report_type = models.CharField(
        max_length=10, choices=ReportType.choices, verbose_name="报告类型"
    )
    period_end = models.DateField(verbose_name="报告期")
    disclosure_date = models.DateField(null=True, blank=True, verbose_name="预约披露日")
    actual_date = models.DateField(null=True, blank=True, verbose_name="实际披露日")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED,
        verbose_name="状态",
    )
    revenue = models.DecimalField(
        max_digits=24, decimal_places=2, null=True, blank=True, verbose_name="营业收入"
    )
    net_profit = models.DecimalField(
        max_digits=24, decimal_places=2, null=True, blank=True, verbose_name="净利润"
    )
    revenue_yoy = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="营收同比(%)",
    )
    profit_yoy = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name="净利同比(%)",
    )
    roe = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True, verbose_name="ROE(%)"
    )
    eps = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name="EPS"
    )
    summary = models.CharField(
        max_length=300, blank=True, default="", verbose_name="摘要"
    )
    source = models.CharField(max_length=30, default="eastmoney", verbose_name="来源")

    class Meta:
        ordering = ["-period_end"]
        verbose_name = "定期报告"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "report_type", "period_end"],
                name="uniq_report_event",
            )
        ]


class MarketRegime(OwnedModel):
    class Regime(models.TextChoices):
        BULL = "BULL", "偏多"
        NEUTRAL = "NEUTRAL", "震荡"
        BEAR = "BEAR", "偏空"

    trade_date = models.DateField(verbose_name="日期")
    regime = models.CharField(
        max_length=20,
        choices=Regime.choices,
        default=Regime.NEUTRAL,
        verbose_name="市场风向",
    )
    score = models.DecimalField(
        max_digits=6, decimal_places=2, default=D("0"), verbose_name="评分"
    )
    index_symbol = models.CharField(
        max_length=20, default="000300", verbose_name="指数"
    )
    index_close = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    ma20 = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    ma60 = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    advance_count = models.IntegerField(default=0)
    decline_count = models.IntegerField(default=0)
    breadth_ratio = models.DecimalField(max_digits=8, decimal_places=4, default=D("0"))
    sectors = models.JSONField(default=list, blank=True, verbose_name="行业动量")
    explanation = models.TextField(blank=True, default="", verbose_name="解释")

    class Meta:
        ordering = ["-trade_date"]
        verbose_name = "市场风向"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "trade_date"], name="uniq_market_regime"
            )
        ]


class ScreenerPreset(OwnedModel):
    name = models.CharField(max_length=80, verbose_name="筛选器名称")
    description = models.CharField(
        max_length=200, blank=True, default="", verbose_name="说明"
    )
    criteria = models.JSONField(default=dict, blank=True, verbose_name="筛选条件")
    is_default = models.BooleanField(default=False, verbose_name="默认")

    class Meta:
        ordering = ["id"]
        verbose_name = "筛选器预设"
        verbose_name_plural = verbose_name


class ScreenerRun(OwnedModel):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "运行中"
        SUCCESS = "SUCCESS", "成功"
        FAILED = "FAILED", "失败"

    preset = models.ForeignKey(
        ScreenerPreset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="runs",
        verbose_name="预设",
    )
    criteria = models.JSONField(default=dict, blank=True, verbose_name="筛选条件")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
        verbose_name="状态",
    )
    universe_size = models.IntegerField(default=0, verbose_name="股票池")
    result_count = models.IntegerField(default=0, verbose_name="结果数")
    error = models.TextField(blank=True, default="", verbose_name="错误")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "筛选运行"
        verbose_name_plural = verbose_name


class ScreenerResult(TimeStampedModel):
    run = models.ForeignKey(
        ScreenerRun,
        on_delete=models.CASCADE,
        related_name="results",
        verbose_name="运行",
    )
    instrument = models.ForeignKey(
        Instrument,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="screener_results",
        verbose_name="标的",
    )
    symbol = models.CharField(max_length=20)
    name = models.CharField(max_length=80)
    industry = models.CharField(max_length=60, blank=True, default="")
    price = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    change_pct = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    pe = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    pb = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    market_cap = models.DecimalField(
        max_digits=24, decimal_places=2, null=True, blank=True
    )
    dividend_yield = models.DecimalField(
        max_digits=10, decimal_places=4, null=True, blank=True
    )
    score = models.DecimalField(max_digits=8, decimal_places=2, default=D("0"))
    reasons = models.JSONField(default=list, blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-score", "symbol"]
        verbose_name = "筛选结果"
        verbose_name_plural = verbose_name


class IPOCalendar(TimeStampedModel):
    code = models.CharField(max_length=20, verbose_name="代码")
    name = models.CharField(max_length=80, verbose_name="名称")
    market = models.CharField(
        max_length=30, blank=True, default="", verbose_name="市场"
    )
    apply_code = models.CharField(
        max_length=20, blank=True, default="", verbose_name="申购代码"
    )
    apply_date = models.DateField(null=True, blank=True, verbose_name="申购日")
    listing_date = models.DateField(null=True, blank=True, verbose_name="上市日")
    issue_price = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True, verbose_name="发行价"
    )
    issue_num = models.DecimalField(
        max_digits=24, decimal_places=2, null=True, blank=True, verbose_name="发行量"
    )
    online_apply_upper = models.DecimalField(
        max_digits=24,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="网上申购上限",
    )
    requirement_market_value = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="所需市值"
    )
    status = models.CharField(
        max_length=30, blank=True, default="", verbose_name="状态"
    )
    source = models.CharField(max_length=30, default="eastmoney", verbose_name="来源")

    class Meta:
        ordering = ["apply_date", "code"]
        verbose_name = "打新日历"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["code", "apply_date"], name="uniq_ipo_code_date"
            )
        ]


class StrategySignal(OwnedModel):
    class Type(models.TextChoices):
        BUY_POINT = "BUY_POINT", "B 点"
        SELL_POINT = "SELL_POINT", "S 点"
        GRID = "GRID", "网格降成本"
        DIVIDEND = "DIVIDEND", "股息持有"

    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="signals",
        verbose_name="标的",
    )
    trade_date = models.DateField(verbose_name="日期")
    signal_type = models.CharField(
        max_length=20, choices=Type.choices, verbose_name="信号类型"
    )
    price_low = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    price_high = models.DecimalField(
        max_digits=18, decimal_places=4, null=True, blank=True
    )
    confidence = models.IntegerField(default=50, verbose_name="置信度")
    reasons = models.JSONField(default=list, blank=True)
    metrics = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-trade_date", "-confidence"]
        verbose_name = "策略信号"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["instrument", "trade_date", "signal_type"],
                name="uniq_strategy_signal",
            )
        ]
