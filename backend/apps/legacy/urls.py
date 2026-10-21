from django.urls import path
from .views import (
    HistoryView,
    HistoryTypesView,
    HouseholdSummaryView,
    MigrationStatusView,
)

urlpatterns = [
    path("history/types", HistoryTypesView.as_view()),
    path("history/records", HistoryView.as_view()),
    path("household/summary", HouseholdSummaryView.as_view()),
    path("migration/status", MigrationStatusView.as_view()),
]
