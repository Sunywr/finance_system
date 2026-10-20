from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Account, ProvidentFundProfile, UserSetting
from .serializers import (
    AccountBalanceSerializer,
    AccountSerializer,
    ProvidentFundProfileSerializer,
    UserSettingSerializer,
)
from .services import balance_breakdown


@extend_schema_view(
    list=extend_schema(tags=["accounts"]),
    create=extend_schema(tags=["accounts"]),
    retrieve=extend_schema(tags=["accounts"]),
    update=extend_schema(tags=["accounts"]),
    partial_update=extend_schema(tags=["accounts"]),
)
class AccountViewSet(viewsets.ModelViewSet):
    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["type", "is_active"]
    search_fields = ["name", "institution", "note"]
    ordering_fields = ["sort_order", "created_at", "name"]

    def get_queryset(self):
        return Account.objects.filter(owner=self.request.user).select_related("pf_profile")

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])

    @extend_schema(summary="账户余额构成", tags=["accounts"], responses=AccountBalanceSerializer)
    @action(detail=True, methods=["get"])
    def balance(self, request, pk=None):
        account = self.get_object()
        as_of = request.query_params.get("as_of")
        return Response(balance_breakdown(account, as_of))

    @extend_schema(
        summary="公积金账户配置",
        tags=["accounts"],
        request=ProvidentFundProfileSerializer,
        responses=ProvidentFundProfileSerializer,
    )
    @action(detail=True, methods=["get", "put"], url_path="pf-profile")
    def pf_profile(self, request, pk=None):
        account = self.get_object()
        if account.type not in [Account.Type.PROVIDENT_FUND_MAIN, Account.Type.PROVIDENT_FUND_SUPP]:
            return Response({"detail": "该账户不是公积金账户"}, status=status.HTTP_400_BAD_REQUEST)
        profile, _ = ProvidentFundProfile.objects.get_or_create(
            account=account,
            defaults={
                "fund_type": ProvidentFundProfile.FundType.MAIN
                if account.type == Account.Type.PROVIDENT_FUND_MAIN
                else ProvidentFundProfile.FundType.SUPPLEMENTARY
            },
        )
        if request.method == "GET":
            return Response(ProvidentFundProfileSerializer(profile).data)
        serializer = ProvidentFundProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class UserSettingView(APIView):
    permission_classes = [IsAuthenticated]

    def _get(self, request):
        setting, _ = UserSetting.objects.get_or_create(user=request.user)
        return setting

    @extend_schema(summary="读取用户设置", tags=["settings"], responses=UserSettingSerializer)
    def get(self, request):
        return Response(UserSettingSerializer(self._get(request), context={"request": request}).data)

    @extend_schema(summary="更新用户设置", tags=["settings"], request=UserSettingSerializer, responses=UserSettingSerializer)
    def patch(self, request):
        setting = self._get(request)
        serializer = UserSettingSerializer(setting, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
