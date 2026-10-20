import pytest
from rest_framework.test import APIClient

from apps.insights.services import overview

pytestmark = pytest.mark.django_db


def test_overview_returns_series(user, setting, savings, categories):
    data = overview(user)
    assert data["cash_now"] == 10000
    assert data["payday"] is not None
    assert "daily_series" in data
    assert "monthly_series" in data
    assert data["net_worth"]["net_worth"] is not None


def test_api_requires_auth_and_allows_token(user):
    client = APIClient()
    response = client.get("/api/v1/transactions/")
    assert response.status_code == 401
    response = client.post(
        "/api/v1/auth/token",
        {"username": "tester", "password": "pass12345"},
        format="json",
    )
    assert response.status_code == 200
    token = response.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/transactions/")
    assert response.status_code == 200
    response = client.get("/api/v1/dashboard/overview")
    assert response.status_code == 200
