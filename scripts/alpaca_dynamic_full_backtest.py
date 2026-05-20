#!/usr/bin/env python3
"""РЕАЛЬНЫЙ backtest Alpaca dynamic_v1 vs static v38 на 24 месяца.

Запуск на сервере (где есть интернет):
    cd /root/by-bot
    pip install yfinance pandas --quiet
    python3 scripts/alpaca_dynamic_full_backtest.py

Выход:
    - Таблица по каждой акции: static % / dynamic % / delta pp / trails / reentries / stops
    - Месячная статистика: win rate, worst month, best month
    - Сравнение топ-5 параметров (grid search)
    - Файл runtime/alpaca_backtest_report_YYYYMMDD.json для дальнейшего анализа
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yfinance as yf


SYMBOLS = ["UNH", "GOOGL", "AAPL", "MSFT", "NVDA", "META", "AMZN", "TSLA",
           "AVGO", "ORCL", "JPM", "LLY"]
START = "2024-05-01"
END = "2026-05-01"
INITIAL_PER_SYMBOL = 1000.0

DEFAULT_PARAMS = {
    "trigger": 5.0,
    "dd_frac": 0.30,
    "partial": 0.50,
    "reentry_pullback_atr": 1.0,
    "max_reentry": 2,
    "hard_sl": 8.0,
}

GRID_SEARCH = [
    {"trigger": t, "dd_frac": d, "partial": p, "reentry_pullback_atr": 1.0, "max_reentry": 2, "hard_sl": 8.0}
    for t in [3.0, 5.0, 8.0]
    for d in [0.20, 0.30, 0.40]
    for p in [0.30, 0.50, 0.70]
]


def compute_atr(df: pd.DataFrame, i: int, period: int = 14) -> float:
    if i < period + 1:
        return 0.0
    sub = df.iloc[max(0, i - period):i + 1]
    trs = []
    prev_close = sub['Close'].iloc[0]
    for _, row in sub.iloc[1:].iterrows():
        tr = max(row['High'] - row['Low'],
                 abs(row['High'] - prev_close),
                 abs(row['Low'] - prev_close))
        trs.append(tr)
        prev_close = row['Close']
    return sum(trs[-period:]) / period if trs else 0.0


def backtest_one(df: pd.DataFrame, params: dict) -> dict:
    """Симулирует BOTH static и dynamic на одном symbol параллельно. Monthly rebalance 1-го числа."""
    if df.empty or len(df) < 30:
        return None

    open0 = float(df['Open'].iloc[0])
    static_cash, static_qty, _ = 0.0, INITIAL_PER_SYMBOL / open0, open0

    dyn_cash, dyn_qty, dyn_entry = 0.0, INITIAL_PER_SYMBOL / open0, open0
    dyn_peak_pnl, dyn_trail_done, dyn_reentry_count = 0.0, False, 0

    monthly_static, monthly_dyn = [], []
    last_month = df.index[0].month
    month_start_s, month_start_d = INITIAL_PER_SYMBOL, INITIAL_PER_SYMBOL
    actions = {"trail": 0, "reentry": 0, "stop": 0}

    for i in range(len(df)):
        row = df.iloc[i]
        date, close = df.index[i], float(row['Close'])

        # Monthly rebalance
        if date.month != last_month:
            val_s = static_cash + static_qty * close
            monthly_static.append((val_s - month_start_s) / month_start_s * 100)
            month_start_s = val_s
            static_qty = val_s / close
            static_cash = 0.0

            val_d = dyn_cash + dyn_qty * close
            monthly_dyn.append((val_d - month_start_d) / month_start_d * 100)
            month_start_d = val_d
            dyn_qty = val_d / close
            dyn_cash = 0.0
            dyn_entry = close
            dyn_peak_pnl = 0.0
            dyn_trail_done = False
            dyn_reentry_count = 0
            last_month = date.month

        # Dynamic logic
        if dyn_qty <= 0 and dyn_cash > 0:
            continue
        if dyn_qty > 0:
            pnl_pct = (close - dyn_entry) / dyn_entry * 100
            dyn_peak_pnl = max(dyn_peak_pnl, pnl_pct)
            atr_pct = compute_atr(df, i) / close * 100 if close > 0 else 0

            # Hard stop
            if pnl_pct <= -params["hard_sl"]:
                dyn_cash += dyn_qty * close
                dyn_qty = 0.0
                actions["stop"] += 1
                continue

            # Trail
            if (not dyn_trail_done
                and dyn_peak_pnl >= params["trigger"]
                and (dyn_peak_pnl - pnl_pct) >= dyn_peak_pnl * params["dd_frac"]):
                sell_qty = dyn_qty * params["partial"]
                dyn_cash += sell_qty * close
                dyn_qty -= sell_qty
                dyn_trail_done = True
                actions["trail"] += 1

            # Re-entry
            if (dyn_trail_done
                and dyn_reentry_count < params["max_reentry"]
                and atr_pct > 0
                and (dyn_peak_pnl - pnl_pct) >= params["reentry_pullback_atr"] * atr_pct
                and i >= 50 and dyn_cash > 0):
                ema50 = float(df['Close'].iloc[i - 50:i].mean())
                if close > ema50:
                    buy_amt = dyn_cash * 0.5
                    dyn_qty += buy_amt / close
                    dyn_cash -= buy_amt
                    dyn_reentry_count += 1
                    actions["reentry"] += 1

    final = float(df['Close'].iloc[-1])
    return {
        "static_return_pct": (static_cash + static_qty * final - INITIAL_PER_SYMBOL) / INITIAL_PER_SYMBOL * 100,
        "dyn_return_pct": (dyn_cash + dyn_qty * final - INITIAL_PER_SYMBOL) / INITIAL_PER_SYMBOL * 100,
        "monthly_static": monthly_static,
        "monthly_dyn": monthly_dyn,
        "actions": actions,
    }


def fetch_bars(symbols: list[str]) -> dict:
    out = {}
    for sym in symbols:
        try:
            df = yf.download(sym, start=START, end=END, progress=False, auto_adjust=True)
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


def print_table(results: dict, label: str):
    print(f"\n=== {label} ===")
    print(f"{'Sym':<6} {'Static':>8} {'Dyn':>8} {'Delta':>9} {'Tr':>3} {'Re':>3} {'St':>3}")
    print("-" * 55)
    for s, r in results.items():
        d = r['dyn_return_pct'] - r['static_return_pct']
        print(f"{s:<6} {r['static_return_pct']:>7.1f}% {r['dyn_return_pct']:>7.1f}% {d:>+8.1f}pp {r['actions']['trail']:>3d} {r['actions']['reentry']:>3d} {r['actions']['stop']:>3d}")

    avg_s = sum(r['static_return_pct'] for r in results.values()) / len(results)
    avg_d = sum(r['dyn_return_pct'] for r in results.values()) / len(results)
    print("-" * 55)
    print(f"{'AVG':<6} {avg_s:>7.1f}% {avg_d:>7.1f}% {avg_d - avg_s:>+8.1f}pp")
    print(f"{'/мес':<6} {avg_s/24:>7.2f}% {avg_d/24:>7.2f}% {(avg_d-avg_s)/24:>+8.2f}pp")

    all_m_s = [m for r in results.values() for m in r['monthly_static']]
    all_m_d = [m for r in results.values() for m in r['monthly_dyn']]
    g_s = sum(1 for m in all_m_s if m > 0)
    g_d = sum(1 for m in all_m_d if m > 0)
    print(f"\nWin rate STATIC: {g_s}/{len(all_m_s)} = {g_s/len(all_m_s)*100:.1f}%  | worst {min(all_m_s):.2f}%  best {max(all_m_s):.2f}%")
    print(f"Win rate DYN:    {g_d}/{len(all_m_d)} = {g_d/len(all_m_d)*100:.1f}%  | worst {min(all_m_d):.2f}%  best {max(all_m_d):.2f}%")

    return avg_s, avg_d


def main():
    print(f"Загружаю {len(SYMBOLS)} акций за {START}..{END} (24 месяца)...\n")
    bars = fetch_bars(SYMBOLS)
    if not bars:
        print("FATAL: ни одной акции не загрузилось")
        return 1

    # Главный прогон с дефолтными параметрами
    print(f"\n\n>>> Default params: {DEFAULT_PARAMS}")
    results_default = {s: backtest_one(df, DEFAULT_PARAMS) for s, df in bars.items()}
    results_default = {s: r for s, r in results_default.items() if r}
    avg_s_def, avg_d_def = print_table(results_default, "DEFAULT PARAMETERS")

    # Grid search
    print(f"\n\n>>> Grid search ({len(GRID_SEARCH)} комбинаций)...")
    grid_results = []
    for params in GRID_SEARCH:
        rs = [backtest_one(df, params) for df in bars.values()]
        rs = [r for r in rs if r]
        avg_s = sum(r['static_return_pct'] for r in rs) / len(rs)
        avg_d = sum(r['dyn_return_pct'] for r in rs) / len(rs)
        grid_results.append((params, avg_s, avg_d, avg_d - avg_s))
    grid_results.sort(key=lambda x: -x[3])

    print(f"\n=== TOP-5 PARAMETER SETS ===")
    print(f"{'trigger':>7} {'dd':>5} {'partial':>7} {'static':>8} {'dyn':>8} {'delta':>8}")
    for p, s, d, dlt in grid_results[:5]:
        print(f"{p['trigger']:>6.1f}% {p['dd_frac']:>4.2f}  {p['partial']:>6.2f}  {s:>7.1f}% {d:>7.1f}% {dlt:>+7.1f}pp")

    print(f"\n=== BOTTOM-5 (хуже всего) ===")
    for p, s, d, dlt in grid_results[-5:]:
        print(f"{p['trigger']:>6.1f}% {p['dd_frac']:>4.2f}  {p['partial']:>6.2f}  {s:>7.1f}% {d:>7.1f}% {dlt:>+7.1f}pp")

    # JSON report
    repo_root = Path(__file__).resolve().parent.parent
    out_dir = Path(os.environ.get("ALPACA_BACKTEST_RUNTIME_DIR", repo_root / "runtime"))
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"alpaca_backtest_report_{datetime.now().strftime('%Y%m%d')}.json"
    report = {
        "ts": datetime.now().isoformat(),
        "period": f"{START}..{END}",
        "symbols": list(bars.keys()),
        "default_params": DEFAULT_PARAMS,
        "default_results": {s: {k: v for k, v in r.items() if k != 'monthly_static' and k != 'monthly_dyn'} for s, r in results_default.items()},
        "default_avg_static": avg_s_def,
        "default_avg_dyn": avg_d_def,
        "grid_top5": [{"params": p, "static": s, "dyn": d, "delta": dlt} for p, s, d, dlt in grid_results[:5]],
        "verdict": "DEPLOY" if (avg_d_def - avg_s_def) / 24 >= 0.5 else "NOT_DEPLOY_NEED_GRID",
    }
    report_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"\n📄 Full report: {report_path}")

    # TG-ready summary
    print(f"\n\n=== TG SUMMARY (copy to user) ===")
    delta_monthly = (avg_d_def - avg_s_def) / 24
    print(f"📊 Alpaca dynamic_v1 backtest DONE (24 мес, {len(bars)} акций)")
    print(f"   Static AVG: {avg_s_def:.1f}% за 24мес = {avg_s_def/24:.2f}%/мес")
    print(f"   Dynamic AVG: {avg_d_def:.1f}% за 24мес = {avg_d_def/24:.2f}%/мес")
    print(f"   Delta: {delta_monthly:+.2f}pp/мес")
    if delta_monthly >= 0.5:
        print(f"   ✅ DEPLOY: на $500 это +${delta_monthly * 5 * 12:.0f}/год")
    else:
        print(f"   ⚠️ Дефолт хуже — пробую grid top-1: {grid_results[0][0]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
