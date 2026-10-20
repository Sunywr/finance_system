from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AccountTransferViewSet, CategoryViewSet, TagViewSet, TransactionViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("tags", TagViewSet, basename="tag")
router.register("transactions", TransactionViewSet, basename="transaction")
router.register("transfers", AccountTransferViewSet, basename="transfer")

urlpatterns = [path("", include(router.urls))]
