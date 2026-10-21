"""Small compatibility layer: facts and provenance, never a copy of 321 schemas."""

from django.conf import settings
from django.db import models


class MigrationBatch(models.Model):
    snapshot_sha256 = models.CharField(max_length=64, unique=True)
    source_identity = models.JSONField(default=dict)
    state = models.CharField(max_length=24, default="IMPORTING")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)
    report = models.JSONField(default=dict)


class Household(models.Model):
    name = models.CharField(max_length=128)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    is_active = models.BooleanField(default=True)


class Membership(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=16)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["household", "user"], name="legacy_unique_member"
            )
        ]


class LegacyRecord(models.Model):
    """Original financial/config facts including fields not represented by projections.

    No secrets are returned by the API. Unknown business tables remain archived.
    """

    batch = models.ForeignKey(MigrationBatch, on_delete=models.PROTECT)
    table = models.CharField(max_length=100)
    source_pk = models.CharField(max_length=200)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT
    )
    business_date = models.DateField(null=True)
    code = models.CharField(max_length=32, blank=True)
    payload = models.JSONField()
    sha256 = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "table", "source_pk"], name="legacy_unique_record"
            )
        ]
        indexes = [models.Index(fields=["table", "owner", "business_date"])]


class SourceMap(models.Model):
    batch = models.ForeignKey(MigrationBatch, on_delete=models.PROTECT)
    table = models.CharField(max_length=100)
    source_pk = models.CharField(max_length=200)
    component = models.CharField(max_length=32, default="main")
    target_model = models.CharField(max_length=100)
    target_pk = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "table", "source_pk", "component"],
                name="legacy_unique_mapping",
            )
        ]


class MigrationIssue(models.Model):
    batch = models.ForeignKey(MigrationBatch, on_delete=models.PROTECT)
    key = models.CharField(max_length=180)
    severity = models.CharField(max_length=32)
    table = models.CharField(max_length=100)
    source_pk = models.CharField(max_length=200, blank=True)
    reason = models.TextField()
    details = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "key"], name="legacy_unique_issue")
        ]


class ArchiveShard(models.Model):
    batch = models.ForeignKey(MigrationBatch, on_delete=models.PROTECT)
    table = models.CharField(max_length=100)
    sequence = models.PositiveIntegerField()
    relative_path = models.CharField(max_length=240)
    rows = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    raw_sha256 = models.CharField(max_length=64)
    owner_ids = models.JSONField(default=list)
    min_date = models.DateField(null=True)
    max_date = models.DateField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "table", "sequence"], name="legacy_unique_shard"
            )
        ]


class PositionBasis(models.Model):
    """Verified imported state at the snapshot boundary, not a fabricated buy.

    Historical native trades are available for audit. Only trades after as_of
    advance this state; a separate cost_anchor preserves manual cost verification.
    """

    batch = models.ForeignKey(MigrationBatch, on_delete=models.PROTECT)
    source_invest_id = models.BigIntegerField()
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    account = models.ForeignKey("accounts.Account", on_delete=models.PROTECT)
    instrument = models.ForeignKey("investments.Instrument", on_delete=models.PROTECT)
    as_of = models.DateTimeField()
    quantity = models.DecimalField(max_digits=24, decimal_places=8)
    cost = models.DecimalField(max_digits=24, decimal_places=8)
    market_value = models.DecimalField(max_digits=24, decimal_places=8)
    profit = models.DecimalField(max_digits=24, decimal_places=8)
    price = models.DecimalField(max_digits=24, decimal_places=8)
    is_active = models.BooleanField(default=True)
    cost_anchor = models.JSONField(default=dict)
    is_auto_plan = models.BooleanField(default=False)
    attribution_verified = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "source_invest_id"], name="legacy_unique_position"
            )
        ]


class AccountBalanceBasis(models.Model):
    account = models.OneToOneField(
        "accounts.Account", on_delete=models.PROTECT, related_name="imported_balance"
    )
    batch = models.ForeignKey(MigrationBatch, on_delete=models.PROTECT)
    as_of = models.DateTimeField()
    balance = models.DecimalField(max_digits=24, decimal_places=8)
    available = models.DecimalField(max_digits=24, decimal_places=8, null=True)
    frozen = models.DecimalField(max_digits=24, decimal_places=8, null=True)


class LoanBalanceBasis(models.Model):
    loan = models.OneToOneField(
        "mortgages.Loan", on_delete=models.PROTECT, related_name="imported_balance"
    )
    batch = models.ForeignKey(MigrationBatch, on_delete=models.PROTECT)
    remaining_principal = models.DecimalField(max_digits=18, decimal_places=2)
    paid_periods = models.JSONField(default=list)
    as_of = models.DateTimeField()
