from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

try:
    import pandas as pd
except ImportError:  # pragma: no cover - research dependency
    pd = None  # type: ignore[assignment]


@dataclass
class EventPosition:
    symbol: str
    entry_date: str
    entry_price: float
    qty: float
    high_water: float
    age_days: int = 0
    days_since_review: int = 0


@dataclass
class EventTrade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    qty: float
    pnl: float
    reason: str


def _safe_float(v, default: float = float("nan")) -> float:
    try:
        x = float(v)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def _atr_pct(df, i: int, period: int = 20) -> float:
    if i < period + 1:
        return 0.0
    trs: List[float] = []
    for j in range(i - period + 1, i + 1):
        prev = _safe_float(df["Close"].iloc[j - 1])
        high = _safe_float(df["High"].iloc[j])
        low = _safe_float(df["Low"].iloc[j])
        close = _safe_float(df["Close"].iloc[j])
        if min(prev, high, low, close) <= 0:
            continue
        trs.append(max(high - low, abs(high - prev), abs(low - prev)))
    close_now = _safe_float(df["Close"].iloc[i])
    if not trs or close_now <= 0:
        return 0.0
    return sum(trs) / len(trs) / close_now


def _momentum(df, i: int, lookback: int) -> float:
    if i < lookback:
        return float("nan")
    prev = _safe_float(df["Close"].iloc[i - lookback])
    cur = _safe_float(df["Close"].iloc[i])
    if prev <= 0 or cur <= 0:
        return float("nan")
    return cur / prev - 1.0



# Sector map — used to tag ranked output for diversity-aware selection
_SECTOR_MAP: dict[str, str] = {
    # Tech
    "AAPL": "tech", "MSFT": "tech", "NVDA": "tech", "GOOGL": "tech",
    "META": "tech", "AMZN": "tech", "AVGO": "tech", "AMD": "tech",
    "QCOM": "tech", "MU": "tech", "AMAT": "tech", "LRCX": "tech",
    "KLAC": "tech", "MRVL": "tech", "TXN": "tech", "ARM": "tech",
    "CRM": "tech", "ADBE": "tech", "NOW": "tech", "ORCL": "tech",
    "SNOW": "tech", "PLTR": "tech", "DDOG": "tech", "CRWD": "tech",
    "PANW": "tech",
    # Finance
    "JPM": "finance", "GS": "finance", "BAC": "finance", "V": "finance",
    "MA": "finance", "BLK": "finance", "SCHW": "finance", "MS": "finance",
    "AXP": "finance", "SPGI": "finance", "ICE": "finance", "BRK-B": "finance",
    # Healthcare
    "UNH": "health", "LLY": "health", "ABBV": "health", "JNJ": "health",
    "MRK": "health", "ISRG": "health", "TMO": "health", "ABT": "health",
    "PFE": "health",
    # Consumer
    "WMT": "consumer", "COST": "consumer", "PG": "consumer", "KO": "consumer",
    "PEP": "consumer", "MCD": "consumer", "SBUX": "consumer", "NKE": "consumer",
    "TGT": "consumer", "TSLA": "consumer",
    # Energy
    "XOM": "energy", "CVX": "energy", "COP": "energy", "OXY": "energy",
    "SLB": "energy",
    # Industrial
    "CAT": "industrial", "DE": "industrial", "HON": "industrial",
    "GE": "industrial", "RTX": "industrial", "LMT": "industrial", "BA": "industrial",
    # Telecom / Media
    "NFLX": "media", "DIS": "media", "T": "telecom", "VZ": "telecom",
    # Growth / Fintech
    "UBER": "growth", "ABNB": "growth", "COIN": "growth",
    "HOOD": "growth", "SOFI": "growth",
    # Dividend
    "O": "reit",
}

def rank_symbols(data: Dict[str, object], date, lookback: int = 60) -> List[dict]:
    rows: List[dict] = []
    for symbol, df in data.items():
        if date not in df.index:
            continue
        i = int(df.index.get_loc(date))
        mom60 = _momentum(df, i, lookback)
        mom20 = _momentum(df, i, 20)
        atr20 = _atr_pct(df, i, 20)
        close = _safe_float(df["Close"].iloc[i])
        if not all(math.isfinite(x) for x in (mom60, mom20, atr20, close)) or close <= 0:
            continue
        score = mom60 + 0.35 * mom20 - 0.45 * atr20
        rows.append({
            "symbol": symbol,
            "score": score,
            "mom60": mom60,
            "mom20": mom20,
            "atr20": atr20,
            "close": close,
            "sector": _SECTOR_MAP.get(symbol, "other"),
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def _price(data: Dict[str, object], symbol: str, date) -> Optional[float]:
    df = data.get(symbol)
    if df is None or date not in df.index:
        return None
    close = _safe_float(df.loc[date, "Close"])
    return close if close > 0 else None


def _drawdown_pct(points: Iterable[float]) -> float:
    peak = -math.inf
    worst = 0.0
    for value in points:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return abs(worst) * 100.0


def _monthly_returns(daily_equity: List[tuple[str, float]]) -> List[float]:
    if not daily_equity:
        return []
    out: List[float] = []
    cur_month = daily_equity[0][0][:7]
    start_value = daily_equity[0][1]
    last_value = start_value
    for day, value in daily_equity[1:]:
        month = day[:7]
        if month != cur_month:
            if start_value > 0:
                out.append((last_value / start_value - 1.0) * 100.0)
            cur_month = month
            start_value = last_value
        last_value = value
    if start_value > 0:
        out.append((last_value / start_value - 1.0) * 100.0)
    return out


def summarize_result(result: dict) -> dict:
    trades: List[EventTrade] = list(result.get("trades") or [])
    daily_equity: List[tuple[str, float]] = list(result.get("daily_equity") or [])
    initial = float(result.get("initial_capital") or 0.0)
    final = float(result.get("final_equity") or initial)
    months = _monthly_returns(daily_equity)
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl < 0]
    pf = sum(wins) / abs(sum(losses)) if losses else (999.0 if wins else 0.0)
    winrate = len(wins) / len(trades) * 100.0 if trades else 0.0
    return {
        "return_pct": (final / initial - 1.0) * 100.0 if initial > 0 else 0.0,
        "max_dd_pct": _drawdown_pct(v for _, v in daily_equity),
        "trades": len(trades),
        "winrate_pct": winrate,
        "profit_factor": pf,
        "neg_months": sum(1 for m in months if m < 0),
        "n_months": len(months),
        "worst_month_pct": min(months) if months else 0.0,
        "best_month_pct": max(months) if months else 0.0,
    }


def run_event_v3(
    data: Dict[str, object],
    *,
    initial_capital: float = 1000.0,
    max_positions: int = 4,
    profit_trigger_pct: float = 8.0,
    profit_pullback_pct: float = 2.5,
    stop_pct: float = 5.0,
    peer_outperform_pct: float = 10.0,
    max_age_days: int = 14,
    hard_max_age_days: int = 60,
    fee_bps: float = 1.0,
) -> dict:
    if pd is None:
        raise RuntimeError("pandas is required")
    all_dates = sorted(set().union(*(set(df.index) for df in data.values())))
    if not all_dates:
        raise ValueError("no dates")

    cash = float(initial_capital)
    review_interval_days = max(1, int(max_age_days))
    hard_holding_limit_days = max(1, int(hard_max_age_days))
    positions: Dict[str, EventPosition] = {}
    cooldown: Dict[str, int] = {}
    trades: List[EventTrade] = []
    daily_equity: List[tuple[str, float]] = []

    def equity(date) -> float:
        value = cash
        for pos in positions.values():
            price = _price(data, pos.symbol, date)
            if price is not None:
                value += pos.qty * price
        return value

    def close_position(symbol: str, date, price: float, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(symbol)
        gross = (price - pos.entry_price) * pos.qty
        fees = (pos.entry_price * pos.qty + price * pos.qty) * fee_bps / 10_000.0
        pnl = gross - fees
        cash += pos.qty * price - fees
        trades.append(EventTrade(symbol, pos.entry_date, str(date.date()), pos.entry_price, price, pos.qty, pnl, reason))
        cooldown[symbol] = 3

    def open_position(symbol: str, date, price: float, slot_value: float) -> None:
        nonlocal cash
        if price <= 0 or slot_value <= 0 or cash <= 0:
            return
        spend = min(cash, slot_value)
        fee = spend * fee_bps / 10_000.0
        qty = max(0.0, (spend - fee) / price)
        if qty <= 0:
            return
        cash -= spend
        positions[symbol] = EventPosition(symbol, str(date.date()), price, qty, price, 0)

    for date in all_dates:
        for symbol in list(cooldown):
            cooldown[symbol] -= 1
            if cooldown[symbol] <= 0:
                del cooldown[symbol]

        ranks = rank_symbols(data, date)
        rank_by_symbol = {r["symbol"]: r for r in ranks}
        top_symbols = [r["symbol"] for r in ranks[: max_positions * 2]]

        for symbol, pos in list(positions.items()):
            price = _price(data, symbol, date)
            if price is None:
                continue
            pos.age_days += 1
            pos.days_since_review += 1
            pos.high_water = max(pos.high_water, price)
            gain_pct = (price / pos.entry_price - 1.0) * 100.0
            pullback_pct = (pos.high_water / price - 1.0) * 100.0 if price > 0 else 0.0

            reason = ""
            if gain_pct <= -stop_pct:
                reason = "stop_5pct"
            elif (pos.high_water / pos.entry_price - 1.0) * 100.0 >= profit_trigger_pct and pullback_pct >= profit_pullback_pct:
                reason = "profit_lock_pullback"
            elif pos.age_days >= hard_holding_limit_days:
                reason = "hard_max_age"
            elif pos.days_since_review >= review_interval_days:
                cur_score = float((rank_by_symbol.get(symbol) or {}).get("score", -999.0))
                best_other = next((r for r in ranks if r["symbol"] not in positions and r["symbol"] not in cooldown), None)
                if symbol not in top_symbols[:max_positions] or (
                    best_other is not None and best_other["score"] - cur_score >= peer_outperform_pct / 100.0
                ):
                    reason = "event_rebalance"
                else:
                    pos.days_since_review = 0
            else:
                cur_score = float((rank_by_symbol.get(symbol) or {}).get("score", -999.0))
                best_other = next((r for r in ranks if r["symbol"] not in positions and r["symbol"] not in cooldown), None)
                if best_other is not None and best_other["score"] - cur_score >= peer_outperform_pct / 100.0:
                    reason = "peer_outperform"

            if reason:
                close_position(symbol, date, price, reason)

        total_equity = equity(date)
        target_slot = total_equity / max(1, max_positions)
        for row in ranks:
            if len(positions) >= max_positions:
                break
            symbol = row["symbol"]
            if symbol in positions or symbol in cooldown:
                continue
            price = _price(data, symbol, date)
            if price is None:
                continue
            open_position(symbol, date, price, target_slot)

        daily_equity.append((str(date.date()), equity(date)))

    if all_dates:
        last_date = all_dates[-1]
        for symbol, pos in list(positions.items()):
            price = _price(data, symbol, last_date)
            if price is not None:
                close_position(symbol, last_date, price, "final_mark")
        daily_equity.append((str(last_date.date()), equity(last_date)))

    return {
        "initial_capital": initial_capital,
        "final_equity": equity(all_dates[-1]),
        "trades": trades,
        "daily_equity": daily_equity,
    }


def run_static_top4(
    data: Dict[str, object],
    *,
    initial_capital: float = 1000.0,
    max_positions: int = 4,
    rebalance_days: int = 21,
    fee_bps: float = 1.0,
) -> dict:
    if pd is None:
        raise RuntimeError("pandas is required")
    all_dates = sorted(set().union(*(set(df.index) for df in data.values())))
    cash = float(initial_capital)
    positions: Dict[str, EventPosition] = {}
    trades: List[EventTrade] = []
    daily_equity: List[tuple[str, float]] = []

    def equity(date) -> float:
        value = cash
        for pos in positions.values():
            price = _price(data, pos.symbol, date)
            if price is not None:
                value += pos.qty * price
        return value

    def close(symbol: str, date, price: float, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(symbol)
        gross = (price - pos.entry_price) * pos.qty
        fees = (pos.entry_price * pos.qty + price * pos.qty) * fee_bps / 10_000.0
        pnl = gross - fees
        cash += pos.qty * price - fees
        trades.append(EventTrade(symbol, pos.entry_date, str(date.date()), pos.entry_price, price, pos.qty, pnl, reason))

    def open_(symbol: str, date, price: float, slot: float) -> None:
        nonlocal cash
        spend = min(cash, slot)
        fee = spend * fee_bps / 10_000.0
        qty = max(0.0, (spend - fee) / price)
        if qty <= 0:
            return
        cash -= spend
        positions[symbol] = EventPosition(symbol, str(date.date()), price, qty, price, 0)

    for day_i, date in enumerate(all_dates):
        do_rebalance = day_i == 0 or day_i % max(1, rebalance_days) == 0
        if do_rebalance:
            ranks = rank_symbols(data, date)
            target = {r["symbol"] for r in ranks[:max_positions]}
            for symbol in list(positions):
                if symbol not in target:
                    price = _price(data, symbol, date)
                    if price is not None:
                        close(symbol, date, price, "monthly_rebalance")
            total = equity(date)
            slot = total / max(1, max_positions)
            for row in ranks:
                if len(positions) >= max_positions:
                    break
                symbol = row["symbol"]
                if symbol in positions:
                    continue
                price = _price(data, symbol, date)
                if price is not None:
                    open_(symbol, date, price, slot)
        daily_equity.append((str(date.date()), equity(date)))

    if all_dates:
        last_date = all_dates[-1]
        for symbol in list(positions):
            price = _price(data, symbol, last_date)
            if price is not None:
                close(symbol, last_date, price, "final_mark")
        daily_equity.append((str(last_date.date()), equity(last_date)))

    return {
        "initial_capital": initial_capital,
        "final_equity": equity(all_dates[-1]),
        "trades": trades,
        "daily_equity": daily_equity,
    }
