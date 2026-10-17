#!/usr/bin/env python3
"""ETF_PREMIYA — 3 измерения БЕЗ доходностей (17.10.2026). Критерии зафиксированы здесь ДО расчёта.

premiya_t = (P_etf / P_coin)_t / k_t − 1, где P_coin = закрытие часового бара Binance, кончающегося на закрытии NYSE (16:00 ET),
k_t = медиана отношения за 20 ПРЕДЫДУЩИХ сессий (только прошлое).
И1 (содержание): Spearman ρ(premiya_t, поток Farside дня t+1) > 0, p < 0.01  → иначе прокси не несёт потоков → KILL без PnL.
И2 (устойчивость k): медиана |k_t/k_{t−1} − 1| < 0.2 %  (иначе премия = шум оценки).
И3 (покрытие): ≥ 80 % сессий окна с определённой премией.
"""
import json, glob, math, datetime as dt
from zoneinfo import ZoneInfo
import numpy as np
from pathlib import Path

def _rang(a):
    a = np.asarray(a, float); o = a.argsort(); r = np.empty(len(a)); r[o] = np.arange(len(a))
    for v in np.unique(a):                                   # средние ранги для связок
        m = a == v
        if m.sum() > 1: r[m] = r[m].mean()
    return r

def spearmanr(x, y):
    rx, ry = _rang(x), _rang(y); n = len(rx); rho = float(np.corrcoef(rx, ry)[0, 1])
    t = rho * math.sqrt((n - 2) / max(1e-12, 1 - rho * rho))
    p = math.erfc(abs(t) / math.sqrt(2))                    # двусторонний, нормальное приближение (n > 100)
    return rho, p
LAB = Path(__file__).resolve().parents[1]; NY = ZoneInfo("America/New_York")

def etf_ryad(tikery):
    out = {}
    for f in sorted(glob.glob(str(LAB / "data/akcii_grouped/20*.json"))):
        d = json.load(open(f)); den = d["date"]
        r = {x[0]: x for x in d["rows"] if x[0] in tikery}
        if r: out[den] = {t: float(v[4]) for t, v in r.items()}
    return out

def coin_na_zakrytii(simvol):
    z = np.load(LAB / "data/h1" / f"{simvol}.npz"); ts = z["ts"].astype(np.int64); c = z["ohlcv"][:, 3].astype(float)
    idx = {int(t): i for i, t in enumerate(ts)}
    def f(den):
        close = dt.datetime.combine(dt.date.fromisoformat(den), dt.time(16, 0), NY).astimezone(dt.timezone.utc)
        t_open = int((close - dt.timedelta(hours=1)).timestamp() * 1000)     # бар [15:00,16:00) ET; его close = цена на 16:00
        i = idx.get(t_open); return None if i is None else c[i]
    return f

def izmerit(tiker, simvol, potok_fayl):
    e = etf_ryad({tiker}); cn = coin_na_zakrytii(simvol)
    dni = sorted(d for d in e if tiker in e[d]); rat = {}
    for d in dni:
        p = cn(d)
        if p: rat[d] = e[d][tiker] / p
    prem, kk = {}, {}
    rd = [d for d in dni if d in rat]
    for i, d in enumerate(rd):
        if i < 20: continue
        k = float(np.median([rat[x] for x in rd[i - 20:i]])); kk[d] = k; prem[d] = rat[d] / k - 1
    potok = {r["date"]: r["last_total_musd"] for r in json.load(open(LAB / potok_fayl)) if r.get("last_total_musd") is not None}
    dpot = sorted(potok); x, y = [], []
    for d in prem:
        nxt = [q for q in dpot if q > d][:1]
        if nxt and (dt.date.fromisoformat(nxt[0]) - dt.date.fromisoformat(d)).days <= 4:
            x.append(prem[d]); y.append(potok[nxt[0]])
    rho, p = spearmanr(x, y) if len(x) > 10 else (float("nan"), float("nan"))
    kd = sorted(kk); dk = [abs(kk[b] / kk[a] - 1) for a, b in zip(kd, kd[1:])]
    sess = [d for d in dni if rd and rd[20 if len(rd) > 20 else 0] <= d <= rd[-1]]
    pokr = len(prem) / max(1, len(sess))
    # для справки: ρ с потоком того же дня (не критерий)
    x0 = [prem[d] for d in prem if d in potok]; y0 = [potok[d] for d in prem if d in potok]
    rho0 = spearmanr(x0, y0)[0] if len(x0) > 10 else float("nan")
    return dict(tiker=tiker, sessiy=len(dni), s_premiey=len(prem), par_s_potokom=len(x),
                I1_rho_t1=round(float(rho), 3), I1_p=float(p), I1=bool(rho > 0 and p < 0.01),
                I2_median_dk_pct=round(100 * float(np.median(dk)), 4), I2=bool(np.median(dk) < 0.002),
                I3_pokrytie=round(pokr, 3), I3=bool(pokr >= 0.8), spravka_rho_t0=round(float(rho0), 3),
                period=[min(prem), max(prem)] if prem else None,
                premiya_bps_p10_50_90=[round(1e4 * v, 1) for v in np.percentile(list(prem.values()), [10, 50, 90])] if prem else None)

if __name__ == "__main__":
    rez = [izmerit("IBIT", "BTCUSDT", "data/etf_potoki/btc.json"), izmerit("ETHA", "ETHUSDT", "data/etf_potoki/eth.json")]
    (LAB / "data/etf_premiya").mkdir(exist_ok=True)
    (LAB / "data/etf_premiya/IZMERENIYA.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    for r in rez: print(json.dumps(r, ensure_ascii=False))
