import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import Account, UserSetting
from apps.debts.models import CreditCard
from apps.ledger.models import Category, Tag

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester", password="pass12345")


@pytest.fixture
def setting(user):
    return UserSetting.objects.create(user=user, payday=10, salary_amount=10000)


@pytest.fixture
def categories(user):
    data = {}
    for name, kind, is_system in [
        ("理财", Category.Kind.INVESTMENT, True),
        ("股票", Category.Kind.STOCK, True),
        ("转账", Category.Kind.TRANSFER, True),
        ("退款", Category.Kind.REFUND, True),
        ("餐饮", Category.Kind.GENERAL, False),
        ("购物", Category.Kind.GENERAL, False),
        ("房贷", Category.Kind.GENERAL, False),
        ("债务支出", Category.Kind.GENERAL, False),
    ]:
        data[name] = Category.objects.create(owner=user, name=name, kind=kind, is_system=is_system)
    data["tag"] = Tag.objects.create(owner=user, name="日常")
    return data


@pytest.fixture
def savings(user):
    return Account.objects.create(
        owner=user, name="储蓄卡", type=Account.Type.SAVINGS, opening_balance="10000"
    )


@pytest.fixture
def alipay(user):
    return Account.objects.create(owner=user, name="支付宝", type=Account.Type.ALIPAY, opening_balance="0")


@pytest.fixture
def card(user):
    return CreditCard.objects.create(
        owner=user,
        name="测试卡",
        statement_start_day=5,
        statement_end_day=4,
        due_day=20,
        credit_limit="30000",
    )
