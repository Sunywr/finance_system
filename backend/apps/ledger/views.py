from datetime import date

from django.db.models import Q
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.utils.dates import day_end, day_start

from .models import AccountTransfer, Category, Tag, Transaction
from .serializers import (
    AccountTransferSerializer,
    CategorySerializer,
    InstallmentPreviewSerializer,
    RefundCreateSerializer,
    TagSerializer,
    TransactionCreateSerializer,
    TransactionSerializer,
    TransactionUpdateSerializer,
    TransferCreateSerializer,
    VoidSerializer,
)
from .services import create_refund, preview_installment, void_transaction


@extend_schema_view(
    list=extend_schema(tags=["categories"]),
    create=extend_schema(tags=["categories"]),
    update=extend_schema(tags=["categories"]),
    partial_update=extend_schema(tags=["categories"]),
    destroy=extend_schema(tags=["categories"]),
)
class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["kind", "parent", "is_active"]
    search_fields = ["name"]

    def get_queryset(self):
        return Category.objects.filter(owner=self.request.user).select_related("parent")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        if instance.is_system:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({"detail": "系统分类不能删除"})
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @extend_schema(summary="分类树", tags=["categories"], responses=CategorySerializer(many=True))
    @action(detail=False, methods=["get"])
    def tree(self, request):
        roots = self.get_queryset().filter(parent__isnull=True, is_active=True)
        return Response(CategorySerializer(roots, many=True).data)


@extend_schema_view(
    list=extend_schema(tags=["tags"]),
    create=extend_schema(tags=["tags"]),
    update=extend_schema(tags=["tags"]),
    partial_update=extend_schema(tags=["tags"]),
    destroy=extend_schema(tags=["tags"]),
)
class TagViewSet(viewsets.ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated]
    search_fields = ["name"]

    def get_queryset(self):
        return Tag.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


@extend_schema_view(
    list=extend_schema(tags=["transactions"]),
    create=extend_schema(tags=["transactions"]),
    retrieve=extend_schema(tags=["transactions"]),
    update=extend_schema(tags=["transactions"]),
    partial_update=extend_schema(tags=["transactions"]),
    destroy=extend_schema(tags=["transactions"]),
)
class TransactionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filterset_fields = [
        "type",
        "category",
        "account",
        "credit_card",
        "status",
        "source",
        "asset",
        "settlement_channel",
        "operation",
    ]
    search_fields = ["txn_no", "note"]
    ordering_fields = ["occurred_at", "amount", "created_at"]

    def get_queryset(self):
        qs = (
            Transaction.objects.filter(owner=self.request.user)
            .select_related("category", "account", "credit_card", "asset", "refund_of", "transfer")
            .prefetch_related("tags")
        )
        params = self.request.query_params
        date_from = params.get("date_from")
        date_to = params.get("date_to")
        if date_from:
            qs = qs.filter(occurred_at__gte=day_start(date_from))
        if date_to:
            qs = qs.filter(occurred_at__lte=day_end(date_to))
        month = params.get("month")
        if month:
            try:
                year, month_num = month.split("-")
                start = date(int(year), int(month_num), 1)
                end = date(
                    start.year + (1 if start.month == 12 else 0),
                    1 if start.month == 12 else start.month + 1,
                    1,
                )
                qs = qs.filter(occurred_at__gte=day_start(start), occurred_at__lt=day_start(end))
            except (ValueError, TypeError):
                pass
        tag = params.get("tag")
        if tag:
            qs = qs.filter(tags__id=tag)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return TransactionCreateSerializer
        if self.action in ("update", "partial_update"):
            return TransactionUpdateSerializer
        return TransactionSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        txn = serializer.save()
        return Response(TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        txn = serializer.save()
        return Response(TransactionSerializer(txn).data)

    def perform_destroy(self, instance):
        void_transaction(instance, reason="删除即作废")

    @extend_schema(summary="退款", tags=["transactions"], request=RefundCreateSerializer, responses=TransactionSerializer)
    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        txn = self.get_object()
        serializer = RefundCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund = create_refund(owner=request.user, original=txn, **serializer.validated_data)
        return Response(TransactionSerializer(refund).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary="作废流水", tags=["transactions"], request=VoidSerializer, responses=TransactionSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        txn = self.get_object()
        serializer = VoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        void_transaction(txn, reason=serializer.validated_data.get("reason", ""))
        txn.refresh_from_db()
        return Response(TransactionSerializer(txn).data)

    @extend_schema(
        summary="分期试算",
        tags=["transactions"],
        request=InstallmentPreviewSerializer,
        responses=dict,
    )
    @action(detail=False, methods=["post"], url_path="installment-preview")
    def installment_preview(self, request):
        serializer = InstallmentPreviewSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = preview_installment(
            card=data["credit_card"],
            principal=data["principal"],
            periods=data["periods"],
            fee_mode=data.get("fee_mode", "NONE"),
            fee_rate=data.get("fee_rate", 0),
            purchase_at=data.get("purchase_at"),
        )
        return Response(result)


@extend_schema_view(
    list=extend_schema(tags=["transfers"]),
    create=extend_schema(tags=["transfers"]),
    retrieve=extend_schema(tags=["transfers"]),
)
class AccountTransferViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    filterset_fields = ["from_account", "to_account"]
    ordering_fields = ["occurred_at", "amount"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return AccountTransfer.objects.filter(owner=self.request.user).select_related(
            "from_account", "to_account"
        )

    def get_serializer_class(self):
        if self.action == "create":
            return TransferCreateSerializer
        return AccountTransferSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        transfer = serializer.save()
        return Response(
            AccountTransferSerializer(transfer).data, status=status.HTTP_201_CREATED
        )
