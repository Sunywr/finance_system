from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import OwnedModel
from apps.common.utils.money import D


class CreditCard(OwnedModel):
    name = models.CharField(max_length=80, verbose_name="信用卡名称")
    bank = models.CharField(max_length=80, blank=True, default="", verbose_name="发卡行")
    last4 = models.CharField(max_length=8, blank=True, default="", verbose_name="卡号后四位")
    statement_start_day = models.IntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(31)], verbose_name="账单起始日"
    )
    statement_end_day = models.IntegerField(
        default=28, validators=[MinValueValidator(1), MaxValueValidator(31)], verbose_name="账单结束日"
    )
    due_day = models.IntegerField(
        default=20, validators=[MinValueValidator(1), MaxValueValidator(31)], verbose_name="还款日"
    )
    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="信用额度")
    min_payment_rate = models.DecimalField(
        max_digits=6, decimal_places=4, default=Decimal("0.1000"), verbose_name="最低还款比例"
    )
    is_active = models.BooleanField(default=True, verbose_name="启用")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "信用卡"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class CreditCardBill(OwnedModel):
    class Status(models.TextChoices):
        OPEN = "OPEN", "未出账"
        CLOSED = "CLOSED", "已出账"

    card = models.ForeignKey(CreditCard, on_delete=models.CASCADE, related_name="bills", verbose_name="信用卡")
    period_start = models.DateField(verbose_name="账单起始")
    period_end = models.DateField(verbose_name="账单结束")
    due_date = models.DateField(verbose_name="还款截止")
    normal_total = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="普通消费")
    installment_total = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="分期应还")
    refund_total = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="退款")
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="账单合计")
    min_payment = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="最低还款")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, verbose_name="状态")
    generated_at = models.DateTimeField(null=True, blank=True, verbose_name="出账时间")

    class Meta:
        ordering = ["-period_start", "-id"]
        verbose_name = "信用卡账单"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["card", "period_start", "period_end"], name="uniq_card_period"
            )
        ]
        indexes = [models.Index(fields=["owner", "due_date", "status"])]

    def __str__(self):
        return f"{self.card.name} {self.period_start}~{self.period_end}"


class RecurringDebt(OwnedModel):
    class DebtType(models.TextChoices):
        INSURANCE = "INSURANCE", "保险"
        MORTGAGE = "MORTGAGE", "房贷"
        RENT = "RENT", "房租"
        EDUCATION = "EDUCATION", "教育"
        OTHER = "OTHER", "其他"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "进行中"
        COMPLETED = "COMPLETED", "已完成"
        CANCELLED = "CANCELLED", "已取消"

    name = models.CharField(max_length=100, verbose_name="债务名称")
    debt_type = models.CharField(max_length=20, choices=DebtType.choices, default=DebtType.OTHER, verbose_name="类型")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="每期金额")
    periods = models.IntegerField(validators=[MinValueValidator(1)], verbose_name="期数")
    interval_months = models.IntegerField(default=1, validators=[MinValueValidator(1)], verbose_name="间隔月数")
    first_due_date = models.DateField(verbose_name="首次到期日")
    due_day = models.IntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(31)], verbose_name="到期日")
    payment_channel = models.CharField(max_length=20, default="CASH", verbose_name="默认支付渠道")
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recurring_debts",
        verbose_name="默认支付账户",
    )
    credit_card = models.ForeignKey(
        CreditCard,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recurring_debts",
        verbose_name="默认信用卡",
    )
    # Stored as an id to keep the migration graph acyclic (ledger depends on debts).
    category_id = models.BigIntegerField(null=True, blank=True, verbose_name="支出分类")
    auto_pay = models.BooleanField(default=False, verbose_name="自动支付")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name="状态")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "周期债务"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class DebtItem(OwnedModel):
    class Kind(models.TextChoices):
        CREDIT_CARD = "CREDIT_CARD", "信用卡债务"
        PERIODIC = "PERIODIC", "周期债务"
        MORTGAGE = "MORTGAGE", "房贷"

    class Status(models.TextChoices):
        PENDING = "PENDING", "待还"
        PARTIAL = "PARTIAL", "部分还款"
        PAID = "PAID", "已结清"
        OVERDUE = "OVERDUE", "逾期"
        CANCELLED = "CANCELLED", "已取消"

    kind = models.CharField(max_length=20, choices=Kind.choices, verbose_name="债务类型")
    bill = models.OneToOneField(
        CreditCardBill,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="debt_item",
        verbose_name="信用卡账单",
    )
    recurring_debt = models.ForeignKey(
        RecurringDebt,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="周期债务",
    )
    loan_schedule = models.OneToOneField(
        "mortgages.LoanSchedule",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="debt_item",
        verbose_name="房贷期次",
    )
    title = models.CharField(max_length=140, verbose_name="标题")
    period_no = models.IntegerField(null=True, blank=True, verbose_name="期数")
    due_date = models.DateField(verbose_name="到期日")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="应还金额")
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="减免金额")
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="已还金额")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="状态")
    settled_at = models.DateTimeField(null=True, blank=True, verbose_name="结清时间")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["due_date", "id"]
        verbose_name = "债务项"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=["recurring_debt", "period_no"], name="uniq_recurring_period"
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "status", "due_date"]),
            models.Index(fields=["owner", "kind", "due_date"]),
        ]

    @property
    def payable_amount(self):
        return max(D(self.amount) - D(self.discount_amount) - D(self.paid_amount), D("0"))

    def refresh_status(self, save=True):
        payable = D(self.amount) - D(self.discount_amount)
        paid = D(self.paid_amount)
        if self.status == self.Status.CANCELLED:
            return self.status
        if paid >= payable:
            self.status = self.Status.PAID
            self.settled_at = self.settled_at or timezone.now()
        elif self.due_date < timezone.localdate():
            self.status = self.Status.OVERDUE
        elif paid > 0:
            self.status = self.Status.PARTIAL
        else:
            self.status = self.Status.PENDING
        if save:
            self.save(update_fields=["status", "settled_at", "updated_at"])
        return self.status

    def __str__(self):
        return f"{self.title} {self.due_date}"


class DebtPayment(OwnedModel):
    class Channel(models.TextChoices):
        CASH = "CASH", "储蓄卡现金"
        PROVIDENT_FUND = "PROVIDENT_FUND", "公积金"
        CREDIT_CARD = "CREDIT_CARD", "信用卡"
        ALIPAY = "ALIPAY", "支付宝"
        WECHAT = "WECHAT", "微信"

    debt_item = models.ForeignKey(DebtItem, on_delete=models.CASCADE, related_name="payments", verbose_name="债务项")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="实付金额")
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="减免金额")
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.CASH, verbose_name="支付渠道")
    account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="debt_payments",
        verbose_name="支付账户",
    )
    credit_card = models.ForeignKey(
        CreditCard,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="debt_payments",
        verbose_name="信用卡",
    )
    paid_at = models.DateTimeField(default=timezone.now, verbose_name="支付时间")
    transaction_id = models.BigIntegerField(null=True, blank=True, verbose_name="关联流水ID")
    idempotency_key = models.CharField(max_length=80, null=True, blank=True, verbose_name="幂等键")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["-paid_at", "-id"]
        verbose_name = "还款记录"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(fields=["owner", "idempotency_key"], name="uniq_payment_idempotency"),
        ]

    def __str__(self):
        return f"{self.debt_item.title} 还款 {self.amount}"
