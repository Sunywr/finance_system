from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenBlacklistView,
)

from apps.common.views import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health", HealthView.as_view(), name="health"),
    path("api/v1/auth/token", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/token/refresh", TokenRefreshView.as_view(), name="token_refresh"),
    path(
        "api/v1/auth/token/blacklist",
        TokenBlacklistView.as_view(),
        name="token_blacklist",
    ),
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.ledger.urls")),
    path("api/v1/", include("apps.debts.urls")),
    path("api/v1/", include("apps.mortgages.urls")),
    path("api/v1/", include("apps.assets.urls")),
    path("api/v1/", include("apps.investments.urls")),
    path("api/v1/", include("apps.insights.urls")),
    path("api/v1/", include("apps.legacy.urls")),
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"
    ),
]
