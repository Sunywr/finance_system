import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger(__name__)


def _run(name):
    try:
        call_command(name)
    except Exception:
        logger.exception("scheduled job failed: %s", name)


class Command(BaseCommand):
    help = "启动财务系统定时任务进程"

    def handle(self, *args, **options):
        if settings.MIGRATION_REHEARSAL:
            raise CommandError("迁移演练环境不启动自动还款、行情、AI 或通知任务")
        scheduler = BlockingScheduler(
            timezone=settings.TIME_ZONE, executors={"default": ThreadPoolExecutor(1)}
        )
        scheduler.add_job(
            lambda: _run("generate_financial_cycles"),
            CronTrigger(hour=0, minute=10),
            id="generate_financial_cycles",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            lambda: _run("settle_auto_payments"),
            CronTrigger(hour=0, minute=30),
            id="settle_auto_payments",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            lambda: _run("generate_pf_contributions"),
            CronTrigger(day=1, hour=1, minute=0),
            id="generate_pf_contributions",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            lambda: _run("sync_market_data"),
            CronTrigger(day_of_week="mon-fri", hour=15, minute=30),
            id="sync_market_data",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            lambda: _run("refresh_investment_intelligence"),
            CronTrigger(day_of_week="mon-fri", hour=18, minute=30),
            id="refresh_investment_intelligence",
            max_instances=1,
            coalesce=True,
        )
        self.stdout.write(self.style.SUCCESS("定时任务进程已启动（Ctrl+C 退出）"))
        for job in scheduler.get_jobs():
            self.stdout.write(f" - {job.id}: {job.trigger}")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self.stdout.write("定时任务进程已停止")
