from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.common.models import JobRun
from apps.debts.models import DebtItem
from apps.debts.services import generate_all_debt_items, generate_due_bills, mark_overdue
from apps.users.models import User


class Command(BaseCommand):
    help = "关闭到期信用卡账单、生成信用卡/周期/房贷债务项、刷新逾期状态"

    def add_arguments(self, parser):
        parser.add_argument("--owner", default=None, help="仅处理指定用户名")

    def handle(self, *args, **options):
        job = JobRun.objects.create(job_name="generate_financial_cycles")
        owner = None
        if options.get("owner"):
            owner = User.objects.filter(username=options["owner"]).first()
        try:
            stats = generate_due_bills(owner=owner)
            stats.update(generate_all_debt_items(owner=owner))
            stats["overdue"] = mark_overdue()
            job.status = JobRun.Status.SUCCESS
            job.stats = stats
            job.save()
            self.stdout.write(self.style.SUCCESS(f"周期生成完成: {stats}"))
        except Exception as exc:
            job.status = JobRun.Status.FAILED
            job.error = str(exc)
            job.save()
            self.stderr.write(self.style.ERROR(f"周期生成失败: {exc}"))
            raise
