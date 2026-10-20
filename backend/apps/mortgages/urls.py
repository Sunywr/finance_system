from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import LoanViewSet

router = DefaultRouter()
router.register("loans", LoanViewSet, basename="loan")

urlpatterns = [path("", include(router.urls))]
