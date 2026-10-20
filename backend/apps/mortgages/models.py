from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import OwnedModel, TimeStampedModel
from apps.common.utils.money import D


class Loan(OwnedModel):
    class LoanType(models.TextChoices):
        COMMERCIAL = "COMMERCIAL", "商业贷款"
        PROVIDENT_FUND = "PROVIDENT_FUND", "公积金贷款"

    class RepaymentMethod(models.TextChoices):
        EQUAL_INSTALLMENT = "EQUAL_INSTALLMENT", "等额本息"
        EQUAL_PRINCIPAL = "EQUAL_PRINCIPAL", "等额本金"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "还款中"
        SETTLED = "SETTLED", "已结清"
        CANCELLED = "CANCELLED", "已取消"

    name = models.CharField(max_length=100, verbose_name="贷款名称")
    loan_type = models.CharField(max_length=20, choices=LoanType.choices, verbose_name="贷款类型")
    lender = models.CharField(max_length=80, blank=True, default="", verbose_name="贷款机构")
    principal = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="贷款本金")
    annual_rate = models.DecimalField(
        max_digits=8, decimal_places=4, verbose_name="年利率(%)", help_text="例如 4.2 表示 4.2%"
    )
    term_months = models.IntegerField(validators=[MinValueValidator(1)], verbose_name="期数(月)")
    repayment_method = models.CharField(
        max_length=24, choices=RepaymentMethod.choices, default=RepaymentMethod.EQUAL_INSTALLMENT, verbose_name="还款方式"
    )
    first_due_date = models.DateField(verbose_name="首次还款日")
    payment_day = models.IntegerField(default=1, validators=[MinValueValidator(1)], verbose_name="每月还款日")
    repayment_account = models.ForeignKey(
        "accounts.Account",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="loan_repayments",
        verbose_name="现金还款账户",
    )
    auto_settle = models.BooleanField(default=False, verbose_name="到期自动结清现金部分")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name="状态")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "贷款"
        verbose_name_plural = verbose_name

    def __str__(self):
        return self.name


class LoanSchedule(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "PENDING", "待还"
        PARTIAL = "PARTIAL", "部分还款"
        PAID = "PAID", "已还"
        OVERDUE = "OVERDUE", "逾期"
        CANCELLED = "CANCELLED", "已取消"

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="schedules", verbose_name="贷款")
    period_no = models.IntegerField(verbose_name="期数")
    due_date = models.DateField(verbose_name="还款日")
    principal_due = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="应还本金")
    interest_due = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="应还利息")
    total_due = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="应还合计")
    remaining_principal = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="剩余本金"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="状态")

    class Meta:
        ordering = ["loan", "period_no"]
        verbose_name = "还款计划"
        verbose_name_plural = verbose_name
        constraints = [models.UniqueConstraint(fields=["loan", "period_no"], name="uniq_loan_period")]
        indexes = [models.Index(fields=["loan", "due_date", "status"])]

    def __str__(self):
        return f"{self.loan.name} 第{self.period_no}期"


class OffsetPlan(TimeStampedModel):
    class Mode(models.TextChoices):
        FULL = "FULL", "全额冲还"
        PARTIAL = "PARTIAL", "部分冲还"

    loan = models.OneToOneField(Loan, on_delete=models.CASCADE, related_name="offset_plan", verbose_name="贷款")
    pf_account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.PROTECT,
        related_name="offset_plans",
        verbose_name="公积金账户",
    )
    enabled = models.BooleanField(default=True, verbose_name="启用")
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.FULL, verbose_name="冲还方式")
    start_date = models.DateField(default=timezone.localdate, verbose_name="开始日期")
    monthly_cap = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="每月冲还上限"
    )
    use_new_contributions = models.BooleanField(default=True, verbose_name="计入未来公积金月缴")
    auto_pay_cash = models.BooleanField(default=False, verbose_name="现金差额自动扣款")

    class Meta:
        verbose_name = "公积金冲还配置"
        verbose_name_plural = verbose_name
