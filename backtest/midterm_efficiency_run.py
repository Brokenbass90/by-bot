"""midterm_efficiency_run — прогон СРЕДНЕСРОЧНЫХ стратегий (4h/дневки).

Аддитивно. Тот же signal-replay + ResampleStore, что package_efficiency_run, но
настроен под swing: скан редкий (по умолчанию каждые 4h), удержание длинное
(дни), т.к. среднесрочные сделки живут не часами. Это тот класс, что терпит
ИИ-анализ в контуре (не скальпинг) — сюда логично вешать deepseek_signal_gate.

Локальный смуук без комиссий; полный прогон + fee/slip = сервер Codex.

Запуск:
    PYTHONPATH=. python3 backtest/midterm_efficiency_run.py
    PYTHONPATH=. python3 backtest/midterm_efficiency_run.py --step 48 --hold 8000
"""
from __future__ import annotations

import importlib
import sys
import time
from typing import List, Optional

from backtest.package_efficiency_run import ResampleStore, _target_from_signal, ROOT

REGISTRY = [
    ("MT-PB   midterm_pullback",      "strategies.btc_eth_midterm_pullback", "BTCETHMidtermPullbackStrategy"),
    ("MT-V3   midterm_v3",            "strategies.btc_eth_midterm_v3",       "BTCETHMidtermV3Strategy"),
    ("MT-SH2  midterm_short_v2",      "strategies.btc_eth_midterm_short_v2", "BTCETHMidtermShortV2Strategy"),
    ("CYC-C   cycle_continuation",    "strategies.btc_cycle_continuation_v1","BTCCycleContinuationV1Strategy"),
    ("CYC-PB  cycle_pullback",        "strategies.btc_cycle_pullback_v1",    "BTCCyclePullbackV1Strategy"),
    ("REG-RT  regime_retest",         "strategies.btc_regime_retest_v1",     "BTCRegimeRetestV1Strategy"),
    ("SLP-RC  sloped_reclaim",        "strategies.btc_sloped_reclaim_v1",    "BTCSlopedReclaimV1Strategy"),
]
SYMBOLS = ["BTCUSDT", "ETHUSDT"]


def run_one(strategy, store: ResampleStore, step: int, max_hold: int) -> List[float]:
    rows = store.base
    Rs: List[float] = []
    in_trade_until = -1
    for i in range(0, len(rows), step):
        if i <= in_trade_until:
            continue
        ts, o, h, l, c, v = rows[i]
        store.set_cursor(ts)
        try:
            sig = strategy.maybe_signal(store, ts, o, h, l, c, v)
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
        exit_R: Optional[float] = None
        for j in range(i + 1, min(i + 1 + max_hold, len(rows))):
            hj, lj, cj = rows[j][2], rows[j][3], rows[j][4]
            if side in ("buy", "long"):
                if lj <= sl:
                    exit_R = -1.0; break
                if tp and hj >= tp:
                    exit_R = (tp - entry) / risk; break
            else:
                if hj >= sl:
                    exit_R = -1.0; break
                if tp and lj <= tp:
                    exit_R = (entry - tp) / risk; break
            in_trade_until = j
        if exit_R is None:
            cj = rows[min(i + max_hold, len(rows) - 1)][4]
            exit_R = ((cj - entry) if side in ("buy", "long") else (entry - cj)) / risk
        Rs.append(exit_R)
    return Rs


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    step = int(argv[argv.index("--step") + 1]) if "--step" in argv else 48      # 4h
    hold = int(argv[argv.index("--hold") + 1]) if "--hold" in argv else 8000    # ~28d
    try:
        sys.stdout.reconfigure(line_buffering=True)  # потоковый вывод на сервере
    except Exception:
        pass
    print(f"=== MIDTERM EFFICIENCY (swing; scan every {step*5}m; hold<= {hold*5//1440}d) ===", flush=True)
    print("(потоковый вывод: каждая стратегия печатается сразу по готовности)", flush=True)
    print(f"{'strategy':28s} {'trd':>4s} {'win%':>5s} {'expR':>6s} {'totR':>7s} {'PF':>5s} {'sec':>6s}", flush=True)
    print("-" * 66, flush=True)
    import json as _json
    from datetime import datetime as _dt, timezone as _tz
    stores = {s: ResampleStore(s) for s in SYMBOLS}
    stores = {s: st for s, st in stores.items() if st.has_base()}
    out = {}
    rep = ROOT / "runtime" / f"midterm_efficiency_{_dt.now(_tz.utc):%Y%m%d_%H%M%S}.json"
    for label, module, cls in REGISTRY:
        t0 = time.time()
        Rs: List[float] = []
        for s, st in stores.items():
            try:
                strat = getattr(importlib.import_module(module), cls)()
            except Exception as e:
                print(f"{label:28s} init fail: {e}", flush=True); Rs = []; break
            st.set_cursor(0)
            Rs.extend(run_one(strat, st, step, hold))
        dt_s = time.time() - t0
        n = len(Rs)
        if not n:
            out[label] = {"trades": 0}
            print(f"{label:28s} {'0':>4s}  (нет сигналов){'':>24s}{dt_s:>6.1f}", flush=True)
        else:
            w = [r for r in Rs if r > 0]; lo = [r for r in Rs if r <= 0]
            pf = (sum(w) / -sum(lo)) if lo and sum(lo) < 0 else float("inf")
            out[label] = {"trades": n, "win_pct": round(100 * len(w) / n, 1),
                          "expectancy_R": round(sum(Rs) / n, 3), "total_R": round(sum(Rs), 1),
                          "profit_factor": round(pf, 2) if pf != float("inf") else "inf"}
            print(f"{label:28s} {n:>4d} {100*len(w)/n:>5.1f} {sum(Rs)/n:>6.2f} {sum(Rs):>7.1f} "
                  f"{str(out[label]['profit_factor']):>5s} {dt_s:>6.1f}", flush=True)
        try:
            rep.write_text(_json.dumps(out, indent=2), encoding="utf-8")
        except Exception:
            pass
    print(f"\nJSON (чекпойнт) -> {rep}", flush=True)
    print("BTC+ETH, локальный кэш ~1г, без комиссий. Полный прогон/комиссии — сервер.", flush=True)
    print("!!! ВЫХОД БИНАРНЫЙ (без ladder/trailing/time-stop) → АБСОЛЮТНЫЙ R "
          "ОПТИМИСТИЧЕН. Только относительное ранжирование; эдж — серверный "
          "execution-accurate прогон (см. midterm_trade_export для ladder-варианта).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
