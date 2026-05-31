"""
alpaca_dynamic_v4_event.py — Улучшенная Alpaca стратегия.

Отличия от v3:
──────────────────────────────────────────────────────────────────────────────
1. SHARPE-LIKE SCORING
   Старый: score = mom60 + 0.35*mom20 - 0.45*atr20
   Новый:  score = sharpe_proxy * recency_boost * trend_quality
   - sharpe_proxy = mom60 / (vol60 + epsilon)  — доходность / риск
   - recency_boost = 1 + 0.3*(mom20 > 0)       — бонус если недавнее движение тоже вверх
   - trend_quality = 1 - (neg_months_12 / 12)  — штраф за хаотичные месяцы
   Это отбирает активы с стабильным ростом, а не просто большим движением.

2. PORTFOLIO MAX DRAWDOWN GUARD
   Если текущая просадка портфеля от high_water > max_portfolio_dd_pct (default 15%):
   - Приостанавливаем новые покупки (not_buying_in_dd)
   - Существующие позиции продолжают работать со своими stop'ами
   Это предотвращает усреднение в падающем рынке.

3. VOLATILITY-ADJUSTED POSITION SIZING
   Старый: slot = total_equity / max_positions (равные доли)
   Новый:  slot_i = total_equity * target_vol_pct / vol_i
   где target_vol_pct = 2.0% по умолчанию, vol_i = 20d realized vol.
   Менее волатильные акции получают больший вес — как в Risk Parity.
   Capped: каждая позиция не более max_position_frac (default 0.40) от портфеля.

4. SECTOR DIVERSIFICATION CAP
   SECTOR_MAP: каждый символ привязан к сектору.
   max_per_sector (default 2): не держим больше 2 акций из одного сектора.
   Это предотвращает концентрацию в tech при отборе топ-4 (NVDA+META+MSFT+GOOGL).

5. MINIMUM MOMENTUM FILTER
   Не покупаем если mom60 < min_entry_mom60 (default 0.0 = просто положительный).
   Не покупаем если atr20 > max_entry_atr_pct (default 0.05 = 5%/день паника).

6. УЛУЧШЕННЫЙ PEER OUTPERFORM
   Старый: если best_other.score - cur.score >= peer_outperform_pct/100
   Новый: учитывает hysteresis — не продаём если score разница < hysteresis_band,
   чтобы не чурнить позицию туда-обратно при marginal difference.
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Sector map — расширяемый, легко добавить новые символы
# ---------------------------------------------------------------------------

SECTOR_MAP: Dict[str, str] = {
    # Tech
    "AAPL": "tech", "MSFT": "tech", "GOOGL": "tech", "META": "tech",
    "NVDA": "tech", "AMD": "tech", "AVGO": "tech", "ORCL": "tech",
    "ADBE": "tech", "CRM": "tech", "NOW": "tech", "INTU": "tech",
    "QCOM": "tech", "TXN": "tech", "ADSK": "tech",
    # E-commerce / Consumer
    "AMZN": "consumer", "TSLA": "consumer", "SHOP": "consumer",
    "NFLX": "consumer", "COST": "consumer", "WMT": "consumer",
    "NKE": "consumer", "SBUX": "consumer", "ABNB": "consumer",
    # Finance
    "JPM": "finance", "BAC": "finance", "GS": "finance", "WFC": "finance",
    "V": "finance", "MA": "finance", "SCHW": "finance", "COIN": "finance",
    "SQ": "finance",
    # Healthcare
    "UNH": "health", "LLY": "health", "JNJ": "health", "MRK": "health",
    "ABBV": "health", "REGN": "health", "ISRG": "health",
    # Energy / Industrials
    "XOM": "energy", "CVX": "energy", "CAT": "industrial", "GE": "industrial",
    "LMT": "industrial",
    # Staples / Other
    "PG": "staples", "KO": "staples",
    # Cloud / Cyber
    "PLTR": "cloud", "DDOG": "cloud", "SNOW": "cloud", "NET": "cyber",
    "CRWD": "cyber", "PANW": "cyber",
    # Biotech / Other
    "TSM": "semi", "UBER": "tech", "HD": "consumer",
    # ETFs (no sector cap)
    "SPY": "etf", "QQQ": "etf", "IWM": "etf",
    # Crypto-adjacent
    "MDB": "tech", "XYZ": "unknown",
}


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

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


def _monthly_returns(daily_equity: List[tuple]) -> List[float]:
    if not daily_equity:
        return []
    out: List[float] = []
    cur_month = daily_equity[0][0][:7]
    start_val = daily_equity[0][1]
    last_val = start_val
    for day, val in daily_equity[1:]:
        m = day[:7]
        if m != cur_month:
            if start_val > 0:
                out.append((last_val / start_val - 1.0) * 100.0)
            cur_month = m
            start_val = last_val
        last_val = val
    if start_val > 0:
        out.append((last_val / start_val - 1.0) * 100.0)
    return out


# ---------------------------------------------------------------------------
# Scoring — Sharpe-like
# ---------------------------------------------------------------------------

def _realized_vol(df, i: int, period: int = 60) -> float:
    """Realized daily volatility over last `period` days (std of daily returns)."""
    if i < period + 1:
        return float("nan")
    returns = []
    for j in range(i - period + 1, i + 1):
        prev = _safe_float(df["Close"].iloc[j - 1])
        cur = _safe_float(df["Close"].iloc[j])
        if prev > 0 and cur > 0:
            returns.append(math.log(cur / prev))
    if len(returns) < period // 2:
        return float("nan")
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    return math.sqrt(var) if var >= 0 else float("nan")


def _momentum(df, i: int, lookback: int) -> float:
    if i < lookback:
        return float("nan")
    prev = _safe_float(df["Close"].iloc[i - lookback])
    cur = _safe_float(df["Close"].iloc[i])
    if prev <= 0 or cur <= 0:
        return float("nan")
    return cur / prev - 1.0


def _neg_months_fraction(df, i: int, months: int = 12) -> float:
    """Fraction of negative months in last `months` months."""
    days = months * 21
    if i < days:
        return 0.5  # not enough data, assume neutral
    monthly_rets = []
    step = 21
    for m in range(months):
        start_idx = i - (m + 1) * step
        end_idx = i - m * step
        if start_idx < 0:
            break
        p_start = _safe_float(df["Close"].iloc[start_idx])
        p_end = _safe_float(df["Close"].iloc[end_idx])
        if p_start > 0 and p_end > 0:
            monthly_rets.append(p_end / p_start - 1.0)
    if not monthly_rets:
        return 0.5
    neg = sum(1 for r in monthly_rets if r < 0)
    return neg / len(monthly_rets)


def rank_symbols_v4(
    data: Dict[str, object],
    date,
    lookback: int = 60,
    target_vol: float = 0.015,  # 1.5% daily vol target для sizing
) -> List[dict]:
    """
    Sharpe-like ranking. Returns sorted list of dicts with scoring info.
    """
    rows: List[dict] = []
    for symbol, df in data.items():
        if date not in df.index:
            continue
        i = int(df.index.get_loc(date))
        mom60 = _momentum(df, i, lookback)
        mom20 = _momentum(df, i, 20)
        vol60 = _realized_vol(df, i, lookback)
        neg_frac = _neg_months_fraction(df, i, 12)
        close = _safe_float(df["Close"].iloc[i])

        if not all(math.isfinite(x) for x in (mom60, mom20, close)) or close <= 0:
            continue
        if not math.isfinite(vol60) or vol60 <= 0:
            vol60 = 0.02  # fallback assumption

        # Sharpe proxy: annualized mom / vol ratio
        # mom60 over 60 trading days ≈ 3 months. Annualized: mom60 * (252/60)
        # vol60 daily, annualized: vol60 * sqrt(252)
        ann_mom = mom60 * (252.0 / max(1, lookback))
        ann_vol = vol60 * math.sqrt(252.0)
        sharpe_proxy = ann_mom / max(0.01, ann_vol)

        # Recency boost: recent 20d also positive
        recency_boost = 1.0 + 0.25 * (1 if (math.isfinite(mom20) and mom20 > 0) else 0)

        # Trend quality: penalize assets with many negative months
        trend_quality = max(0.0, 1.0 - 1.5 * neg_frac)

        score = sharpe_proxy * recency_boost * trend_quality

        # Sizing weight: inverse of vol (risk parity principle)
        # Position size = target_vol / vol60 (as fraction of portfolio)
        vol_size_weight = target_vol / max(vol60, 0.005)

        rows.append({
            "symbol": symbol,
            "score": score,
            "sharpe_proxy": sharpe_proxy,
            "mom60": mom60,
            "mom20": mom20 if math.isfinite(mom20) else 0.0,
            "vol60": vol60,
            "neg_frac": neg_frac,
            "close": close,
            "vol_size_weight": vol_size_weight,
            "sector": SECTOR_MAP.get(symbol, "unknown"),
        })

    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


# ---------------------------------------------------------------------------
# Portfolio max DD tracker
# ---------------------------------------------------------------------------

class PortfolioGuard:
    """Tracks portfolio high-water and current drawdown."""

    def __init__(self, max_dd_pct: float = 15.0) -> None:
        self.max_dd_pct = max_dd_pct
        self._high_water = 0.0

    def update(self, equity: float) -> None:
        if equity > self._high_water:
            self._high_water = equity

    def in_drawdown(self, equity: float) -> bool:
        if self._high_water <= 0:
            return False
        dd_pct = (self._high_water - equity) / self._high_water * 100.0
        return dd_pct >= self.max_dd_pct

    def drawdown_pct(self, equity: float) -> float:
        if self._high_water <= 0:
            return 0.0
        return max(0.0, (self._high_water - equity) / self._high_water * 100.0)


# ---------------------------------------------------------------------------
# Sector diversification check
# ---------------------------------------------------------------------------

def _sector_slots_available(
    positions: Dict[str, EventPosition],
    candidate_symbol: str,
    max_per_sector: int,
    sector_map: Dict[str, str],
) -> bool:
    """True if adding candidate doesn't exceed sector cap."""
    sector = sector_map.get(candidate_symbol, "unknown")
    if sector in ("unknown", "etf"):
        return True  # no cap for unknowns and ETFs
    current_count = sum(
        1 for sym in positions
        if sector_map.get(sym, "unknown") == sector
    )
    return current_count < max_per_sector


# ---------------------------------------------------------------------------
# Main strategy — run_event_v4
# ---------------------------------------------------------------------------

def run_event_v4(
    data: Dict[str, object],
    *,
    initial_capital: float = 1000.0,
    max_positions: int = 4,
    # Exit rules
    profit_trigger_pct: float = 8.0,
    profit_pullback_pct: float = 2.5,
    stop_pct: float = 9.0,
    peer_outperform_pct: float = 12.0,  # lowered from 15 for faster rotation
    hysteresis_band: float = 0.03,       # NEW: prevents micro-churn
    max_age_days: int = 21,
    hard_max_age_days: int = 60,
    # New risk controls
    max_portfolio_dd_pct: float = 15.0,  # NEW: pause buys above this DD
    max_per_sector: int = 2,             # NEW: sector cap
    target_vol_pct: float = 0.015,       # NEW: risk parity vol target (daily)
    max_position_frac: float = 0.40,     # NEW: max single position as fraction
    min_entry_mom60: float = 0.0,        # NEW: minimum 60d momentum to buy
    max_entry_atr_pct: float = 0.06,     # NEW: skip if daily vol > 6%
    fee_bps: float = 1.0,
) -> dict:
    """
    Event-driven Alpaca strategy v4.
    Improvements over v3: Sharpe scoring, portfolio DD guard,
    vol-adjusted sizing, sector cap, hysteresis for rotation.
    """
    if pd is None:
        raise RuntimeError("pandas required")

    all_dates = sorted(set().union(*(set(df.index) for df in data.values())))
    if not all_dates:
        raise ValueError("no dates")

    cash = float(initial_capital)
    positions: Dict[str, EventPosition] = {}
    cooldown: Dict[str, int] = {}
    trades: List[EventTrade] = []
    daily_equity: List[tuple] = []
    guard = PortfolioGuard(max_dd_pct=max_portfolio_dd_pct)
    sector_map = {**SECTOR_MAP}  # local copy for extensibility

    def equity(date) -> float:
        value = cash
        for pos in positions.values():
            p = _price(data, pos.symbol, date)
            if p is not None:
                value += pos.qty * p
        return value

    def close_pos(symbol: str, date, price: float, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(symbol)
        fees = (pos.entry_price * pos.qty + price * pos.qty) * fee_bps / 10_000.0
        pnl = (price - pos.entry_price) * pos.qty - fees
        cash += pos.qty * price - fees
        trades.append(EventTrade(symbol, pos.entry_date, str(date.date()),
                                 pos.entry_price, price, pos.qty, pnl, reason))
        cooldown[symbol] = 3

    def open_pos(symbol: str, date, price: float, slot_value: float) -> None:
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
        # Cooldown decay
        for sym in list(cooldown):
            cooldown[sym] -= 1
            if cooldown[sym] <= 0:
                del cooldown[sym]

        # Current portfolio equity & guard update
        eq = equity(date)
        guard.update(eq)
        in_dd = guard.in_drawdown(eq)

        # Rank symbols (v4 scoring)
        ranks = rank_symbols_v4(data, date, target_vol=target_vol_pct)
        rank_by_sym = {r["symbol"]: r for r in ranks}
        top_syms = [r["symbol"] for r in ranks[: max_positions * 3]]

        # Manage existing positions
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
                reason = "stop_loss"
            elif ((pos.high_water / pos.entry_price - 1.0) * 100.0 >= profit_trigger_pct
                  and pullback_pct >= profit_pullback_pct):
                reason = "profit_lock_pullback"
            elif pos.age_days >= hard_max_age_days:
                reason = "hard_max_age"
            elif pos.days_since_review >= max_age_days:
                cur_score = float((rank_by_sym.get(symbol) or {}).get("score", -999.0))
                # Find best non-held candidate (with hysteresis)
                best_other = next(
                    (r for r in ranks
                     if r["symbol"] not in positions and r["symbol"] not in cooldown
                     and r["mom60"] >= min_entry_mom60),
                    None
                )
                if symbol not in top_syms[:max_positions] or (
                    best_other is not None
                    and best_other["score"] - cur_score >= peer_outperform_pct / 100.0 + hysteresis_band
                ):
                    reason = "event_rebalance"
                else:
                    pos.days_since_review = 0
            else:
                # Intra-period: only replace on strong peer outperform
                cur_score = float((rank_by_sym.get(symbol) or {}).get("score", -999.0))
                best_other = next(
                    (r for r in ranks
                     if r["symbol"] not in positions and r["symbol"] not in cooldown
                     and r["mom60"] >= min_entry_mom60),
                    None
                )
                if (best_other is not None
                        and best_other["score"] - cur_score
                        >= peer_outperform_pct / 100.0 + hysteresis_band):
                    reason = "peer_outperform"

            if reason:
                close_pos(symbol, date, price, reason)

        # Open new positions
        total_eq = equity(date)

        if not in_dd:
            for row in ranks:
                if len(positions) >= max_positions:
                    break
                symbol = row["symbol"]
                if symbol in positions or symbol in cooldown:
                    continue
                if row["mom60"] < min_entry_mom60:
                    continue  # min momentum filter
                if row["vol60"] > max_entry_atr_pct:
                    continue  # panic filter
                if not _sector_slots_available(positions, symbol, max_per_sector, sector_map):
                    continue  # sector cap

                price = _price(data, symbol, date)
                if price is None:
                    continue

                # Volatility-adjusted slot: target_vol / actual_vol * total_equity
                vol_weight = row["vol_size_weight"]
                raw_slot = total_eq * min(1.0 / max_positions, vol_weight)
                slot = min(raw_slot, total_eq * max_position_frac)
                slot = max(0.0, min(slot, cash))

                open_pos(symbol, date, price, slot)
        # else: in drawdown — no new buys

        daily_equity.append((str(date.date()), equity(date)))

    # Final mark-to-market
    if all_dates:
        last_date = all_dates[-1]
        for symbol, pos in list(positions.items()):
            p = _price(data, symbol, last_date)
            if p is not None:
                close_pos(symbol, last_date, p, "final_mark")
        daily_equity.append((str(last_date.date()), equity(last_date)))

    return {
        "initial_capital": initial_capital,
        "final_equity": equity(all_dates[-1]) if all_dates else initial_capital,
        "trades": trades,
        "daily_equity": daily_equity,
    }


# ---------------------------------------------------------------------------
# Static top-N (same interface as v3, uses v4 scoring)
# ---------------------------------------------------------------------------

def run_static_top4_v4(
    data: Dict[str, object],
    *,
    initial_capital: float = 1000.0,
    max_positions: int = 4,
    rebalance_days: int = 21,
    max_per_sector: int = 2,
    fee_bps: float = 1.0,
) -> dict:
    """Monthly rebalance static portfolio using v4 Sharpe scoring + sector cap."""
    if pd is None:
        raise RuntimeError("pandas required")

    all_dates = sorted(set().union(*(set(df.index) for df in data.values())))
    cash = float(initial_capital)
    positions: Dict[str, EventPosition] = {}
    trades: List[EventTrade] = []
    daily_equity: List[tuple] = []
    sector_map = {**SECTOR_MAP}

    def equity(date) -> float:
        value = cash
        for pos in positions.values():
            p = _price(data, pos.symbol, date)
            if p is not None:
                value += pos.qty * p
        return value

    def close_(symbol: str, date, price: float, reason: str) -> None:
        nonlocal cash
        pos = positions.pop(symbol)
        fees = (pos.entry_price * pos.qty + price * pos.qty) * fee_bps / 10_000.0
        pnl = (price - pos.entry_price) * pos.qty - fees
        cash += pos.qty * price - fees
        trades.append(EventTrade(symbol, pos.entry_date, str(date.date()),
                                 pos.entry_price, price, pos.qty, pnl, reason))

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
            ranks = rank_symbols_v4(data, date)

            # Pick top-N respecting sector cap
            target: List[str] = []
            sector_counts: Dict[str, int] = {}
            for r in ranks:
                if len(target) >= max_positions:
                    break
                sym = r["symbol"]
                sec = sector_map.get(sym, "unknown")
                if sec not in ("unknown", "etf"):
                    if sector_counts.get(sec, 0) >= max_per_sector:
                        continue
                    sector_counts[sec] = sector_counts.get(sec, 0) + 1
                target.append(sym)

            target_set = set(target)
            # Close positions not in target
            for sym in list(positions):
                if sym not in target_set:
                    p = _price(data, sym, date)
                    if p is not None:
                        close_(sym, date, p, "monthly_rebalance")

            total = equity(date)
            slot = total / max(1, max_positions)
            for sym in target:
                if sym in positions:
                    continue
                p = _price(data, sym, date)
                if p is not None:
                    open_(sym, date, p, slot)

        daily_equity.append((str(date.date()), equity(date)))

    if all_dates:
        last_date = all_dates[-1]
        for sym in list(positions):
            p = _price(data, sym, last_date)
            if p is not None:
                close_(sym, last_date, p, "final_mark")
        daily_equity.append((str(last_date.date()), equity(last_date)))

    return {
        "initial_capital": initial_capital,
        "final_equity": equity(all_dates[-1]) if all_dates else initial_capital,
        "trades": trades,
        "daily_equity": daily_equity,
    }


# ---------------------------------------------------------------------------
# Shared helpers (backward-compatible with v3)
# ---------------------------------------------------------------------------

def summarize_result(result: dict) -> dict:
    trades: List[EventTrade] = list(result.get("trades") or [])
    daily_equity = list(result.get("daily_equity") or [])
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


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import random
    random.seed(42)
    print("=== Alpaca v4 Smoke Test ===")

    # Test scoring functions
    from unittest.mock import MagicMock
    import pandas

    # Test sector map
    assert SECTOR_MAP.get("NVDA") == "tech"
    assert SECTOR_MAP.get("JPM") == "finance"
    print(f"Sector map: NVDA={SECTOR_MAP['NVDA']}, JPM={SECTOR_MAP['JPM']} OK")

    # Test sector cap logic
    mock_pos = {
        "NVDA": EventPosition("NVDA", "2026-01-01", 100, 1, 100),
        "MSFT": EventPosition("MSFT", "2026-01-01", 100, 1, 100),
    }
    # Adding AAPL (tech, 3rd) should be blocked
    assert not _sector_slots_available(mock_pos, "AAPL", max_per_sector=2, sector_map=SECTOR_MAP)
    # Adding JPM (finance, 1st) should be allowed
    assert _sector_slots_available(mock_pos, "JPM", max_per_sector=2, sector_map=SECTOR_MAP)
    print("Sector cap logic OK")

    # Test portfolio guard
    guard = PortfolioGuard(max_dd_pct=15.0)
    guard.update(1000)
    guard.update(1100)
    assert not guard.in_drawdown(950)  # 13.6% DD, below 15%
    assert guard.in_drawdown(900)      # 18.2% DD, above 15%
    print(f"Portfolio guard: DD@950={guard.drawdown_pct(950):.1f}%, DD@900={guard.drawdown_pct(900):.1f}% OK")

    print("\nAll smoke tests passed")
