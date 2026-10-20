from django.core.management.base import BaseCommand

from apps.common.models import JobRun
from apps.investments.models import ScreenerPreset
from apps.investments.services import (
    ensure_presets,
    refresh_market_regime,
    run_screener,
    sync_ipo_calendar,
)
from apps.users.models import User


class Command(BaseCommand):
    help = "刷新市场风向、打新日历，并按默认筛选器运行一次全市场筛选"

    def add_arguments(self, parser):
        parser.add_argument("--owner", default=None)
        parser.add_argument("--skip-screener", action="store_true")

    def handle(self, *args, **options):
        job = JobRun.objects.create(job_name="refresh_investment_intelligence")
        users = User.objects.all()
        if options.get("owner"):
            users = users.filter(username=options["owner"])
        stats = {"regime": 0, "screener": 0, "ipo": 0, "errors": 0}
        try:
            ipo_result = sync_ipo_calendar()
            stats["ipo"] = ipo_result.get("count", 0)
            for user in users:
                ensure_presets(user)
                try:
                    refresh_market_regime(user)
                    stats["regime"] += 1
                except Exception:
                    stats["errors"] += 1
                if not options.get("skip_screener"):
                    preset = ScreenerPreset.objects.filter(owner=user, is_default=True).first()
                    if preset:
                        try:
                            run = run_screener(user, preset=preset)
                            if run.status == "SUCCESS":
                                stats["screener"] += 1
                            else:
                                stats["errors"] += 1
                        except Exception:
                            stats["errors"] += 1
            job.status = JobRun.Status.SUCCESS
            job.stats = stats
            job.save()
            self.stdout.write(self.style.SUCCESS(f"投资智能刷新完成: {stats}"))
        except Exception as exc:
            job.status = JobRun.Status.FAILED
            job.error = str(exc)
            job.save()
            self.stderr.write(self.style.ERROR(f"投资智能刷新失败: {exc}"))
            raise
