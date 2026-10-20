from django.core.management.base import BaseCommand

from apps.common.models import JobRun
from apps.debts.services import auto_settle_due_items
from apps.users.models import User


class Command(BaseCommand):
    help = "执行到期自动还款（房贷公积金冲还/现金差额、周期债务自动支付）"

    def add_arguments(self, parser):
        parser.add_argument("--owner", default=None, help="仅处理指定用户名")

    def handle(self, *args, **options):
        job = JobRun.objects.create(job_name="settle_auto_payments")
        owner = None
        if options.get("owner"):
            owner = User.objects.filter(username=options["owner"]).first()
        try:
            stats = auto_settle_due_items(owner=owner)
            job.status = JobRun.Status.SUCCESS
            job.stats = stats
            job.save()
            self.stdout.write(self.style.SUCCESS(f"自动还款完成: {stats}"))
        except Exception as exc:
            job.status = JobRun.Status.FAILED
            job.error = str(exc)
            job.save()
            self.stderr.write(self.style.ERROR(f"自动还款失败: {exc}"))
            raise
