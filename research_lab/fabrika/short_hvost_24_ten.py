#!/usr/bin/env python3
"""short_hvost_24_ten.py — параллельная тень SHORT_HVOST «удержание 24 ч» рядом с базой 16 ч (27.10.2026, Claude;
решение по PREREG_SHORT_HVOST_UDERZHANIE_2026_10_27, вывод 24CH_V_PARALLELNUYU_TEN). Хук сторожа, только чтение публичного REST Bybit.
Только НОВЫЕ события (event_ts ≥ 2026-10-27 18:00 UTC — после решения), каждое — когда прошло ≥ 33 ч: H1 монеты и BTC, фандинг со знаком.
Считается тем же кодом, что и история (short_hvost_uderzhanie): net с хеджем BTC для 16 и 24 ч, MAE, аварийный стоп +80 %.
Журнал data/short_hvost_24_ten.jsonl (дописывается), сводка data/short_hvost_24_ten_svodka.json: парная разница 24 − 16 на новых сделках.
Вердикт (описательно до 30 событий): 24 ч лучше базы, если среднее и медиана парной разницы > 0 и аварийных стопов не больше, чем у базы."""
import json, statistics as st, sys, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB))
import fanding_hvost as F, short_hvost_uderzhanie as U
OT = 1793124000000; H = 3600000
ZH, SV = LAB / "data" / "short_hvost_24_ten.jsonl", LAB / "data" / "short_hvost_24_ten_svodka.json"

def prohod():
    now = int(time.time() * 1000)
    bylo = {(r["sym"], r["ts"]) for r in map(json.loads, ZH.open())} if ZH.exists() else set()
    ev = set()
    for fn in F.LEDGERY:
        p = F.ROOT / fn
        if not p.exists(): continue
        for l in open(p):
            r = json.loads(l)
            if r.get("side") == -1 and r.get("symbol") not in F.NE_HVOST and r.get("event_ts") and r["event_ts"] >= OT:
                ev.add((r["symbol"], int(r["event_ts"])))
    novyh = 0
    for s, t in sorted(ev, key=lambda x: x[1]):
        if (s, t) in bylo or now < t + 34 * H: continue
        try: b = U.svechi(s, t, 33); bt = U.svechi("BTCUSDT", t, 33); fd = U.fanding(s, t, t + 33 * H)
        except Exception: continue
        if len(b) < 25 or len(bt) < 25: continue
        e, eb = b[0][1], bt[0][1]; z = dict(sym=s, ts=t, zapisano=now)
        for h in (16, 24):
            avar = next((k for k in range(h) if b[k][2] >= e * 1.8), None)
            vyh = e * 1.8 * 1.05 if avar is not None else b[h - 1][4]; kon = t + ((avar + 1) if avar is not None else h) * H
            fund = sum(fr for ts_, fr in fd if t < ts_ <= kon) * 1e4
            net = (e - vyh) / e * 1e4 + fund - 36; btc = (bt[h - 1][4] / eb - 1) * 1e4
            z[str(h)] = dict(net_hedzh=round(net + btc - 12, 1), mae=round((max(x[2] for x in b[:h]) / e - 1) * 100, 2), avar=avar is not None)
        with ZH.open("a") as f: f.write(json.dumps(z, ensure_ascii=False) + "\n")
        novyh += 1; time.sleep(0.15)
    L = [json.loads(l) for l in ZH.open()] if ZH.exists() else []
    d = [r["24"]["net_hedzh"] - r["16"]["net_hedzh"] for r in L]
    out = dict(kogda=time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), sobytiy=len(L),
               baza16_sred=round(st.mean(r["16"]["net_hedzh"] for r in L), 1) if L else None,
               v24_sred=round(st.mean(r["24"]["net_hedzh"] for r in L), 1) if L else None,
               raznica_sred=round(st.mean(d), 1) if d else None, raznica_med=round(st.median(d), 1) if d else None,
               avar16=sum(r["16"]["avar"] for r in L), avar24=sum(r["24"]["avar"] for r in L),
               status="NAKOPLENIE" if len(L) < 30 else ("24CH_LUCHSHE" if st.mean(d) > 0 and st.median(d) > 0 and sum(r["24"]["avar"] for r in L) <= sum(r["16"]["avar"] for r in L) else "BAZA_16CH"))
    SV.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return dict(novyh=novyh, sobytiy=len(L), status=out["status"])

if __name__ == "__main__":
    print(prohod())
