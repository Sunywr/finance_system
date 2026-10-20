from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Loan, OffsetPlan
from .serializers import (
    LoanScheduleSerializer,
    LoanSerializer,
    OffsetPlanSerializer,
    OffsetSimulationRequestSerializer,
)
from .services import generate_schedule, loan_stats, simulate_offset


@extend_schema_view(
    list=extend_schema(tags=["mortgages"]),
    create=extend_schema(tags=["mortgages"]),
    retrieve=extend_schema(tags=["mortgages"]),
    update=extend_schema(tags=["mortgages"]),
    partial_update=extend_schema(tags=["mortgages"]),
    destroy=extend_schema(tags=["mortgages"]),
)
class LoanViewSet(viewsets.ModelViewSet):
    serializer_class = LoanSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["loan_type", "repayment_method", "status"]
    search_fields = ["name", "lender"]
    ordering_fields = ["created_at", "first_due_date", "principal"]

    def get_queryset(self):
        return Loan.objects.filter(owner=self.request.user).select_related("offset_plan")

    def perform_create(self, serializer):
        loan = serializer.save(owner=self.request.user)
        generate_schedule(loan)

    def perform_update(self, serializer):
        loan = serializer.save()
        if loan.status == Loan.Status.ACTIVE:
            generate_schedule(loan)

    @extend_schema(summary="完整还款计划", tags=["mortgages"], responses=LoanScheduleSerializer(many=True))
    @action(detail=True, methods=["get"])
    def schedule(self, request, pk=None):
        loan = self.get_object()
        return Response(LoanScheduleSerializer(loan.schedules.all(), many=True).data)

    @extend_schema(summary="贷款统计", tags=["mortgages"])
    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        loan = self.get_object()
        stats = loan_stats(loan)
        return Response(
            {
                **{key: value for key, value in stats.items() if key != "next_due"},
                "next_due": LoanScheduleSerializer(stats["next_due"]).data if stats["next_due"] else None,
            }
        )

    @extend_schema(
        summary="公积金冲还配置",
        tags=["mortgages"],
        request=OffsetPlanSerializer,
        responses=OffsetPlanSerializer,
    )
    @action(detail=True, methods=["get", "put"], url_path="offset-plan")
    def offset_plan(self, request, pk=None):
        loan = self.get_object()
        plan = getattr(loan, "offset_plan", None)
        if request.method == "GET":
            if not plan:
                return Response({"detail": "尚未配置公积金冲还"})
            return Response(OffsetPlanSerializer(plan, context={"request": request}).data)
        if plan:
            serializer = OffsetPlanSerializer(plan, data=request.data, partial=True, context={"request": request})
        else:
            serializer = OffsetPlanSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(loan=loan)
        return Response(serializer.data)

    @extend_schema(
        summary="公积金冲还模拟",
        tags=["mortgages"],
        request=OffsetSimulationRequestSerializer,
        responses=dict,
    )
    @action(detail=True, methods=["get", "post"], url_path="offset-simulation")
    def offset_simulation(self, request, pk=None):
        loan = self.get_object()
        data = {}
        if request.method == "POST":
            serializer = OffsetSimulationRequestSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
        else:
            raw_use_new = request.query_params.get("use_new_contributions")
            if raw_use_new is not None:
                data["use_new_contributions"] = raw_use_new.strip().lower() in {"1", "true", "yes", "on"}
            if request.query_params.get("mode"):
                data["mode"] = request.query_params["mode"]
            if request.query_params.get("monthly_cap"):
                data["monthly_cap"] = request.query_params["monthly_cap"]
        result = simulate_offset(
            loan,
            use_new_contributions=data.get("use_new_contributions"),
            mode=data.get("mode"),
            monthly_cap=data.get("monthly_cap"),
        )
        return Response(result)
