"""Convert business facts without calling commands that generate financial effects."""

from collections import Counter, defaultdict
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Account, ProvidentFundProfile, UserSetting
from apps.assets.models import Asset
from apps.debts.models import CreditCard, DebtItem, DebtPayment
from apps.insights.models import AIProviderConfig
from apps.common.utils.crypto import encrypt_text
from apps.investments.models import Instrument, Trade, DailyBar
from apps.ledger.models import Category, Tag, Transaction
from apps.ledger.services import channel_for_account
from apps.mortgages.models import Loan, LoanSchedule
from .models import (
    AccountBalanceBasis,
    LoanBalanceBasis,
    Household,
    Membership,
    MigrationIssue,
    PositionBasis,
    SourceMap,
)
from .source import assert_target, business_time, digest, money, normalized, number


class Projector:
    def __init__(self, source, batch):
        assert_target()
        self.source = source
        self.batch = batch
        self.maps = {
            (m.table, m.source_pk, m.component): m
            for m in SourceMap.objects.filter(batch=batch)
        }
        self.objects = {}
        self.table_cache = {}
        self.users = {u.pk: u for u in get_user_model().objects.all()}
        self.as_of = datetime.fromisoformat(
            batch.source_identity["snapshot_finished_at"]
        )

    def rows(self, table):
        if table not in self.table_cache:
            self.table_cache[table] = self.source.all(table)
        return self.table_cache[table]

    def index(self, table):
        return {r["id"]: r for r in self.rows(table)}

    def issue(self, table, pk, reason, severity="SOURCE_LIMITATION", details=None):
        MigrationIssue.objects.update_or_create(
            batch=self.batch,
            key=f"{table}:{pk}:{digest(reason)[:12]}",
            defaults=dict(
                table=table,
                source_pk=str(pk),
                reason=reason,
                severity=severity,
                details=normalized(details or {}),
            ),
        )

    def make(self, model_cls, table, row, component="main", **values):
        pk = str(row.get("id", row.get("account_invest_id")))
        key = (table, pk, str(component))
        sha = digest(row)
        if key in self.maps:
            m = self.maps[key]
            if m.sha256 != sha:
                raise RuntimeError("Fixed snapshot row changed: " + table + ":" + pk)
            if key not in self.objects:
                self.objects[key] = model_cls.objects.get(pk=m.target_pk)
            return self.objects[key]
        with transaction.atomic():
            obj = model_cls.objects.create(**values)
            m = SourceMap.objects.create(
                batch=self.batch,
                table=table,
                source_pk=pk,
                component=str(component),
                target_model=obj._meta.label,
                target_pk=obj.pk,
                sha256=sha,
            )
        self.maps[key] = m
        self.objects[key] = obj
        return obj

    def mapped(self, model, table, pk, component="main"):
        key = (table, str(pk), str(component))
        m = self.maps.get(key)
        if m is None:
            return None
        if key not in self.objects:
            self.objects[key] = model.objects.get(pk=m.target_pk)
        return self.objects[key]

    def owner(self, row):
        uid = row.get("owner_id_id", row.get("owner_id"))
        if uid not in self.users:
            raise RuntimeError("Unknown source owner: " + str(uid))
        return self.users[uid]

    def dictionary(self):
        categories = self.rows("account_category")
        for uid, u in self.users.items():
            for r in categories:
                name = r.get("name", "").lower()
                kind = (
                    "STOCK"
                    if name in ("stock", "stock_account")
                    else (
                        "INVESTMENT"
                        if name == "financial"
                        else (
                            "TRANSFER"
                            if name in ("cash_transfer", "early_loan_repayment")
                            else "GENERAL"
                        )
                    )
                )
                self.make(
                    Category,
                    "account_category",
                    r,
                    component=uid,
                    owner=u,
                    name=r.get("display_name", r["name"])[:60],
                    kind=kind,
                )
            for r in self.rows("account_label"):
                self.make(
                    Tag, "account_label", r, component=uid, owner=u, name=r["name"][:30]
                )

    def accounts(self):
        categories = self.index("cash_account_category")
        for r in self.rows("cash_account"):
            cat = categories.get(r["category_id"], {}).get("name", "")
            kind = (
                "WECHAT"
                if "微信" in cat
                else (
                    "ALIPAY"
                    if "支付宝" in cat
                    else "SAVINGS" if "储蓄" in cat else "WALLET"
                )
            )
            self.make(
                Account,
                "cash_account",
                r,
                owner=self.owner(r),
                name=r["name"][:80],
                type=kind,
                opening_balance=money(r["opening_balance"]),
                is_active=bool(r["enabled"]),
                note="原现金账户；余额保留期初和原关联流水口径",
            )
        for r in self.rows("account_stockaccount"):
            a = self.make(
                Account,
                "account_stockaccount",
                r,
                owner=self.owner(r),
                name=r["name"][:80],
                institution=(r.get("institution_name") or "")[:80],
                type="STOCK",
            )
            AccountBalanceBasis.objects.get_or_create(
                account=a,
                defaults=dict(
                    batch=self.batch,
                    as_of=self.as_of,
                    balance=number(r["total_cash"]),
                    available=number(r["available_cash"]),
                    frozen=number(r["frozen_cash"]),
                ),
            )
        for r in self.rows("mortgage_housing_fund_account"):
            kind = (
                "PROVIDENT_FUND_SUPP"
                if "supp" in r["account_kind"].lower()
                or "补" in r.get("display_name", "")
                else "PROVIDENT_FUND_MAIN"
            )
            # The fund's user_id is the actual member; owner_id may be the manager.
            u = self.users.get(r.get("user_id")) or self.owner(r)
            a = self.make(
                Account,
                "mortgage_housing_fund_account",
                r,
                owner=u,
                name=r["display_name"][:80],
                type=kind,
                is_active=bool(r["enabled"]),
            )
            AccountBalanceBasis.objects.get_or_create(
                account=a,
                defaults=dict(
                    batch=self.batch, as_of=self.as_of, balance=number(r["balance"])
                ),
            )
            ProvidentFundProfile.objects.get_or_create(
                account=a,
                defaults=dict(
                    fund_type="SUPPLEMENTARY" if kind.endswith("SUPP") else "MAIN",
                    monthly_employee_amount=money(r["monthly_contribution"]),
                    contribution_day=min(max(r.get("contribution_day") or 10, 1), 28),
                    auto_contribute=False,
                ),
            )
        for r in self.rows("household"):
            self.make(
                Household,
                "household",
                r,
                name=r["name"],
                manager_id=r["manager_user_id"],
                is_active=r["status"] == "active",
            )
        for r in self.rows("household_member"):
            h = self.mapped(Household, "household", r["household_id"])
            self.make(
                Membership,
                "household_member",
                r,
                household=h,
                user_id=r["user_id"],
                role=r["role"],
                is_active=r["status"] == "active",
            )
        for r in self.rows("account_cockpitusersetting"):
            data = r["settings"]
            if isinstance(data, str):
                import json

                data = json.loads(data)
            home = data.get("home", {})
            UserSetting.objects.get_or_create(
                user_id=r["owner_id"],
                defaults={
                    "payday": min(max(int(home.get("salary_day") or 10), 1), 31),
                    "dashboard_prefs": home,
                },
            )

    def subjects(self):
        for r in self.rows("account_creditcard"):
            statement = r.get("statement_day") or 1
            self.make(
                CreditCard,
                "account_creditcard",
                r,
                owner=self.owner(r),
                name=r["description"][:80],
                statement_start_day=statement % 31 + 1,
                statement_end_day=statement,
                due_day=r.get("repayment_due_day") or 20,
                credit_limit=money(r.get("credit_limit")),
                note="原账单事实独立保留；不据当前规则重建历史",
            )
        for r in self.rows("account_asset"):
            self.make(
                Asset,
                "account_asset",
                r,
                owner=self.owner(r),
                name=r["description"][:100],
                valuation_mode="MANUAL",
                manual_value=money(r["value"]),
                status="ACTIVE" if r["status"] == 0 else "DISPOSED",
                acquired_date=r["create_at"].date(),
                note=(r.get("remark") or "")[:200],
            )
        categories = self.index("account_investcategory")
        linked = defaultdict(set)
        for r in self.rows("account_account"):
            if r["invest_id"] and r.get("stock_account_id"):
                linked[r["invest_id"]].add(r["stock_account_id"])
        anchors = {
            r["account_invest_id"]: r for r in self.rows("stock_cost_basis_anchor")
        }
        auto_ids = {p["invest_id"] for p in self.rows("account_autoinvestplan")}
        for r in self.rows("account_invest"):
            u = self.owner(r)
            c = categories.get(r["invest_type_id"], {})
            label = (c.get("name", "") + " " + c.get("display_name", "")).lower()
            code = r["code"] or f'legacy-{r["id"]}'
            convertible = (
                code.startswith(("110", "111", "113", "118", "123", "127", "128"))
                and len(code) == 6
            )
            kind = (
                "CONVERTIBLE_BOND"
                if convertible
                else (
                    "STOCK"
                    if "stock" in label
                    else "GOLD" if "gold" in label else "WEALTH"
                )
            )
            mode = (
                "MARKET"
                if kind in ("STOCK", "ETF", "CONVERTIBLE_BOND")
                else "YIELD_PER_10000" if "10000" in label else "MANUAL"
            )
            if (
                kind == "STOCK"
                and len(code) == 6
                and code.isdigit()
                and code.startswith(("5", "15", "16"))
            ):
                kind = "ETF"
            inst = Instrument.objects.filter(
                owner=u, symbol=code[:32], type=kind
            ).first()
            if inst is None:
                inst = self.make(
                    Instrument,
                    "account_invest",
                    r,
                    component="instrument",
                    owner=u,
                    symbol=code[:32],
                    name=r["description"][:80],
                    type=kind,
                    exchange=(
                        "SH"
                        if code.startswith(("6", "5", "11"))
                        else (
                            "SZ"
                            if kind in ("STOCK", "ETF", "CONVERTIBLE_BOND")
                            else "OTC"
                        )
                    ),
                    valuation_mode=mode,
                    note=(r.get("remark") or "")[:200],
                )
            elif ("account_invest", str(r["id"]), "instrument") not in self.maps:
                m = SourceMap.objects.create(
                    batch=self.batch,
                    table="account_invest",
                    source_pk=str(r["id"]),
                    component="instrument",
                    target_model=inst._meta.label,
                    target_pk=inst.pk,
                    sha256=digest(r),
                )
                self.maps[("account_invest", str(r["id"]), "instrument")] = m
            if inst.type != kind:
                inst.type = kind
                inst.save(update_fields=["type"])
            account = None
            verified = False
            if len(linked[r["id"]]) == 1:
                account = self.mapped(
                    Account, "account_stockaccount", next(iter(linked[r["id"]]))
                )
                verified = True
            if account is None and kind in ("STOCK", "ETF", "CONVERTIBLE_BOND"):
                owned = list(Account.objects.filter(owner=u, type="STOCK"))
                if len(owned) == 1:
                    account = owned[0]
            if account is None:
                account, _ = Account.objects.get_or_create(
                    owner=u,
                    name=(
                        "历史理财账户"
                        if kind not in ("STOCK", "ETF", "CONVERTIBLE_BOND")
                        else "历史未归属证券账户"
                    ),
                    type=(
                        "WEALTH"
                        if kind not in ("STOCK", "ETF", "CONVERTIBLE_BOND")
                        else "STOCK"
                    ),
                    defaults={"note": "历史持仓归属容器，无新增资金流水"},
                )
            vals = {
                k: number(r[k]) for k in ("share", "cost", "value", "profit", "price")
            }
            # These are original stored facts. Verified reconciliation books and
            # anchors stay separately accessible; never silently substitute costs.
            basis = self.make(
                PositionBasis,
                "account_invest",
                r,
                component="basis",
                batch=self.batch,
                source_invest_id=r["id"],
                owner=u,
                account=account,
                instrument=inst,
                as_of=self.as_of,
                quantity=vals["share"],
                cost=vals["cost"],
                market_value=vals["value"],
                profit=vals["profit"],
                price=vals["price"],
                is_active=r["status"] == 0,
                cost_anchor=normalized(anchors.get(r["id"], {})),
                attribution_verified=verified,
                is_auto_plan=r["id"] in auto_ids,
            )
            if basis.is_auto_plan != (r["id"] in auto_ids):
                basis.is_auto_plan = r["id"] in auto_ids
                basis.save(update_fields=["is_auto_plan"])
        for r in self.rows("mortgage_loan"):
            schedules = [
                s
                for s in self.rows("mortgage_repayment_plan")
                if s["loan_id"] == r["id"]
            ]
            first = min(
                (s["due_date"] for s in schedules), default=r["first_repayment_date"]
            )
            method = (
                "EQUAL_PRINCIPAL"
                if r["repayment_method"].lower()
                in ("equal_principal", "equal-principal")
                else "EQUAL_INSTALLMENT"
            )
            rate = number(r["current_rate"])
            rate = rate * 100 if abs(rate) < 1 else rate
            self.make(
                Loan,
                "mortgage_loan",
                r,
                owner=self.owner(r),
                name=r["name"][:100],
                loan_type=(
                    "PROVIDENT_FUND"
                    if "fund" in r["loan_type"].lower()
                    else "COMMERCIAL"
                ),
                principal=money(r["original_principal"]),
                annual_rate=rate,
                term_months=max(
                    [s["period_no"] for s in schedules] or [r["remaining_terms"]]
                ),
                repayment_method=method,
                first_due_date=first,
                payment_day=r["repayment_day"],
                auto_settle=False,
            )
        for r in self.rows("mortgage_repayment_plan"):
            loan = self.mapped(Loan, "mortgage_loan", r["loan_id"])
            status = {
                "paid": "PAID",
                "pending": "PENDING",
                "overdue": "OVERDUE",
                "partial": "PARTIAL",
                "cancelled": "CANCELLED",
            }.get(r["status"].lower(), "PENDING")
            self.make(
                LoanSchedule,
                "mortgage_repayment_plan",
                r,
                loan=loan,
                period_no=r["period_no"],
                due_date=r["due_date"],
                principal_due=money(r["principal_due"]),
                interest_due=money(r["interest_due"]),
                total_due=money(r["payment_due"]),
                remaining_principal=money(r["closing_principal"]),
                status=status,
            )
        debt_types = self.index("account_debtcategory")
        for r in self.rows("account_debt"):
            due = r["repayment_deadline"] or r["repayment_at"] or r["create_at"]
            card = self.mapped(CreditCard, "account_creditcard", r["credit_card_id"])
            name = debt_types.get(r["debt_type_id"], {}).get("name", "").lower()
            status = (
                "PAID"
                if r["status"] == 1
                else "CANCELLED" if r["status"] not in (0, 1) else "PENDING"
            )
            self.make(
                DebtItem,
                "account_debt",
                r,
                owner=self.owner(r),
                kind="CREDIT_CARD" if name == "credit_card" else "PERIODIC",
                legacy_card=card if name == "credit_card" else None,
                title=r["description"][:140],
                due_date=due.date(),
                amount=money(r["debt_amount"]),
                paid_amount=money(r["debt_amount"]) if status == "PAID" else 0,
                status=status,
                settled_at=(
                    business_time(r["repayment_at"]) if status == "PAID" else None
                ),
                note=(r.get("remark") or "")[:200],
            )
        for r in self.rows("stock_ai_model_config"):
            self.make(
                AIProviderConfig,
                "stock_ai_model_config",
                r,
                owner=self.owner(r),
                name=r["config_name"][:80],
                base_url=r["base_url"],
                api_key_encrypted=encrypt_text(r["api_key"]),
                model=r["model_name"],
                enabled=False,
            )

    def ledger(self):
        cats = self.index("account_category")
        allrows = self.rows("account_account")
        tags = defaultdict(list)
        tag_links = set()
        for r in self.rows("account_accountlabel"):
            tags[r["account_id_id"]].append(r["label_id_id"])
        for index, r in enumerate(allrows):
            u = self.owner(r)
            cat = self.mapped(Category, "account_category", r["account_type_id"], u.pk)
            if cat is None:
                raise RuntimeError("Missing transaction category")
            account = self.mapped(Account, "cash_account", r.get("cash_account_id"))
            # Preserve original cash-account association exactly; legacy is_cash=1
            # alone never proves a specific bank account.
            card = self.mapped(CreditCard, "account_creditcard", r["credit_card_id"])
            channel = (
                channel_for_account(account)
                if account
                else (
                    "CREDIT_CARD"
                    if r["is_cash"] == 0 and card
                    else "STOCK" if r.get("stock_account_id") else "CASH"
                )
            )
            category_name = cats.get(r["account_type_id"], {}).get("name", "").lower()
            for component, field in [
                ("income", "income"),
                ("expenditure", "expenditure"),
            ]:
                amount = number(r[field])
                if not amount:
                    continue
                kind = "INCOME" if component == "income" else "EXPENSE"
                if r["refund_of_id"] and component == "income":
                    kind = "REFUND"
                if (
                    r.get("transfer_id")
                    or category_name in ("cash_transfer", "early_loan_repayment")
                    or (r["debt_id"] and r["is_cash"] == 1 and card)
                ):
                    kind = "TRANSFER_IN" if component == "income" else "TRANSFER_OUT"
                item = self.make(
                    Transaction,
                    "account_account",
                    r,
                    component=component,
                    owner=u,
                    txn_no=f'legacy-{r["id"]}-{component[0]}',
                    type=kind,
                    category=cat,
                    occurred_at=business_time(r["account_date"]),
                    amount=money(amount),
                    settlement_channel=channel,
                    account=account,
                    credit_card=card,
                    asset=self.mapped(Asset, "account_asset", r["asset_id"]),
                    source="LEGACY",
                    source_id=r["id"],
                    idempotency_key=f'legacy:{self.batch.snapshot_sha256[:16]}:{r["id"]}:{component}',
                    note=(r["description"] + "\n" + (r.get("remark") or ""))[:500],
                )
                for tid in tags[r["id"]]:
                    tag = self.mapped(Tag, "account_label", tid, u.pk)
                    if tag:
                        tag_links.add((item.pk, tag.pk))
            if not number(r["income"]) and not number(r["expenditure"]):
                note_item = self.make(
                    Transaction,
                    "account_account",
                    r,
                    component="note",
                    owner=u,
                    txn_no=f'legacy-{r["id"]}-n',
                    type="NOTE",
                    category=cat,
                    occurred_at=business_time(r["account_date"]),
                    amount=0,
                    settlement_channel=channel,
                    account=account,
                    credit_card=card,
                    source="LEGACY",
                    source_id=r["id"],
                    note=(r["description"] + "\n" + (r.get("remark") or ""))[:500],
                )
                for tid in tags[r["id"]]:
                    tag = self.mapped(Tag, "account_label", tid, u.pk)
                    if tag:
                        tag_links.add((note_item.pk, tag.pk))
            if index % 2000 == 0:
                print(f"Projected ledger {index}/{len(allrows)}", flush=True)
        through = Transaction.tags.through
        through.objects.bulk_create(
            [through(transaction_id=t, tag_id=tag) for t, tag in tag_links],
            ignore_conflicts=True,
            batch_size=1000,
        )
        for r in allrows:
            if r["refund_of_id"]:
                refund = self.mapped(Transaction, "account_account", r["id"], "income")
                original = self.mapped(
                    Transaction, "account_account", r["refund_of_id"], "expenditure"
                )
                if refund and original:
                    refund.refund_of = original
                    refund.save(update_fields=["refund_of"])
                else:
                    self.issue(
                        "account_account",
                        r["id"],
                        "Original refund association cannot be resolved",
                        details={"refund_of_id": r["refund_of_id"]},
                    )

    def trades(self):
        # The securities cash ledger is the authoritative link, not a second cash entry.
        accounts = self.index("account_account")
        invests = self.index("account_invest")
        for r in self.rows("stock_cash_flow_ledger"):
            if r["flow_type"] not in ("trade_buy", "trade_sell", "dividend"):
                continue
            if ("stock_cash_flow_ledger", str(r["id"]), "main") in self.maps:
                continue
            original = accounts.get(r["related_account_id"])
            invest_id = r.get("related_invest_id") or (original or {}).get("invest_id")
            basis = PositionBasis.objects.filter(
                batch=self.batch, source_invest_id=invest_id
            ).first()
            if basis is None:
                self.issue(
                    "stock_cash_flow_ledger",
                    r["id"],
                    "Cash-flow fact has no surviving investment; preserved as an original fact",
                    details={
                        "related_account_id": r["related_account_id"],
                        "related_invest_id": invest_id,
                    },
                )
                continue
            side = {"trade_buy": "BUY", "trade_sell": "SELL", "dividend": "DIVIDEND"}[
                r["flow_type"]
            ]
            txn = self.mapped(
                Transaction,
                "account_account",
                r["related_account_id"],
                "expenditure" if side == "BUY" else "income",
            )
            if txn is None:
                self.issue(
                    "stock_cash_flow_ledger",
                    r["id"],
                    "Original ledger row absent; imported trade has no fabricated cash transaction",
                    details={"related_account_id": r["related_account_id"]},
                )
            qty = abs(number((original or {}).get("trade_share")))
            amt = abs(money(r["amount"]))
            fee = abs(money(r["fee"]))
            price = (amt / qty) if qty else 0
            if txn and Trade.objects.filter(transaction=txn).exists():
                self.issue(
                    "stock_cash_flow_ledger",
                    r["id"],
                    "Multiple source cash flows reference one original cash transaction; original facts retained",
                )
                continue
            self.make(
                Trade,
                "stock_cash_flow_ledger",
                r,
                legacy_batch=self.batch,
                owner=self.owner(r),
                account=basis.account,
                instrument=basis.instrument,
                transaction=txn,
                side=side,
                operation=(
                    "OPEN"
                    if side == "BUY"
                    else "REDUCE" if side == "SELL" else "DIVIDEND"
                ),
                trade_date=business_time(r["flow_date"]),
                quantity=qty,
                price=price,
                amount=amt,
                fee=fee,
                note="历史证券现金流；资金流水仅关联一次",
            )
        # Non-stock and older unlinked investment operations remain original
        # financial facts; only explicit share/action evidence becomes a Trade.
        linked_ids = set(
            Trade.objects.exclude(transaction=None).values_list(
                "transaction_id", flat=True
            )
        )
        for r in self.rows("account_account"):
            if not r["invest_id"] or not number(r.get("trade_share")):
                continue
            basis = PositionBasis.objects.filter(
                batch=self.batch, source_invest_id=r["invest_id"]
            ).first()
            if basis is None:
                continue
            component = "expenditure" if number(r["expenditure"]) > 0 else "income"
            txn = self.mapped(Transaction, "account_account", r["id"], component)
            if txn is None or txn.pk in linked_ids:
                continue
            qty = abs(number(r["trade_share"]))
            side = "BUY" if component == "expenditure" else "SELL"
            self.make(
                Trade,
                "account_account",
                r,
                component="trade",
                legacy_batch=self.batch,
                owner=self.owner(r),
                account=basis.account,
                instrument=basis.instrument,
                transaction=txn,
                side=side,
                operation="OPEN" if side == "BUY" else "REDUCE",
                trade_date=business_time(r["account_date"]),
                quantity=qty,
                price=number(txn.amount) / qty,
                amount=txn.amount,
                note="历史份额明确的投资操作",
            )

    def payments(self):
        for r in self.rows("account_account"):
            if not r["debt_id"] or number(r["expenditure"]) <= 0:
                continue
            debt = self.mapped(DebtItem, "account_debt", r["debt_id"])
            txn = self.mapped(Transaction, "account_account", r["id"], "expenditure")
            if debt is None or txn is None:
                self.issue(
                    "account_account",
                    r["id"],
                    "Original payment references an absent debt; cash fact retained",
                    details={"debt_id": r["debt_id"]},
                )
                continue
            if debt.owner_id != txn.owner_id:
                self.issue(
                    "account_account",
                    r["id"],
                    "Payment and debt have different source owners; no cross-owner payment link created",
                )
                continue
            self.make(
                DebtPayment,
                "account_account",
                r,
                component="payment",
                owner=txn.owner,
                debt_item=debt,
                amount=txn.amount,
                channel=txn.settlement_channel,
                account=txn.account,
                credit_card=txn.credit_card,
                paid_at=txn.occurred_at,
                transaction_id=txn.pk,
                idempotency_key=f'legacy-payment:{r["id"]}',
                note="关联原历史资金流水；不再次扣款或重算原债务状态",
            )

    def run(self):
        self.dictionary()
        self.accounts()
        self.subjects()
        self.ledger()
        self.trades()
        self.payments()
        self.market_history()
        self.batch.state = "IMPORTED"
        if self.batch.completed_at is None:
            self.batch.completed_at = timezone.now()
        self.batch.save(update_fields=["state", "completed_at"])
        return {
            "mappings": SourceMap.objects.filter(batch=self.batch).count(),
            "source_limitations": MigrationIssue.objects.filter(
                batch=self.batch
            ).count(),
        }

    def market_history(self):
        instruments = Instrument.objects.filter(
            positionbasis__batch=self.batch,
            positionbasis__is_active=True,
            type__in=["STOCK", "ETF", "CONVERTIBLE_BOND"],
        ).distinct()
        count = 0
        for inst in instruments:
            existing = set(
                DailyBar.objects.filter(instrument=inst).values_list(
                    "trade_date", flat=True
                )
            )
            rows = self.source.query(
                "SELECT date,open,high,low,close,volume,amount FROM stock_daily_bar WHERE code=%s ORDER BY date",
                [inst.symbol],
            )
            bars = []
            for r in rows:
                if r["date"] in existing:
                    continue
                bars.append(
                    DailyBar(
                        instrument=inst,
                        trade_date=r["date"],
                        **{
                            f: number(r[f])
                            for f in (
                                "open",
                                "high",
                                "low",
                                "close",
                                "volume",
                                "amount",
                            )
                        },
                    )
                )
            DailyBar.objects.bulk_create(bars, batch_size=500)
            count += len(bars)
        print(f"Imported {count} necessary price-history bars", flush=True)
        for r in self.rows("mortgage_loan"):
            loan = self.mapped(Loan, "mortgage_loan", r["id"])
            paid = [
                s["period_no"]
                for s in self.rows("mortgage_repayment_plan")
                if s["loan_id"] == r["id"] and s["status"].lower() == "paid"
            ]
            LoanBalanceBasis.objects.get_or_create(
                loan=loan,
                defaults=dict(
                    batch=self.batch,
                    remaining_principal=money(r["remaining_principal"]),
                    paid_periods=paid,
                    as_of=self.as_of,
                ),
            )
