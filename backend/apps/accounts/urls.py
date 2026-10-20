from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AccountViewSet, UserSettingView

router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="account")

urlpatterns = [
    path("settings", UserSettingView.as_view(), name="user-setting"),
    path("", include(router.urls)),
]
