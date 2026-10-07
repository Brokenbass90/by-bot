#!/usr/bin/env python3
"""B2: сравнение существующих определений режима по свойствам (без PnL). Критерии — os2/B2_KRITERII_REZHIMA.md (записаны до расчёта).
Данные: BTCUSDT H1 < 2025-10-01. Выход: os2/B2_REZHIM_SRAVNENIE.json + метки os2/rezhim_metki/<D>.json (час → состояние)."""
import ast, hashlib, json, math, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(ROOT))
SEALED = 1759276800000; H = 3600000; H4 = 4 * H; PROGREV = 60 * 24

def btc():
    d = np.load(LAB / "data/h1/BTCUSDT.npz"); ts = d["ts"].astype(np.int64); o = d["ohlcv"].astype(float)
    m = ts < SEALED; return ts[m], o[m]

def agg4h(ts, o):
    rows, cur = [], None
    for t, (op, hi, lo, cl, v) in zip(ts, o):
        b = int(t // H4 * H4)
        if cur is None or cur[0] != b:
            if cur: rows.append(cur)
            cur = [b, op, hi, lo, cl, v]
        else:
            cur[2] = max(cur[2], hi); cur[3] = min(cur[3], lo); cur[4] = cl; cur[5] += v
    if cur: rows.append(cur)
    return rows   # бар закрыт, когда t_close = b + 4h

def d1(ts, o):
    c = o[:, 3]; k = 2 / 201; e = np.empty(len(c)); e[0] = c[0]
    for i in range(1, len(c)): e[i] = c[i] * k + e[i - 1] * (1 - k)
    x = (c - e) / e
    return [("тренд-" if v < -0.02 else "флет-" if v < 0 else "флет+" if v < 0.02 else "тренд+") for v in x]

def po_4h(ts, rows4, fn, nuzhno):
    """состояние на каждый час: по 4h-барам, закрытым к концу этого часа"""
    close_t = [r[0] + H4 for r in rows4]; out = []; j = 0; kesh = {}
    for t in ts:
        tc = t + H
        while j < len(rows4) and close_t[j] <= tc: j += 1
        if j < nuzhno: out.append(None); continue
        if j not in kesh: kesh[j] = fn(rows4[:j])
        out.append(kesh[j])
    return out

def d2_fn():
    from bot.regime_orchestrator import compute_regime
    return lambda r: compute_regime([list(x) for x in r[-200:]])["regime"]

def d3_ns():
    src = (ROOT / "scripts/build_regime_state.py").read_text(); tree = ast.parse(src); ns = {"math": math}
    from typing import Dict, List, Tuple, Any
    ns.update(Dict=Dict, List=List, Tuple=Tuple, Any=Any)
    keep = {"_ema", "_atr", "_efficiency_ratio", "_mixed_sign_bias", "_classify_regime"}
    consts = {"MIN_HOLD_CYCLES": 3, "ER_TREND_THRESH": 0.28, "ER_PERIOD": 30, "MIXED_SIGN_PRICE_WEIGHT": 1.0,
              "MIXED_SIGN_EMA_WEIGHT": 0.5, "MIXED_SIGN_EDGE_PCT": 0.15}   # значения по умолчанию из файла (env не задан)
    ns.update(consts)
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "").startswith("REGIME_") or getattr(t, "id", "") == "ALL_REGIMES" for t in n.targets):
            exec(compile(ast.Module([n], []), "brs", "exec"), ns)
        if isinstance(n, ast.FunctionDef) and n.name in keep:
            exec(compile(ast.Module([n], []), "brs", "exec"), ns)
    return ns, hashlib.sha256(src.encode()).hexdigest()

def d3(ts, rows4):
    ns, _ = d3_ns(); cl = ns["_classify_regime"]
    raw = po_4h(ts, rows4, lambda r: cl([dict(ts=x[0], o=x[1], h=x[2], l=x[3], c=x[4], v=x[5]) for x in r[-120:]])[0], 120)
    out, app, pend, cnt = [], None, None, 0
    for r in raw:
        if r is None: out.append(None); continue
        if app is None: app, pend, cnt = r, r, 0
        elif r == app: pend, cnt = r, 0
        elif r == pend:
            cnt += 1
            if cnt >= ns["MIN_HOLD_CYCLES"]: app, cnt = pend, 0
        else: pend, cnt = r, 1
        out.append(app)
    return out

def d4(ts, rows4):
    from bot.regime_hmm import regime_probs
    st = {"prior": None}; res = {}
    close_t = [r[0] + H4 for r in rows4]
    for j in range(60, len(rows4) + 1):        # последовательно, prior переносится
        s = regime_probs([list(x) for x in rows4[max(0, j - 200):j]], prior=st["prior"])
        st["prior"] = s.probs if s.ok else None; res[j] = s.dominant if s.ok else None
    out = []; j = 0
    for t in ts:
        while j < len(rows4) and close_t[j] <= t + H: j += 1
        out.append(res.get(j))
    return out

NAPR = {"тренд+": 1, "флет+": 1, "BULL_TREND": 1, "bull_trend": 1, "bull_chop": 1, "bull": 1,
        "тренд-": -1, "флет-": -1, "BEAR_TREND": -1, "bear_trend": -1, "bear_chop": -1, "bear": -1}

def metriki(ts, s, c):
    s = s[PROGREV:]; c = c[PROGREV:]; n = len(s)
    ok = [x is not None for x in s]; pokr = sum(ok) / n
    v = [x for x in s if x is not None]
    doli = {k: round(v.count(k) / len(v), 3) for k in sorted(set(v))}
    runs, prev, L, perekl = [], None, 0, []
    for i, x in enumerate(s):
        if x is None: continue
        if x != prev:
            if prev is not None: runs.append(L); perekl.append((i, prev, x))
            prev, L = x, 1
        else: L += 1
    pily = sum(1 for a, b in zip(perekl, perekl[1:]) if b[0] - a[0] <= 24 and b[2] == a[1])
    sc = np.array([NAPR.get(x, 0) if x is not None else 0 for x in s], float)
    ref = np.zeros(n); W = 84
    for i in range(W, n - W): ref[i] = np.sign(c[i + W] - c[i - W])
    best, lag = -9, 0
    for k in range(0, 169, 2):
        a = sc[k:]; b = ref[:n - k]
        if a.std() == 0: continue
        r = float(np.corrcoef(a, b)[0, 1])
        if r > best: best, lag = r, k
    dni = n / 24
    return dict(pokrytie=round(pokr, 4), doli=doli, pereklyucheniy_na_30d=round(len(perekl) / dni * 30, 1),
                mediana_dlitelnosti_ch=float(np.median(runs)) if runs else None, dolya_pil=round(pily / max(1, len(perekl)), 3),
                zaderzhka_ch=lag, korr_s_etalonom=round(best, 3))

def vorota(m):
    k1 = m["pokrytie"] >= 0.99; k2 = (m["mediana_dlitelnosti_ch"] or 0) >= 12; k3 = m["dolya_pil"] <= 0.30
    k4 = sum(1 for v in m["doli"].values() if v >= 0.10) >= 3
    return dict(K1=k1, K2=k2, K3=k3, K4=k4, K5=True, PASS=k1 and k2 and k3 and k4)

def main():
    ts, o = btc(); rows4 = agg4h(ts, o); c = o[:, 3]
    defs = {"D1_EMA200_H1": d1(ts, o), "D2_REGIME_ORCH_4H": po_4h(ts, rows4, d2_fn(), 60),
            "D3_BUILD_REGIME_STATE_4H": d3(ts, rows4), "D4_REGIME_HMM_4H": d4(ts, rows4)}
    out = {"dannye": dict(chasov=len(ts), s=int(ts[0]), po=int(ts[-1]), progrev_ch=PROGREV), "kandidaty": {}}
    md = LAB / "os2/rezhim_metki"; md.mkdir(parents=True, exist_ok=True)
    for k, s in defs.items():
        m = metriki(ts, s, c); m["vorota"] = vorota(m); out["kandidaty"][k] = m
        b = json.dumps({"ts": [int(x) for x in ts], "s": s}, ensure_ascii=False).encode()
        (md / f"{k}.json").write_bytes(b); m["metki_sha256"] = hashlib.sha256(b).hexdigest()
    prosh = [(k, m) for k, m in out["kandidaty"].items() if m["vorota"]["PASS"]]
    if not prosh: out["vybor"] = "BLOCKED_IMPLEMENTATION"
    else:
        prosh.sort(key=lambda km: km[1]["zaderzhka_ch"]); best = prosh[0]
        bliz = [km for km in prosh if km[1]["zaderzhka_ch"] - best[1]["zaderzhka_ch"] <= 12]
        bliz.sort(key=lambda km: (km[1]["pereklyucheniy_na_30d"], 0 if km[0].startswith("D3") else 1))
        mn = bliz[0][1]["pereklyucheniy_na_30d"]
        rav = [km for km in bliz if km[1]["pereklyucheniy_na_30d"] == mn]
        out["vybor"] = next((k for k, _ in rav if k.startswith("D3")), rav[0][0])
    (LAB / "os2/B2_REZHIM_SRAVNENIE.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
