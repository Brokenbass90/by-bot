"""RESEARCH-ONLY: level_dca_v1 — усреднение по СИЛЬНЫМ уровням (запрос владельца 2026-07-20).

Идея владельца: капитал $1000 делится на 10 колен. Вход 1/10 у сильного уровня.
Пошло в нашу сторону -> фикс ПЕРЕД следующим уровнем. Пошло против -> усреднение
НЕ по сетке, а на следующем сильном уровне (уровни из мульти-тач кластеров пивотов),
до 10 колен. Стопа нет (дорогой) -> границы: ликвидация (при плече), time-stop.

Это семейство мартингейла: главный вопрос НЕ средний PnL, а ХВОСТ (сколько раз
глубина 10 колен пробита и чем это кончилось). Симулятор считает это явно.

Каузальность: уровни из ЗАКРЫТЫХ 1h баров (рефит раз в день), триггеры на закрытом
5m баре, исполнение на open следующего бара. Издержки: fee 6bps+slip 2bps на каждую
ногу каждого колена, funding ~3bps/день на нотионал (консервативно против нас).

НЕ прод, НЕ live, НЕ вердикт станции — первичный скрининг + tail-risk.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
for p in (ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

FEE_SIDE = 0.0006 + 0.0002          # taker fee + slippage, на сторону
FUNDING_PER_DAY = 0.0003            # 3 bps/день, против позиции (консервативно)
BAR_MS = 5 * 60 * 1000


# ---------- данные ----------
def load_5m(sym, cap=210000):
    import glob
    fs = sorted(glob.glob(f"{ROOT}/data_cache/{sym}_5_*.json"), key=os.path.getsize)
    if not fs:
        return None
    d = json.load(open(fs[-1]))
    rows = d if isinstance(d, list) else d.get("data")
    g = lambda r, k, i: (r[k] if isinstance(r, dict) else r[i])
    out = [(int(g(r, 'ts', 0)), float(g(r, 'o', 1)), float(g(r, 'h', 2)),
            float(g(r, 'l', 3)), float(g(r, 'c', 4))) for r in rows]
    return out[-cap:]


def to_1h(bars5):
    out = []
    for i in range(0, len(bars5) - len(bars5) % 12, 12):
        ch = bars5[i:i + 12]
        out.append((ch[0][0], ch[0][1], max(b[2] for b in ch),
                    min(b[3] for b in ch), ch[-1][4]))
    return out


# ---------- уровни: мульти-тач кластеры пивотов ----------
def _pivots(h1, left=3, right=3, mode="low"):
    n = len(h1)
    idx = 3 if mode == "low" else 2
    vals = [b[idx] for b in h1]
    out = []
    for i in range(left, n - right):
        px = vals[i]
        if mode == "low":
            if all(px <= vals[j] for j in range(i - left, i)) and all(px < vals[j] for j in range(i + 1, i + right + 1)):
                out.append(px)
        else:
            if all(px >= vals[j] for j in range(i - left, i)) and all(px > vals[j] for j in range(i + 1, i + right + 1)):
                out.append(px)
    return out


def _atr(h1, period=14):
    if len(h1) < period + 1:
        return 0.0
    trs = []
    for i in range(len(h1) - period, len(h1)):
        hi, lo, pc = h1[i][2], h1[i][3], h1[i - 1][4]
        trs.append(max(hi - lo, abs(hi - pc), abs(lo - pc)))
    return sum(trs) / period


def build_levels(h1, min_touches=2, lookback=1000):
    """-> (supports asc, resistances asc, atr). Только закрытые 1h бары."""
    win = h1[-lookback:]
    atr = _atr(win)
    if atr <= 0:
        return [], [], 0.0
    tol = 0.5 * atr
    res = {}
    for mode in ("low", "high"):
        piv = sorted(_pivots(win, mode=mode))
        levels = []
        cluster = []
        for px in piv:
            if not cluster or px - cluster[0] <= tol:
                cluster.append(px)
            else:
                levels.append((sum(cluster) / len(cluster), len(cluster)))
                cluster = [px]
        if cluster:
            levels.append((sum(cluster) / len(cluster), len(cluster)))
        res[mode] = sorted(px for px, t in levels if t >= min_touches)
    return res["low"], res["high"], atr


# ---------- симуляция одного символа/стороны ----------
def simulate(bars5, side="long", capital=1000.0, tranches=10, leverage=1.0,
             min_touches=2, touch_tol_atr=0.2, level_gap_atr=0.5,
             tp_buf_atr=0.25, min_tp_pct=0.006, fallback_tp_pct=0.010,
             max_hold_days=45, refit_bars=288):
    """Возвращает метрики + список циклов. Каждое колено = capital/tranches маржи,
    нотионал колена = маржа*leverage. Ликвидация approx: loss == вся внесённая маржа."""
    h1_all = to_1h(bars5)
    tranche_margin = capital / tranches
    sup = resl = []
    atr = 0.0

    pos = None          # dict: legs [(px, notional)], last_lvl, entry_ts, side
    pend = None         # ("enter"|"add"|"exit_all", px_hint)
    cycles = []
    equity = capital
    eq_min = capital
    eq_max = capital
    busts = 0

    def avg_px():
        tot_n = sum(n for _, n in pos["legs"])
        return sum(px * n for px, n in pos["legs"]) / tot_n, tot_n

    def close_cycle(exit_px, ts, reason):
        nonlocal pos, equity, eq_min, eq_max, busts
        a, tot_n = avg_px()
        if side == "long":
            gross = (exit_px / a - 1.0) * tot_n
        else:
            gross = (1.0 - exit_px / a) * tot_n
        days = max(0.0, (ts - pos["entry_ts"]) / 86400000.0)
        cost = tot_n * FEE_SIDE * 2 + tot_n * FUNDING_PER_DAY * days
        pnl = gross - cost
        if reason == "liq":
            pnl = -sum(n for _, n in pos["legs"]) / leverage - tot_n * FEE_SIDE
            busts += 1
        equity += pnl
        eq_min = min(eq_min, equity)
        eq_max = max(eq_max, equity)
        cycles.append({"pnl": round(pnl, 2), "legs": len(pos["legs"]),
                       "days": round(days, 1), "reason": reason})
        pos = None

    n5 = len(bars5)
    for i in range(max(refit_bars, 12 * 40), n5 - 1):
        ts, o, h, l, c = bars5[i]

        # исполняем отложенное на open ТЕКУЩЕГО бара (сигнал был на закрытии прошлого)
        if pend is not None:
            act = pend
            pend = None
            if act[0] == "enter" and pos is None:
                pos = {"legs": [(o, tranche_margin * leverage)], "last_lvl": act[1],
                       "entry_ts": ts}
            elif act[0] == "add" and pos is not None and len(pos["legs"]) < tranches:
                pos["legs"].append((o, tranche_margin * leverage))
                pos["last_lvl"] = act[1]
            elif act[0] == "exit" and pos is not None:
                close_cycle(o, ts, "tp")

        # ежедневный рефит уровней (только закрытые 1h)
        if i % refit_bars == 0:
            h1 = h1_all[: i // 12]
            sup, resl, atr = build_levels(h1, min_touches=min_touches)
        if atr <= 0 or (not sup and not resl):
            continue

        lv_entry = sup if side == "long" else resl
        lv_target = resl if side == "long" else sup

        if pos is None:
            # вход: касание ближайшего уровня + закрытие на нашей стороне
            for L_ in (reversed(lv_entry) if side == "long" else lv_entry):
                if side == "long":
                    if l <= L_ + touch_tol_atr * atr and c >= L_ and c <= L_ + 1.5 * atr:
                        pend = ("enter", L_)
                        break
                    if L_ > c:
                        continue
                else:
                    if h >= L_ - touch_tol_atr * atr and c <= L_ and c >= L_ - 1.5 * atr:
                        pend = ("enter", L_)
                        break
            continue

        # --- в позиции ---
        a, tot_n = avg_px()
        margin_used = tot_n / leverage

        # ликвидация approx (внутрибарно, консервативно по экстремуму)
        if leverage > 1.0:
            liq_px = a * (1.0 - margin_used / tot_n) if side == "long" else a * (1.0 + margin_used / tot_n)
            if (side == "long" and l <= liq_px) or (side == "short" and h >= liq_px):
                close_cycle(liq_px, ts, "liq")
                continue

        # time-stop
        if (ts - pos["entry_ts"]) / 86400000.0 >= max_hold_days:
            close_cycle(c, ts, "time")
            continue

        # тейк: перед следующим уровнем от средней
        tp = None
        if side == "long":
            nxt = [x for x in lv_target if x > a * (1 + min_tp_pct)]
            tp = (min(nxt) - tp_buf_atr * atr) if nxt else a * (1 + fallback_tp_pct)
            if tp <= a * (1 + min_tp_pct):
                tp = a * (1 + fallback_tp_pct)
            if h >= tp:
                close_cycle(tp, ts, "tp")
                continue
        else:
            nxt = [x for x in lv_target if x < a * (1 - min_tp_pct)]
            tp = (max(nxt) + tp_buf_atr * atr) if nxt else a * (1 - fallback_tp_pct)
            if tp >= a * (1 - min_tp_pct):
                tp = a * (1 - fallback_tp_pct)
            if l <= tp:
                close_cycle(tp, ts, "tp")
                continue

        # усреднение: следующий СИЛЬНЫЙ уровень дальше по ходу против нас
        if len(pos["legs"]) < tranches:
            if side == "long":
                deeper = [x for x in lv_entry if x < pos["last_lvl"] - level_gap_atr * atr]
                if deeper:
                    nl = max(deeper)
                    if l <= nl + touch_tol_atr * atr and c >= nl:
                        pend = ("add", nl)
            else:
                deeper = [x for x in lv_entry if x > pos["last_lvl"] + level_gap_atr * atr]
                if deeper:
                    nl = min(deeper)
                    if h >= nl - touch_tol_atr * atr and c <= nl:
                        pend = ("add", nl)

    # незакрытый цикл в конце — закрываем по последнему close (честно пометим)
    if pos is not None:
        close_cycle(bars5[-1][4], bars5[-1][0], "eod")

    wins = [c_ for c_ in cycles if c_["pnl"] > 0]
    max_legs = max((c_["legs"] for c_ in cycles), default=0)
    deep = [c_ for c_ in cycles if c_["legs"] >= tranches]
    return {
        "cycles": len(cycles), "net": round(equity - capital, 2),
        "wr": round(len(wins) / len(cycles), 3) if cycles else 0.0,
        "worst": round(min((c_["pnl"] for c_ in cycles), default=0.0), 2),
        "max_legs": max_legs, "full_depth_cycles": len(deep),
        "busts": busts, "eq_min": round(eq_min, 2), "eq_max": round(eq_max, 2),
        "maxdd": round(eq_max - eq_min, 2),
        "avg_days": round(sum(c_["days"] for c_ in cycles) / len(cycles), 1) if cycles else 0.0,
        "detail": cycles,
    }


IS_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT",
              "LINKUSDT", "AVAXUSDT", "XRPUSDT", "DOGEUSDT"]
OOS_SYMBOLS = ["ATOMUSDT", "DOTUSDT", "LTCUSDT", "1000PEPEUSDT"]

GRID = [
    {"side": s, "min_touches": mt, "leverage": lv}
    for s in ("long", "short") for mt in (2, 3) for lv in (1.0, 3.0)
]


def run_checkpointed(run_id="level_dca_v1", symbols=None, cap=210000):
    """Чанк-раннер с resume: результат каждой пары (комбо,символ) — строка jsonl."""
    import time
    symbols = symbols or (IS_SYMBOLS + OOS_SYMBOLS)
    path = os.path.join(_HERE, "results", f"{run_id}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                r = json.loads(line)
                done.add((r["sym"], json.dumps(r["params"], sort_keys=True)))
            except Exception:
                pass
    t0 = time.time()
    for sym in symbols:
        bars = None
        for p in GRID:
            key = (sym, json.dumps(p, sort_keys=True))
            if key in done:
                continue
            if bars is None:
                bars = load_5m(sym, cap=cap)
                if not bars:
                    break
            m = simulate(bars, **p)
            m.pop("detail", None)
            rec = {"sym": sym, "params": p, **m, "oos": sym in OOS_SYMBOLS}
            with open(path, "a") as f:
                f.write(json.dumps(rec) + "\n")
            print(f"{sym} {p['side']} mt={p['min_touches']} lev={p['leverage']}: "
                  f"net={m['net']} cycles={m['cycles']} wr={m['wr']} worst={m['worst']} "
                  f"maxlegs={m['max_legs']} busts={m['busts']}", flush=True)
            if time.time() - t0 > 38:
                print("CHUNK_TIMEOUT — перезапусти для продолжения")
                return False
    print("ALL_DONE")
    return True


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        bars = load_5m("LINKUSDT", cap=60000)
        m = simulate(bars, side="long")
        m.pop("detail")
        print(json.dumps(m, indent=1))
    else:
        run_checkpointed()
