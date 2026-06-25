"""liquidation_sweep_run — прогон гипотезы «отскок после каскада ликвидаций».

Аддитивно. Использует боевой движок `backtest.liquidation_sweep_research`
(detect_clusters + measure_bounce). Обрабатывает символы по одному, чтобы
безопасно запускаться рядом с live-ботом на 1GB VPS через systemd MemoryMax.

Два режима:
  * РЕАЛЬНЫЙ (сервер Codex): если есть `runtime/liquidations/bybit_liquidations.jsonl`
    — грузит настоящие события ликвидаций + бары из data_cache → честный тест эджа.
  * ПРОКСИ (локально): синтезирует «каскады» из цены — резкое движение 5m +
    всплеск объёма = синтетическое событие (down→ликвидированы лонги→отскок вверх;
    up→ликвидированы шорты→фейд вниз). Это НЕ реальные ликвидации, а
    приблизительная проверка гипотезы на цене. Помечено явно.

Запуск:
    PYTHONPATH=. python3 backtest/liquidation_sweep_run.py            # авто-режим
    PYTHONPATH=. python3 backtest/liquidation_sweep_run.py --drop 1.5 --z 2.5
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

from backtest.liquidation_sweep_research import detect_clusters, measure_bounce

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data_cache"
LIQ_JSONL = ROOT / "runtime" / "liquidations" / "bybit_liquidations.jsonl"

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "AVAXUSDT", "LINKUSDT", "ADAUSDT"]


def _load_5m(symbol: str) -> List[list]:
    rows: Dict[int, list] = {}
    for f in glob.glob(str(CACHE / f"{symbol}_5_*.json")):
        try:
            for r in json.loads(Path(f).read_text()):
                rows[r["ts"]] = [int(r["ts"]), float(r["o"]), float(r["h"]),
                                 float(r["l"]), float(r["c"]), float(r["v"])]
        except Exception:
            continue
    return [rows[k] for k in sorted(rows)]


def _bars_for_engine(base: List[list]) -> List[Tuple[int, float, float, float]]:
    # движок ждёт (ts, high, low, close)
    return [(r[0], r[2], r[3], r[4]) for r in base]


def _synth_events(symbol: str, base: List[list], drop_pct: float, zmin: float,
                  vol_win: int = 50) -> List[dict]:
    """Синтетические каскады из цены: резкое движение + всплеск объёма."""
    ev: List[dict] = []
    for i in range(vol_win + 1, len(base)):
        prev_c = base[i - 1][4]
        if prev_c <= 0:
            continue
        ret = (base[i][4] - prev_c) / prev_c * 100.0
        vols = [base[j][5] for j in range(i - vol_win, i)]
        mean = sum(vols) / len(vols)
        var = sum((x - mean) ** 2 for x in vols) / len(vols)
        std = var ** 0.5 or 1e-9
        z = (base[i][5] - mean) / std
        if z < zmin:
            continue
        if ret <= -drop_pct:
            ev.append({"ts_ms": base[i][0], "symbol": symbol, "side": "long", "usd": 2_000_000.0})
        elif ret >= drop_pct:
            ev.append({"ts_ms": base[i][0], "symbol": symbol, "side": "short", "usd": 2_000_000.0})
    return ev


def _load_real_events() -> List[dict]:
    out: List[dict] = []
    with open(LIQ_JSONL) as fh:
        for line in fh:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _agg_Rs(rs: List[float], clusters: int) -> dict:
    n = len(rs)
    if n == 0:
        return {"clusters": clusters, "trades": 0, "verdict": "NO DATA"}
    wins = sum(1 for r in rs if r > 0)
    wr = 100.0 * wins / n
    exp = sum(rs) / n
    gp = sum(r for r in rs if r > 0)
    gl = -sum(r for r in rs if r <= 0)
    pf = (gp / gl) if gl > 0 else float("inf")
    verdict = "PASS (research)" if (wr > 55.0 and exp > 0) else "FAIL (noise / no edge)"
    return {
        "clusters": clusters,
        "trades": n,
        "win_pct": round(wr, 1),
        "expectancy_R": round(exp, 3),
        "profit_factor": round(pf, 2) if pf != float("inf") else "inf",
        "verdict": verdict,
    }


def _run_for_symbol(symbol: str, events: List[dict], bars: List[Tuple[int, float, float, float]]) -> dict:
    symbol_events = [e for e in events if str(e.get("symbol") or "").upper() == symbol]
    clusters = detect_clusters(symbol_events, window_ms=5 * 60_000, min_usd=1_000_000.0)
    rs: List[float] = []
    for c in clusters:
        r = measure_bounce(c, bars, horizon_ms=15 * 60_000, target_pct=0.4, stop_pct=0.4, fee_bps=10.0)
        if r is not None:
            rs.append(r)
    return {"symbol": symbol, "Rs": rs, "summary": _agg_Rs(rs, len(clusters))}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    drop = float(argv[argv.index("--drop") + 1]) if "--drop" in argv else 1.5
    zmin = float(argv[argv.index("--z") + 1]) if "--z" in argv else 2.5
    only_symbols = None
    if "--symbols" in argv:
        only_symbols = {s.strip().upper() for s in argv[argv.index("--symbols") + 1].split(",") if s.strip()}
    max_symbols = int(argv[argv.index("--max-symbols") + 1]) if "--max-symbols" in argv else 0
    symbols = [s for s in SYMBOLS if only_symbols is None or s in only_symbols]
    if max_symbols > 0:
        symbols = symbols[:max_symbols]
    real = LIQ_JSONL.exists()
    print("=== LIQUIDATION SWEEP — bounce-after-cascade ===", flush=True)
    print(f"режим: {'РЕАЛЬНЫЕ ликвидации' if real else 'ПРОКСИ из цены (drop>=%.1f%%, volZ>=%.1f)' % (drop, zmin)}", flush=True)
    print(f"symbols={','.join(symbols)} (memory-safe: one symbol at a time)", flush=True)

    per_symbol: List[dict] = []
    all_Rs: List[float] = []
    all_clusters = 0
    events: List[dict] = []
    if real:
        events = _load_real_events()
    for s in symbols:
        base = _load_5m(s)
        if len(base) < 200:
            continue
        bars = _bars_for_engine(base)
        if not real:
            events_s = _synth_events(s, base, drop, zmin)
        else:
            events_s = events
        r = _run_for_symbol(s, events_s, bars)
        per_symbol.append({k: v for k, v in r.items() if k != "Rs"})
        all_Rs.extend(r["Rs"])
        all_clusters += int(r["summary"].get("clusters", 0) or 0)
        sm = r["summary"]
        print(f"[{s}] clusters={sm.get('clusters')} trades={sm.get('trades')} "
              f"win={sm.get('win_pct')} expR={sm.get('expectancy_R')} PF={sm.get('profit_factor')} "
              f"{sm.get('verdict')}", flush=True)
        del base, bars

    res = _agg_Rs(all_Rs, all_clusters)
    print(f"\nсобытий: {len(events) if real else 'proxy'}  символов: {len(per_symbol)}")
    print(f"кластеров: {res.get('clusters')}  сделок: {res.get('trades')}")
    if res.get("trades"):
        print(f"win%: {res['win_pct']}   expectancy_R: {res['expectancy_R']}   PF: {res['profit_factor']}")
    print(f"ВЕРДИКТ: {res.get('verdict')}")
    out = ROOT / "runtime" / "liquidation_sweep_run_latest.json"
    try:
        out.write_text(json.dumps({"mode": "real" if real else "proxy", "params": {"drop": drop, "z": zmin},
                                   "result": res, "per_symbol": per_symbol}, indent=2), encoding="utf-8")
        print(f"JSON -> {out}")
    except Exception:
        pass
    if not real:
        print("\nПрим.: ПРОКСИ из цены ≠ реальные ликвидации. Это предварительная проверка "
              "гипотезы. Настоящий тест — на сервере с bybit_liquidations.jsonl (13k+ событий).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
