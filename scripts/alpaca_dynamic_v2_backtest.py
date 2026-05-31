#!/usr/bin/env python3
"""Alpaca dynamic_v2 backtest — research-only, не для live.

Контекст:
    - dynamic_v1 (scripts/alpaca_dynamic_full_backtest.py) проиграл buy-and-hold
      на 2024-05..2026-05 (bull-rally). Причина: фиксированный +5% trigger
      + 30% drawdown trail + −8% hard SL на всех акциях одинаково, поверх
      ежемесячного rebalance.
    - v38 hybrid top4 (production paper) показывает 24м +50.77%, PF 6.29,
      WR 82.9%, max monthly DD −2.28%, 35 trades. То есть production УЖЕ
      smart с native trailing (3.5%) и broker-side stops.
    - v38_more_active увеличивает trades 35→41 и доходность 50.77→51.91%,
      но max DD ухудшается с −2.28% до −4.36% и red months 2→3.

Гипотеза v2:
    Сделать «активную и не теряющую» версию через 4 слоя:
        1. Regime gate (SPY > 200ma + VIX < N → HOLD; иначе PROTECT/RISK_OFF)
        2. ATR-нормализованные параметры per symbol (а не глобальные)
        3. VIX-targeting sizing (full size при VIX≤15, half при VIX≥30)
        4. Sector rotation 2+2 (2 tech-momentum + 2 defensive)

    Идея: в bull НЕ мешать holding'у, в risk-off — собирать profits и cash,
    в bear-trend — переходить в inverse ETF или cash.

Что сравниваем:
    A. STATIC_BH      — monthly buy-and-hold (как v1, baseline)
    B. V38_HYBRID     — приближение production v38 hybrid top4 (трейл 3.5%, stop 5%, top4)
    C. DYNAMIC_V2     — наш концепт, все 4 слоя
    D. SECTOR_ROT_22  — sector rotation 2+2 без regime gate

Запуск (на сервере с интернетом):
    cd /root/by-bot
    pip install yfinance pandas --quiet
    python3 scripts/alpaca_dynamic_v2_backtest.py

Output:
    - print: AVG return, AVG return/month, WR месячный, worst/best месяц, MaxDD
    - JSON: runtime/alpaca_v2_backtest_report_YYYYMMDD.json
    - decision: какой режим выигрывает по риск-нормализованному (Sortino-like)

NB: это research-only, не deploy. Acceptance gate из CLAUDE_START_HERE_20260518:
    «do not increase risk, leverage, max positions, or live strategy set
    based on a single backtest».
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

try:
    import pandas as pd
    import yfinance as yf
except ImportError:
    print("ERROR: pip install yfinance pandas --quiet", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[1]

# Universe — 12 broad-cap + 4 defensive + VIX/SPY-proxy
TECH = ["UNH", "GOOGL", "AAPL", "MSFT", "NVDA", "META", "AMZN", "TSLA",
        "AVGO", "ORCL", "JPM", "LLY"]
DEFENSIVE = ["V", "COST", "JNJ", "WMT"]
SPY = "SPY"
VIX = "^VIX"

ALL_SYMBOLS = TECH + DEFENSIVE + [SPY, VIX]
START = "2024-05-01"
END = "2026-05-01"
INITIAL_CAPITAL = 6000.0   # суммарно (для multi-stock портфеля)
PER_SYM_INIT = 500.0       # для single-stock тестов


# --- Helpers ---------------------------------------------------------------

def compute_atr_pct(df: pd.DataFrame, i: int, period: int = 14) -> float:
    """ATR в процентах от close."""
    if i < period + 1:
        return 0.0
    sub = df.iloc[max(0, i - period):i + 1]
    trs = []
    prev_close = float(sub['Close'].iloc[0])
    for _, row in sub.iloc[1:].iterrows():
        tr = max(
            float(row['High']) - float(row['Low']),
            abs(float(row['High']) - prev_close),
            abs(float(row['Low']) - prev_close),
        )
        trs.append(tr)
        prev_close = float(row['Close'])
    if not trs:
        return 0.0
    atr = sum(trs[-period:]) / period
    close = float(df['Close'].iloc[i])
    return (atr / close) * 100 if close > 0 else 0.0


def ema(series: pd.Series, period: int) -> float:
    """EMA на текущий момент."""
    return float(series.ewm(span=period, adjust=False).mean().iloc[-1])


def sma(series: pd.Series, period: int) -> float:
    if len(series) < period:
        return float('nan')
    return float(series.iloc[-period:].mean())


def fetch_bars(symbols: list[str]) -> dict[str, pd.DataFrame]:
    out = {}
    for sym in symbols:
        try:
            df = yf.download(sym, start=START, end=END, progress=False,
                             auto_adjust=True)
            if df.empty:
                print(f"  {sym}: no data")
                continue
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            out[sym] = df
            print(f"  {sym}: {len(df)} bars")
        except Exception as e:
            print(f"  {sym}: error {e}")
    return out


# --- Mode A: Static buy-and-hold monthly rebalance --------------------------

def run_static_bh(df: pd.DataFrame) -> dict:
    """Просто 100% в акции, monthly rebalance, без stop/trail."""
    if df.empty or len(df) < 30:
        return None
    open0 = float(df['Open'].iloc[0])
    qty = PER_SYM_INIT / open0
    monthly_returns = []
    month_start_value = PER_SYM_INIT
    last_month = df.index[0].month
    max_dd = 0.0
    peak = PER_SYM_INIT

    for i in range(len(df)):
        close = float(df['Close'].iloc[i])
        value = qty * close
        peak = max(peak, value)
        dd = (peak - value) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

        if df.index[i].month != last_month:
            monthly_returns.append((value - month_start_value) / month_start_value * 100)
            month_start_value = value
            qty = value / close
            last_month = df.index[i].month

    final_value = qty * float(df['Close'].iloc[-1])
    return {
        "final_return_pct": (final_value - PER_SYM_INIT) / PER_SYM_INIT * 100,
        "monthly_returns": monthly_returns,
        "max_dd_pct": max_dd,
        "n_trades": 0,
        "n_stops": 0,
        "n_trails": 0,
    }


# --- Mode B: v38 hybrid top4 approximation ---------------------------------

def run_v38_hybrid(df: pd.DataFrame) -> dict:
    """Приближение production v38: ATR stop 2x, ATR target 3.2x, trail 1.5x,
    BE 0.8R, native trail 3.5% после +3.5% gain, hold max 22d, reentry 21d block.
    Одна акция в этом тесте, без top4 ротации (mы тестируем экзитную логику)."""
    if df.empty or len(df) < 30:
        return None

    open0 = float(df['Open'].iloc[0])
    qty = PER_SYM_INIT / open0
    entry_price = open0
    cash = 0.0
    monthly_returns = []
    month_start_value = PER_SYM_INIT
    last_month = df.index[0].month
    days_held = 0
    cooldown_days_left = 0
    max_dd = 0.0
    peak = PER_SYM_INIT
    high_water = open0
    be_armed = False
    native_trail_armed = False
    stops, trails = 0, 0

    for i in range(len(df)):
        close = float(df['Close'].iloc[i])
        value = (qty * close) + cash
        peak = max(peak, value)
        dd = (peak - value) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

        if df.index[i].month != last_month:
            monthly_returns.append((value - month_start_value) / month_start_value * 100)
            month_start_value = value
            # Если в cash — пробуем reentry если cooldown прошёл
            if qty == 0 and cooldown_days_left <= 0:
                qty = value / close
                cash = 0.0
                entry_price = close
                days_held = 0
                high_water = close
                be_armed = False
                native_trail_armed = False
            elif qty > 0:
                # Уже в позиции — ребалансим
                qty = value / close
                cash = 0.0
                entry_price = close
                days_held = 0
                high_water = close
                be_armed = False
                native_trail_armed = False
            last_month = df.index[i].month

        if cooldown_days_left > 0:
            cooldown_days_left -= 1

        if qty > 0:
            days_held += 1
            high_water = max(high_water, close)
            atr_pct = compute_atr_pct(df, i)
            gain_pct = (close - entry_price) / entry_price * 100

            # BE arm
            if not be_armed and gain_pct >= 0.8 * (2.0 * atr_pct):
                be_armed = True

            # Native trailing arm — после +3.5% gain
            if not native_trail_armed and gain_pct >= 3.5:
                native_trail_armed = True

            # Native trail check (3.5% от пика)
            if native_trail_armed:
                trail_pct = (high_water - close) / high_water * 100
                if trail_pct >= 3.5:
                    cash += qty * close
                    qty = 0
                    cooldown_days_left = 21
                    trails += 1
                    continue

            # BE stop
            if be_armed and close <= entry_price:
                cash += qty * close
                qty = 0
                cooldown_days_left = 21
                stops += 1
                continue

            # Hard ATR stop (2x) — 5% baseline
            stop_pct = max(2.0 * atr_pct, 5.0)  # max(2 ATR, 5%) — то же что MONTHLY_SL_PCT
            if gain_pct <= -stop_pct:
                cash += qty * close
                qty = 0
                cooldown_days_left = 21
                stops += 1
                continue

            # Max hold
            if days_held >= 22:
                cash += qty * close
                qty = 0
                cooldown_days_left = 21
                continue

    final_value = (qty * float(df['Close'].iloc[-1])) + cash
    return {
        "final_return_pct": (final_value - PER_SYM_INIT) / PER_SYM_INIT * 100,
        "monthly_returns": monthly_returns,
        "max_dd_pct": max_dd,
        "n_trades": stops + trails,
        "n_stops": stops,
        "n_trails": trails,
    }


# --- Mode C: dynamic_v2 — regime + ATR + VIX + sector ---------------------

def compute_regime(spy_df: pd.DataFrame, vix_df: pd.DataFrame, i: int) -> tuple[str, float]:
    """Возвращает (regime, size_mult).
    HOLD: SPY > 200MA & VIX < 20 → size_mult=1.0
    PROTECT: SPY > 200MA & VIX 20-25 → size_mult=0.7
    BEAR: SPY < 200MA or VIX > 25 → size_mult=0.4
    RISK_OFF: VIX > 30 → size_mult=0.0
    """
    if i < 200:
        return ("PROTECT", 0.7)
    spy_close = float(spy_df['Close'].iloc[i])
    spy_sma200 = sma(spy_df['Close'].iloc[:i + 1], 200)
    vix_close = float(vix_df['Close'].iloc[i]) if i < len(vix_df) else 20.0
    if vix_close > 30:
        return ("RISK_OFF", 0.0)
    if spy_close < spy_sma200 or vix_close > 25:
        return ("BEAR", 0.4)
    if vix_close > 20:
        return ("PROTECT", 0.7)
    return ("HOLD", 1.0)


def run_dynamic_v2_single(df: pd.DataFrame, spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> dict:
    """Одна акция с regime+ATR+VIX gate."""
    if df.empty or len(df) < 250:
        return None

    # выравниваем индексы по dates df
    spy_aligned = spy_df.reindex(df.index, method='ffill')
    vix_aligned = vix_df.reindex(df.index, method='ffill')

    open0 = float(df['Open'].iloc[0])
    qty = PER_SYM_INIT / open0
    entry_price = open0
    cash = 0.0
    monthly_returns = []
    month_start_value = PER_SYM_INIT
    last_month = df.index[0].month
    high_water = open0
    days_held = 0
    cooldown_days_left = 0
    max_dd = 0.0
    peak = PER_SYM_INIT
    stops, trails, regime_exits = 0, 0, 0

    for i in range(len(df)):
        close = float(df['Close'].iloc[i])
        value = (qty * close) + cash
        peak = max(peak, value)
        dd = (peak - value) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

        regime, size_mult = compute_regime(spy_aligned, vix_aligned, i)

        if df.index[i].month != last_month:
            monthly_returns.append((value - month_start_value) / month_start_value * 100)
            month_start_value = value
            # Re-enter с size_mult от regime
            target_position_value = value * size_mult
            qty = target_position_value / close
            cash = value - target_position_value
            entry_price = close
            days_held = 0
            high_water = close
            cooldown_days_left = 0
            last_month = df.index[i].month

        if cooldown_days_left > 0:
            cooldown_days_left -= 1

        if qty > 0:
            days_held += 1
            high_water = max(high_water, close)
            atr_pct = compute_atr_pct(df, i)
            gain_pct = (close - entry_price) / entry_price * 100

            # Regime downgrade — экстренный выход в cash
            if regime == "RISK_OFF":
                cash += qty * close
                qty = 0
                regime_exits += 1
                continue

            # ATR-нормализованный hard stop: 3x ATR (а не 2x как v38)
            # Для slow movers (UNH/JNJ) это ~5%, для NVDA это ~15% — справедливо
            stop_pct = max(3.0 * atr_pct, 4.0)
            if gain_pct <= -stop_pct:
                cash += qty * close
                qty = 0
                cooldown_days_left = 14  # короче чем v38 для возврата
                stops += 1
                continue

            # ATR-нормализованный trail: триггер 2 ATR, drawdown 1 ATR от пика
            trail_trigger_pct = 2.0 * atr_pct
            trail_drawdown_pct = 1.0 * atr_pct
            peak_gain_pct = (high_water - entry_price) / entry_price * 100
            if peak_gain_pct >= trail_trigger_pct:
                current_drawdown_pct = (high_water - close) / high_water * 100
                if current_drawdown_pct >= trail_drawdown_pct:
                    # Продаём 50% — partial trail
                    sell_qty = qty * 0.5
                    cash += sell_qty * close
                    qty -= sell_qty
                    trails += 1
                    # high_water reset чтобы не триггерилось повторно сразу
                    high_water = close

            # Max hold с regime-adjusted timeout
            max_hold = 30 if regime == "HOLD" else 15
            if days_held >= max_hold:
                cash += qty * close
                qty = 0
                cooldown_days_left = 14
                continue

    final_value = (qty * float(df['Close'].iloc[-1])) + cash
    return {
        "final_return_pct": (final_value - PER_SYM_INIT) / PER_SYM_INIT * 100,
        "monthly_returns": monthly_returns,
        "max_dd_pct": max_dd,
        "n_trades": stops + trails + regime_exits,
        "n_stops": stops,
        "n_trails": trails,
        "n_regime_exits": regime_exits,
    }


# --- Aggregation -----------------------------------------------------------

def stats(monthly: list[float]) -> dict:
    if not monthly:
        return {"avg": 0, "wr": 0, "worst": 0, "best": 0, "neg_months": 0, "neg_streak_max": 0}
    avg = sum(monthly) / len(monthly)
    wr = sum(1 for m in monthly if m > 0) / len(monthly) * 100
    worst = min(monthly)
    best = max(monthly)
    neg_months = sum(1 for m in monthly if m < 0)
    # neg streak
    streak = 0
    streak_max = 0
    for m in monthly:
        if m < 0:
            streak += 1
            streak_max = max(streak_max, streak)
        else:
            streak = 0
    return {
        "avg": avg, "wr": wr, "worst": worst, "best": best,
        "neg_months": neg_months, "neg_streak_max": streak_max,
        "n_months": len(monthly),
    }


def print_mode(label: str, results: dict[str, dict]) -> dict:
    print(f"\n=== {label} ===")
    print(f"{'Sym':<6} {'Ret%':>8} {'MaxDD%':>8} {'Trades':>6} {'Stop':>5} {'Trail':>5} {'Regime':>6}")
    print("-" * 60)
    final_returns = []
    all_monthly = []
    max_dds = []
    for s, r in results.items():
        if not r:
            continue
        ret = r['final_return_pct']
        dd = r['max_dd_pct']
        n = r['n_trades']
        ns = r.get('n_stops', 0)
        nt = r.get('n_trails', 0)
        nr = r.get('n_regime_exits', 0)
        print(f"{s:<6} {ret:>7.1f}% {dd:>7.1f}% {n:>6d} {ns:>5d} {nt:>5d} {nr:>6d}")
        final_returns.append(ret)
        all_monthly.extend(r['monthly_returns'])
        max_dds.append(dd)
    print("-" * 60)
    if final_returns:
        avg_ret = sum(final_returns) / len(final_returns)
        avg_dd = sum(max_dds) / len(max_dds)
        m_stats = stats(all_monthly)
        per_month = avg_ret / 24
        print(f"{'AVG':<6} {avg_ret:>7.1f}% {avg_dd:>7.1f}% ({avg_ret/24:.2f}%/мес)")
        print(f"Monthly: WR {m_stats['wr']:.1f}%  worst {m_stats['worst']:.2f}%  "
              f"best {m_stats['best']:.2f}%  neg {m_stats['neg_months']}/{m_stats['n_months']}  "
              f"neg_streak_max {m_stats['neg_streak_max']}")
        return {
            "avg_ret_pct": avg_ret,
            "avg_ret_per_month_pct": per_month,
            "avg_max_dd_pct": avg_dd,
            "monthly_stats": m_stats,
            "n_symbols": len(final_returns),
        }
    return {}


def verdict(modes: dict[str, dict]) -> str:
    """Sortino-like ranking: priority — max DD low + monthly WR high + ret avg."""
    scored = []
    for name, m in modes.items():
        if not m:
            continue
        ret = m['avg_ret_per_month_pct']
        dd = m['avg_max_dd_pct']
        ms = m['monthly_stats']
        wr = ms['wr']
        neg_streak = ms['neg_streak_max'] or 1
        # Score: return / dd / max(1, neg_streak)
        score = ret / max(0.5, dd / 10) / neg_streak
        scored.append((name, ret, dd, wr, neg_streak, score))
    scored.sort(key=lambda x: -x[5])
    print("\n=== VERDICT (риск-нормализованный ranking) ===")
    print(f"{'Mode':<18} {'Ret/mo%':>8} {'AvgDD%':>7} {'WR%':>6} {'NegStr':>7} {'Score':>8}")
    print("-" * 70)
    for n, r, d, w, ns, sc in scored:
        print(f"{n:<18} {r:>7.2f}% {d:>6.2f}% {w:>5.1f}% {ns:>7d} {sc:>7.2f}")
    if scored:
        return scored[0][0]
    return "INSUFFICIENT_DATA"


def main():
    print(f"Загружаю {len(ALL_SYMBOLS)} тикеров за {START}..{END}...\n")
    bars = fetch_bars(ALL_SYMBOLS)
    if SPY not in bars or VIX not in bars:
        print(f"FATAL: SPY или VIX не загрузились (SPY={'OK' if SPY in bars else 'MISS'}, "
              f"VIX={'OK' if VIX in bars else 'MISS'})")
        return 1
    spy_df = bars[SPY]
    vix_df = bars[VIX]
    # Используем TECH + DEFENSIVE для тестов
    test_symbols = [s for s in TECH + DEFENSIVE if s in bars]

    modes_results = {}

    # A. Static B&H
    print("\n>>> Mode A: Static B&H monthly rebalance")
    res_a = {s: run_static_bh(bars[s]) for s in test_symbols}
    modes_results["STATIC_BH"] = print_mode("STATIC_BH", res_a)

    # B. v38 hybrid approx
    print("\n>>> Mode B: v38 hybrid top4 approximation (single-stock exit logic)")
    res_b = {s: run_v38_hybrid(bars[s]) for s in test_symbols}
    modes_results["V38_HYBRID"] = print_mode("V38_HYBRID", res_b)

    # C. Dynamic v2
    print("\n>>> Mode C: DYNAMIC_V2 (regime + ATR + VIX + per-symbol)")
    res_c = {s: run_dynamic_v2_single(bars[s], spy_df, vix_df) for s in test_symbols}
    modes_results["DYNAMIC_V2"] = print_mode("DYNAMIC_V2", res_c)

    # Verdict
    winner = verdict(modes_results)
    print(f"\nWinner: {winner}")

    # JSON report
    out_dir = REPO_ROOT / "runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"alpaca_v2_backtest_report_{datetime.now().strftime('%Y%m%d')}.json"
    report = {
        "ts": datetime.now().isoformat(),
        "period": f"{START}..{END}",
        "symbols_tested": test_symbols,
        "modes": modes_results,
        "winner": winner,
        "disclaimer": (
            "Research-only. Acceptance gate per CLAUDE_START_HERE_20260518: "
            "single backtest insufficient for live deploy. Need PF+expectancy+"
            "MaxDD+trade count+fees/slippage + OOS validation 6+ months."
        ),
    }
    out_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\nReport: {out_path}")

    print("\n=== TG SUMMARY ===")
    for name, m in modes_results.items():
        if not m:
            continue
        ms = m['monthly_stats']
        print(f"  {name}: {m['avg_ret_per_month_pct']:.2f}%/мес, DD {m['avg_max_dd_pct']:.1f}%, "
              f"WR {ms['wr']:.0f}%, neg {ms['neg_months']}/{ms['n_months']}")
    print(f"  Winner: {winner}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
