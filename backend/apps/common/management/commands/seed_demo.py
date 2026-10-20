from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Account, ProvidentFundProfile
from apps.assets.models import Asset
from apps.common.utils.dates import add_months, today_local
from apps.common.utils.money import D
from apps.debts.models import CreditCard, RecurringDebt
from apps.debts.services import (
    create_recurring_items,
    generate_due_bills,
    generate_mortgage_items,
)
from apps.investments.models import Instrument, Quote, Watchlist
from apps.investments.services import create_trade
from apps.ledger.models import Category, Tag
from apps.ledger.services import (
    create_installment_purchase,
    create_transaction,
    create_transfer,
)
from apps.mortgages.models import Loan, OffsetPlan
from apps.mortgages.services import generate_schedule
from apps.users.models import User


class Command(BaseCommand):
    help = "生成演示数据（需先执行 seed_system_data）"

    def add_arguments(self, parser):
        parser.add_argument("--owner", default="admin")
        parser.add_argument("--force", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        user = User.objects.filter(username=options["owner"]).first()
        if not user:
            self.stderr.write(self.style.ERROR("用户不存在，请先执行 seed_system_data"))
            return
        if Account.objects.filter(owner=user).exists() and not options["force"]:
            self.stdout.write("演示账户已存在，跳过。使用 --force 可重复创建（可能产生重复数据）")
            return
        today = today_local()
        now = timezone.now()

        savings = Account.objects.create(
            owner=user, name="招商银行储蓄卡", type=Account.Type.SAVINGS, institution="招商银行",
            opening_balance=D("50000"), note="日常收支主账户", sort_order=1,
        )
        alipay = Account.objects.create(
            owner=user, name="支付宝", type=Account.Type.ALIPAY, institution="支付宝",
            opening_balance=D("2000"), sort_order=3,
        )
        wechat = Account.objects.create(
            owner=user, name="微信", type=Account.Type.WECHAT, institution="微信",
            opening_balance=D("1000"), sort_order=4,
        )
        pf_main = Account.objects.create(
            owner=user, name="公积金主账户", type=Account.Type.PROVIDENT_FUND_MAIN, institution="公积金中心",
            opening_balance=D("30000"), sort_order=5,
        )
        pf_supp = Account.objects.create(
            owner=user, name="公积金补充账户", type=Account.Type.PROVIDENT_FUND_SUPP, institution="公积金中心",
            opening_balance=D("5000"), sort_order=6,
        )
        stock_account = Account.objects.create(
            owner=user, name="股票账户", type=Account.Type.STOCK, institution="华泰证券",
            opening_balance=D("100000"), sort_order=7,
        )
        wealth_account = Account.objects.create(
            owner=user, name="理财账户", type=Account.Type.WEALTH, institution="招商银行",
            opening_balance=D("20000"), sort_order=8,
        )
        ProvidentFundProfile.objects.create(
            account=pf_main,
            fund_type=ProvidentFundProfile.FundType.MAIN,
            monthly_employee_amount=D("2000"),
            monthly_employer_amount=D("2000"),
            contribution_day=10,
            auto_contribute=True,
        )
        ProvidentFundProfile.objects.create(
            account=pf_supp,
            fund_type=ProvidentFundProfile.FundType.SUPPLEMENTARY,
            monthly_employee_amount=D("500"),
            monthly_employer_amount=D("500"),
            contribution_day=10,
            auto_contribute=False,
        )

        card = CreditCard.objects.create(
            owner=user, name="招行经典白金卡", bank="招商银行", last4="8888",
            statement_start_day=5, statement_end_day=4, due_day=20,
            credit_limit=D("30000"), min_payment_rate=D("0.1"), sort_order=1,
        )

        tag_daily = Tag.objects.get(owner=user, name="日常")
        category_food = Category.objects.get(owner=user, name="餐饮")
        category_shopping = Category.objects.get(owner=user, name="购物")
        category_insurance = Category.objects.get(owner=user, name="保险")

        create_transaction(
            owner=user, txn_type="EXPENSE", category=category_food, amount=D("128.50"),
            occurred_at=now - timedelta(days=2), settlement_channel="CASH", account=savings,
            note="工作日午餐", tags=[tag_daily],
        )
        create_transaction(
            owner=user, txn_type="EXPENSE", category=category_shopping, amount=D("1200"),
            occurred_at=now - timedelta(days=1), settlement_channel="CREDIT_CARD", credit_card=card,
            note="信用卡购物",
        )
        create_installment_purchase(
            owner=user, card=card, principal=D("6000"), periods=6, occurred_at=now - timedelta(days=1),
            category=category_shopping, note="家电分期", fee_mode="NONE",
        )
        create_transfer(
            owner=user, from_account=savings, to_account=alipay, amount=D("1000"),
            occurred_at=now - timedelta(days=3), note="生活费",
        )

        asset = Asset.objects.create(
            owner=user, name="MacBook Pro", type=Asset.Type.ELECTRONICS,
            valuation_mode=Asset.ValuationMode.LINKED_SUM, acquired_date=today - timedelta(days=30),
        )
        create_transaction(
            owner=user, txn_type="EXPENSE", category=category_shopping, amount=D("8000"),
            occurred_at=now - timedelta(days=30), settlement_channel="CASH", account=savings,
            note="购买电脑", asset=asset, asset_amount=D("8000"),
        )

        recurring = RecurringDebt.objects.create(
            owner=user, name="重疾险年缴分摊", debt_type=RecurringDebt.DebtType.INSURANCE,
            amount=D("300"), periods=12, interval_months=1,
            first_due_date=add_months(today, 1, day=5), due_day=5,
            payment_channel="CASH", account=savings, category_id=category_insurance.id,
            auto_pay=False, note="每月预留保费",
        )
        create_recurring_items(recurring)

        loan = Loan.objects.create(
            owner=user, name="首套房贷", loan_type=Loan.LoanType.COMMERCIAL, lender="招商银行",
            principal=D("500000"), annual_rate=D("4.2000"), term_months=360,
            repayment_method=Loan.RepaymentMethod.EQUAL_INSTALLMENT,
            first_due_date=add_months(today, 1, day=10), payment_day=10,
            repayment_account=savings, auto_settle=False,
        )
        generate_schedule(loan)
        OffsetPlan.objects.create(
            loan=loan, pf_account=pf_main, enabled=True, mode=OffsetPlan.Mode.FULL,
            start_date=today, use_new_contributions=True, auto_pay_cash=False,
        )
        generate_mortgage_items(loan)

        stock = Instrument.objects.create(
            owner=user, symbol="600519", name="贵州茅台", type=Instrument.Type.STOCK,
            exchange=Instrument.Exchange.SH, industry="白酒", valuation_mode=Instrument.ValuationMode.MARKET,
            dividend_yield=D("3.5000"),
        )
        Quote.objects.create(
            instrument=stock, price=D("1600"), prev_close=D("1580"), change_pct=D("1.27"),
            open=D("1585"), high=D("1610"), low=D("1575"), volume=D("30000"), amount=D("48000000"),
            pe=D("30.5"), pb=D("8.2"), market_cap=D("2000000000000"), source="demo",
        )
        create_trade(
            owner=user, account=stock_account, instrument=stock, side="BUY", operation="OPEN",
            quantity=D("50"), price=D("1500"), fee=D("5"), trade_date=now - timedelta(days=20), note="演示建仓",
        )
        Watchlist.objects.create(owner=user, instrument=stock, note="长期观察", target_buy_price=D("1450"))

        wealth = Instrument.objects.create(
            owner=user, symbol="WY001", name="稳盈理财1号", type=Instrument.Type.WEALTH,
            exchange=Instrument.Exchange.OTC, valuation_mode=Instrument.ValuationMode.ACCRUAL,
            annual_rate=D("3.5000"), data_source="manual",
        )
        create_trade(
            owner=user, account=wealth_account, instrument=wealth, side="BUY", operation="OPEN",
            quantity=D("1"), price=D("10000"), fee=D("0"), trade_date=now - timedelta(days=10),
            note="稳健理财",
        )

        generate_due_bills(owner=user)
        self.stdout.write(self.style.SUCCESS("演示数据生成完成"))
        self.stdout.write("登录账号：admin / admin123456（如已修改请使用新密码）")
        self.stdout.write("账户：储蓄卡/支付宝/微信/公积金主+补充/股票/理财；信用卡：招行经典白金卡")
        self.stdout.write("含现金流水、信用卡消费、6期分期、转账、资产、周期保险、房贷+公积金冲还、股票与理财持仓")
