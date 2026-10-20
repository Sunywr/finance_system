import json
import logging
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

import requests
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Account, UserSetting
from apps.accounts.services import balances_for_owner, cash_balance
from apps.assets.models import Asset
from apps.assets.services import asset_value
from apps.common.utils.crypto import decrypt_text
from apps.common.utils.dates import add_months, date_range, day_end, day_start, month_bounds, next_payday, today_local
from apps.common.utils.money import D, money, percent
from apps.debts.models import CreditCard, CreditCardBill, DebtItem
from apps.debts.services import card_liability
from apps.investments.services import portfolio_summary
from apps.ledger.models import Category, Transaction
from apps.mortgages.models import Loan
from apps.mortgages.services import loan_stats, simulate_offset

from .models import AIAnalysis, AIProviderConfig

logger = logging.getLogger(__name__)

CASH_TYPES = [Account.Type.SAVINGS, Account.Type.ALIPAY, Account.Type.WECHAT]
ASSET_TYPES = [
    Account.Type.SAVINGS,
    Account.Type.ALIPAY,
    Account.Type.WECHAT,
    Account.Type.STOCK,
    Account.Type.WEALTH,
    Account.Type.PROVIDENT_FUND_MAIN,
    Account.Type.PROVIDENT_FUND_SUPP,
]


def jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def get_setting(owner):
    setting, _ = UserSetting.objects.get_or_create(user=owner)
    return setting


def _sum(qs, field="amount", **filters):
    result = qs.filter(**filters).aggregate(total=Sum(field))["total"]
    return D(result or 0)


def period_summary(owner, start, end):
    qs = Transaction.objects.filter(
        owner=owner,
        status=Transaction.Status.POSTED,
        occurred_at__gte=day_start(start),
        occurred_at__lte=day_end(end),
    )
    income = _sum(qs, type=Transaction.Type.INCOME)
    expense = _sum(qs, type=Transaction.Type.EXPENSE)
    refund = _sum(qs, type=Transaction.Type.REFUND)
    living_expense = _sum(
        qs.filter(category__kind=Category.Kind.GENERAL), type=Transaction.Type.EXPENSE
    )
    investment_out = _sum(
        qs.filter(category__kind__in=[Category.Kind.INVESTMENT, Category.Kind.STOCK]),
        type=Transaction.Type.EXPENSE,
    )
    card_repayment = _sum(qs, type=Transaction.Type.TRANSFER_OUT, credit_card__isnull=False)
    periodic_cash = _sum(
        qs,
        type=Transaction.Type.EXPENSE,
        source=Transaction.Source.DEBT_PAYMENT,
        settlement_channel__in=[
            Transaction.SettlementChannel.CASH,
            Transaction.SettlementChannel.ALIPAY,
            Transaction.SettlementChannel.WECHAT,
        ],
    )
    category_rows = (
        qs.filter(type=Transaction.Type.EXPENSE, category__kind=Category.Kind.GENERAL)
        .values("category__id", "category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    return {
        "period_start": start,
        "period_end": end,
        "income": income,
        "expense": expense,
        "refund": refund,
        "net_expense": expense - refund,
        "living_expense": living_expense,
        "investment_out": investment_out,
        "card_repayment": card_repayment,
        "periodic_cash": periodic_cash,
        "savings_rate": percent(income - living_expense, income) if income > 0 else D("0"),
        "category_breakdown": [
            {
                "category_id": row["category__id"],
                "name": row["category__name"],
                "amount": D(row["total"] or 0),
            }
            for row in category_rows
        ],
    }


def _cash_due(item, offset_cache):
    payable = item.payable_amount
    if item.kind == DebtItem.Kind.CREDIT_CARD:
        return payable
    if item.kind == DebtItem.Kind.PERIODIC:
        channel = item.recurring_debt.payment_channel if item.recurring_debt_id else "CASH"
        return D("0") if channel in ("PROVIDENT_FUND", "CREDIT_CARD") else payable
    if item.kind == DebtItem.Kind.MORTGAGE and item.loan_schedule_id:
        loan = item.loan_schedule.loan
        plan = getattr(loan, "offset_plan", None)
        if not plan or not plan.enabled:
            return payable
        if loan.id not in offset_cache:
            offset_cache[loan.id] = simulate_offset(loan)
        row = next(
            (item_row for item_row in offset_cache[loan.id]["rows"] if item_row["period_no"] == item.period_no),
            None,
        )
        return D(row["cash_due"]) if row else payable
    return payable


def upcoming_payments(owner, start, end, offset_cache=None):
    offset_cache = offset_cache if offset_cache is not None else {}
    qs = (
        DebtItem.objects.filter(owner=owner)
        .exclude(status__in=[DebtItem.Status.PAID, DebtItem.Status.CANCELLED])
        .filter(due_date__lte=end)
        .select_related("bill__card", "recurring_debt", "loan_schedule__loan__offset_plan__pf_account")
        .order_by("due_date", "id")
    )
    rows = []
    for item in qs:
        cash_due = _cash_due(item, offset_cache)
        rows.append(
            {
                "id": item.id,
                "source": item.kind,
                "kind": item.kind,
                "title": item.title,
                "due_date": item.due_date,
                "amount": D(item.amount),
                "payable": item.payable_amount,
                "cash_due": cash_due,
                "status": item.status,
                "overdue": item.due_date < start,
            }
        )
    open_bills = CreditCardBill.objects.filter(
        owner=owner,
        status=CreditCardBill.Status.OPEN,
        total_amount__gt=0,
        due_date__lte=end,
    ).select_related("card")
    for bill in open_bills:
        rows.append(
            {
                "id": f"bill-{bill.id}",
                "source": "CREDIT_CARD_OPEN",
                "kind": "CREDIT_CARD",
                "title": f"{bill.card.name} 预计账单",
                "due_date": bill.due_date,
                "amount": D(bill.total_amount),
                "payable": D(bill.total_amount),
                "cash_due": D(bill.total_amount),
                "status": "PROJECTED",
                "overdue": bill.due_date < start,
            }
        )
    rows.sort(key=lambda row: (row["due_date"], str(row["id"])))
    return rows


def net_worth(owner):
    balances = balances_for_owner(owner)
    accounts = list(Account.objects.filter(owner=owner, is_active=True))
    account_total = sum((balances.get(account.id, D(account.opening_balance)) for account in accounts), D("0"))
    investment = portfolio_summary(owner)["totals"]
    physical_assets = sum(
        (asset_value(asset) for asset in Asset.objects.filter(owner=owner, status=Asset.Status.ACTIVE)), D("0")
    )
    cards = CreditCard.objects.filter(owner=owner, is_active=True)
    card_debt = sum((card_liability(card) for card in cards), D("0"))
    periodic_debt = D("0")
    for item in DebtItem.objects.filter(
        owner=owner,
        kind=DebtItem.Kind.PERIODIC,
        status__in=[DebtItem.Status.PENDING, DebtItem.Status.PARTIAL, DebtItem.Status.OVERDUE],
    ):
        periodic_debt += item.payable_amount
    loan_debt = D("0")
    loan_detail = []
    for loan in Loan.objects.filter(owner=owner, status=Loan.Status.ACTIVE):
        stats = loan_stats(loan)
        loan_debt += stats["remaining_principal"]
        loan_detail.append(
            {
                "id": loan.id,
                "name": loan.name,
                "remaining_principal": stats["remaining_principal"],
            }
        )
    liabilities = card_debt + periodic_debt + loan_debt
    total_assets = account_total + D(investment["market_value"]) + physical_assets
    return {
        "account_total": account_total,
        "cash": cash_balance(owner),
        "investment_market_value": D(investment["market_value"]),
        "physical_assets": physical_assets,
        "total_assets": total_assets,
        "card_debt": card_debt,
        "periodic_debt": periodic_debt,
        "loan_debt": loan_debt,
        "loans": loan_detail,
        "liabilities": liabilities,
        "net_worth": total_assets - liabilities,
    }


def monthly_series(owner, months_back=6, months_forward=3):
    today = today_local()
    current_start, _ = month_bounds(today)
    setting = get_setting(owner)
    series = []
    start_month = add_months(current_start, -(months_back - 1))
    for index in range(months_back):
        month_start = add_months(start_month, index)
        month_end = month_bounds(month_start)[1]
        summary = period_summary(owner, month_start, month_end)
        series.append(
            {
                "month": f"{month_start:%Y-%m}",
                "income": summary["income"],
                "expense": summary["living_expense"],
                "card_repayment": summary["card_repayment"],
                "periodic_cash": summary["periodic_cash"],
                "ending_cash": cash_balance(owner, as_of=month_end),
                "actual": True,
            }
        )
    recent = [row for row in series[-3:] if row["actual"]]
    avg_expense = (
        sum((row["expense"] for row in recent), D("0")) / len(recent) if recent else D("0")
    )
    salary = D(setting.salary_amount) if setting.salary_amount is not None else D("0")
    balance = series[-1]["ending_cash"] if series else cash_balance(owner)
    for index in range(1, months_forward + 1):
        month_start = add_months(current_start, index)
        month_end = month_bounds(month_start)[1]
        month_end_date = month_end
        debt_items = DebtItem.objects.filter(
            owner=owner,
            due_date__gte=month_start,
            due_date__lte=month_end_date,
        ).exclude(status__in=[DebtItem.Status.PAID, DebtItem.Status.CANCELLED]).select_related(
            "recurring_debt", "loan_schedule__loan__offset_plan__pf_account"
        )
        offset_cache = {}
        card_repayment = D("0")
        periodic_cash = D("0")
        for item in debt_items:
            cash_due = _cash_due(item, offset_cache)
            if item.kind == DebtItem.Kind.CREDIT_CARD:
                card_repayment += cash_due
            elif item.kind in (DebtItem.Kind.PERIODIC, DebtItem.Kind.MORTGAGE):
                periodic_cash += cash_due
        balance = balance + salary - avg_expense - card_repayment - periodic_cash
        series.append(
            {
                "month": f"{month_start:%Y-%m}",
                "income": salary,
                "expense": avg_expense,
                "card_repayment": card_repayment,
                "periodic_cash": periodic_cash,
                "ending_cash": balance,
                "actual": False,
            }
        )
    return series


def daily_series(owner, start, end, salary=D("0"), events=None):
    events = events or defaultdict(lambda: D("0"))
    balance = cash_balance(owner, as_of=start)
    series = []
    for current in date_range(start, end):
        inflow = D(salary) if current == end else D("0")
        outflow = D(events.get(current, D("0")))
        balance = balance + inflow - outflow
        series.append(
            {
                "date": current,
                "inflow": inflow,
                "outflow": outflow,
                "balance": balance,
            }
        )
    return series


def overview(owner, as_of=None):
    today = as_of or today_local()
    setting = get_setting(owner)
    payday = next_payday(today, setting.payday)
    offset_cache = {}
    upcoming = upcoming_payments(owner, today, payday, offset_cache)
    cash_now = cash_balance(owner, as_of=today)
    salary = D(setting.salary_amount) if setting.salary_amount is not None else D("0")
    events = defaultdict(lambda: D("0"))
    for row in upcoming:
        events[row["due_date"]] += D(row["cash_due"])
    daily = daily_series(owner, today, payday, salary=salary, events=events)
    projected = daily[-1]["balance"] if daily else cash_now
    upcoming_total = sum((D(row["cash_due"]) for row in upcoming), D("0"))
    min_balance = min((row["balance"] for row in daily), default=cash_now)
    current_start, current_end = month_bounds(today)
    current_summary = period_summary(owner, current_start, current_end)
    investment = portfolio_summary(owner)["totals"]
    worth = net_worth(owner)
    overdue = sum(1 for row in upcoming if row["overdue"])
    alerts = []
    if overdue:
        alerts.append(f"有 {overdue} 笔应还未还，已逾期")
    if min_balance < 0:
        alerts.append(f"发薪日前现金缺口约 {abs(min_balance)}")
    if not AIProviderConfig.objects.filter(owner=owner, enabled=True).exists():
        alerts.append("尚未配置 AI 服务")
    return {
        "as_of": today,
        "payday": payday,
        "days_to_payday": (payday - today).days,
        "cash_now": cash_now,
        "salary_expected": salary,
        "upcoming_total": upcoming_total,
        "projected_cash": projected,
        "min_cash": min_balance,
        "shortfall": abs(min_balance) if min_balance < 0 else D("0"),
        "upcoming": upcoming,
        "daily_series": daily,
        "monthly_series": monthly_series(owner),
        "current_month": current_summary,
        "investment": investment,
        "net_worth": worth,
        "alerts": alerts,
    }


def build_snapshot(owner, period_start=None, period_end=None):
    today = today_local()
    if not period_start or not period_end:
        period_start, period_end = month_bounds(today)
    summary = period_summary(owner, period_start, period_end)
    overview_data = overview(owner)
    snapshot = {
        "period": {"start": period_start, "end": period_end},
        "cashflow": summary,
        "cash": {
            "cash_now": overview_data["cash_now"],
            "projected_cash": overview_data["projected_cash"],
            "upcoming_total": overview_data["upcoming_total"],
            "shortfall": overview_data["shortfall"],
        },
        "upcoming": [
            {
                "title": row["title"],
                "due_date": row["due_date"],
                "amount": row["amount"],
                "cash_due": row["cash_due"],
                "kind": row["kind"],
            }
            for row in overview_data["upcoming"]
        ],
        "net_worth": overview_data["net_worth"],
        "investment": overview_data["investment"],
        "monthly_series": overview_data["monthly_series"],
    }
    return jsonable(snapshot)


def _chat_url(base_url):
    value = base_url.rstrip("/")
    if value.endswith("/chat/completions"):
        return value
    return f"{value}/chat/completions"


def _error_detail(response):
    try:
        data = response.json()
        error = data.get("error") or {}
        message = error.get("message") or data.get("message") or response.text
        code = error.get("code") or ""
        return f"{message}" + (f"（{code}）" if code else "")
    except Exception:
        return response.text[:500]


def _retry_after_seconds(response, default):
    raw = response.headers.get("Retry-After")
    if raw:
        try:
            return max(1, int(float(raw)))
        except (TypeError, ValueError):
            pass
    return max(1, int(default or 60))


def call_provider(provider, messages, max_tokens=None, retries_override=None):
    key = decrypt_text(provider.api_key_encrypted)
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    if provider.extra_headers:
        headers.update(provider.extra_headers)
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": float(provider.temperature),
        "max_tokens": max_tokens or provider.max_tokens,
    }
    if provider.extra_body:
        payload.update(provider.extra_body)
    # SenseNova DeepSeek V4.1 Flash defaults to thinking mode. The reasoning
    # content consumes the output budget and is not the answer we want in a
    # financial report; disable it unless the caller explicitly opted in.
    if (
        "thinking" not in payload
        and "sensenova" in provider.base_url.lower()
        and provider.model.startswith("deepseek")
    ):
        payload["thinking"] = {"type": "disabled"}
    retries = (
        max(0, int(retries_override))
        if retries_override is not None
        else max(0, int(provider.max_retries or 0))
    )
    wait_default = provider.retry_wait_seconds or 60
    last_error = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(
                _chat_url(provider.base_url),
                json=payload,
                headers=headers,
                timeout=provider.timeout_seconds,
            )
        except requests.Timeout as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(10 * (attempt + 1), 30))
                continue
            raise RuntimeError(
                f"AI 服务请求超时（{provider.timeout_seconds}s）。"
                "DeepSeek V4.1 Flash 思考模式可能耗时较长，可关闭 thinking 或提高超时时间。"
            ) from exc
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(min(5 * (attempt + 1), 20))
                continue
            raise RuntimeError(f"AI 服务网络错误：{exc}") from exc

        if response.status_code == 429:
            wait = _retry_after_seconds(response, wait_default)
            detail = _error_detail(response)
            if attempt < retries:
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"AI 服务限流（429）：{detail}。已重试 {retries} 次；"
                f"当前账号可能受 RPM/TPM 配额限制，请等待约 {wait} 秒后重试，"
                "或在服务商控制台提升配额/更换 API Key。DeepSeek V4.1 Flash "
                "默认思考模式会消耗大量输出 token，建议保持 thinking=disabled 并适当降低 max_tokens。"
            )
        if response.status_code >= 500:
            detail = _error_detail(response)
            if attempt < retries:
                time.sleep(min(10 * (attempt + 1), 30))
                continue
            raise RuntimeError(f"AI 服务暂时不可用（{response.status_code}）：{detail}")
        if response.status_code >= 400:
            detail = _error_detail(response)
            hint = ""
            if response.status_code in (401, 403):
                hint = " 请检查 API Key、模型是否在当前 token plan 中，以及 Base URL 是否为 https://token.sensenova.cn/v1。"
            raise RuntimeError(f"AI 服务返回 {response.status_code}：{detail}{hint}")

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("AI 服务未返回 choices 内容")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        reasoning = message.get("reasoning_content") or ""
        if not content:
            if reasoning:
                raise RuntimeError(
                    "AI 服务只返回了 reasoning_content，没有最终回答。"
                    "通常是 max_tokens 太小被思考过程耗尽；建议增大 max_tokens，"
                    "或在请求体中设置 {\"thinking\": {\"type\": \"disabled\"}}。"
                )
            raise RuntimeError("AI 服务返回空内容，请检查模型、提示词和 max_tokens。")
        tokens = (data.get("usage") or {}).get("total_tokens", 0)
        return content, tokens
    raise RuntimeError(f"AI 服务请求失败：{last_error}")


def test_provider(provider):
    content, tokens = call_provider(
        provider,
        [
            {"role": "system", "content": "你是连通性测试助手，只回复 OK。"},
            {"role": "user", "content": "请回复 OK"},
        ],
        max_tokens=128,
        retries_override=0,
    )
    return {"ok": True, "content": content, "tokens": tokens}


def generate_analysis(
    owner,
    analysis_type=AIAnalysis.Type.MONTHLY,
    provider=None,
    period_start=None,
    period_end=None,
    custom_prompt="",
):
    provider = provider or AIProviderConfig.objects.filter(owner=owner, enabled=True, is_default=True).first()
    if not provider:
        provider = AIProviderConfig.objects.filter(owner=owner, enabled=True).first()
    if not provider:
        raise ValidationError({"detail": "请先配置 AI 服务"})
    today = today_local()
    if not period_start or not period_end:
        period_start, period_end = month_bounds(today)
    snapshot = build_snapshot(owner, period_start, period_end)
    system_prompt = (
        "你是一名谨慎、务实的个人财务顾问。只依据用户提供的账务数据进行分析，"
        "不要编造数据，不要给出具体证券买卖指令，不承诺收益。"
        "输出中文，结构清晰，包含：现金流与储蓄率、债务与还款风险、投资与净资产、"
        "未来 30 天风险点、3-5 条可执行建议。金额保留两位小数。"
    )
    user_prompt = (
        f"分析类型：{analysis_type}\n"
        f"分析区间：{period_start} 至 {period_end}\n"
        f"以下是聚合后的财务数据 JSON：\n{json.dumps(snapshot, ensure_ascii=False, indent=2)}\n"
    )
    if custom_prompt:
        user_prompt += f"\n用户额外要求：{custom_prompt}\n"
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    analysis = AIAnalysis.objects.create(
        owner=owner,
        analysis_type=analysis_type,
        period_start=period_start,
        period_end=period_end,
        provider=provider,
        data_snapshot=snapshot,
        prompt_snapshot=json.dumps(messages, ensure_ascii=False),
        status=AIAnalysis.Status.PENDING,
    )
    started = time.monotonic()
    try:
        content, tokens = call_provider(provider, messages)
        analysis.response_text = content
        analysis.tokens = tokens
        analysis.status = AIAnalysis.Status.SUCCESS
    except Exception as exc:
        logger.exception("AI analysis failed")
        analysis.status = AIAnalysis.Status.FAILED
        analysis.error = str(exc)
    analysis.elapsed_ms = int((time.monotonic() - started) * 1000)
    analysis.save()
    return analysis


def meta_enums():
    from apps.debts.models import DebtPayment, RecurringDebt
    from apps.investments.models import Instrument, Trade
    from apps.ledger.models import InstallmentPlan, Transaction
    from apps.mortgages.models import Loan, OffsetPlan

    return {
        "account_types": Account.Type.choices,
        "transaction_types": Transaction.Type.choices,
        "settlement_channels": Transaction.SettlementChannel.choices,
        "operations": Transaction.Operation.choices,
        "category_kinds": Category.Kind.choices,
        "credit_card_bill_status": CreditCardBill.Status.choices,
        "debt_kinds": DebtItem.Kind.choices,
        "debt_status": DebtItem.Status.choices,
        "payment_channels": DebtPayment.Channel.choices,
        "recurring_types": RecurringDebt.DebtType.choices,
        "loan_types": Loan.LoanType.choices,
        "repayment_methods": Loan.RepaymentMethod.choices,
        "offset_modes": OffsetPlan.Mode.choices,
        "installment_fee_modes": InstallmentPlan.FeeMode.choices,
        "instrument_types": Instrument.Type.choices,
        "exchanges": Instrument.Exchange.choices,
        "trade_sides": Trade.Side.choices,
        "trade_operations": Trade.Operation.choices,
        "asset_types": Asset.Type.choices,
        "asset_valuation_modes": Asset.ValuationMode.choices,
    }
