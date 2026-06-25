"""hedge_pairing_run — кормит hedge_pairing реальными стримами сделок.

Аддитивно. Прогоняет PRIMARY (range/ARS1) и HEDGE (breakdown_retest_v3) через
тот же signal-replay, что package_efficiency_run, собирает по-сделочные стримы
{exit_ts_ms, pnl(=R), regime} и зовёт hedge_report — отвечает на вопрос:
закрывает ли breakdown красные медвежьи месяцы range?

Медвежьи месяцы определяются по close-to-close BTC (месяц с отрицательной
доходностью = bear). Это локальный смуук; ОКОНЧАТЕЛЬНЫЙ вердикт — на сервере
Codex с реальными range-стримами и комиссиями.

Запуск:
    PYTHONPATH=. python3 backtest/hedge_pairing_run.py [SYMBOL ...] [--step N]
"""
from __future__ import annotations

import datetime as dt
import importlib
import sys
from typing import Dict, List

from backtest.package_efficiency_run import ResampleStore, _target_from_signal, MAX_HOLD_BARS
from backtest.hedge_pairing import hedge_report, format_hedge_summary

PRIMARY = ("strategies.alt_range_scalp_v1", "AltRangeScalpV1Strategy")      # range
HEDGE = ("strategies.breakdown_retest_v3", "BreakdownRetestV3Strategy")      # breakdown


def _month(ts_ms: int) -> str:
    d = dt.datetime.utcfromtimestamp(ts_ms / 1000.0)
    return f"{d.year:04d}-{d.month:02d}"


def bear_months_from_btc(step: int = 1) -> set:
    """Месяцы с отрицательной close-to-close доходностью BTC = медвежьи."""
    st = ResampleStore("BTCUSDT")
    by_month: Dict[str, List[float]] = {}
    for ts, o, h, l, c, v in st.base[::step]:
        by_month.setdefault(_month(ts), []).append(c)
    bears = set()
    for m, closes in by_month.items():
        if len(closes) > 2 and closes[-1] < closes[0]:
            bears.add(m)
    return bears


def stream_for(module: str, cls: str, symbols: List[str], step: int = 3) -> List[dict]:
    """Replay -> список сделок {exit_ts_ms, pnl(=R), regime}."""
    out: List[dict] = []
    for sym in symbols:
        st = ResampleStore(sym)
        if not st.has_base():
            continue
        rows = st.base
        strat = getattr(importlib.import_module(module), cls)()
        until = -1
        for i in range(0, len(rows), step):
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
            exit_R = None; exit_ts = ts
            for j in range(i + 1, min(i + 1 + MAX_HOLD_BARS, len(rows))):
                hj, lj, cj = rows[j][2], rows[j][3], rows[j][4]
                exit_ts = rows[j][0]
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
                until = j
            if exit_R is None:
                k = min(i + MAX_HOLD_BARS, len(rows) - 1)
                cj = rows[k][4]; exit_ts = rows[k][0]
                exit_R = ((cj - entry) if side in ("buy", "long") else (entry - cj)) / risk
            out.append({"exit_ts_ms": int(exit_ts), "pnl": float(exit_R), "regime": ""})
    return out


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    step = 3
    if "--step" in argv:
        step = int(argv[argv.index("--step") + 1])
    symbols = [a for a in argv if a.endswith("USDT")] or ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    print(f"=== HEDGE PAIRING (range vs breakdown) symbols={symbols} step={step} ===")
    bears = bear_months_from_btc(step=12)
    print(f"bear months (BTC c2c<0): {sorted(bears) or 'none'}")
    primary = stream_for(*PRIMARY, symbols=symbols, step=step)
    hedge = stream_for(*HEDGE, symbols=symbols, step=step)
    print(f"primary(range) trades={len(primary)}  hedge(breakdown) trades={len(hedge)}")
    rep = hedge_report(primary, hedge, bear_months=bears)
    print(format_hedge_summary(rep))
    print("\nЛокальный смуук без комиссий. Окончательный вердикт improved=True — "
          "на сервере Codex с реальными range-стримами + fee/slip.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
