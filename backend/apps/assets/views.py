from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Asset
from .serializers import AssetSerializer, AssetValuationSerializer, LinkedTransactionSerializer
from .services import linked_transactions


@extend_schema_view(
    list=extend_schema(tags=["assets"]),
    create=extend_schema(tags=["assets"]),
    retrieve=extend_schema(tags=["assets"]),
    update=extend_schema(tags=["assets"]),
    partial_update=extend_schema(tags=["assets"]),
    destroy=extend_schema(tags=["assets"]),
)
class AssetViewSet(viewsets.ModelViewSet):
    serializer_class = AssetSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["type", "status", "valuation_mode"]
    search_fields = ["name", "note"]
    ordering_fields = ["created_at", "name"]

    def get_queryset(self):
        return Asset.objects.filter(owner=self.request.user).prefetch_related("valuations")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @extend_schema(summary="资产关联流水", tags=["assets"], responses=LinkedTransactionSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="transactions")
    def transactions(self, request, pk=None):
        asset = self.get_object()
        rows = []
        for txn in linked_transactions(asset):
            rows.append(
                {
                    "id": txn.id,
                    "txn_no": txn.txn_no,
                    "occurred_at": txn.occurred_at,
                    "type": txn.type,
                    "amount": txn.amount,
                    "asset_amount": txn.asset_amount,
                    "category_name": txn.category.name if txn.category else "",
                    "note": txn.note,
                }
            )
        return Response(rows)

    @extend_schema(
        summary="资产估值历史/新增估值",
        tags=["assets"],
        request=AssetValuationSerializer,
        responses=AssetValuationSerializer(many=True),
    )
    @action(detail=True, methods=["get", "post"], url_path="valuations")
    def valuations(self, request, pk=None):
        asset = self.get_object()
        if request.method == "GET":
            return Response(AssetValuationSerializer(asset.valuations.all(), many=True).data)
        serializer = AssetValuationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(asset=asset)
        if asset.valuation_mode == Asset.ValuationMode.MANUAL:
            asset.manual_value = serializer.validated_data["value"]
            asset.save(update_fields=["manual_value", "updated_at"])
        return Response(serializer.data, status=201)
