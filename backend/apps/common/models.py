from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OwnedModel(TimeStampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
    )

    class Meta:
        abstract = True


class JobRun(models.Model):
    class Status(models.TextChoices):
        RUNNING = "RUNNING", "运行中"
        SUCCESS = "SUCCESS", "成功"
        FAILED = "FAILED", "失败"
        SKIPPED = "SKIPPED", "跳过"

    job_name = models.CharField(max_length=100, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "任务运行记录"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.job_name}@{self.started_at:%Y-%m-%d %H:%M} ({self.status})"
