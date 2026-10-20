from django.db import transaction as db_transaction
from rest_framework import serializers

from apps.accounts.models import Account
from apps.assets.models import Asset
from apps.debts.models import CreditCard

from .models import (
    AccountTransfer,
    Category,
    InstallmentPeriod,
    InstallmentPlan,
    Tag,
    Transaction,
)
from .services import (
    create_installment_purchase,
    create_refund,
    create_transaction,
    create_transfer,
    preview_installment,
    update_transaction,
)


class CategorySerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "parent",
            "parent_name",
            "kind",
            "kind_label",
            "is_system",
            "is_active",
            "sort_order",
            "color",
            "icon",
            "children",
        ]
        read_only_fields = ["id", "kind", "is_system", "children"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["parent"].queryset = Category.objects.filter(owner=request.user, is_active=True)

    def get_children(self, obj):
        return CategorySerializer(obj.children.filter(is_active=True), many=True).data

    def validate(self, attrs):
        request = self.context.get("request")
        if request and request.method == "POST":
            attrs["kind"] = Category.Kind.GENERAL
            attrs["is_system"] = False
        if self.instance and self.instance.is_system:
            forbidden = {"kind", "is_system"}
            if any(field in attrs for field in forbidden):
                raise serializers.ValidationError("系统分类不能修改类型")
        return attrs


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ["id", "name", "color"]
        read_only_fields = ["id"]


class AccountTransferSerializer(serializers.ModelSerializer):
    from_account_name = serializers.CharField(source="from_account.name", read_only=True)
    to_account_name = serializers.CharField(source="to_account.name", read_only=True)

    class Meta:
        model = AccountTransfer
        fields = [
            "id",
            "from_account",
            "from_account_name",
            "to_account",
            "to_account_name",
            "amount",
            "fee",
            "occurred_at",
            "note",
            "out_transaction_id",
            "in_transaction_id",
            "created_at",
        ]
        read_only_fields = ["id", "out_transaction_id", "in_transaction_id", "created_at"]


class TransferCreateSerializer(serializers.Serializer):
    from_account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none())
    to_account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none())
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    fee = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=0)
    occurred_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(required=False, allow_null=True, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            qs = Account.objects.filter(owner=request.user, is_active=True)
            self.fields["from_account"].queryset = qs
            self.fields["to_account"].queryset = qs

    def create(self, validated_data):
        request = self.context["request"]
        return create_transfer(owner=request.user, **validated_data)


class InstallmentPeriodSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = InstallmentPeriod
        fields = [
            "id",
            "period_no",
            "bill_period_start",
            "bill_period_end",
            "due_date",
            "principal_part",
            "fee_part",
            "amount",
            "status",
            "status_label",
            "bill",
        ]


class InstallmentPlanSerializer(serializers.ModelSerializer):
    period_rows = InstallmentPeriodSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = InstallmentPlan
        fields = [
            "id",
            "credit_card",
            "purchase_transaction_id",
            "principal",
            "periods",
            "fee_mode",
            "fee_rate",
            "total_fee",
            "per_period_amount",
            "first_period_start",
            "status",
            "status_label",
            "period_rows",
        ]


class InstallmentPreviewSerializer(serializers.Serializer):
    credit_card = serializers.PrimaryKeyRelatedField(queryset=CreditCard.objects.none())
    principal = serializers.DecimalField(max_digits=18, decimal_places=2)
    periods = serializers.IntegerField(min_value=1, max_value=60)
    fee_mode = serializers.ChoiceField(choices=InstallmentPlan.FeeMode.choices, required=False, default="NONE")
    fee_rate = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, default=0)
    purchase_at = serializers.DateTimeField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            self.fields["credit_card"].queryset = CreditCard.objects.filter(owner=request.user, is_active=True)


class InstallmentInputSerializer(serializers.Serializer):
    periods = serializers.IntegerField(min_value=1, max_value=60)
    fee_mode = serializers.ChoiceField(choices=InstallmentPlan.FeeMode.choices, required=False, default="NONE")
    fee_rate = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, default=0)


class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    category_kind = serializers.CharField(source="category.kind", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    credit_card_name = serializers.CharField(source="credit_card.name", read_only=True)
    asset_name = serializers.CharField(source="asset.name", read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    channel_label = serializers.CharField(source="get_settlement_channel_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    operation_label = serializers.CharField(source="get_operation_display", read_only=True)
    refund_of_txn_no = serializers.CharField(source="refund_of.txn_no", read_only=True)
    installment_plan_id = serializers.IntegerField(read_only=True)
    transfer_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "txn_no",
            "type",
            "type_label",
            "category",
            "category_name",
            "category_kind",
            "tags",
            "occurred_at",
            "amount",
            "settlement_channel",
            "channel_label",
            "account",
            "account_name",
            "credit_card",
            "credit_card_name",
            "operation",
            "operation_label",
            "note",
            "transfer_id",
            "refund_of",
            "refund_of_txn_no",
            "installment_plan_id",
            "asset",
            "asset_name",
            "asset_amount",
            "status",
            "status_label",
            "source",
            "exclude_from_card_bill",
            "created_at",
            "updated_at",
        ]


class TransactionCreateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=Transaction.Type.choices)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.none(), required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    occurred_at = serializers.DateTimeField(required=False)
    settlement_channel = serializers.ChoiceField(
        choices=Transaction.SettlementChannel.choices, required=False
    )
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none(), required=False, allow_null=True)
    credit_card = serializers.PrimaryKeyRelatedField(
        queryset=CreditCard.objects.none(), required=False, allow_null=True
    )
    operation = serializers.ChoiceField(
        choices=Transaction.Operation.choices, required=False, default=Transaction.Operation.NONE
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.none(), many=True, required=False)
    tag_names = serializers.ListField(child=serializers.CharField(max_length=30), required=False)
    refund_of = serializers.PrimaryKeyRelatedField(
        queryset=Transaction.objects.none(), required=False, allow_null=True
    )
    cancel_installment = serializers.BooleanField(required=False, default=False)
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.none(), required=False, allow_null=True)
    asset_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)
    asset_name = serializers.CharField(required=False, allow_blank=True, max_length=100)
    asset_type = serializers.ChoiceField(choices=Asset.Type.choices, required=False, default=Asset.Type.OTHER)
    installment = InstallmentInputSerializer(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            user = request.user
            self.fields["category"].queryset = Category.objects.filter(owner=user, is_active=True)
            self.fields["account"].queryset = Account.objects.filter(owner=user, is_active=True)
            self.fields["credit_card"].queryset = CreditCard.objects.filter(owner=user, is_active=True)
            self.fields["tags"].child_relation.queryset = Tag.objects.filter(owner=user)
            self.fields["refund_of"].queryset = Transaction.objects.filter(owner=user, status=Transaction.Status.POSTED)
            self.fields["asset"].queryset = Asset.objects.filter(owner=user, status=Asset.Status.ACTIVE)

    def validate(self, attrs):
        txn_type = attrs.get("type")
        if txn_type != Transaction.Type.REFUND and not attrs.get("category"):
            raise serializers.ValidationError({"category": "请选择分类"})
        if txn_type == Transaction.Type.REFUND and not attrs.get("refund_of"):
            raise serializers.ValidationError({"refund_of": "退款必须选择原流水"})
        if attrs.get("installment") and not attrs.get("credit_card"):
            raise serializers.ValidationError({"credit_card": "分期必须选择信用卡"})
        if attrs.get("installment") and attrs.get("type") != Transaction.Type.EXPENSE:
            raise serializers.ValidationError({"type": "只有支出可以分期"})
        return attrs

    @db_transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        owner = request.user
        tags = list(validated_data.pop("tags", []) or [])
        for name in validated_data.pop("tag_names", []) or []:
            tag, _ = Tag.objects.get_or_create(owner=owner, name=name, defaults={"color": "#909399"})
            tags.append(tag)
        installment = validated_data.pop("installment", None)
        asset = validated_data.pop("asset", None)
        asset_amount = validated_data.pop("asset_amount", None)
        asset_name = validated_data.pop("asset_name", "")
        asset_type = validated_data.pop("asset_type", Asset.Type.OTHER)
        if not asset and asset_name:
            asset = Asset.objects.create(owner=owner, name=asset_name, type=asset_type)
        cancel_installment = validated_data.pop("cancel_installment", False)

        txn_type = validated_data.pop("type")
        if txn_type == Transaction.Type.REFUND:
            return create_refund(
                owner=owner,
                original=validated_data.pop("refund_of"),
                amount=validated_data.pop("amount"),
                occurred_at=validated_data.get("occurred_at"),
                note=validated_data.get("note", ""),
                cancel_installment=cancel_installment,
                asset=asset,
            )

        if installment:
            return create_installment_purchase(
                owner=owner,
                card=validated_data.pop("credit_card"),
                principal=validated_data.pop("amount"),
                periods=installment["periods"],
                occurred_at=validated_data.get("occurred_at") or None,
                category=validated_data.pop("category"),
                note=validated_data.get("note", ""),
                fee_mode=installment.get("fee_mode", InstallmentPlan.FeeMode.NONE),
                fee_rate=installment.get("fee_rate", 0),
                asset=asset,
            )[0]

        channel = validated_data.pop("settlement_channel", None)
        if not channel:
            credit_card = validated_data.get("credit_card")
            account = validated_data.get("account")
            if credit_card:
                channel = Transaction.SettlementChannel.CREDIT_CARD
            elif account:
                from .services import channel_for_account

                channel = channel_for_account(account)
            else:
                channel = Transaction.SettlementChannel.CASH
        return create_transaction(
            settlement_channel=channel,
            owner=owner,
            txn_type=txn_type,
            category=validated_data.pop("category"),
            amount=validated_data.pop("amount"),
            asset=asset,
            asset_amount=asset_amount,
            tags=tags,
            **validated_data,
        )


class TransactionUpdateSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=Transaction.Type.choices, required=False)
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.none(), required=False)
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    occurred_at = serializers.DateTimeField(required=False)
    settlement_channel = serializers.ChoiceField(choices=Transaction.SettlementChannel.choices, required=False)
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none(), required=False, allow_null=True)
    credit_card = serializers.PrimaryKeyRelatedField(
        queryset=CreditCard.objects.none(), required=False, allow_null=True
    )
    operation = serializers.ChoiceField(choices=Transaction.Operation.choices, required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.PrimaryKeyRelatedField(queryset=Tag.objects.none(), many=True, required=False)
    asset = serializers.PrimaryKeyRelatedField(queryset=Asset.objects.none(), required=False, allow_null=True)
    asset_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, allow_null=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            user = request.user
            self.fields["category"].queryset = Category.objects.filter(owner=user, is_active=True)
            self.fields["account"].queryset = Account.objects.filter(owner=user, is_active=True)
            self.fields["credit_card"].queryset = CreditCard.objects.filter(owner=user, is_active=True)
            self.fields["tags"].child_relation.queryset = Tag.objects.filter(owner=user)
            self.fields["asset"].queryset = Asset.objects.filter(owner=user, status=Asset.Status.ACTIVE)

    def update(self, instance, validated_data):
        tags = validated_data.pop("tags", None)
        return update_transaction(instance, data=validated_data, tags=tags)


class RefundCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    occurred_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    cancel_installment = serializers.BooleanField(required=False, default=False)


class VoidSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")
