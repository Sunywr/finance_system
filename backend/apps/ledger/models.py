from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.common.models import OwnedModel
from apps.common.utils.money import D


class Category(OwnedModel):
    class Kind(models.TextChoices):
        GENERAL = "GENERAL", "通用"
        INVESTMENT = "INVESTMENT", "理财"
        STOCK = "STOCK", "股票"
        TRANSFER = "TRANSFER", "转账"
        REFUND = "REFUND", "退款"

    name = models.CharField(max_length=60, verbose_name="分类名称")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        verbose_name="父分类",
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        default=Kind.GENERAL,
        verbose_name="分类类型",
    )
    is_system = models.BooleanField(default=False, verbose_name="系统分类")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    color = models.CharField(max_length=16, default="#409EFF", verbose_name="颜色")
    icon = models.CharField(max_length=40, blank=True, default="", verbose_name="图标")

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "分类"
        verbose_name_plural = verbose_name
        indexes = [models.Index(fields=["owner", "kind", "is_active"])]

    def __str__(self):
        return self.name


class Tag(OwnedModel):
    name = models.CharField(max_length=30, verbose_name="标签")
    color = models.CharField(max_length=16, default="#909399", verbose_name="颜色")

    class Meta:
        ordering = ["name"]
        verbose_name = "标签"
        verbose_name_plural = verbose_name
        indexes = [models.Index(fields=["owner", "name"])]

    def __str__(self):
        return self.name


class AccountTransfer(OwnedModel):
    from_account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="transfers_out",
        verbose_name="转出账户",
    )
    to_account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="transfers_in",
        verbose_name="转入账户",
    )
    amount = models.DecimalField(
        max_digits=18, decimal_places=2, verbose_name="转账金额"
    )
    fee = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="手续费"
    )
    occurred_at = models.DateTimeField(default=timezone.now, verbose_name="转账时间")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")
    out_transaction_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="转出流水"
    )
    in_transaction_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="转入流水"
    )
    idempotency_key = models.CharField(
        max_length=80, null=True, blank=True, verbose_name="幂等键"
    )

    class Meta:
        ordering = ["-occurred_at", "-id"]
        verbose_name = "账户转账"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "idempotency_key"], name="uniq_transfer_idempotency"
            ),
        ]

    def __str__(self):
        return f"{self.from_account} -> {self.to_account} {self.amount}"


class Transaction(OwnedModel):
    class Type(models.TextChoices):
        EXPENSE = "EXPENSE", "支出"
        INCOME = "INCOME", "收入"
        TRANSFER_OUT = "TRANSFER_OUT", "转出"
        TRANSFER_IN = "TRANSFER_IN", "转入"
        REFUND = "REFUND", "退款"
        NOTE = "NOTE", "历史零金额记录"

    class SettlementChannel(models.TextChoices):
        CASH = "CASH", "现金(储蓄卡)"
        CREDIT_CARD = "CREDIT_CARD", "信用卡"
        PROVIDENT_FUND = "PROVIDENT_FUND", "公积金"
        ALIPAY = "ALIPAY", "支付宝"
        WECHAT = "WECHAT", "微信"
        STOCK = "STOCK", "股票账户"
        WEALTH = "WEALTH", "理财账户"
        WALLET = "WALLET", "其他钱包"

    class Operation(models.TextChoices):
        NONE = "NONE", "无"
        OPEN = "OPEN", "建仓"
        ADD = "ADD", "加仓"
        REDUCE = "REDUCE", "减仓"
        DIVIDEND = "DIVIDEND", "分红"

    class Status(models.TextChoices):
        POSTED = "POSTED", "已记账"
        VOID = "VOID", "已作废"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "手工"
        TRANSFER = "TRANSFER", "转账"
        DEBT_PAYMENT = "DEBT_PAYMENT", "债务还款"
        INVESTMENT = "INVESTMENT", "投资交易"
        REFUND = "REFUND", "退款"
        INSTALLMENT = "INSTALLMENT", "分期"
        SYSTEM = "SYSTEM", "系统生成"
        LEGACY = "LEGACY", "历史迁移"

    txn_no = models.CharField(max_length=40, verbose_name="流水号")
    type = models.CharField(
        max_length=20, choices=Type.choices, verbose_name="流水类型"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="分类",
    )
    tags = models.ManyToManyField(
        Tag, blank=True, related_name="transactions", verbose_name="标签"
    )
    occurred_at = models.DateTimeField(default=timezone.now, verbose_name="发生时间")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="金额")
    settlement_channel = models.CharField(
        max_length=20,
        choices=SettlementChannel.choices,
        default=SettlementChannel.CASH,
        verbose_name="支付渠道",
    )
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="资金账户",
    )
    credit_card = models.ForeignKey(
        "debts.CreditCard",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name="信用卡",
    )
    operation = models.CharField(
        max_length=20,
        choices=Operation.choices,
        default=Operation.NONE,
        verbose_name="投资操作",
    )
    note = models.CharField(max_length=500, blank=True, default="", verbose_name="备注")
    transfer = models.ForeignKey(
        AccountTransfer,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name="转账",
    )
    refund_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="refunds",
        verbose_name="原流水",
    )
    installment_plan = models.ForeignKey(
        "InstallmentPlan",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name="分期计划",
    )
    asset = models.ForeignKey(
        "assets.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="transactions",
        verbose_name="关联资产",
    )
    asset_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="计入资产金额"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.POSTED,
        verbose_name="状态",
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL,
        verbose_name="来源",
    )
    source_id = models.BigIntegerField(null=True, blank=True, verbose_name="来源ID")
    idempotency_key = models.CharField(
        max_length=80, null=True, blank=True, verbose_name="幂等键"
    )
    exclude_from_card_bill = models.BooleanField(
        default=False, verbose_name="不计入信用卡账单统计"
    )
    voided_at = models.DateTimeField(null=True, blank=True, verbose_name="作废时间")
    void_reason = models.CharField(
        max_length=200, blank=True, default="", verbose_name="作废原因"
    )

    class Meta:
        ordering = ["-occurred_at", "-id"]
        verbose_name = "记账流水"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "idempotency_key"], name="uniq_txn_idempotency"
            ),
            models.UniqueConstraint(fields=["owner", "txn_no"], name="uniq_txn_no"),
        ]
        indexes = [
            models.Index(fields=["owner", "occurred_at"]),
            models.Index(fields=["owner", "status", "occurred_at"]),
            models.Index(fields=["owner", "account", "occurred_at"]),
            models.Index(fields=["owner", "credit_card", "occurred_at"]),
            models.Index(fields=["owner", "category", "occurred_at"]),
        ]

    def __str__(self):
        return f"{self.txn_no} {self.amount}"


class InstallmentPlan(OwnedModel):
    class FeeMode(models.TextChoices):
        NONE = "NONE", "免手续费"
        FLAT = "FLAT", "一次性手续费"
        PER_PERIOD = "PER_PERIOD", "每期手续费"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "进行中"
        COMPLETED = "COMPLETED", "已完成"
        CANCELLED = "CANCELLED", "已取消"

    purchase_transaction_id = models.BigIntegerField(
        null=True, blank=True, verbose_name="购买流水"
    )
    credit_card = models.ForeignKey(
        "debts.CreditCard",
        on_delete=models.PROTECT,
        related_name="installment_plans",
        verbose_name="信用卡",
    )
    principal = models.DecimalField(
        max_digits=18, decimal_places=2, verbose_name="分期本金"
    )
    periods = models.IntegerField(verbose_name="期数")
    fee_mode = models.CharField(
        max_length=20,
        choices=FeeMode.choices,
        default=FeeMode.NONE,
        verbose_name="手续费模式",
    )
    fee_rate = models.DecimalField(
        max_digits=8, decimal_places=4, default=Decimal("0"), verbose_name="手续费率"
    )
    total_fee = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="总手续费"
    )
    per_period_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="每期应还"
    )
    first_period_start = models.DateField(verbose_name="首期账单起始")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="状态",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "分期计划"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.credit_card} 分期 {self.principal}/{self.periods}"


class InstallmentPeriod(OwnedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待出账"
        BILLED = "BILLED", "已出账"
        PAID = "PAID", "已还"
        CANCELLED = "CANCELLED", "已取消"

    plan = models.ForeignKey(
        InstallmentPlan,
        on_delete=models.CASCADE,
        related_name="period_rows",
        verbose_name="分期计划",
    )
    period_no = models.IntegerField(verbose_name="期数")
    bill_period_start = models.DateField(verbose_name="账单起始")
    bill_period_end = models.DateField(verbose_name="账单结束")
    due_date = models.DateField(verbose_name="还款日")
    principal_part = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="本金部分"
    )
    fee_part = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="手续费部分"
    )
    amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="每期应还"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="状态",
    )
    bill = models.ForeignKey(
        "debts.CreditCardBill",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="installment_periods",
        verbose_name="账单",
    )

    class Meta:
        ordering = ["plan", "period_no"]
        verbose_name = "分期期次"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "period_no"], name="uniq_plan_period"
            )
        ]
