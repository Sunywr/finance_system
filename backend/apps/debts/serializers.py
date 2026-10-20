from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Account
from apps.ledger.models import Category, InstallmentPlan
from apps.ledger.serializers import InstallmentPlanSerializer

from .models import CreditCard, CreditCardBill, DebtItem, DebtPayment, RecurringDebt
from .services import card_summary, create_recurring_items


class CreditCardSerializer(serializers.ModelSerializer):
    current_summary = serializers.SerializerMethodField()

    class Meta:
        model = CreditCard
        fields = [
            "id",
            "name",
            "bank",
            "last4",
            "statement_start_day",
            "statement_end_day",
            "due_day",
            "credit_limit",
            "min_payment_rate",
            "is_active",
            "sort_order",
            "note",
            "current_summary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "current_summary", "created_at", "updated_at"]

    def get_current_summary(self, obj):
        summary = card_summary(obj)
        return {
            "period_start": summary["current_period_start"],
            "period_end": summary["current_period_end"],
            "due_date": summary["current_due_date"],
            "total": summary["current_total"],
            "min_payment": summary["current_min_payment"],
            "used_credit": summary["used_credit"],
            "available_credit": summary["available_credit"],
        }

    def validate(self, attrs):
        start = attrs.get("statement_start_day", getattr(self.instance, "statement_start_day", 1))
        end = attrs.get("statement_end_day", getattr(self.instance, "statement_end_day", 28))
        if start == end:
            raise serializers.ValidationError("账单起始日和结束日不能相同")
        return attrs


class CreditCardBillSerializer(serializers.ModelSerializer):
    card_name = serializers.CharField(source="card.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    period_label = serializers.SerializerMethodField()
    debt_item_id = serializers.SerializerMethodField()
    debt_status = serializers.SerializerMethodField()
    debt_status_label = serializers.SerializerMethodField()
    payable_amount = serializers.SerializerMethodField()
    installment_periods = serializers.SerializerMethodField()

    class Meta:
        model = CreditCardBill
        fields = [
            "id",
            "card",
            "card_name",
            "period_start",
            "period_end",
            "period_label",
            "due_date",
            "normal_total",
            "installment_total",
            "refund_total",
            "total_amount",
            "min_payment",
            "status",
            "status_label",
            "generated_at",
            "debt_item_id",
            "debt_status",
            "debt_status_label",
            "payable_amount",
            "installment_periods",
        ]

    def get_period_label(self, obj):
        return f"{obj.period_start:%Y-%m-%d} ~ {obj.period_end:%Y-%m-%d}"

    def _debt(self, obj):
        return getattr(obj, "debt_item", None)

    def get_debt_item_id(self, obj):
        debt = self._debt(obj)
        return debt.id if debt else None

    def get_debt_status(self, obj):
        debt = self._debt(obj)
        return debt.status if debt else None

    def get_debt_status_label(self, obj):
        debt = self._debt(obj)
        return debt.get_status_display() if debt else "未生成"

    def get_payable_amount(self, obj):
        debt = self._debt(obj)
        return debt.payable_amount if debt else obj.total_amount

    def get_installment_periods(self, obj):
        return [
            {
                "period_no": period.period_no,
                "amount": period.amount,
                "principal_part": period.principal_part,
                "fee_part": period.fee_part,
                "status": period.status,
            }
            for period in obj.installment_periods.all()
        ]


class DebtPaymentSerializer(serializers.ModelSerializer):
    channel_label = serializers.CharField(source="get_channel_display", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    credit_card_name = serializers.CharField(source="credit_card.name", read_only=True)

    class Meta:
        model = DebtPayment
        fields = [
            "id",
            "debt_item",
            "amount",
            "discount_amount",
            "channel",
            "channel_label",
            "account",
            "account_name",
            "credit_card",
            "credit_card_name",
            "paid_at",
            "transaction_id",
            "note",
        ]


class DebtItemSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    payable_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    card_name = serializers.CharField(source="bill.card.name", read_only=True)
    recurring_name = serializers.CharField(source="recurring_debt.name", read_only=True)
    loan_name = serializers.CharField(source="loan_schedule.loan.name", read_only=True)
    payments = DebtPaymentSerializer(many=True, read_only=True)
    days_until_due = serializers.SerializerMethodField()

    class Meta:
        model = DebtItem
        fields = [
            "id",
            "kind",
            "kind_label",
            "bill",
            "card_name",
            "recurring_debt",
            "recurring_name",
            "loan_schedule",
            "loan_name",
            "title",
            "period_no",
            "due_date",
            "amount",
            "discount_amount",
            "paid_amount",
            "payable_amount",
            "status",
            "status_label",
            "settled_at",
            "note",
            "payments",
            "days_until_due",
            "created_at",
            "updated_at",
        ]

    def get_days_until_due(self, obj):
        return (obj.due_date - timezone.localdate()).days


class PayDebtSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=0)
    discount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=0)
    channel = serializers.ChoiceField(choices=DebtPayment.Channel.choices, required=False, default="CASH")
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none(), required=False, allow_null=True)
    credit_card = serializers.PrimaryKeyRelatedField(
        queryset=CreditCard.objects.none(), required=False, allow_null=True
    )
    paid_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["account"].queryset = Account.objects.filter(owner=request.user, is_active=True)
            self.fields["credit_card"].queryset = CreditCard.objects.filter(owner=request.user, is_active=True)

    def validate(self, attrs):
        if not attrs.get("amount") and not attrs.get("discount"):
            raise serializers.ValidationError("还款金额和减免金额不能同时为 0")
        return attrs


class RecurringDebtSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()
    paid_count = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    debt_type_label = serializers.CharField(source="get_debt_type_display", read_only=True)
    category = serializers.PrimaryKeyRelatedField(
        source="category_id", queryset=Category.objects.none(), required=False, allow_null=True
    )

    class Meta:
        model = RecurringDebt
        fields = [
            "id",
            "name",
            "debt_type",
            "debt_type_label",
            "amount",
            "periods",
            "interval_months",
            "first_due_date",
            "due_day",
            "payment_channel",
            "account",
            "credit_card",
            "category",
            "auto_pay",
            "note",
            "status",
            "status_label",
            "items_count",
            "paid_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "items_count", "paid_count", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            user = request.user
            self.fields["account"].queryset = Account.objects.filter(owner=user, is_active=True)
            self.fields["credit_card"].queryset = CreditCard.objects.filter(owner=user, is_active=True)
            self.fields["category"].queryset = Category.objects.filter(
                owner=user, kind=Category.Kind.GENERAL, is_active=True
            )

    def get_items_count(self, obj):
        return obj.items.count()

    def get_paid_count(self, obj):
        return obj.items.filter(status=DebtItem.Status.PAID).count()

    def validate(self, attrs):
        channel = attrs.get("payment_channel", getattr(self.instance, "payment_channel", "CASH"))
        credit_card = attrs.get("credit_card", getattr(self.instance, "credit_card", None))
        account = attrs.get("account", getattr(self.instance, "account", None))
        if channel == "CREDIT_CARD":
            if not credit_card:
                raise serializers.ValidationError({"credit_card": "信用卡支付请选择信用卡"})
        elif attrs.get("auto_pay", getattr(self.instance, "auto_pay", False)) and not account:
            raise serializers.ValidationError({"account": "自动支付请选择支付账户"})
        return attrs


class BillSummarySerializer(serializers.Serializer):
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    due_date = serializers.DateField()
    total = serializers.DecimalField(max_digits=18, decimal_places=2)
    min_payment = serializers.DecimalField(max_digits=18, decimal_places=2)
    used_credit = serializers.DecimalField(max_digits=18, decimal_places=2)
    available_credit = serializers.DecimalField(max_digits=18, decimal_places=2)
