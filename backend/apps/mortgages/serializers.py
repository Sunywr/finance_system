from rest_framework import serializers

from apps.accounts.models import Account

from .models import Loan, LoanSchedule, OffsetPlan
from .services import loan_stats


class LoanScheduleSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = LoanSchedule
        fields = [
            "id",
            "period_no",
            "due_date",
            "principal_due",
            "interest_due",
            "total_due",
            "remaining_principal",
            "status",
            "status_label",
        ]


class LoanSerializer(serializers.ModelSerializer):
    stats = serializers.SerializerMethodField()
    loan_type_label = serializers.CharField(source="get_loan_type_display", read_only=True)
    repayment_method_label = serializers.CharField(source="get_repayment_method_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Loan
        fields = [
            "id",
            "name",
            "loan_type",
            "loan_type_label",
            "lender",
            "principal",
            "annual_rate",
            "term_months",
            "repayment_method",
            "repayment_method_label",
            "first_due_date",
            "payment_day",
            "repayment_account",
            "auto_settle",
            "status",
            "status_label",
            "note",
            "stats",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "stats", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["repayment_account"].queryset = Account.objects.filter(
                owner=request.user, is_active=True, type=Account.Type.SAVINGS
            )

    def get_stats(self, obj):
        stats = loan_stats(obj)
        return {
            "principal": stats["principal"],
            "total_interest": stats["total_interest"],
            "paid_principal": stats["paid_principal"],
            "paid_interest": stats["paid_interest"],
            "remaining_principal": stats["remaining_principal"],
            "paid_periods": stats["paid_periods"],
            "term_months": stats["term_months"],
            "next_due": LoanScheduleSerializer(stats["next_due"]).data if stats["next_due"] else None,
            "progress": stats["progress"],
        }

    def validate_principal(self, value):
        if value <= 0:
            raise serializers.ValidationError("贷款本金必须大于 0")
        return value

    def validate_term_months(self, value):
        if value < 1 or value > 600:
            raise serializers.ValidationError("期数必须在 1-600 之间")
        return value

    def validate_payment_day(self, value):
        if value < 1 or value > 31:
            raise serializers.ValidationError("还款日必须在 1-31 之间")
        return value


class OffsetPlanSerializer(serializers.ModelSerializer):
    mode_label = serializers.CharField(source="get_mode_display", read_only=True)

    class Meta:
        model = OffsetPlan
        fields = [
            "id",
            "loan",
            "pf_account",
            "enabled",
            "mode",
            "mode_label",
            "start_date",
            "monthly_cap",
            "use_new_contributions",
            "auto_pay_cash",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "loan", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["pf_account"].queryset = Account.objects.filter(
                owner=request.user,
                is_active=True,
                type__in=[Account.Type.PROVIDENT_FUND_MAIN, Account.Type.PROVIDENT_FUND_SUPP],
            )


class OffsetSimulationRequestSerializer(serializers.Serializer):
    use_new_contributions = serializers.BooleanField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=OffsetPlan.Mode.choices, required=False, allow_null=True)
    monthly_cap = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)
