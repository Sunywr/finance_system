from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CreditCardBillViewSet,
    CreditCardViewSet,
    DebtItemViewSet,
    DebtPaymentViewSet,
    RecurringDebtViewSet,
)

router = DefaultRouter()
router.register("credit-cards", CreditCardViewSet, basename="credit-card")
router.register("bills", CreditCardBillViewSet, basename="bill")
router.register("debts", DebtItemViewSet, basename="debt")
router.register("recurring-debts", RecurringDebtViewSet, basename="recurring-debt")
router.register("debt-payments", DebtPaymentViewSet, basename="debt-payment")

urlpatterns = [path("", include(router.urls))]
