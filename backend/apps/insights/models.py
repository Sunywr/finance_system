from django.db import models

from apps.common.models import OwnedModel


class AIProviderConfig(OwnedModel):
    name = models.CharField(max_length=80, verbose_name="名称")
    base_url = models.CharField(max_length=300, verbose_name="Base URL")
    api_key_encrypted = models.TextField(blank=True, default="", verbose_name="API Key(加密)")
    model = models.CharField(max_length=120, verbose_name="模型")
    temperature = models.DecimalField(max_digits=4, decimal_places=2, default=0.3, verbose_name="温度")
    max_tokens = models.IntegerField(default=2048, verbose_name="最大输出")
    timeout_seconds = models.IntegerField(default=90, verbose_name="超时秒数")
    max_retries = models.IntegerField(default=2, verbose_name="限流重试次数")
    retry_wait_seconds = models.IntegerField(default=60, verbose_name="重试等待秒数")
    is_default = models.BooleanField(default=False, verbose_name="默认")
    enabled = models.BooleanField(default=True, verbose_name="启用")
    extra_headers = models.JSONField(default=dict, blank=True, verbose_name="额外请求头")
    extra_body = models.JSONField(default=dict, blank=True, verbose_name="额外请求体")

    class Meta:
        ordering = ["-is_default", "id"]
        verbose_name = "AI 服务配置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.name} ({self.model})"


class AIAnalysis(OwnedModel):
    class Type(models.TextChoices):
        MONTHLY = "MONTHLY", "月度总结"
        QUARTERLY = "QUARTERLY", "季度总结"
        DEBT = "DEBT", "债务健康"
        INVESTMENT = "INVESTMENT", "投资复盘"
        CUSTOM = "CUSTOM", "自定义"

    class Status(models.TextChoices):
        PENDING = "PENDING", "生成中"
        SUCCESS = "SUCCESS", "成功"
        FAILED = "FAILED", "失败"

    analysis_type = models.CharField(max_length=20, choices=Type.choices, default=Type.MONTHLY, verbose_name="分析类型")
    period_start = models.DateField(verbose_name="开始日期")
    period_end = models.DateField(verbose_name="结束日期")
    provider = models.ForeignKey(
        AIProviderConfig, null=True, blank=True, on_delete=models.SET_NULL, related_name="analyses", verbose_name="服务"
    )
    data_snapshot = models.JSONField(default=dict, blank=True, verbose_name="数据快照")
    prompt_snapshot = models.TextField(blank=True, default="", verbose_name="提示词快照")
    response_text = models.TextField(blank=True, default="", verbose_name="分析结果")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="状态")
    error = models.TextField(blank=True, default="", verbose_name="错误")
    tokens = models.IntegerField(default=0, verbose_name="Token")
    elapsed_ms = models.IntegerField(default=0, verbose_name="耗时毫秒")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "AI 分析"
        verbose_name_plural = verbose_name
