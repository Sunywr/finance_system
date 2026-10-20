import logging
import time
from datetime import date, datetime, timedelta
from decimal import Decimal

import requests
from django.conf import settings

from .models import Instrument

logger = logging.getLogger(__name__)

QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _session():
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Referer": "https://quote.eastmoney.com/",
        }
    )
    proxies = {"http": None, "https": None}
    if settings.MARKET_DATA_PROXY:
        proxies = {"http": settings.MARKET_DATA_PROXY, "https": settings.MARKET_DATA_PROXY}
    session.proxies.update(proxies)
    return session


def _secid(instrument):
    if instrument.exchange == Instrument.Exchange.SH:
        return f"1.{instrument.symbol}"
    if instrument.exchange in (Instrument.Exchange.SZ, Instrument.Exchange.BJ):
        return f"0.{instrument.symbol}"
    return None


def _num(value, default=None):
    if value in (None, "", "-", "—"):
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _get(url, params, timeout=None):
    timeout = timeout or settings.MARKET_DATA_TIMEOUT
    last_error = None
    for attempt in range(5):
        try:
            with _session() as session:
                response = session.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                return response.json()
        except Exception as exc:
            last_error = exc
            logger.warning("market request failed (%s/%s): %s", attempt + 1, 5, exc)
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(str(last_error))


def fetch_quote(instrument):
    secid = _secid(instrument)
    if not secid:
        return None
    payload = _get(
        QUOTE_URL,
        {
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60,f116,f117,f162,f167,f170",
            "fltt": 2,
            "invt": 2,
        },
    )
    data = payload.get("data")
    if not data:
        return None
    price = _num(data.get("f43"))
    prev_close = _num(data.get("f60"))
    change_pct = _num(data.get("f170"))
    return {
        "symbol": data.get("f57") or instrument.symbol,
        "name": data.get("f58") or instrument.name,
        "price": price or prev_close or Decimal("0"),
        "prev_close": prev_close or Decimal("0"),
        "change_pct": change_pct or Decimal("0"),
        "open": _num(data.get("f46"), Decimal("0")),
        "high": _num(data.get("f44"), Decimal("0")),
        "low": _num(data.get("f45"), Decimal("0")),
        "volume": _num(data.get("f47"), Decimal("0")),
        "amount": _num(data.get("f48"), Decimal("0")),
        "market_cap": _num(data.get("f116")),
        "float_market_cap": _num(data.get("f117")),
        "pe": _num(data.get("f162")),
        "pb": _num(data.get("f167")),
        "source": "eastmoney",
    }


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None


def fetch_spot_universe(max_pages=10, page_size=100):
    """Top A-share universe by total market cap, using Eastmoney's 100-row pages."""
    rows = []
    for page in range(1, max_pages + 1):
        payload = _get(
            CLIST_URL,
            {
                "pn": page,
                "pz": page_size,
                "po": 1,
                "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2,
                "invt": 2,
                "fid": "f20",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f2,f3,f5,f6,f8,f9,f10,f12,f14,f20,f21,f23,f24,f25,f62,f100",
            },
        )
        data = payload.get("data") or {}
        batch = data.get("diff") or []
        if not batch:
            break
        for item in batch:
            price = _num(item.get("f2"))
            if price is None or price <= 0:
                continue
            rows.append(
                {
                    "symbol": str(item.get("f12") or ""),
                    "name": item.get("f14") or "",
                    "price": price,
                    "change_pct": _num(item.get("f3"), Decimal("0")),
                    "volume": _num(item.get("f5"), Decimal("0")),
                    "amount": _num(item.get("f6"), Decimal("0")),
                    "turnover": _num(item.get("f8"), Decimal("0")),
                    "pe": _num(item.get("f9")),
                    "volume_ratio": _num(item.get("f10")),
                    "market_cap": _num(item.get("f20")),
                    "float_market_cap": _num(item.get("f21")),
                    "pb": _num(item.get("f23")),
                    "change_60d": _num(item.get("f24")),
                    "change_ytd": _num(item.get("f25")),
                    "industry": item.get("f100") or "",
                }
            )
        if len(batch) < page_size:
            break
        time.sleep(0.8)
    return rows


def fetch_index_bars(symbol="000300", exchange="SH", limit=180):
    fake = Instrument(symbol=symbol, exchange=exchange, name="", type=Instrument.Type.STOCK)
    return fetch_bars(fake, limit=limit)


def fetch_reports(instrument, limit=8):
    payload = _get(
        DATACENTER_URL,
        {
            "reportName": "RPT_LICO_FN_CPD",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{instrument.symbol}")',
            "pageNumber": 1,
            "pageSize": limit,
            "sortColumns": "REPORTDATE",
            "sortTypes": -1,
        },
    )
    data = (payload.get("result") or {}).get("data") or []
    rows = []
    for item in data:
        period_end = _parse_date(item.get("REPORTDATE"))
        if not period_end:
            continue
        month = period_end.month
        report_type = "Q1" if month == 3 else "H1" if month == 6 else "Q3" if month == 9 else "ANNUAL"
        rows.append(
            {
                "report_type": report_type,
                "period_end": period_end,
                "actual_date": _parse_date(item.get("NOTICE_DATE") or item.get("UPDATE_DATE")),
                "revenue": _num(item.get("TOTAL_OPERATE_INCOME")),
                "net_profit": _num(item.get("PARENT_NETPROFIT")),
                "revenue_yoy": _num(item.get("YSTZ")),
                "profit_yoy": _num(item.get("SJLTZ")),
                "roe": _num(item.get("WEIGHTAVG_ROE")),
                "eps": _num(item.get("BASIC_EPS")),
                "summary": item.get("REPORT_TYPE") or "",
            }
        )
    return rows


def fetch_report_appointments(instrument, limit=8):
    payload = _get(
        DATACENTER_URL,
        {
            "reportName": "RPT_PUBLIC_BS_APPOIN",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{instrument.symbol}")',
            "pageNumber": 1,
            "pageSize": limit,
            "sortColumns": "REPORT_DATE",
            "sortTypes": -1,
        },
    )
    data = (payload.get("result") or {}).get("data") or []
    rows = []
    for item in data:
        period_end = _parse_date(item.get("REPORT_DATE"))
        if not period_end:
            continue
        month = period_end.month
        report_type = "Q1" if month == 3 else "H1" if month == 6 else "Q3" if month == 9 else "ANNUAL"
        rows.append(
            {
                "report_type": report_type,
                "period_end": period_end,
                "disclosure_date": _parse_date(item.get("APPOINT_PUBLISH_DATE")),
                "actual_date": _parse_date(item.get("ACTUAL_PUBLISH_DATE")),
            }
        )
    return rows


def fetch_ipo_calendar(limit=50):
    payload = _get(
        DATACENTER_URL,
        {
            "reportName": "RPTA_APP_IPOAPPLY",
            "columns": "ALL",
            "pageNumber": 1,
            "pageSize": limit,
            "sortColumns": "APPLY_DATE",
            "sortTypes": -1,
        },
    )
    data = (payload.get("result") or {}).get("data") or []
    today = date.today()
    rows = []
    for item in data:
        apply_date = _parse_date(item.get("APPLY_DATE"))
        listing_date = _parse_date(item.get("LISTING_DATE"))
        if listing_date and listing_date <= today:
            status = "已上市"
        elif apply_date and apply_date > today:
            status = "待申购"
        else:
            status = "申购/待上市"
        rows.append(
            {
                "code": str(item.get("SECURITY_CODE") or ""),
                "name": item.get("SECURITY_NAME") or "",
                "market": item.get("MARKET_TYPE") or "",
                "apply_code": str(item.get("APPLY_CODE") or ""),
                "apply_date": apply_date,
                "listing_date": listing_date,
                "issue_price": _num(item.get("ISSUE_PRICE") or item.get("ONLINE_APPLY_PRICE")),
                "issue_num": _num(item.get("ISSUE_NUM")),
                "online_apply_upper": _num(item.get("ONLINE_APPLY_UPPER")),
                "requirement_market_value": _num(item.get("TOP_APPLY_MARKETCAP")),
                "status": status,
            }
        )
    return rows


def fetch_bars(instrument, limit=300):
    secid = _secid(instrument)
    if not secid:
        return []
    begin = (date.today() - timedelta(days=max(limit * 2, 400))).strftime("%Y%m%d")
    payload = _get(
        KLINE_URL,
        {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": 101,
            "fqt": 1,
            "beg": begin,
            "end": 20500101,
            "lmt": limit,
        },
    )
    data = payload.get("data")
    if not data:
        return []
    rows = []
    for line in data.get("klines", []):
        values = line.split(",")
        if len(values) < 7:
            continue
        rows.append(
            {
                "trade_date": values[0],
                "open": _num(values[1], Decimal("0")),
                "close": _num(values[2], Decimal("0")),
                "high": _num(values[3], Decimal("0")),
                "low": _num(values[4], Decimal("0")),
                "volume": _num(values[5], Decimal("0")),
                "amount": _num(values[6], Decimal("0")),
            }
        )
    return rows
