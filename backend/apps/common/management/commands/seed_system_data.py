import os

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import UserSetting
from apps.ledger.models import Category, Tag
from apps.users.models import User

SPECIAL = [
    ("理财", Category.Kind.INVESTMENT, "#67C23A"),
    ("股票", Category.Kind.STOCK, "#E6A23C"),
    ("转账", Category.Kind.TRANSFER, "#909399"),
    ("退款", Category.Kind.REFUND, "#F56C6C"),
]

GENERAL = [
    ("工资", "#409EFF"),
    ("奖金", "#409EFF"),
    ("餐饮", "#F56C6C"),
    ("交通", "#E6A23C"),
    ("购物", "#67C23A"),
    ("居住", "#909399"),
    ("娱乐", "#9B59B6"),
    ("医疗", "#1ABC9C"),
    ("教育", "#3498DB"),
    ("保险", "#34495E"),
    ("房贷", "#2C3E50"),
    ("债务支出", "#7F8C8D"),
    ("公积金缴存", "#16A085"),
    ("其他", "#95A5A6"),
]


class Command(BaseCommand):
    help = "初始化默认用户、用户设置、系统分类与示例标签"

    def add_arguments(self, parser):
        parser.add_argument("--username", default=os.getenv("ADMIN_USERNAME", "admin"))
        parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD", "admin123456"))

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"is_staff": True, "is_superuser": True, "display_name": "管理员"},
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"已创建用户 {username}，密码 {password}（请登录后修改）"))
        else:
            self.stdout.write(f"用户 {username} 已存在")
        UserSetting.objects.get_or_create(user=user)
        for name, kind, color in SPECIAL:
            Category.objects.get_or_create(
                owner=user,
                name=name,
                kind=kind,
                defaults={"is_system": True, "color": color, "sort_order": 0},
            )
        for index, (name, color) in enumerate(GENERAL, start=10):
            Category.objects.get_or_create(
                owner=user,
                name=name,
                kind=Category.Kind.GENERAL,
                defaults={"is_system": False, "color": color, "sort_order": index},
            )
        for name, color in [("日常", "#909399"), ("大额", "#F56C6C"), ("报销", "#409EFF")]:
            Tag.objects.get_or_create(owner=user, name=name, defaults={"color": color})
        from apps.investments.services import ensure_presets

        ensure_presets(user)
        self.stdout.write(self.style.SUCCESS("系统基础数据初始化完成"))
