from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AIAnalysisViewSet,
    AIProviderViewSet,
    CashflowSeriesView,
    DashboardOverviewView,
    MetaEnumsView,
)

router = DefaultRouter()
router.register("ai/providers", AIProviderViewSet, basename="ai-provider")
router.register("ai/analyses", AIAnalysisViewSet, basename="ai-analysis")

urlpatterns = [
    path("dashboard/overview", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("dashboard/cashflow", CashflowSeriesView.as_view(), name="dashboard-cashflow"),
    path("meta/enums", MetaEnumsView.as_view(), name="meta-enums"),
    path("", include(router.urls)),
]
