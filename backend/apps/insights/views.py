from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AIAnalysis, AIProviderConfig
from .serializers import (
    AIAnalysisDetailSerializer,
    AIAnalysisListSerializer,
    AIProviderConfigSerializer,
    AnalysisCreateSerializer,
)
from .services import meta_enums, monthly_series, overview, test_provider


@extend_schema_view(
    list=extend_schema(tags=["ai"]),
    create=extend_schema(tags=["ai"]),
    retrieve=extend_schema(tags=["ai"]),
    update=extend_schema(tags=["ai"]),
    partial_update=extend_schema(tags=["ai"]),
    destroy=extend_schema(tags=["ai"]),
)
class AIProviderViewSet(viewsets.ModelViewSet):
    serializer_class = AIProviderConfigSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["enabled", "is_default"]

    def get_queryset(self):
        return AIProviderConfig.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @extend_schema(summary="测试 AI 连接", tags=["ai"])
    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        provider = self.get_object()
        try:
            return Response(test_provider(provider))
        except Exception as exc:
            return Response({"ok": False, "error": str(exc)}, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(tags=["ai"]),
    retrieve=extend_schema(tags=["ai"]),
    create=extend_schema(tags=["ai"]),
)
class AIAnalysisViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["analysis_type", "status", "provider"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return AIAnalysis.objects.filter(owner=self.request.user).select_related("provider")

    def get_serializer_class(self):
        if self.action == "create":
            return AnalysisCreateSerializer
        if self.action == "list":
            return AIAnalysisListSerializer
        return AIAnalysisDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        analysis = serializer.save()
        return Response(AIAnalysisDetailSerializer(analysis).data, status=status.HTTP_201_CREATED)


class DashboardOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="总览数据", tags=["dashboard"])
    def get(self, request):
        as_of = request.query_params.get("as_of")
        return Response(overview(request.user, as_of=as_of))


class CashflowSeriesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="现金流月度序列", tags=["dashboard"])
    def get(self, request):
        months_back = int(request.query_params.get("months_back", 6))
        months_forward = int(request.query_params.get("months_forward", 3))
        return Response(
            {
                "monthly": monthly_series(
                    request.user, months_back=months_back, months_forward=months_forward
                )
            }
        )


class MetaEnumsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="枚举字典", tags=["system"])
    def get(self, request):
        return Response(meta_enums())
