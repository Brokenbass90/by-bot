#!/usr/bin/env python3
"""kity_m3_risk.py — ОПИСАТЕЛЬНЫЙ риск-профиль KITY M3 для решения о лимитах (владелец/Codex). Не судья: вердикт и правило
не меняются, порогов нет, ничего не «улучшается». Та же логика сделки, что sudya_xs; окно PRIMARY 2023-01…2026-09-23."""
import datetime as dt, json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sudya_xs as X
TF = {"TSLA", "QQQ", "SPY", "NVDA", "AAPL", "AMZN", "GOOGL", "META", "MSFT", "COIN", "HOOD", "MSTR", "PAXG", "XAU", "XAG",
      "SKHYNIX", "SPCX", "CRCL", "PLTR", "AMD", "NFLX", "INTC", "BABA", "TSM"}
M = X.zagruzit(X.LAB / "data" / "binance_kity")
ned, nogi = [], []
d = dt.date(2023, 1, 5)
while d <= dt.date(2026, 9, 23):
    vch = (d - dt.timedelta(days=1)).isoformat()
    oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
    rows = []
    for _, s in oi:
        x = M[s]; i = int(np.searchsorted(x["ts"], X.ms(d)))
        if i >= len(x["ts"]) or x["ts"][i] != X.ms(d) or i < 60:
            continue
        z = x["taker"].get(vch)
        if z is not None and np.isfinite(z):
            rows.append((z, s, i))
    if len(rows) >= 30:
        rows.sort(); k = len(rows) // 10; legs = []
        for side, part in ((-1, rows[:k]), (+1, rows[-k:])):
            for _, s, i in part:
                r = X.sdelka(M[s], i, 7, side, 0.0012, dt.date(2026, 9, 30))
                if r is not None:
                    legs.append(r); nogi.append(dict(d=d.isoformat(), s=s, side=side, r=r, tf=s.replace("USDT", "") in TF))
        if legs:
            ned.append(dict(d=d.isoformat(), r=float(np.mean(legs)), k=k))
    d += dt.timedelta(days=7)
r = np.array([w["r"] for w in ned]); eq = np.cumprod(1 + r); dd = eq / np.maximum.accumulate(eq) - 1
nr = np.array([n["r"] for n in nogi])
sh = [n for n in nogi if n["side"] < 0]; lo = [n for n in nogi if n["side"] > 0]
tf_vklad = sum(n["r"] for n in nogi if n["tf"]) / max(1e-12, sum(n["r"] for n in nogi))
god = {}
for w in ned:
    god.setdefault(w["d"][:4], []).append(w["r"])
rez = dict(nedel=len(ned), srednee_bps=round(r.mean() * 1e4, 1), mediana_bps=round(float(np.median(r)) * 1e4, 1),
           dolya_plyusovyh_nedel=round(float((r > 0).mean()), 2), hudshaya_nedelya_pct=round(r.min() * 100, 1),
           luchshaya_nedelya_pct=round(r.max() * 100, 1), maks_prosadka_pct=round(dd.min() * 100, 1),
           godovaya_vol_pct=round(r.std(ddof=1) * np.sqrt(52) * 100, 1), sharp=round(r.mean() / r.std(ddof=1) * np.sqrt(52), 2),
           po_godam_bps={g: round(float(np.mean(v)) * 1e4, 1) for g, v in god.items()},
           noga_hudshaya_pct=round(nr.min() * 100, 1), nog_huzhe_minus30pct=int((nr < -0.30).sum()), nog_huzhe_minus50pct=int((nr < -0.50).sum()),
           long_srednee_bps=round(np.mean([n["r"] for n in lo]) * 1e4, 1), short_srednee_bps=round(np.mean([n["r"] for n in sh]) * 1e4, 1),
           short_hudshaya_pct=round(min(n["r"] for n in sh) * 100, 1),
           dolya_pnl_ot_TradFi=round(tf_vklad, 3), nog_TradFi=sum(n["tf"] for n in nogi), nog_vsego=len(nogi))
print(json.dumps(rez, ensure_ascii=False, indent=1))
(X.LAB / "data" / "binance_kity" / "KITY_M3_RISK_PROFIL.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
