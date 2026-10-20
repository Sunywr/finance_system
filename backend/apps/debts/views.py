from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import CreditCard, CreditCardBill, DebtItem, DebtPayment, RecurringDebt
from .serializers import (
    CreditCardBillSerializer,
    CreditCardSerializer,
    DebtItemSerializer,
    DebtPaymentSerializer,
    PayDebtSerializer,
    RecurringDebtSerializer,
)
from .services import (
    card_summary,
    create_recurring_items,
    generate_all_debt_items,
    generate_due_bills,
    mark_overdue,
    settle_debt,
)


def _idempotency(request, data):
    return data.get("idempotency_key") or request.headers.get("Idempotency-Key")


@extend_schema_view(
    list=extend_schema(tags=["credit-cards"]),
    create=extend_schema(tags=["credit-cards"]),
    retrieve=extend_schema(tags=["credit-cards"]),
    update=extend_schema(tags=["credit-cards"]),
    partial_update=extend_schema(tags=["credit-cards"]),
    destroy=extend_schema(tags=["credit-cards"]),
)
class CreditCardViewSet(viewsets.ModelViewSet):
    serializer_class = CreditCardSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["is_active"]
    search_fields = ["name", "bank", "last4"]

    def get_queryset(self):
        return CreditCard.objects.filter(owner=self.request.user).prefetch_related("bills")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @extend_schema(summary="当前账单周期概览", tags=["credit-cards"])
    @action(detail=True, methods=["get"])
    def current(self, request, pk=None):
        card = self.get_object()
        summary = card_summary(card)
        return Response(
            {
                "card": CreditCardSerializer(card).data,
                "period_start": summary["current_period_start"],
                "period_end": summary["current_period_end"],
                "due_date": summary["current_due_date"],
                "normal_total": summary["current_normal_total"],
                "installment_total": summary["current_installment_total"],
                "refund_total": summary["current_refund_total"],
                "total": summary["current_total"],
                "min_payment": summary["current_min_payment"],
                "credit_limit": summary["credit_limit"],
                "used_credit": summary["used_credit"],
                "available_credit": summary["available_credit"],
                "next_due": DebtItemSerializer(summary["next_due"]).data if summary["next_due"] else None,
            }
        )

    @extend_schema(summary="信用卡账单列表", tags=["credit-cards"], responses=CreditCardBillSerializer(many=True))
    @action(detail=True, methods=["get"])
    def bills(self, request, pk=None):
        card = self.get_object()
        bills = card.bills.select_related("card").prefetch_related("installment_periods").all()
        return Response(CreditCardBillSerializer(bills, many=True).data)

    @extend_schema(summary="信用卡分期列表", tags=["credit-cards"])
    @action(detail=True, methods=["get"])
    def installments(self, request, pk=None):
        card = self.get_object()
        from apps.ledger.serializers import InstallmentPlanSerializer

        return Response(InstallmentPlanSerializer(card.installment_plans.all(), many=True).data)

    @extend_schema(summary="生成当前账单", tags=["credit-cards"])
    @action(detail=False, methods=["post"])
    def generate(self, request):
        stats = generate_due_bills(owner=request.user)
        stats.update(generate_all_debt_items(owner=request.user))
        stats["overdue"] = mark_overdue()
        return Response(stats)


@extend_schema_view(
    list=extend_schema(tags=["bills"]),
    retrieve=extend_schema(tags=["bills"]),
)
class CreditCardBillViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CreditCardBillSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["card", "status"]
    ordering_fields = ["period_start", "due_date", "total_amount"]

    def get_queryset(self):
        return (
            CreditCardBill.objects.filter(owner=self.request.user)
            .select_related("card")
            .prefetch_related("installment_periods", "debt_item__payments")
        )

    @extend_schema(summary="账单还款", tags=["bills"], request=PayDebtSerializer, responses=DebtPaymentSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        bill = self.get_object()
        debt = getattr(bill, "debt_item", None)
        if not debt:
            raise ValidationError({"detail": "该账单尚未生成债务项"})
        serializer = PayDebtSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment = settle_debt(
            owner=request.user,
            debt_item=debt,
            amount=data.get("amount", 0),
            discount=data.get("discount", 0),
            channel=data.get("channel", DebtPayment.Channel.CASH),
            account=data.get("account"),
            credit_card=data.get("credit_card"),
            paid_at=data.get("paid_at"),
            note=data.get("note", ""),
            idempotency_key=_idempotency(request, data),
        )
        return Response(DebtPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(tags=["debts"]),
    retrieve=extend_schema(tags=["debts"]),
)
class DebtItemViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DebtItemSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["kind", "status", "bill", "recurring_debt", "loan_schedule"]
    search_fields = ["title"]
    ordering_fields = ["due_date", "amount", "created_at"]

    def get_queryset(self):
        qs = (
            DebtItem.objects.filter(owner=self.request.user)
            .select_related("bill__card", "recurring_debt", "loan_schedule__loan")
            .prefetch_related("payments")
        )
        params = self.request.query_params
        if params.get("due_before"):
            qs = qs.filter(due_date__lte=params["due_before"])
        if params.get("due_after"):
            qs = qs.filter(due_date__gte=params["due_after"])
        if params.get("month"):
            try:
                year, month = params["month"].split("-")
                qs = qs.filter(due_date__year=int(year), due_date__month=int(month))
            except (ValueError, TypeError):
                pass
        return qs

    @extend_schema(summary="债务还款", tags=["debts"], request=PayDebtSerializer, responses=DebtPaymentSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        debt = self.get_object()
        serializer = PayDebtSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment = settle_debt(
            owner=request.user,
            debt_item=debt,
            amount=data.get("amount", 0),
            discount=data.get("discount", 0),
            channel=data.get("channel", DebtPayment.Channel.CASH),
            account=data.get("account"),
            credit_card=data.get("credit_card"),
            paid_at=data.get("paid_at"),
            note=data.get("note", ""),
            idempotency_key=_idempotency(request, data),
        )
        return Response(DebtPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @extend_schema(summary="取消债务项", tags=["debts"], request=None)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        debt = self.get_object()
        if debt.paid_amount > 0:
            raise ValidationError({"detail": "已有还款记录，不能取消"})
        if debt.kind == DebtItem.Kind.CREDIT_CARD:
            raise ValidationError({"detail": "信用卡账单不能取消"})
        debt.status = DebtItem.Status.CANCELLED
        debt.save(update_fields=["status", "updated_at"])
        if debt.loan_schedule_id:
            debt.loan_schedule.status = "CANCELLED"
            debt.loan_schedule.save(update_fields=["status", "updated_at"])
        return Response(DebtItemSerializer(debt).data)

    @extend_schema(summary="债务汇总", tags=["debts"])
    @action(detail=False, methods=["get"])
    def summary(self, request):
        qs = self.get_queryset().exclude(status__in=[DebtItem.Status.PAID, DebtItem.Status.CANCELLED])
        total = sum((item.payable_amount for item in qs), 0)
        by_kind = {}
        for item in qs:
            by_kind[item.kind] = by_kind.get(item.kind, 0) + item.payable_amount
        overdue = qs.filter(due_date__lt=timezone.localdate()).count()
        return Response(
            {
                "unpaid_total": total,
                "by_kind": by_kind,
                "overdue_count": overdue,
                "unpaid_count": qs.count(),
            }
        )

    @extend_schema(summary="生成债务项", tags=["debts"])
    @action(detail=False, methods=["post"])
    def generate(self, request):
        stats = generate_due_bills(owner=request.user)
        stats.update(generate_all_debt_items(owner=request.user))
        stats["overdue"] = mark_overdue()
        return Response(stats)


@extend_schema_view(
    list=extend_schema(tags=["recurring-debts"]),
    create=extend_schema(tags=["recurring-debts"]),
    retrieve=extend_schema(tags=["recurring-debts"]),
    update=extend_schema(tags=["recurring-debts"]),
    partial_update=extend_schema(tags=["recurring-debts"]),
    destroy=extend_schema(tags=["recurring-debts"]),
)
class RecurringDebtViewSet(viewsets.ModelViewSet):
    serializer_class = RecurringDebtSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["debt_type", "status", "payment_channel"]
    search_fields = ["name", "note"]

    def get_queryset(self):
        return RecurringDebt.objects.filter(owner=self.request.user).select_related(
            "account", "credit_card"
        )

    def perform_create(self, serializer):
        recurring = serializer.save(owner=self.request.user)
        create_recurring_items(recurring)

    def perform_update(self, serializer):
        recurring = serializer.save()
        if recurring.status == RecurringDebt.Status.ACTIVE:
            create_recurring_items(recurring)
        else:
            recurring.items.exclude(status__in=[DebtItem.Status.PAID, DebtItem.Status.CANCELLED]).update(
                status=DebtItem.Status.CANCELLED
            )

    def perform_destroy(self, instance):
        instance.status = RecurringDebt.Status.CANCELLED
        instance.save(update_fields=["status", "updated_at"])
        instance.items.exclude(status__in=[DebtItem.Status.PAID, DebtItem.Status.CANCELLED]).update(
            status=DebtItem.Status.CANCELLED
        )

    @extend_schema(summary="周期债务的期次", tags=["recurring-debts"], responses=DebtItemSerializer(many=True))
    @action(detail=True, methods=["get"])
    def items(self, request, pk=None):
        recurring = self.get_object()
        return Response(DebtItemSerializer(recurring.items.all(), many=True).data)


@extend_schema_view(list=extend_schema(tags=["debt-payments"]), retrieve=extend_schema(tags=["debt-payments"]))
class DebtPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DebtPaymentSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["debt_item", "channel"]
    ordering_fields = ["paid_at", "amount"]

    def get_queryset(self):
        return DebtPayment.objects.filter(owner=self.request.user).select_related(
            "account", "credit_card", "debt_item"
        )
