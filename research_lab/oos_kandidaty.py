#!/usr/bin/env python3
"""Одна OOS-проверка 5 стратегий корпуса (PREREG_OOS_KANDIDATY_2026_07_10_2026_10_20).
    .venv/bin/python3 research_lab/oos_kandidaty.py
Публичные свечи Bybit, без ключей и ордеров. Итог: research_lab/results/oos_kandidaty_20261020.json"""
from __future__ import annotations
import glob, hashlib, importlib, inspect, json, math, os, sys, time, urllib.request
from pathlib import Path
import numpy as np

KOREN = Path(__file__).resolve().parents[1]
os.chdir(KOREN); sys.path.insert(0, str(KOREN)); sys.path.insert(0, str(KOREN / "research_lab"))
from research_machine import Store, simulate, pervyy_argument, MAX_LEV, ROZYGRYSHEY   # noqa: E402
from random_control import sim_geo                                                   # noqa: E402

KANDIDATY = ["pump_momentum_v1", "smart_grid", "pump_fade_simple"]   # микроскальперы сняты: дополнение 1
OKNO_S = 1782864000000          # 2026-07-01 00:00 UTC
RAZOGREV_S = 1777593600000      # 2026-05-01 00:00 UTC
STOP_MULT, HOLD, F1, ZERNO, SIGMA_PROG = 4.0, 168, 0.55, 31, 2.58
CHAS = 3_600_000
KESH = Path("research_lab/data/oos_bybit_h1_20261020")
VYVOD = Path("research_lab/results/oos_kandidaty_20261020.json")


def svechi(sym, s, e):
    out = []
    while s < e:
        u = (f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60"
             f"&start={s}&end={min(e, s + 999 * CHAS)}&limit=1000")
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "oos/1.0"}), timeout=25) as f:
            lst = ((json.loads(f.read().decode()).get("result") or {}).get("list") or [])
        part = sorted([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in lst)
        if not part: break
        out.extend(p for p in part if not out or p[0] > out[-1][0]); s = part[-1][0] + CHAS; time.sleep(0.12)
    return out


def bary():
    KESH.mkdir(parents=True, exist_ok=True)
    now = int(time.time() * 1000); konec = (now // CHAS) * CHAS
    out = {}
    for f in sorted(glob.glob("research_lab/data/h1/*.npz")):
        sym = Path(f).stem; p = KESH / f"{sym}.json"
        if p.exists():
            b = json.loads(p.read_text())
        else:
            try:
                b = [x for x in svechi(sym, RAZOGREV_S, konec) if x[0] + CHAS <= now]
            except Exception:
                b = []
            p.write_text(json.dumps(b))
        if len(b) > 400: out[sym] = b
    return out


def klass(mod):
    m = importlib.import_module(f"strategies.{mod}")
    k = [o for _, o in vars(m).items() if inspect.isclass(o) and hasattr(o, "maybe_signal") and o.__module__ == m.__name__]
    return k[0] if k else None


def odna(K, B):
    rng = np.random.default_rng(ZERNO)
    R, po, ctrl = [], {}, [[] for _ in range(ROZYGRYSHEY)]
    for sym, b in B.items():
        try: strat = K()
        except Exception: return {"oshibka": "класс не создаётся"}
        st = Store(sym); pervyy = sym if pervyy_argument(K) == "symbol" else st
        ts = np.array([r[0] for r in b], dtype=np.int64)
        pool = np.flatnonzero(ts >= OKNO_S); pool = pool[pool < len(b) - HOLD - 2]
        block = -1
        for i in range(200, len(b) - 1):
            st.rows = b[: i + 1]; r_ = b[i]
            try: s = strat.maybe_signal(pervyy, r_[0], r_[1], r_[2], r_[3], r_[4], r_[5])
            except Exception: continue
            if i <= block or r_[0] < OKNO_S or s is None or getattr(s, "side", None) not in ("long", "short"):
                continue
            res = simulate(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [F1])[0], STOP_MULT, HOLD)
            if res is None or res.get("lev", 0) > MAX_LEV: continue
            e = i + 1
            if not (e + HOLD <= len(b) or res["bars"] < len(b) - 1 - e):
                block = len(b); continue                       # открыта на конце данных — вне замера
            block = i + res["bars"] + 1
            R.append(res["R"]); po.setdefault(sym, []).append(res["R"])
            if len(pool) < 5: continue
            e_ = float(b[e][1]); sl_w = e_ + (float(s.sl) - e_) * STOP_MULT; rw = abs(e_ - sl_w)
            if rw <= 0: continue
            tl = list(s.tps or []); k1 = abs(tl[0] - e_) / rw if tl else 999.0; k2 = abs(tl[1] - e_) / rw if len(tl) > 1 else 999.0
            for d in range(ROZYGRYSHEY):
                x = sim_geo(b, int(rng.choice(pool)), s.side == "short", 1.0 / res["lev"], k1, k2, (s.tp_fracs or [F1])[0], HOLD)
                if x is not None: ctrl[d].append(x)
    R = np.array(R, float); cm = np.array([np.mean(c) for c in ctrl if len(c) > 20], float)
    if len(R) < 50 or len(cm) < 5:
        return {"n": int(len(R)), "verdikt": "OOS_FAIL (не хватило данных)"}
    edge = float(R.mean() - cm.mean()); se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1)); z = edge / se if se > 1e-12 else 0.0
    plus = sum(1 for v in po.values() if np.mean(v) > 0)
    ok = edge > 0 and z >= SIGMA_PROG and plus * 2 >= len(po)
    return {"n": int(len(R)), "sredniy_R": float(R.mean()), "kontrol": float(cm.mean()), "edzh": edge, "sigma": float(z),
            "vinreyt": float((R > 0).mean()), "itog_R": float(R.sum()), "monet_v_pluse": plus, "monet": len(po),
            "verdikt": "OOS_PASS" if ok else "OOS_FAIL"}


def main():
    B = bary()
    sha = hashlib.sha256(json.dumps({k: B[k] for k in sorted(B)}).encode()).hexdigest()
    out = {"prereg": "PREREG_OOS_KANDIDATY_2026_07_10_2026_10_20", "simvolov": len(B), "bary_sha256": sha, "rez": {}}
    for mod in KANDIDATY:
        t = time.time(); K = klass(mod)
        out["rez"][mod] = odna(K, B) if K else {"oshibka": "класс не найден"}
        out["rez"][mod]["sekund"] = round(time.time() - t, 1)
        print(mod, json.dumps(out["rez"][mod], ensure_ascii=False), flush=True)
        VYVOD.parent.mkdir(parents=True, exist_ok=True); VYVOD.write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
