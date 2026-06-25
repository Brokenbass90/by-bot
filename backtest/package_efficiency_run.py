"""package_efficiency_run — прогон ВСЕГО пакета крипто-стратегий одним заходом.

Аддитивно / standalone. Signal-replay по 5m с anti-lookahead курсором; высшие TF
(15m/1h/4h) синтезируются из 5m ресэмплингом (предрасчёт + bisect, без O(N^2)),
поэтому стратегии получают любой нужный им таймфрейм даже если в кэше только 5m.
Агрегирует метрики ПО СТРАТЕГИИ (expectancy/PF/win%/частота) → ранжирование
«у кого реально есть эдж».

На сервере Codex с полной историей + комиссиями это и есть «прогнать максимальный
пакет и отобрать рабочие ноги». Локально — смуук без комиссий.

Запуск:
    PYTHONPATH=. python3 backtest/package_efficiency_run.py
    PYTHONPATH=. python3 backtest/package_efficiency_run.py BTCUSDT SOLUSDT   # подмножество
"""
from __future__ import annotations

import bisect
import glob
import importlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data_cache"

# Контракт maybe_signal(store, ts, o,h,l,c,v); высшие TF берутся ресэмплингом,
# поэтому env-оверрайды TF не нужны — у каждой стратегии работают её дефолты.
REGISTRY = [
    ("ASB1  support_bounce (long)",   "strategies.alt_support_bounce_v1",        "AltSupportBounceV1Strategy"),
    ("ATT1  trendline_touch",         "strategies.alt_trendline_touch_v1",       "AltTrendlineTouchV1Strategy"),
    ("ARF1  resistance_fade (short)", "strategies.alt_resistance_fade_v1",       "AltResistanceFadeV1Strategy"),
    ("ARS1  range_scalp (L+S)",       "strategies.alt_range_scalp_v1",           "AltRangeScalpV1Strategy"),
    ("IVB1  impulse_breakout",        "strategies.alt_volume_spike_momentum_v1", "AltVolumeSpikeV1Strategy"),
    ("BRV3  breakdown_retest_v3",     "strategies.breakdown_retest_v3",          "BreakdownRetestV3Strategy"),
    ("SFV3  spike_fade_v3",           "strategies.spike_fade_v3",                "SpikeFadeV3Strategy"),
    ("IRV3  inplay_retest_v3",        "strategies.inplay_retest_v3",             "InplayRetestV3Strategy"),
    ("PF2   pump_fade_v2",            "strategies.pump_fade_v2",                 "PumpFadeV2Strategy"),
    ("ELD3  elder_triple_screen_v3",  "strategies.elder_triple_screen_v3",       "ElderTripleScreenV3Strategy"),
]
# Прим.: охотник за ликвидностью (liquidation_cascade_entry / sweep_reversal) сюда
# НЕ входит — ему нужны события ликвидаций, а не OHLC. Его движок:
# backtest/liquidation_sweep_research.py (отдельный data feed).

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "ADAUSDT", "DOTUSDT",
                   "LTCUSDT", "DOGEUSDT", "XRPUSDT", "AVAXUSDT", "SUIUSDT", "ONDOUSDT"]
MAX_HOLD_BARS = 200
# Издержки в R: на сервере замени на реальные. Здесь грубо: 6bps fee + 2bps slip /side.
COST_R_PER_TRADE = float(os.getenv("PKG_COST_R", "0.0"))  # 0 = смуук без комиссий


def _interval_ms(iv: str) -> int:
    iv = str(iv).upper()
    if iv.isdigit():
        return int(iv) * 60000
    return {"D": 1440, "W": 10080}.get(iv, 5) * 60000


class ResampleStore:
    """5m база + синтез любого TF (предрасчёт, anti-lookahead по курсору)."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        rows: Dict[int, list] = {}
        for f in glob.glob(str(CACHE / f"{symbol}_5_*.json")):
            try:
                data = json.loads(Path(f).read_text())
            except Exception:
                continue
            for r in (data if isinstance(data, list) else []):
                try:
                    rows[r["ts"]] = [int(r["ts"]), float(r["o"]), float(r["h"]),
                                     float(r["l"]), float(r["c"]), float(r["v"])]
                except Exception:
                    continue
        self.base = [rows[k] for k in sorted(rows)]
        self.bts = [r[0] for r in self.base]
        self._cur = 0
        self._cache: Dict[str, Tuple[List[list], List[int]]] = {}

    def has_base(self) -> bool:
        return len(self.base) > 50

    def set_cursor(self, ts: int):
        self._cur = ts

    def _resample(self, ms: int) -> Tuple[List[list], List[int]]:
        buckets: Dict[int, list] = {}
        order: List[int] = []
        for ts, o, h, l, c, v in self.base:
            b = ts - (ts % ms)
            x = buckets.get(b)
            if x is None:
                buckets[b] = [b, o, h, l, c, v]
                order.append(b)
            else:
                if h > x[2]:
                    x[2] = h
                if l < x[3]:
                    x[3] = l
                x[4] = c
                x[5] += v
        cans = [buckets[b] for b in order]
        ends = [b + ms for b in order]
        return cans, ends

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        ms = _interval_ms(interval)
        if ms <= 300000:  # 5m/1m: вернуть включая текущий бар (rows[-1]=текущий)
            hi = bisect.bisect_right(self.bts, self._cur)
            lo = max(0, hi - limit) if limit else 0
            return self.base[lo:hi]
        key = str(interval)
        if key not in self._cache:
            self._cache[key] = self._resample(ms)
        cans, ends = self._cache[key]
        hi = bisect.bisect_right(ends, self._cur)  # только полностью закрытые бакеты
        lo = max(0, hi - limit) if limit else 0
        return cans[lo:hi]


def _target_from_signal(sig) -> Optional[float]:
    tp = getattr(sig, "tp", None)
    if tp:
        return float(tp)
    tps = getattr(sig, "tps", None)
    if tps:
        return float(tps[-1])
    return None


def run_one(strategy, store: ResampleStore) -> List[float]:
    rows = store.base
    Rs: List[float] = []
    in_trade_until = -1
    for i in range(len(rows)):
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
        sl = float(sl)
        risk = abs(entry - sl)
        if risk <= 0:
            continue
        exit_R: Optional[float] = None
        for j in range(i + 1, min(i + 1 + MAX_HOLD_BARS, len(rows))):
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
            cj = rows[min(i + MAX_HOLD_BARS, len(rows) - 1)][4]
            exit_R = ((cj - entry) if side in ("buy", "long") else (entry - cj)) / risk
        Rs.append(exit_R)   # RAW R (без комиссии); издержки применяются в _agg
    return Rs


def _agg(Rs_raw: List[float], n_syms: int, cost: float = 0.0) -> dict:
    """Метрики при заданной издержке `cost` (в R) на сделку (taker или maker)."""
    n = len(Rs_raw)
    if n == 0:
        return {"trades": 0}
    Rs = [r - cost for r in Rs_raw]
    wins = [r for r in Rs if r > 0]
    losses = [r for r in Rs if r <= 0]
    gp = sum(wins); gl = -sum(losses)
    pf = (gp / gl) if gl > 0 else float("inf")
    days = 365.0 * max(1, n_syms)
    return {
        "trades": n,
        "win_pct": round(100.0 * len(wins) / n, 1),
        "expectancy_R": round(sum(Rs) / n, 3),
        "total_R": round(sum(Rs), 1),
        "profit_factor": round(pf, 2) if pf != float("inf") else "inf",
        "trades_per_30d": round(n / days * 30.0, 2),
    }


def main(argv: Optional[List[str]] = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    # Потоковый вывод: на сервере stdout редиректят в файл -> блочная буферизация
    # «вешает» вывод. Делаем line-buffered + flush после каждой строки.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    symbols = [a for a in argv if a.endswith("USDT")] or DEFAULT_SYMBOLS
    # --strategies foo,bar  → прогнать только подмножество (дробление тяжёлого прогона)
    only = None
    if "--strategies" in argv:
        only = {x.strip().lower() for x in argv[argv.index("--strategies") + 1].split(",") if x.strip()}
    registry = [r for r in REGISTRY if (only is None or any(t in r[0].lower() for t in only))]

    # Maker/taker: один replay -> две издержки. taker = полная COST_R; maker =
    # COST_R * фактор (entry-нога у уровня становится rebate/дешевле). Фактор по
    # умолчанию 0.4 (грубо: одна из двух ног бесплатна + рибейт). FILL-RISK НЕ
    # моделируется -> maker = оптимистичная верхняя оценка.
    taker_cost = COST_R_PER_TRADE
    maker_factor = float(os.getenv("PKG_MAKER_FACTOR", "0.4"))
    maker_cost = round(taker_cost * maker_factor, 4)

    print("=== PACKAGE EFFICIENCY (resample store; signal-replay; R-multiples) ===", flush=True)
    print(f"symbols={len(symbols)}  strategies={len(registry)}  hold<= {MAX_HOLD_BARS} bars  "
          f"cost taker={taker_cost} maker={maker_cost} (фактор {maker_factor})", flush=True)
    print("(потоковый вывод; колонки taker/maker; ↑ = maker выводит в плюс)\n", flush=True)

    t_load = time.time()
    stores = {s: ResampleStore(s) for s in symbols}
    stores = {s: st for s, st in stores.items() if st.has_base()}
    print(f"[load] {len(stores)} символов загружено за {time.time()-t_load:.1f}s\n", flush=True)

    hdr = (f"{'strategy':30s} {'trd':>5s} {'win%':>5s} "
           f"{'expR_tk':>7s} {'PF_tk':>5s}  {'expR_mk':>7s} {'PF_mk':>5s} {'flip':>4s} {'sec':>5s}")
    print(hdr, flush=True); print("-" * len(hdr), flush=True)
    out: Dict[str, dict] = {}
    rep = ROOT / "runtime" / f"package_efficiency_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.json"
    for label, module, cls in registry:
        t0 = time.time()
        all_Rs: List[float] = []
        nsy = 0
        for s, st in stores.items():
            try:
                strat = getattr(importlib.import_module(module), cls)()
            except Exception as e:
                print(f"{label:30s}  init fail: {e}", flush=True)
                all_Rs = []; break
            r = run_one(strat, st)
            if r:
                nsy += 1
            all_Rs.extend(r)
        mt = _agg(all_Rs, nsy or 1, cost=taker_cost)
        mk = _agg(all_Rs, nsy or 1, cost=maker_cost)
        out[label] = {"taker": mt, "maker": mk}
        dt_s = time.time() - t0
        if not mt.get("trades"):
            print(f"{label:30s} {'0':>5s}  (нет сигналов){'':>40s}{dt_s:>5.1f}", flush=True)
        else:
            flip = "↑" if (mt["expectancy_R"] <= 0 < mk["expectancy_R"]) else ""
            print(f"{label:30s} {mt['trades']:>5d} {mt['win_pct']:>5.1f} "
                  f"{mt['expectancy_R']:>7.2f} {str(mt['profit_factor']):>5s}  "
                  f"{mk['expectancy_R']:>7.2f} {str(mk['profit_factor']):>5s} {flip:>4s} {dt_s:>5.1f}",
                  flush=True)
        try:
            rep.write_text(json.dumps(out, indent=2), encoding="utf-8")
        except Exception:
            pass

    print(f"\nJSON (чекпойнт, дополняется по ходу) -> {rep}", flush=True)
    print("tk=taker (полные комиссии), mk=maker (entry-нога дешевле/rebate). "
          "↑ = maker выводит стратегию в плюс. FILL-RISK не моделируется → maker оптимистичен.", flush=True)
    print("Заметка: COST_R задаётся через env PKG_COST_R; для дробления — "
          "--strategies ivb1,midterm и/или список символов. Доказательство эджа = "
          "серверный next-open прогон через promotion_gate.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
