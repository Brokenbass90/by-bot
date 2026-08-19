"""СТАНЦИЯ: weekly TSM BTC/ETH+ (тройной анти-overfit гейт) — 2026-07-20.

Варианты сигнала (классика TSMOM-исследований):
- tsm_L: знак return за L недель (L=3..6);
- ens: ансамбль знаков за 4/8/12 недель (среднее, торгуем если |avg|>=2/3);
- skip: tsm с пропуском последней недели;
- macross: пересечение SMA fast/slow по дневкам.
Моды: long_short / long_only. Vol-target: позиция * min(1, tv/realized_vol20d).

Гейт (как search_station): IS первая половина 8 монет (wf_folds+oos_selector+LOSO)
-> forward вторая половина -> OOS-symbols. SURVIVOR = все три. Resumable jsonl.
"""
from __future__ import annotations
import json, os, sys, time, itertools, hashlib

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from level_dca_v1 import load_5m, to_1h, FEE_SIDE, FUNDING_PER_DAY
from weekly_tsm_v1 import to_daily
from bot.wf_folds import purge_embargo_folds
from bot.oos_selector import evaluate_candidate
from bot.loso_concentration import loso_check

IS_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
              "LINKUSDT", "AVAXUSDT", "XRPUSDT", "DOGEUSDT"]
OOS_SYMBOLS = ["ATOMUSDT", "DOTUSDT", "LTCUSDT", "1000PEPEUSDT"]
CAPITAL = 1000.0
R_UNIT = 100.0  # 1R = $100

_DAILY = {}
def daily(sym):
    if sym not in _DAILY:
        b5 = load_5m(sym, cap=400000)
        _DAILY[sym] = to_daily(to_1h(b5)) if b5 else None
    return _DAILY[sym]


def _sig(closes, i, p):
    kind = p["kind"]
    if kind == "tsm":
        L = p["L"] * 7
        if i < L:
            return 0
        r = closes[i] / closes[i - L] - 1.0
        return 1 if r > 0 else -1
    if kind == "skip":
        L = p["L"] * 7
        if i < L + 7:
            return 0
        r = closes[i - 7] / closes[i - 7 - L] - 1.0
        return 1 if r > 0 else -1
    if kind == "ens":
        vs = []
        for Lw in (4, 8, 12):
            L = Lw * 7
            if i < L:
                return 0
            vs.append(1 if closes[i] / closes[i - L] - 1.0 > 0 else -1)
        s = sum(vs)
        return 1 if s >= 2 else (-1 if s <= -2 else 0)
    if kind == "macross":
        f, s_ = p["fast"], p["slow"]
        if i < s_:
            return 0
        fa = sum(closes[i - f + 1:i + 1]) / f
        sa = sum(closes[i - s_ + 1:i + 1]) / s_
        return 1 if fa > sa else -1
    return 0


def backtest(sym, part, p):
    d = daily(sym)
    if not d:
        return []
    if part == "first":
        d = d[: len(d) // 2]
    elif part == "second":
        d = d[len(d) // 2:]
    closes = [b[4] for b in d]
    trades = []
    pos = 0; entry = None; entry_ts = None; days_in = 0; scale = 1.0
    warm = 200 if p["kind"] == "macross" else (p.get("L", 12) * 7 + 14)
    for i in range(warm, len(d) - 1, 7):
        want = _sig(closes, i, p)
        if p["mode"] == "long_only" and want < 0:
            want = 0
        if want != pos:
            nxt = d[i + 1][1]
            if pos != 0 and entry:
                notional = CAPITAL * scale
                gross = (nxt / entry - 1.0) * notional * pos
                pnl = gross - notional * FEE_SIDE - notional * FUNDING_PER_DAY * days_in
                trades.append({"sym": sym, "entry_ts": entry_ts, "exit_ts": d[i + 1][0],
                               "r": pnl / R_UNIT})
            if want != 0:
                if p["vol_target"]:
                    rets = [closes[j] / closes[j - 1] - 1.0 for j in range(i - 19, i + 1)]
                    m = sum(rets) / len(rets)
                    rv = (sum((x - m) ** 2 for x in rets) / len(rets)) ** 0.5
                    scale = max(0.25, min(1.0, p["vol_target"] / max(rv, 1e-9)))
                else:
                    scale = 1.0
                entry = nxt; entry_ts = d[i + 1][0]; days_in = 0
            pos = want
        if pos != 0:
            days_in += 7
    if pos != 0 and entry:
        notional = CAPITAL * scale
        pnl = (closes[-1] / entry - 1.0) * notional * pos - notional * FEE_SIDE \
              - notional * FUNDING_PER_DAY * days_in
        trades.append({"sym": sym, "entry_ts": entry_ts, "exit_ts": d[-1][0], "r": pnl / R_UNIT})
    return trades


def gate(trades, min_n=30):
    if len(trades) < min_n:
        return False, f"low_N_{len(trades)}"
    fs = purge_embargo_folds(trades, n_folds=4, embargo=6 * 3600 * 1000)
    rep = evaluate_candidate(
        {"id": "c", "folds": [{"trades": f["trades"], "net_r": f["net_r"]} for f in fs.folds]},
        min_folds=3, min_frac_positive=0.75, min_trades_total=min_n, min_trades_per_fold=3)
    if not rep.passes:
        return False, "folds_" + rep.reason
    by = {}
    for t in trades:
        by.setdefault(t["sym"], []).append(t["r"])
    lo = loso_check(by)
    return (lo.passes, "PASS" if lo.passes else "loso_" + lo.reason)


def combos():
    out = []
    for L in (3, 4, 5, 6):
        out.append({"kind": "tsm", "L": L})
    out.append({"kind": "skip", "L": 4})
    out.append({"kind": "ens"})
    out.append({"kind": "macross", "fast": 10, "slow": 40})
    out.append({"kind": "macross", "fast": 20, "slow": 100})
    full = []
    for base in out:
        for mode in ("long_short", "long_only"):
            for vt in (None, 0.02):
                c = dict(base, mode=mode, vol_target=vt)
                full.append(c)
    return full


def run(run_id="tsm_v1"):
    path = os.path.join(_HERE, "results", f"{run_id}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                done.add(json.loads(line)["key"])
            except Exception:
                pass
    t0 = time.time()
    survivors = 0
    for p in combos():
        k = hashlib.sha1(json.dumps(p, sort_keys=True).encode()).hexdigest()[:12]
        if k in done:
            continue
        tr = []
        for sym in IS_SYMBOLS:
            tr += backtest(sym, "first", p)
        ok, reason = gate(tr)
        rec = {"key": k, "params": p, "is_pass": ok, "is_reason": reason,
               "is_net_r": round(sum(t["r"] for t in tr), 2), "is_n": len(tr)}
        if ok:
            tr2 = []
            for sym in IS_SYMBOLS:
                tr2 += backtest(sym, "second", p)
            ok2, r2 = gate(tr2)
            tr3 = []
            for sym in OOS_SYMBOLS:
                tr3 += backtest(sym, "all", p)
            ok3, r3 = gate(tr3)
            rec.update({"fwd_pass": ok2, "fwd_reason": r2, "fwd_net_r": round(sum(t["r"] for t in tr2), 2),
                        "oos_pass": ok3, "oos_reason": r3, "oos_net_r": round(sum(t["r"] for t in tr3), 2),
                        "survivor": bool(ok2 and ok3)})
            if rec["survivor"]:
                survivors += 1
                print(f"🟢 SURVIVOR {p} is={rec['is_net_r']}R fwd={rec['fwd_net_r']}R oos={rec['oos_net_r']}R")
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{p['kind']}{p.get('L','')} {p['mode']} vt={p['vol_target']}: "
              f"IS {rec['is_reason']} net={rec['is_net_r']}R n={rec['is_n']}", flush=True)
        if time.time() - t0 > 38:
            print("CHUNK_TIMEOUT")
            return False
    print(f"ALL_DONE survivors={survivors}")
    return True


if __name__ == "__main__":
    run()
