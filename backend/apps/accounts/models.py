from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from apps.common.models import OwnedModel, TimeStampedModel
from apps.common.utils.money import D


class Account(OwnedModel):
    class Type(models.TextChoices):
        SAVINGS = "SAVINGS", "储蓄卡"
        PROVIDENT_FUND_MAIN = "PROVIDENT_FUND_MAIN", "公积金主账户"
        PROVIDENT_FUND_SUPP = "PROVIDENT_FUND_SUPP", "公积金补充账户"
        STOCK = "STOCK", "股票账户"
        WEALTH = "WEALTH", "理财账户"
        ALIPAY = "ALIPAY", "支付宝"
        WECHAT = "WECHAT", "微信"

    name = models.CharField(max_length=80, verbose_name="账户名称")
    type = models.CharField(max_length=32, choices=Type.choices, verbose_name="账户类型")
    institution = models.CharField(max_length=80, blank=True, default="", verbose_name="机构")
    account_no_masked = models.CharField(max_length=40, blank=True, default="", verbose_name="账号后四位")
    currency = models.CharField(max_length=8, default="CNY", verbose_name="币种")
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="期初余额")
    opening_date = models.DateField(default=timezone.localdate, verbose_name="期初日期")
    allow_negative = models.BooleanField(default=False, verbose_name="允许负余额")
    is_active = models.BooleanField(default=True, verbose_name="启用")
    sort_order = models.IntegerField(default=0, verbose_name="排序")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "账户"
        verbose_name_plural = verbose_name
        indexes = [models.Index(fields=["owner", "type", "is_active"])]

    def __str__(self):
        return f"{self.name}({self.get_type_display()})"


class ProvidentFundProfile(TimeStampedModel):
    class FundType(models.TextChoices):
        MAIN = "MAIN", "主账户"
        SUPPLEMENTARY = "SUPPLEMENTARY", "补充账户"

    account = models.OneToOneField(
        Account, on_delete=models.CASCADE, related_name="pf_profile", verbose_name="公积金账户"
    )
    fund_type = models.CharField(max_length=20, choices=FundType.choices, default=FundType.MAIN, verbose_name="账户性质")
    monthly_employee_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="个人月缴"
    )
    monthly_employer_amount = models.DecimalField(
        max_digits=18, decimal_places=2, default=D("0"), verbose_name="单位月缴"
    )
    contribution_day = models.IntegerField(
        default=10, validators=[MinValueValidator(1), MaxValueValidator(28)], verbose_name="每月缴存日"
    )
    auto_contribute = models.BooleanField(default=False, verbose_name="自动生成月缴流水")
    city = models.CharField(max_length=40, blank=True, default="", verbose_name="城市")

    class Meta:
        verbose_name = "公积金配置"
        verbose_name_plural = verbose_name

    @property
    def monthly_total(self):
        return D(self.monthly_employee_amount) + D(self.monthly_employer_amount)


class UserSetting(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="setting")
    payday = models.IntegerField(
        default=10, validators=[MinValueValidator(1), MaxValueValidator(31)], verbose_name="发薪日"
    )
    salary_amount = models.DecimalField(
        max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="预计月薪"
    )
    salary_account = models.ForeignKey(
        Account,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="salary_settings",
        verbose_name="工资账户",
    )
    currency = models.CharField(max_length=8, default="CNY", verbose_name="币种")
    dashboard_prefs = models.JSONField(default=dict, blank=True, verbose_name="总览偏好")

    class Meta:
        verbose_name = "用户设置"
        verbose_name_plural = verbose_name
