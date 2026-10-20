from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    display_name = models.CharField(max_length=80, blank=True, default="", verbose_name="显示名")

    class Meta:
        verbose_name = "用户"
        verbose_name_plural = verbose_name
