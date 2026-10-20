from django.core.management.base import BaseCommand

from apps.common.models import JobRun
from apps.investments.services import sync_all_market_data
from apps.users.models import User


class Command(BaseCommand):
    help = "同步持仓/自选相关标的行情与日线"

    def add_arguments(self, parser):
        parser.add_argument("--owner", default=None, help="仅处理指定用户名")

    def handle(self, *args, **options):
        job = JobRun.objects.create(job_name="sync_market_data")
        users = User.objects.all()
        if options.get("owner"):
            users = users.filter(username=options["owner"])
        totals = {"total": 0, "ok": 0, "error": 0, "skipped": 0}
        try:
            for user in users:
                stats = sync_all_market_data(user)
                for key in totals:
                    totals[key] += stats.get(key, 0)
            job.status = JobRun.Status.SUCCESS
            job.stats = totals
            job.save()
            self.stdout.write(self.style.SUCCESS(f"行情同步完成: {totals}"))
        except Exception as exc:
            job.status = JobRun.Status.FAILED
            job.error = str(exc)
            job.save()
            self.stderr.write(self.style.ERROR(f"行情同步失败: {exc}"))
            raise
