import math

import pandas as pd


def _clean(value, digits=4):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return round(number, digits)


def build_indicator_rows(rows):
    """Compute MA/MACD/KDJ/RSI/BOLL from ascending daily bars.

    Rows are dicts with trade_date/open/high/low/close/volume.
    """
    if not rows:
        return []
    df = pd.DataFrame(rows).copy()
    df = df.sort_values("trade_date").reset_index(drop=True)
    for column in ("open", "high", "low", "close", "volume"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    df["ma5"] = close.rolling(5).mean()
    df["ma10"] = close.rolling(10).mean()
    df["ma20"] = close.rolling(20).mean()
    df["ma60"] = close.rolling(60).mean()

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["macd_dif"] = ema12 - ema26
    df["macd_dea"] = df["macd_dif"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = (df["macd_dif"] - df["macd_dea"]) * 2

    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, pd.NA) * 100
    df["kdj_k"] = rsv.ewm(com=2, adjust=False).mean()
    df["kdj_d"] = df["kdj_k"].ewm(com=2, adjust=False).mean()
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]

    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    for period in (6, 12, 24):
        avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, pd.NA)
        df[f"rsi{period}"] = 100 - 100 / (1 + rs)

    df["boll_mid"] = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    df["boll_upper"] = df["boll_mid"] + 2 * std
    df["boll_lower"] = df["boll_mid"] - 2 * std
    df["volume_ma5"] = volume.rolling(5).mean()

    result = []
    for _, row in df.iterrows():
        result.append(
            {
                "trade_date": row["trade_date"],
                "open": _clean(row["open"]),
                "high": _clean(row["high"]),
                "low": _clean(row["low"]),
                "close": _clean(row["close"]),
                "volume": _clean(row["volume"], 2),
                "ma5": _clean(row["ma5"]),
                "ma10": _clean(row["ma10"]),
                "ma20": _clean(row["ma20"]),
                "ma60": _clean(row["ma60"]),
                "macd_dif": _clean(row["macd_dif"], 6),
                "macd_dea": _clean(row["macd_dea"], 6),
                "macd_hist": _clean(row["macd_hist"], 6),
                "kdj_k": _clean(row["kdj_k"]),
                "kdj_d": _clean(row["kdj_d"]),
                "kdj_j": _clean(row["kdj_j"]),
                "rsi6": _clean(row["rsi6"]),
                "rsi12": _clean(row["rsi12"]),
                "rsi24": _clean(row["rsi24"]),
                "boll_upper": _clean(row["boll_upper"]),
                "boll_mid": _clean(row["boll_mid"]),
                "boll_lower": _clean(row["boll_lower"]),
            }
        )
    return result


def latest_signals(rows, computed=None):
    computed = computed or build_indicator_rows(rows)
    if not computed:
        return {}
    latest = computed[-1]
    previous = computed[-2] if len(computed) > 1 else None
    signals = {}
    if previous:
        signals["macd_golden_cross"] = bool(
            previous.get("macd_dif") is not None
            and latest.get("macd_dif") is not None
            and previous["macd_dif"] <= previous["macd_dea"]
            and latest["macd_dif"] > latest["macd_dea"]
        )
        signals["macd_death_cross"] = bool(
            previous.get("macd_dif") is not None
            and latest.get("macd_dif") is not None
            and previous["macd_dif"] >= previous["macd_dea"]
            and latest["macd_dif"] < latest["macd_dea"]
        )
        signals["kdj_golden_cross"] = bool(
            previous.get("kdj_k") is not None
            and latest.get("kdj_k") is not None
            and previous["kdj_k"] <= previous["kdj_d"]
            and latest["kdj_k"] > latest["kdj_d"]
        )
    signals["above_ma20"] = bool(latest.get("ma20") and (latest.get("close") or 0) > latest["ma20"])
    signals["above_ma60"] = bool(latest.get("ma60") and (latest.get("close") or 0) > latest["ma60"])
    signals["kdj_oversold"] = bool(latest.get("kdj_k") is not None and latest["kdj_k"] < 20)
    signals["kdj_overbought"] = bool(latest.get("kdj_k") is not None and latest["kdj_k"] > 80)
    signals["rsi_oversold"] = bool(latest.get("rsi6") is not None and latest["rsi6"] < 30)
    signals["rsi_overbought"] = bool(latest.get("rsi6") is not None and latest["rsi6"] > 70)
    return signals
