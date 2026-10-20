from rest_framework import serializers

from .models import Asset, AssetValuation
from .services import asset_value, linked_transactions


class AssetValuationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssetValuation
        fields = ["id", "asset", "value", "valued_at", "note", "created_at"]
        read_only_fields = ["id", "asset", "created_at"]


class AssetSerializer(serializers.ModelSerializer):
    current_value = serializers.SerializerMethodField()
    linked_count = serializers.SerializerMethodField()
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Asset
        fields = [
            "id",
            "name",
            "type",
            "type_label",
            "valuation_mode",
            "manual_value",
            "acquired_date",
            "status",
            "status_label",
            "note",
            "current_value",
            "linked_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "current_value", "linked_count", "created_at", "updated_at"]

    def get_current_value(self, obj):
        return asset_value(obj)

    def get_linked_count(self, obj):
        return linked_transactions(obj).count()


class LinkedTransactionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    txn_no = serializers.CharField()
    occurred_at = serializers.DateTimeField()
    type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    asset_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    category_name = serializers.CharField()
    note = serializers.CharField()
