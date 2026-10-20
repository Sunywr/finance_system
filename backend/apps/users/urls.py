from django.urls import path

from .views import ChangePasswordView, MeView

urlpatterns = [
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("auth/change-password", ChangePasswordView.as_view(), name="auth-change-password"),
]
