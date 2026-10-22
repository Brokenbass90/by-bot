#!/usr/bin/env python3
"""Оценщик forward-тени SLOPE_BREAKDOWN_SHORT + хедж BTC (prereg PREREG_SLOPE_BREAKDOWN_HEDGE_VPERED_2026_10_20).
Сигналы и нога монеты — точно как вариант A в slope_breakdown_oos.py (пробой растущей наклонной по двум H4-впадинам закрытием H4
на 0.25 ATR, вход по open следующего H1, стоп = линия + 0.5 ATR, цель 1 ATR, 96 ч, без перекрытия сделок по монете).
Хедж: лонг BTCUSDT на β·номинал шорта, β — OLS-бета часовых доходностей монеты к BTC за 720 ч до сигнала, обрезка [0.3; 2].
Обе ноги закрываются вместе (на баре выхода ноги монеты; BTC — по close этого бара — допущение раскрыто). Издержки 6 bps/сторона на
каждую ногу; фандинг обеих ног по публичной истории Bybit за время удержания. Засчитываются только сигналы ≥ 2026-10-21 00:00 UTC
и только закрытые пары. Нужна сеть (публичные свечи Bybit), ключей нет:  .venv/bin/python3 research_lab/slope_hedge_vpered.py"""
import json, math, time, datetime as dt, urllib.request
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent
H = 3_600_000; H4 = 4 * H; FEE = 6.0; HOLD = 96
S0 = int(dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc).timestamp() * 1000)
ZAGRUZKA_OT = S0 - 75 * 24 * H

def _get(u):
    r = urllib.request.Request(u, headers={"User-Agent": "slope-vpered/1.0"})
    with urllib.request.urlopen(r, timeout=25) as f:
        return json.loads(f.read().decode())

def svechi(sym, start, end):
    out, s = [], start
    while s < end:
        lst = ((_get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60&start={s}&end={min(end, s + 999 * H)}&limit=1000")
                .get("result") or {}).get("list") or [])
        part = sorted([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in lst)
        if not part: break
        out.extend(p for p in part if not out or p[0] > out[-1][0]); s = part[-1][0] + H; time.sleep(0.12)
    return [x for x in out if x[0] + H <= end]

def fanding(sym, start, end):
    try:
        lst = ((_get(f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={sym}&startTime={start}&endTime={end}&limit=200")
                .get("result") or {}).get("list") or [])
        return sum(float(x["fundingRate"]) for x in lst)
    except Exception:
        return None

def signaly(a):
    ts = a[:, 0].astype(np.int64); o, h, l, c, v = a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
    k = ts // H4; gr = np.flatnonzero(np.r_[True, k[1:] != k[:-1]]); en_ = np.r_[gr[1:], len(ts)]
    Hh = np.array([h[s:e].max() for s, e in zip(gr, en_)]); Hl = np.array([l[s:e].min() for s, e in zip(gr, en_)]); Hc = c[en_ - 1]
    tr = np.maximum(Hh[1:] - Hl[1:], np.maximum(abs(Hh[1:] - Hc[:-1]), abs(Hl[1:] - Hc[:-1])))
    atr = np.r_[np.nan, np.convolve(tr, np.ones(14) / 14, "full")[:len(tr)]]; atr[:15] = np.nan
    piv = [j for j in range(3, len(gr) - 3) if Hl[j] < Hl[j - 3:j].min() and Hl[j] < Hl[j + 1:j + 4].min()]
    sig = []
    for p1, p2 in zip(piv, piv[1:]):
        if not (6 <= p2 - p1 <= 60) or Hl[p2] <= Hl[p1]: continue
        A = atr[p2 + 3]
        if not A > 0: continue
        slope = (Hl[p2] - Hl[p1]) / (p2 - p1)
        for j in range(p2 + 4, min(len(gr), p2 + 3 + 120)):
            lvl = Hl[p1] + slope * float(k[gr[j]] - k[gr[p1]])
            if (Hc[j] - lvl) / A <= -0.25:
                i = en_[j] - 1
                if ts[i] >= S0 and en_[j] <= len(ts): sig.append((i, lvl, A))
                break
    return sorted(sig)

def main():
    seychas = int(time.time() * 1000) // H * H
    btc = np.array(svechi("BTCUSDT", ZAGRUZKA_OT, seychas), float); bidx = {int(t): n for n, t in enumerate(btc[:, 0])}
    br = np.diff(np.log(btc[:, 4]))
    pary, statusy = [], {}
    for f in sorted((LAB / "data" / "oos_bybit_h1_20261020").glob("*.json")):
        sym = f.stem
        if "_B21" in sym or sym == "BTCUSDT": continue
        try: a = np.array(svechi(sym, ZAGRUZKA_OT, seychas), float)
        except Exception: statusy["NET_DANNYH"] = statusy.get("NET_DANNYH", 0) + 1; continue
        if len(a) < 400: continue
        o, h, l, c = a[:, 1], a[:, 2], a[:, 3], a[:, 4]; ts = a[:, 0].astype(np.int64)
        zanyato = -1
        for i, lvl, A in signaly(a):
            if i <= zanyato or i + 1 >= len(c): continue
            e = i + 1; en = o[e]; stop = lvl + 0.5 * A
            if stop <= en: continue
            risk = stop - en; tp = en - A
            vyh = None
            for j in range(e, min(len(c), e + HOLD)):
                if h[j] >= stop: vyh = (j, stop); break
                if l[j] <= tp: vyh = (j, tp); break
            if vyh is None:
                if e + HOLD <= len(c): vyh = (e + HOLD - 1, c[e + HOLD - 1])
                else: statusy["OTKRYTA"] = statusy.get("OTKRYTA", 0) + 1; zanyato = i + HOLD; continue
            zanyato = i + HOLD
            j, px = vyh
            bi = bidx.get(int(ts[i])); bj = bidx.get(int(ts[e])); bx = bidx.get(int(ts[j]))
            if bi is None or bj is None or bx is None or bi < 721:
                statusy["NET_BTC"] = statusy.get("NET_BTC", 0) + 1; continue
            ci = {int(t): n for n, t in enumerate(ts)}
            cr, xr = [], []
            for t_ in range(int(ts[i]) - 720 * H, int(ts[i]), H):
                n1, m1 = ci.get(t_), bidx.get(t_)
                if n1 and m1 and ci.get(t_ - H) is not None and bidx.get(t_ - H) is not None:
                    cr.append(math.log(c[n1] / c[ci[t_ - H]])); xr.append(math.log(btc[m1, 4] / btc[bidx[t_ - H], 4]))
            if len(cr) < 300: statusy["MALO_DLYA_BETY"] = statusy.get("MALO_DLYA_BETY", 0) + 1; continue
            cr, xr = np.array(cr), np.array(xr); beta = float(np.clip(np.cov(cr, xr)[0, 1] / np.var(xr, ddof=1), 0.3, 2.0))
            notional = en / risk                                              # номинал шорта на 1R (в долях цены)
            R_coin = (en - px) / risk - 2 * FEE / 1e4 * notional
            b_en, b_ex = btc[bj, 1], btc[bx, 4]
            R_hedge = beta * notional * (b_ex / b_en - 1) - 2 * FEE / 1e4 * beta * notional
            fc, fb = fanding(sym, int(ts[e]), int(ts[j]) + H), fanding("BTCUSDT", int(ts[e]), int(ts[j]) + H)
            R_fund = (notional * fc if fc is not None else 0.0) - (beta * notional * fb if fb is not None else 0.0)
            pary.append(dict(sym=sym, ts=int(ts[i]), beta=round(beta, 3), R_moneta=round(R_coin, 4), R_hedzh=round(R_hedge, 4),
                             R_fand=round(R_fund, 4), fand_izvesten=fc is not None and fb is not None, R=round(R_coin + R_hedge + R_fund, 4),
                             chasov=int(j - e + 1)))
    statusy["ZAKRYTA"] = len(pary)
    out = dict(prereg="PREREG_SLOPE_BREAKDOWN_HEDGE_VPERED_2026_10_20", kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               statusy=statusy, pary=pary)
    if len(pary) >= 3:
        R = np.array([p["R"] for p in pary]); dni = {}
        for p in pary: dni.setdefault(p["ts"] // (24 * H), []).append(p["R"])
        m = R.mean(); se = math.sqrt(sum((sum(v) - m * len(v)) ** 2 for v in dni.values())) / len(R)
        po = {}
        for p in pary: po.setdefault(p["sym"], []).append(p["R"])
        out["svod"] = dict(n=len(R), sredniy_R=round(float(m), 4), t_klastery_dni=round(float(m / se), 2) if se > 0 else None,
                           R_moneta=round(float(np.mean([p["R_moneta"] for p in pary])), 4), R_hedzh=round(float(np.mean([p["R_hedzh"] for p in pary])), 4),
                           monet_v_pluse=int(sum(np.mean(v) > 0 for v in po.values())), monet=len(po),
                           etap="VERDIKT_150" if len(R) >= 150 else "NAKOPLENIE")
    p = LAB / "results" / f"slope_hedge_vpered_{time.strftime('%Y%m%d_%H%M', time.gmtime())}.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1)); print(json.dumps({k: out.get(k) for k in ("statusy", "svod")}, ensure_ascii=False, indent=1)); print("файл:", p)

if __name__ == "__main__": main()
