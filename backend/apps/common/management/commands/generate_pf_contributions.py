from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Account, ProvidentFundProfile
from apps.common.models import JobRun
from apps.common.utils.money import money
from apps.ledger.models import Category, Transaction
from apps.ledger.services import create_transaction, get_or_create_category
from apps.users.models import User


class Command(BaseCommand):
    help = "为开启自动缴存的公积金账户生成当月缴存流水"

    def add_arguments(self, parser):
        parser.add_argument("--owner", default=None, help="仅处理指定用户名")

    @transaction.atomic
    def handle(self, *args, **options):
        job = JobRun.objects.create(job_name="generate_pf_contributions")
        qs = ProvidentFundProfile.objects.filter(auto_contribute=True).select_related("account")
        if options.get("owner"):
            user = User.objects.filter(username=options["owner"]).first()
            if user:
                qs = qs.filter(account__owner=user)
        stats = {"created": 0, "skipped": 0}
        try:
            today = timezone.localdate()
            month_key = f"{today:%Y%m}"
            for profile in qs:
                amount = money(profile.monthly_employee_amount) + money(profile.monthly_employer_amount)
                if amount <= 0:
                    stats["skipped"] += 1
                    continue
                category = get_or_create_category(profile.account.owner, "公积金缴存", Category.Kind.GENERAL)
                key = f"pf:{profile.id}:{month_key}"
                if Transaction.objects.filter(owner=profile.account.owner, idempotency_key=key).exists():
                    stats["skipped"] += 1
                    continue
                create_transaction(
                    owner=profile.account.owner,
                    txn_type=Transaction.Type.INCOME,
                    category=category,
                    amount=amount,
                    occurred_at=timezone.now(),
                    settlement_channel=Transaction.SettlementChannel.PROVIDENT_FUND,
                    account=profile.account,
                    note=f"{today:%Y-%m} 公积金缴存",
                    source=Transaction.Source.SYSTEM,
                    source_id=profile.id,
                    idempotency_key=key,
                    check_balance=False,
                )
                stats["created"] += 1
            job.status = JobRun.Status.SUCCESS
            job.stats = stats
            job.save()
            self.stdout.write(self.style.SUCCESS(f"公积金缴存完成: {stats}"))
        except Exception as exc:
            job.status = JobRun.Status.FAILED
            job.error = str(exc)
            job.save()
            raise
