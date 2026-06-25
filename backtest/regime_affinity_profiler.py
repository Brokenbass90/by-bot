"""regime_affinity_profiler — в каком режиме BTC каждая стратегия зарабатывает.

Находка §30: связь с режимом СТРАТЕГИЕ-СПЕЦИФИЧНА (трендовые → по тренду,
mean-reversion → против). Этот профайлер считает R каждой стратегии в трёх
режимах BTC (BULL_TREND / BEAR_TREND / CHOP) и выдаёт «благоприятный режим» —
готовую цель для `bot/regime_orchestrator` (включать ногу только в её режиме).

Memory-safe (один символ в RAM). Binary выход + cost → ОТНОСИТЕЛЬНЫЙ сигнал
(абсолютный R оптимистичен). Малые локальные выборки → ГИПОТЕЗА, не доказательство;
финал — серверный execution-accurate прогон + WF.

Запуск:
    PYTHONPATH=. python3 backtest/regime_affinity_profiler.py
    PYTHONPATH=. python3 backtest/regime_affinity_profiler.py --strategies asb1,att1 --step 24
"""
from __future__ import annotations

import csv
import datetime as dt
import gc
import importlib
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from backtest.package_efficiency_run import ResampleStore, _target_from_signal, ROOT
from backtest.cross_sectional_momentum import daily_closes

REGISTRY = [
    ("ASB1  support_bounce",   "strategies.alt_support_bounce_v1",        "AltSupportBounceV1Strategy"),
    ("ARF1  resistance_fade",  "strategies.alt_resistance_fade_v1",       "AltResistanceFadeV1Strategy"),
    ("ATT1  trendline_touch",  "strategies.alt_trendline_touch_v1",       "AltTrendlineTouchV1Strategy"),
    ("ARS1  range_scalp",      "strategies.alt_range_scalp_v1",           "AltRangeScalpV1Strategy"),
    ("BRV3  breakdown_retest", "strategies.breakdown_retest_v3",          "BreakdownRetestV3Strategy"),
    ("SFV3  spike_fade",       "strategies.spike_fade_v3",                "SpikeFadeV3Strategy"),
    ("IVB1  impulse_breakout", "strategies.alt_volume_spike_momentum_v1", "AltVolumeSpikeV1Strategy"),
    ("MTPB  midterm_pullback", "strategies.btc_eth_midterm_pullback",     "BTCETHMidtermPullbackStrategy"),
]
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
COST_R = 0.12
HOLD = 200


def build_regime():
    """BTC daily SMA50 + наклон → 3-режимный классификатор по timestamp."""
    btc = daily_closes("BTCUSDT")
    dts = sorted(btc)
    sma, slope = {}, {}
    for i, d in enumerate(dts):
        if i >= 50:
            s = sum(btc[dts[j]] for j in range(i - 50, i)) / 50
            sma[d] = s
            if i >= 70:
                s_prev = sum(btc[dts[j]] for j in range(i - 70, i - 20)) / 50
                slope[d] = (s - s_prev) / s_prev * 100.0  # % за 20 дней

    def regime(ts_ms: int) -> str:
        d = dt.datetime.fromtimestamp(ts_ms / 1000.0, dt.UTC).strftime("%Y-%m-%d")
        cand = [x for x in dts if x <= d]
        if not cand:
            return "?"
        dd = cand[-1]
        if dd not in sma or dd not in slope:
            return "?"
        above = btc[dd] > sma[dd]
        sl = slope[dd]
        if above and sl > 1.0:
            return "BULL_TREND"
        if (not above) and sl < -1.0:
            return "BEAR_TREND"
        return "CHOP"
    return regime


def _norm_side(side: str) -> str:
    s = str(side or "").strip().lower()
    if s in {"buy", "long"}:
        return "long"
    if s in {"sell", "short"}:
        return "short"
    return s or "?"


def _month_from_ts(ts_ms: int) -> str:
    return dt.datetime.fromtimestamp(ts_ms / 1000.0, dt.UTC).strftime("%Y-%m")


def _stats(rs: Iterable[float]) -> dict:
    vals = list(rs)
    n = len(vals)
    if n == 0:
        return {"trades": 0}
    wins = [v for v in vals if v > 0]
    losses = [v for v in vals if v <= 0]
    gl = -sum(losses)
    pf = (sum(wins) / gl) if gl > 0 else float("inf")
    return {
        "trades": n,
        "sumR": round(sum(vals), 3),
        "avgR": round(sum(vals) / n, 4),
        "win_pct": round(100.0 * len(wins) / n, 1),
        "profit_factor": round(pf, 3) if pf != float("inf") else "inf",
    }


def _series_stats(trades: List[dict]) -> dict:
    if not trades:
        return {"trades": 0}
    ordered = sorted(trades, key=lambda r: int(r["exit_ts"]))
    rs = [float(r["R"]) for r in ordered]
    by_month: Dict[str, float] = {}
    for r in ordered:
        m = _month_from_ts(int(r["exit_ts"]))
        by_month[m] = by_month.get(m, 0.0) + float(r["R"])
    vals = [by_month[m] for m in sorted(by_month)]
    streak = mx = 0
    for v in vals:
        streak = streak + 1 if v <= 0 else 0
        mx = max(mx, streak)
    eq = pk = ddmin = 0.0
    for r in rs:
        eq += r
        pk = max(pk, eq)
        ddmin = min(ddmin, eq - pk)
    total = sum(rs)
    top = max(vals) if vals else 0.0
    top_share = (top / total * 100.0) if total > 0 else 0.0
    return {
        **_stats(rs),
        "months": len(vals),
        "green_months": sum(1 for v in vals if v > 0),
        "green_month_pct": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 1) if vals else 0.0,
        "max_red_streak": mx,
        "top_month_share_pct": round(top_share, 1),
        "maxDD_R": round(ddmin, 3),
        "by_month": {m: round(by_month[m], 3) for m in sorted(by_month)},
    }


def _macro_side_allowed(regime: str, side: str, *, allow_chop: bool = True) -> bool:
    """Принципиальный macro-side gate: не шортить bull, не лонговать bear."""
    rg = str(regime or "").upper()
    sd = _norm_side(side)
    if rg == "BULL_TREND":
        return sd != "short"
    if rg == "BEAR_TREND":
        return sd != "long"
    return bool(allow_chop)


def load_trade_csv(path: Path) -> List[dict]:
    regime = build_regime()
    out: List[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                entry_ts = int(float(row["entry_ts"]))
                exit_ts = int(float(row.get("exit_ts") or entry_ts))
                R = float(row.get("pnl_net") or row.get("R") or row.get("R_net"))
            except Exception:
                continue
            rg = regime(entry_ts)
            if rg == "?":
                continue
            out.append({
                "strategy": str(row.get("strategy") or "?"),
                "symbol": str(row.get("symbol") or "?"),
                "side": _norm_side(str(row.get("side") or "")),
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "regime": rg,
                "R": R,
            })
    return sorted(out, key=lambda r: int(r["entry_ts"]))


def _print_regime_side(trades: List[dict]) -> dict:
    REGIMES = ["BULL_TREND", "BEAR_TREND", "CHOP"]
    SIDES = ["long", "short"]
    out: Dict[str, dict] = {}
    print("\n=== TRADE CSV REGIME × SIDE PROFILE ===", flush=True)
    print("Ячейка: sumR/trades/avgR. Режим берётся на entry_ts по BTC daily SMA50+slope.\n", flush=True)
    for strat in sorted({t["strategy"] for t in trades}):
        sub = [t for t in trades if t["strategy"] == strat]
        out[strat] = {"all": _series_stats(sub), "buckets": {}}
        print(f"--- {strat} ({len(sub)} trades, total {sum(float(t['R']) for t in sub):+.2f}R) ---", flush=True)
        for side in SIDES:
            cells = []
            for rg in REGIMES:
                vals = [float(t["R"]) for t in sub if t["side"] == side and t["regime"] == rg]
                st = _stats(vals)
                out[strat]["buckets"][f"{rg}:{side}"] = st
                if st.get("trades"):
                    cells.append(f"{rg}:{side} {st['sumR']:+.2f}/{st['trades']}/{st['avgR']:+.3f}")
                else:
                    cells.append(f"{rg}:{side} +0.00/0/+0.000")
            print("  " + " | ".join(cells), flush=True)
    return out


def _selected_by_train(train: List[dict], *, min_trades: int, min_avg_R: float) -> Dict[str, set]:
    selected: Dict[str, set] = {}
    for strat in sorted({t["strategy"] for t in train}):
        buckets = []
        for rg in ["BULL_TREND", "BEAR_TREND", "CHOP"]:
            for side in ["long", "short"]:
                vals = [float(t["R"]) for t in train if t["strategy"] == strat and t["regime"] == rg and t["side"] == side]
                if len(vals) < min_trades:
                    continue
                avg = sum(vals) / len(vals)
                if avg >= min_avg_R:
                    buckets.append((rg, side))
        selected[strat] = set(buckets)
    return selected


def _apply_selected(trades: List[dict], selected: Dict[str, set]) -> List[dict]:
    return [t for t in trades if (t["regime"], t["side"]) in selected.get(t["strategy"], set())]


def _wf_regime_route(
    trades: List[dict],
    *,
    train_months: int,
    test_months: int,
    min_trades: int,
    min_avg_R: float,
) -> dict:
    months = sorted({_month_from_ts(int(t["entry_ts"])) for t in trades})
    if len(months) < train_months + test_months:
        return {"error": "not enough months", "months": len(months)}
    folds = []
    oos: List[dict] = []
    start = train_months
    while start + test_months <= len(months):
        train_set = set(months[start - train_months:start])
        test_set = set(months[start:start + test_months])
        train = [t for t in trades if _month_from_ts(int(t["entry_ts"])) in train_set]
        test = [t for t in trades if _month_from_ts(int(t["entry_ts"])) in test_set]
        selected = _selected_by_train(train, min_trades=min_trades, min_avg_R=min_avg_R)
        routed = _apply_selected(test, selected)
        oos.extend(routed)
        folds.append({
            "train": [months[start - train_months], months[start - 1]],
            "test": [months[start], months[start + test_months - 1]],
            "selected": {k: sorted([f"{rg}:{side}" for rg, side in v]) for k, v in selected.items() if v},
            "test_all": _series_stats(test),
            "test_routed": _series_stats(routed),
        })
        start += test_months
    return {
        "params": {
            "train_months": train_months,
            "test_months": test_months,
            "min_trades": min_trades,
            "min_avg_R": min_avg_R,
        },
        "folds": folds,
        "oos": _series_stats(oos),
    }


def _wf_grid(trades: List[dict]) -> List[dict]:
    rows = []
    for train_months in (12, 18, 24):
        for test_months in (3, 6):
            for min_trades in (3, 4, 5, 8):
                for min_avg_R in (0.0, 0.05, 0.10, 0.15):
                    wf = _wf_regime_route(
                        trades,
                        train_months=train_months,
                        test_months=test_months,
                        min_trades=min_trades,
                        min_avg_R=min_avg_R,
                    )
                    if "error" in wf:
                        continue
                    o = wf["oos"]
                    rows.append({
                        "train_months": train_months,
                        "test_months": test_months,
                        "min_trades": min_trades,
                        "min_avg_R": min_avg_R,
                        "folds": len(wf.get("folds", [])),
                        "trades": int(o.get("trades", 0) or 0),
                        "sumR": float(o.get("sumR", 0.0) or 0.0),
                        "avgR": float(o.get("avgR", 0.0) or 0.0),
                        "profit_factor": o.get("profit_factor"),
                        "green_month_pct": float(o.get("green_month_pct", 0.0) or 0.0),
                        "max_red_streak": int(o.get("max_red_streak", 0) or 0),
                        "top_month_share_pct": float(o.get("top_month_share_pct", 0.0) or 0.0),
                        "maxDD_R": float(o.get("maxDD_R", 0.0) or 0.0),
                    })
    rows.sort(key=lambda r: (r["sumR"], r["avgR"]), reverse=True)
    return rows


def run_trade_csv_mode(argv: List[str]) -> int:
    path = Path(argv[argv.index("--trades-csv") + 1])
    train_months = int(argv[argv.index("--train-months") + 1]) if "--train-months" in argv else 24
    test_months = int(argv[argv.index("--test-months") + 1]) if "--test-months" in argv else 6
    min_trades = int(argv[argv.index("--min-trades") + 1]) if "--min-trades" in argv else 5
    min_avg_R = float(argv[argv.index("--min-avg-r") + 1]) if "--min-avg-r" in argv else 0.0

    trades = load_trade_csv(path)
    print("=== REGIME AFFINITY FROM TRADE CSV ===", flush=True)
    print(f"csv={path} trades={len(trades)} train={train_months}m test={test_months}m "
          f"min_trades={min_trades} min_avg_R={min_avg_R}\n", flush=True)
    profile = _print_regime_side(trades)

    all_stats = _series_stats(trades)
    macro = [t for t in trades if _macro_side_allowed(t["regime"], t["side"], allow_chop=True)]
    strict_macro = [t for t in trades if _macro_side_allowed(t["regime"], t["side"], allow_chop=False)]
    in_sample_selected = _selected_by_train(trades, min_trades=min_trades, min_avg_R=min_avg_R)
    in_sample_routed = _apply_selected(trades, in_sample_selected)
    wf = _wf_regime_route(
        trades,
        train_months=train_months,
        test_months=test_months,
        min_trades=min_trades,
        min_avg_R=min_avg_R,
    )
    grid = _wf_grid(trades) if "--wf-grid" in argv else []

    print("\n=== FILTER COMPARISON ===", flush=True)
    for label, subset in [
        ("ALL", trades),
        ("MACRO_SIDE_GATE (no short in bull, no long in bear, chop allowed)", macro),
        ("STRICT_TREND_ONLY (bull long / bear short, no chop)", strict_macro),
        ("IN_SAMPLE_BUCKET_ROUTE (optimistic, not deployable)", in_sample_routed),
    ]:
        st = _series_stats(subset)
        print(f"{label}: trades={st.get('trades', 0)} total={st.get('sumR', 0):+.2f}R "
              f"avg={st.get('avgR', 0):+.3f} PF={st.get('profit_factor')} "
              f"green={st.get('green_month_pct', 0)}% red_streak={st.get('max_red_streak', 0)} "
              f"top={st.get('top_month_share_pct', 0)}% DD={st.get('maxDD_R', 0):+.2f}R", flush=True)

    print("\n=== WALK-FORWARD ROUTE ===", flush=True)
    if "error" in wf:
        print(f"WF error: {wf}", flush=True)
    else:
        for i, fold in enumerate(wf["folds"], 1):
            a = fold["test_all"]; r = fold["test_routed"]
            print(f"fold {i}: train {fold['train'][0]}..{fold['train'][1]} "
                  f"test {fold['test'][0]}..{fold['test'][1]} | "
                  f"all {a.get('sumR', 0):+.2f}R/{a.get('trades', 0)} "
                  f"routed {r.get('sumR', 0):+.2f}R/{r.get('trades', 0)} "
                  f"selected={fold['selected']}", flush=True)
        o = wf["oos"]
        print(f"OOS ROUTED: trades={o.get('trades', 0)} total={o.get('sumR', 0):+.2f}R "
              f"avg={o.get('avgR', 0):+.3f} PF={o.get('profit_factor')} "
              f"green={o.get('green_month_pct', 0)}% red_streak={o.get('max_red_streak', 0)} "
              f"top={o.get('top_month_share_pct', 0)}% DD={o.get('maxDD_R', 0):+.2f}R", flush=True)

    if grid:
        print("\n=== WF PARAM GRID (diagnostic; do not cherry-pick without stability) ===", flush=True)
        positive = [r for r in grid if r["sumR"] > 0 and r["trades"] >= 15]
        print(f"grid variants={len(grid)} positive_with_15trades={len(positive)}", flush=True)
        print("top 12 by OOS sumR:", flush=True)
        for r in grid[:12]:
            print(
                f"  train={r['train_months']} test={r['test_months']} "
                f"minN={r['min_trades']} minAvg={r['min_avg_R']:.2f} | "
                f"trades={r['trades']} total={r['sumR']:+.2f}R avg={r['avgR']:+.3f} "
                f"PF={r['profit_factor']} green={r['green_month_pct']}% "
                f"streak={r['max_red_streak']} top={r['top_month_share_pct']}% DD={r['maxDD_R']:+.2f}R",
                flush=True,
            )

    out = {
        "source_csv": str(path),
        "all": all_stats,
        "profile": profile,
        "macro_side_gate": _series_stats(macro),
        "strict_trend_only": _series_stats(strict_macro),
        "in_sample_selected": {k: sorted([f"{rg}:{side}" for rg, side in v]) for k, v in in_sample_selected.items() if v},
        "in_sample_route": _series_stats(in_sample_routed),
        "walk_forward": wf,
        "wf_grid": grid,
    }
    rep = ROOT / "runtime" / "regime_affinity_trade_csv_latest.json"
    rep.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nJSON -> {rep}", flush=True)
    print("Decision rule: deploy only if OOS route improves total/PF/DD and stays robust across folds. "
          "In-sample route is diagnostic only.", flush=True)
    return 0


def replay(strat, store: ResampleStore, step: int) -> List[Tuple[int, float]]:
    rows = store.base
    out: List[Tuple[int, float]] = []
    until = -1
    for i in range(0, len(rows), step):
        if i <= until:
            continue
        ts, o, h, l, c, v = rows[i]
        store.set_cursor(ts)
        try:
            sig = strat.maybe_signal(store, ts, o, h, l, c, v)
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
        isl = side in ("buy", "long"); eR = None
        for j in range(i + 1, min(i + 1 + HOLD, len(rows))):
            hj, lj, cj = rows[j][2], rows[j][3], rows[j][4]
            if isl:
                if lj <= sl:
                    eR = -1.0; break
                if tp and hj >= tp:
                    eR = (tp - entry) / risk; break
            else:
                if hj >= sl:
                    eR = -1.0; break
                if tp and lj <= tp:
                    eR = (entry - tp) / risk; break
            until = j
        if eR is None:
            k = min(i + HOLD, len(rows) - 1); cj = rows[k][4]
            eR = ((cj - entry) if isl else (entry - cj)) / risk
        out.append((int(ts), eR - COST_R))
    return out


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    if "--trades-csv" in argv:
        return run_trade_csv_mode(argv)
    step = int(argv[argv.index("--step") + 1]) if "--step" in argv else 24
    only = None
    if "--strategies" in argv:
        only = {x.strip().lower() for x in argv[argv.index("--strategies") + 1].split(",") if x.strip()}
    reg = [r for r in REGISTRY if (only is None or any(t in r[0].lower() for t in only))]
    regime = build_regime()
    REGIMES = ["BULL_TREND", "BEAR_TREND", "CHOP"]

    print("=== REGIME AFFINITY PROFILER (BTC режим × стратегия, BTC+ETH) ===", flush=True)
    print("ГИПОТЕЗА (binary выход, малые выборки). Финал — сервер + WF.\n", flush=True)
    # собрать сделки с режимом, memory-safe
    by: Dict[str, Dict[str, List[float]]] = {lab: {rg: [] for rg in REGIMES} for lab, _, _ in reg}
    for sym in SYMBOLS:
        st = ResampleStore(sym)
        if not st.has_base():
            del st; continue
        for lab, mod, cls in reg:
            strat = getattr(importlib.import_module(mod), cls)()
            for ts, R in replay(strat, st, step):
                rg = regime(ts)
                if rg in by[lab]:
                    by[lab][rg].append(R)
        del st; gc.collect()
        print(f"[{sym}] обработан", flush=True)

    print(f"\n{'strategy':24s} {'BULL_TREND':>14s} {'BEAR_TREND':>14s} {'CHOP':>12s}   рекомендация", flush=True)
    print("-" * 92, flush=True)
    out = {}
    for lab, _, _ in reg:
        cells = {}
        best = None; best_avg = 0.0
        line = f"{lab:24s}"
        for rg in REGIMES:
            rs = by[lab][rg]; n = len(rs); s = sum(rs)
            avg = s / n if n else 0.0
            cells[rg] = {"trades": n, "sumR": round(s, 1), "avgR": round(avg, 3)}
            line += f" {f'{s:+.1f}/{n}':>14s}" if rg != "CHOP" else f" {f'{s:+.1f}/{n}':>12s}"
            if n >= 5 and avg > best_avg:
                best_avg = avg; best = rg
        rec = f"→ {best} (avg {best_avg:+.2f}R)" if best else "→ нет (мало данных/везде минус)"
        print(line + f"   {rec}", flush=True)
        out[lab] = {"by_regime": cells, "recommended": best}
    rep = ROOT / "runtime" / "regime_affinity_latest.json"
    try:
        rep.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nJSON -> {rep}", flush=True)
    except Exception:
        pass
    print("Формат ячейки: суммаR/сделок. Рекомендация = режим с лучшим avgR (>=5 сделок).", flush=True)
    print("Завести «recommended» в regime_orchestrator: нога активна только в своём режиме.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
