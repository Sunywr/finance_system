from datetime import date

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.services import cash_balance
from apps.assets.models import Asset
from apps.debts.models import CreditCard
from apps.ledger.services import create_transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_cash_balance_as_of_today_includes_transactions(user, categories, savings):
    create_transaction(
        owner=user,
        txn_type="EXPENSE",
        category=categories["餐饮"],
        amount="100",
        occurred_at=timezone.now(),
        settlement_channel="CASH",
        account=savings,
    )
    assert cash_balance(user, as_of=date.today()) == 9900


def test_create_card_and_asset_sets_owner(api, user):
    response = api.post(
        "/api/v1/credit-cards/",
        {
            "name": "API 卡",
            "bank": "测试银行",
            "statement_start_day": 5,
            "statement_end_day": 4,
            "due_day": 20,
            "credit_limit": "5000",
            "min_payment_rate": "0.1",
        },
        format="json",
    )
    assert response.status_code == 201
    card = CreditCard.objects.get(id=response.data["id"])
    assert card.owner == user

    response = api.post(
        "/api/v1/assets/",
        {
            "name": "API 资产",
            "type": "OTHER",
            "valuation_mode": "MANUAL",
            "manual_value": "123.45",
            "acquired_date": "2026-10-01",
        },
        format="json",
    )
    assert response.status_code == 201
    assert Asset.objects.get(id=response.data["id"]).owner == user


def test_tag_and_transaction_api(api, user, categories, savings):
    tag = api.post("/api/v1/tags/", {"name": "联调", "color": "#123456"}, format="json")
    assert tag.status_code == 201
    response = api.post(
        "/api/v1/transactions/",
        {
            "type": "EXPENSE",
            "amount": "12.34",
            "occurred_at": timezone.now().isoformat(),
            "category": categories["餐饮"].id,
            "settlement_channel": "CASH",
            "account": savings.id,
            "note": "标签联调",
            "tags": [tag.data["id"]],
            "tag_names": ["新标签"],
        },
        format="json",
    )
    assert response.status_code == 201
    names = {item["name"] for item in response.data["tags"]}
    assert {"联调", "新标签"} <= names


def test_transaction_date_filter(api, already_today_txn):
    today = timezone.localdate().isoformat()
    response = api.get(f"/api/v1/transactions/?date_from={today}&date_to={today}")
    assert response.status_code == 200
    assert response.data["count"] >= 1


@pytest.fixture
def already_today_txn(user, categories, savings):
    return create_transaction(
        owner=user,
        txn_type="EXPENSE",
        category=categories["餐饮"],
        amount="1",
        occurred_at=timezone.now(),
        settlement_channel="CASH",
        account=savings,
    )


def test_settings_patch(api):
    response = api.patch("/api/v1/settings", {"payday": 15, "salary_amount": "8000"}, format="json")
    assert response.status_code == 200
    assert response.data["payday"] == 15
    assert response.data["next_payday"]
