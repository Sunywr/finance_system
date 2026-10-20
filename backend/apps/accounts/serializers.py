from django.utils import timezone
from rest_framework import serializers

from apps.common.utils.dates import next_payday

from .models import Account, ProvidentFundProfile, UserSetting
from .services import account_balance


class ProvidentFundProfileSerializer(serializers.ModelSerializer):
    monthly_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = ProvidentFundProfile
        fields = [
            "id",
            "account",
            "fund_type",
            "monthly_employee_amount",
            "monthly_employer_amount",
            "monthly_total",
            "contribution_day",
            "auto_contribute",
            "city",
        ]
        read_only_fields = ["id", "account"]


class AccountSerializer(serializers.ModelSerializer):
    current_balance = serializers.SerializerMethodField()
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    pf_profile = ProvidentFundProfileSerializer(read_only=True)

    class Meta:
        model = Account
        fields = [
            "id",
            "name",
            "type",
            "type_label",
            "institution",
            "account_no_masked",
            "currency",
            "opening_balance",
            "opening_date",
            "allow_negative",
            "is_active",
            "sort_order",
            "note",
            "current_balance",
            "pf_profile",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "current_balance", "pf_profile"]

    def get_current_balance(self, obj):
        return account_balance(obj)


class AccountBalanceSerializer(serializers.Serializer):
    opening_balance = serializers.DecimalField(max_digits=18, decimal_places=2)
    income = serializers.DecimalField(max_digits=18, decimal_places=2)
    refund = serializers.DecimalField(max_digits=18, decimal_places=2)
    expense = serializers.DecimalField(max_digits=18, decimal_places=2)
    transfer_in = serializers.DecimalField(max_digits=18, decimal_places=2)
    transfer_out = serializers.DecimalField(max_digits=18, decimal_places=2)
    current_balance = serializers.DecimalField(max_digits=18, decimal_places=2)


class UserSettingSerializer(serializers.ModelSerializer):
    salary_account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none(), allow_null=True, required=False)
    next_payday = serializers.SerializerMethodField()

    class Meta:
        model = UserSetting
        fields = [
            "id",
            "payday",
            "salary_amount",
            "salary_account",
            "currency",
            "dashboard_prefs",
            "next_payday",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at", "next_payday"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["salary_account"].queryset = Account.objects.filter(owner=request.user, is_active=True)

    def get_next_payday(self, obj):
        return next_payday(timezone.localdate(), obj.payday)
