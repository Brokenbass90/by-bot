"""midterm_trade_export — экспорт по-сделочного CSV + месячный анализ стабильности.

Генерирует CSV сделок midterm (entry_ts, exit_ts, pnl_net, side, symbol) — ровно
то, что просит DeepSeek для месячного анализа — И сразу считает метрики
стабильности по его фреймворку, выдавая предварительный вердикт для shadow.

Единица — R; pnl_net = R после taker-комиссии (PKG_COST_R). Локальный кэш
(BTC+ETH ~год) — это меньше серверных 111 сделок, но реальные данные для метода.

Запуск:
    PYTHONPATH=. python3 backtest/midterm_trade_export.py
"""
from __future__ import annotations

import csv
import datetime as dt
import gc
import importlib
import os
import sys
from typing import Dict, List, Tuple

from backtest.package_efficiency_run import ResampleStore, _target_from_signal, ROOT

STRATS = [
    ("midterm_pullback", "strategies.btc_eth_midterm_pullback", "BTCETHMidtermPullbackStrategy"),
    ("midterm_v3",       "strategies.btc_eth_midterm_v3",       "BTCETHMidtermV3Strategy"),
]
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
STEP = 48
# Реальная лестница выхода midterm (а не binary TP/SL): половину на TP1=RR1.2,
# остаток -> безубыток -> TP2; time-stop ~7h (84 5m-бара), НЕ 28 дней.
TIMESTOP_BARS = 84
TP1_RR = 1.2
TP1_FRAC = 0.5
COST_R = float(os.getenv("PKG_COST_R", "0.12"))


def export_trades() -> List[dict]:
    trades: List[dict] = []
    for sym in SYMBOLS:
        st = ResampleStore(sym)
        if not st.has_base():
            continue
        rows = st.base
        for sname, mod, cls in STRATS:
            strat = getattr(importlib.import_module(mod), cls)()
            until = -1
            for i in range(0, len(rows), STEP):
                if i <= until:
                    continue
                ts, o, h, l, c, v = rows[i]
                st.set_cursor(ts)
                try:
                    sig = strat.maybe_signal(st, ts, o, h, l, c, v)
                except Exception:
                    sig = None
                if sig is None:
                    continue
                side = str(getattr(sig, "side", "")).lower()
                entry = float(getattr(sig, "entry", c) or c)
                sl = getattr(sig, "sl", None)
                tp = _target_from_signal(sig)
                if not sl or entry <= 0:
                    continue
                sl = float(sl); risk = abs(entry - sl)
                if risk <= 0:
                    continue
                is_long = side in ("buy", "long")
                tp1 = entry + TP1_RR * risk if is_long else entry - TP1_RR * risk
                phase = 1; locked = 0.0; rem_stop = sl
                exitR = None; xts = ts
                end_j = min(i + 1 + TIMESTOP_BARS, len(rows))
                for j in range(i + 1, end_j):
                    hj, lj, cj = rows[j][2], rows[j][3], rows[j][4]; xts = rows[j][0]
                    if phase == 1:
                        hit_sl = (lj <= rem_stop) if is_long else (hj >= rem_stop)
                        if hit_sl:
                            exitR = -1.0; break                  # обе половины по стопу
                        hit_tp1 = (hj >= tp1) if is_long else (lj <= tp1)
                        if hit_tp1:
                            locked = TP1_FRAC * TP1_RR            # половина зафиксирована
                            rem_stop = entry                     # остаток -> безубыток
                            phase = 2
                            continue
                    else:  # остаток, стоп = безубыток
                        hit_tp2 = (hj >= tp) if (is_long and tp) else ((lj <= tp) if tp else False)
                        if hit_tp2:
                            rem = (tp - entry) / risk if is_long else (entry - tp) / risk
                            exitR = locked + (1 - TP1_FRAC) * rem; break
                        hit_be = (lj <= rem_stop) if is_long else (hj >= rem_stop)
                        if hit_be:
                            exitR = locked + 0.0; break          # остаток в ноль (безубыток)
                    until = j
                if exitR is None:  # time-stop ~7h: закрываем по close
                    k = min(end_j - 1, len(rows) - 1); xts = rows[k][0]; cj = rows[k][4]
                    rem = ((cj - entry) if is_long else (entry - cj)) / risk
                    exitR = (locked + (1 - TP1_FRAC) * rem) if phase == 2 else rem
                trades.append({
                    "strategy": sname, "symbol": sym, "side": "long" if is_long else "short",
                    "entry_ts": int(ts), "exit_ts": int(xts),
                    "entry_dt": dt.datetime.utcfromtimestamp(ts / 1000.0).strftime("%Y-%m-%d %H:%M"),
                    "exit_dt": dt.datetime.utcfromtimestamp(xts / 1000.0).strftime("%Y-%m-%d %H:%M"),
                    "R_gross": round(exitR, 3), "pnl_net": round(exitR - COST_R, 3),
                })
        del st; gc.collect()
    return trades


def monthly_analysis(trades: List[dict]) -> dict:
    by_month: Dict[str, float] = {}
    for t in trades:
        m = t["exit_dt"][:7]
        by_month[m] = by_month.get(m, 0.0) + t["pnl_net"]
    months = sorted(by_month)
    vals = [by_month[m] for m in months]
    n = len(vals)
    if n == 0:
        return {"months": 0}
    green = [v for v in vals if v > 0]
    red = [v for v in vals if v <= 0]
    # макс серия красных
    streak = mx = 0
    for v in vals:
        streak = streak + 1 if v <= 0 else 0
        mx = max(mx, streak)
    import statistics
    mean = sum(vals) / n
    sd = statistics.pstdev(vals)
    cov = (sd / mean) if mean != 0 else float("inf")
    avg_green = sum(green) / len(green) if green else 0.0
    avg_red = sum(red) / len(red) if red else 0.0
    asym = (avg_green / -avg_red) if red and avg_red < 0 else float("inf")
    total = sum(vals)
    top_month = max(vals)
    concentration = (top_month / total) if total > 0 else 0.0
    # equity по сделкам -> maxDD
    eq = pk = ddmin = 0.0
    for t in sorted(trades, key=lambda x: x["exit_ts"]):
        eq += t["pnl_net"]; pk = max(pk, eq); ddmin = min(ddmin, eq - pk)
    return {
        "months": n, "total_R": round(total, 1),
        "pct_profitable_months": round(100 * len(green) / n, 0),
        "max_red_streak": mx, "avg_green_R": round(avg_green, 2), "avg_red_R": round(avg_red, 2),
        "asymmetry": round(asym, 2) if asym != float("inf") else "inf",
        "coef_variation": round(cov, 2) if cov != float("inf") else "inf",
        "top_month_share_pct": round(100 * concentration, 0),
        "maxDD_R": round(ddmin, 1), "by_month": {m: round(by_month[m], 1) for m in months},
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    print(f"=== MIDTERM TRADE EXPORT + MONTHLY ANALYSIS (BTC+ETH, cost_R={COST_R}) ===\n", flush=True)
    trades = export_trades()
    print(f"сделок: {len(trades)}", flush=True)
    # CSV
    csv_path = ROOT / "runtime" / "midterm_trades_latest.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["strategy", "symbol", "side", "entry_ts", "exit_ts",
                                           "entry_dt", "exit_dt", "R_gross", "pnl_net"])
        w.writeheader(); w.writerows(trades)
    print(f"CSV -> {csv_path}  (для DeepSeek)\n", flush=True)
    # анализ — общий и по стратегии
    for label, subset in [("ВСЕ midterm", trades),
                          ("midterm_pullback", [t for t in trades if t["strategy"] == "midterm_pullback"]),
                          ("midterm_v3", [t for t in trades if t["strategy"] == "midterm_v3"])]:
        a = monthly_analysis(subset)
        if not a.get("months"):
            print(f"--- {label}: нет сделок ---"); continue
        print(f"--- {label} ({len(subset)} сделок) ---", flush=True)
        print(f"  итог {a['total_R']}R | плюс.месяцев {a['pct_profitable_months']:.0f}% | "
              f"макс.красная серия {a['max_red_streak']} | CoV {a['coef_variation']} | "
              f"асимметрия {a['asymmetry']} | топ-месяц {a['top_month_share_pct']:.0f}% прибыли | "
              f"maxDD {a['maxDD_R']}R", flush=True)
        # вердикт по порогам DeepSeek
        ready = (a["pct_profitable_months"] >= 70 and a["max_red_streak"] <= 2
                 and isinstance(a["coef_variation"], (int, float)) and a["coef_variation"] < 1.5)
        caveat = (a["pct_profitable_months"] >= 50 and a["max_red_streak"] <= 3)
        v = "ГОТОВА к shadow" if ready else ("ГОТОВА С ОГОВОРКАМИ" if caveat else "НЕ ГОТОВА")
        print(f"  вердикт: {v}", flush=True)
    print("\nЗаметка: локальный кэш BTC+ETH ~год (меньше серверных 111 сделок). "
          "Метод тот же; финальный вердикт — на серверных данных + WF.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
