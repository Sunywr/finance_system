from django.db import models
from django.utils import timezone

from apps.common.models import OwnedModel, TimeStampedModel
from apps.common.utils.money import D


class Asset(OwnedModel):
    class Type(models.TextChoices):
        REAL_ESTATE = "REAL_ESTATE", "房产"
        VEHICLE = "VEHICLE", "车辆"
        ELECTRONICS = "ELECTRONICS", "数码"
        COLLECTIBLE = "COLLECTIBLE", "收藏"
        GOLD = "GOLD", "贵金属"
        OTHER = "OTHER", "其他"

    class ValuationMode(models.TextChoices):
        LINKED_SUM = "LINKED_SUM", "按关联流水汇总"
        MANUAL = "MANUAL", "手工估值"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "持有"
        DISPOSED = "DISPOSED", "已处置"

    name = models.CharField(max_length=100, verbose_name="资产名称")
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.OTHER, verbose_name="资产类型")
    valuation_mode = models.CharField(
        max_length=20, choices=ValuationMode.choices, default=ValuationMode.LINKED_SUM, verbose_name="估值方式"
    )
    manual_value = models.DecimalField(max_digits=18, decimal_places=2, default=D("0"), verbose_name="手工估值")
    acquired_date = models.DateField(default=timezone.localdate, verbose_name="取得日期")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name="状态")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "资产"
        verbose_name_plural = verbose_name
        indexes = [models.Index(fields=["owner", "status"])]

    def __str__(self):
        return self.name


class AssetValuation(TimeStampedModel):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="valuations", verbose_name="资产")
    value = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="估值")
    valued_at = models.DateField(default=timezone.localdate, verbose_name="估值日期")
    note = models.CharField(max_length=200, blank=True, default="", verbose_name="备注")

    class Meta:
        ordering = ["-valued_at", "-id"]
        verbose_name = "资产估值"
        verbose_name_plural = verbose_name
