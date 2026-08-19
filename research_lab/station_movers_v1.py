"""СТАНЦИЯ MOVERS v1: 4 семейства на свежих листингах (там, где живут скриншот-сетапы).

Запуск на Mac ПОСЛЕ окончания fetch_movers_5m (в movers_fetch.log слово ГОТОВО):
    nohup bash research_lab/run_station.sh movers_v1 station_movers_v1.py >/dev/null 2>&1 &
    tail -5 research_lab/results/movers_v1.log

64 комбо × десятки монет: многочасовой прогон, resumable. Универс замораживается
при первом старте (results/movers_v1_universe.json). IS = старшие 60% листингов,
OOS-symbols = младшие 40% (point-in-time: «новые монеты, которых поиск не видел»).
"""
from __future__ import annotations
import glob, hashlib, itertools, json, os, sys, time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from backtest.engine import Candle, KlineStore, BacktestParams, run_symbol_backtest
from search_station import _gate
from sloped_break_retest import SlopedBreakRetest
from horizontal_break_retest import HorizontalBreakRetest
from sweep_reclaim import SweepReclaim
from pump_spike_fade import PumpSpikeFade

DATA = os.path.join(_HERE, "data", "movers_5m")
RESULTS = os.path.join(_HERE, "results")
P = dict(starting_equity=1000.0, risk_pct=0.01, cap_notional_usd=1000.0, leverage=1.0,
         max_positions=1, fee_bps=6.0, slippage_bps=2.0, entry_on_next_open=True)
_CACHE = {}


def universe(run_id):
    upath = os.path.join(RESULTS, f"{run_id}_universe.json")
    if os.path.exists(upath):
        u = json.load(open(upath))
        return u["is"], u["oos"]
    files = sorted(glob.glob(os.path.join(DATA, "*.json")))
    syms = []
    for f in files:
        try:
            rows = json.load(open(f))
            if len(rows) >= 20000:  # минимум ~70 дней истории
                syms.append((int(rows[0][0]), os.path.basename(f)[:-5]))
        except Exception:
            pass
    syms.sort()
    syms = syms[:60]  # кап 60 монет: иначе 64 комбо x 342 монеты = неделя счёта
    cut = max(1, int(len(syms) * 0.6))
    IS = [s for _, s in syms[:cut]]
    OOS = [s for _, s in syms[cut:]]
    json.dump({"is": IS, "oos": OOS, "frozen_at": int(time.time())}, open(upath, "w"))
    print(f"универс заморожен: IS={len(IS)} OOS={len(OOS)}")
    return IS, OOS


def load(sym):
    if sym in _CACHE:
        return _CACHE[sym]
    try:
        rows = json.load(open(os.path.join(DATA, f"{sym}.json")))
    except Exception:
        _CACHE[sym] = None
        return None
    cs = [Candle(ts=int(r[0]), o=float(r[1]), h=float(r[2]), l=float(r[3]),
                 c=float(r[4]), v=float(r[5] or 0)) for r in rows]
    _CACHE[sym] = cs
    return cs


def bt(factory, symbols, part):
    trades, by = [], {}
    for sym in symbols:
        cs = load(sym)
        if not cs:
            continue
        if part == "first":
            cs = cs[: len(cs) // 2]
        elif part == "second":
            cs = cs[len(cs) // 2:]
        if len(cs) < 3000:
            continue
        st = KlineStore(sym, cs, base_interval_min=5)
        strat = factory()
        def sf(s_o, bar, strat=strat):
            try:
                return strat.maybe_signal(s_o, int(bar.ts), float(bar.o), float(bar.h),
                                          float(bar.l), float(bar.c), float(bar.v))
            except Exception:
                return None
        tr, _ = run_symbol_backtest(st, strategy_name="x", signal_fn=sf,
                                    params=BacktestParams(**P))
        for t in tr:
            trades.append({"sym": sym, "entry_ts": t.entry_ts, "exit_ts": t.exit_ts,
                           "r": t.pnl / 10.0})
            by.setdefault(sym, []).append(t.pnl / 10.0)
    return trades, by


def registry():
    reg = []
    reg.append(("sloped", lambda p: (lambda: SlopedBreakRetest(**p)), {
        "side": ["short", "long"], "entry_style": ["reject"],
        "retest_tol": [0.25, 0.40], "rr": [1.8, 2.5]}))
    reg.append(("horizontal", lambda p: (lambda: HorizontalBreakRetest(**p)), {
        "side": ["long", "short"], "min_touches": [2, 3],
        "retest_tol": [0.25, 0.40], "rr": [1.8, 2.5]}))
    reg.append(("sweep", lambda p: (lambda: SweepReclaim(**p)), {
        "side": ["long", "short"], "min_touches": [2, 3],
        "sweep_atr": [0.3, 0.5], "rr": [1.5, 2.0]}))
    reg.append(("pumpfade", lambda p: (lambda: PumpSpikeFade(**p)), {
        "side": ["short", "long"], "lookback_bars": [24, 72],
        "spike_pct": [0.12, 0.20], "rr": [1.5, 2.2]}))
    return reg


def run(run_id="movers_v1"):
    IS, OOS = universe(run_id)
    path = os.path.join(RESULTS, f"{run_id}.jsonl")
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                done.add(json.loads(line)["key"])
            except Exception:
                pass
    print(f"[{run_id}] resume: {len(done)} готово")
    survivors = 0
    for name, builder, grid in registry():
        keys = list(grid)
        for vals in itertools.product(*[grid[k] for k in keys]):
            params = dict(zip(keys, vals))
            k = hashlib.sha1((name + json.dumps(params, sort_keys=True)).encode()).hexdigest()[:12]
            if k in done:
                continue
            fac = builder(params)
            tr, by = bt(fac, IS, "first")
            ok, reason = _gate(tr, by)
            rec = {"key": k, "strategy": name, "params": params, "is_pass": ok,
                   "is_reason": reason, "is_net_r": round(sum(t["r"] for t in tr), 2),
                   "is_n": len(tr), "ts": int(time.time())}
            if ok:
                tr2, by2 = bt(fac, IS, "second")
                ok2, r2 = _gate(tr2, by2)
                tr3, by3 = bt(fac, OOS, "all")
                ok3, r3 = _gate(tr3, by3)
                rec.update({"fwd_pass": ok2, "fwd_net_r": round(sum(t["r"] for t in tr2), 2),
                            "oos_pass": ok3, "oos_net_r": round(sum(t["r"] for t in tr3), 2),
                            "survivor": bool(ok2 and ok3)})
                if rec["survivor"]:
                    survivors += 1
                    print(f"🟢 SURVIVOR {name} {params}")
            with open(path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"{name} {params}: net={rec['is_net_r']}R n={rec['is_n']} [{reason}]", flush=True)
    print(f"[{run_id}] ГОТОВО: survivors={survivors}. Результаты: {path}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "movers_v1")
