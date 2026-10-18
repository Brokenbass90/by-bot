"""Пересчёт PREREG_KITY_M3_KRIPTO_PERESCHET_2026_10_18 (0757597). Логика недели — копия kity_bybit_sudya.py + фильтр вселенной.
Также пересчитывает оригинал (без фильтра) тем же кодом — контроль, что совпадает с квитанцией 07.10."""
import datetime as dt, json
from pathlib import Path
import numpy as np
import kity_bybit_sudya as S
LAB = Path(__file__).resolve().parent; DEN = S.DEN
INS = {r["symbol"]: r for r in json.loads((LAB / "data/bybit_instruments_linear.json").read_text())["records"]}
def kripto(s):
    r = INS.get(s)
    return r is None or (r.get("symbolType") not in ("stock", "commodity") and r.get("baseCoin") not in ("XAUT", "PAXG"))

def progon(filtr):
    sostav = json.loads((LAB / "data/basis/vselennaya_pit_usd50.json").read_text())["sostav"]
    ned, nogi_vse = [], []
    d = dt.date(2023, 1, 5)
    while d <= dt.date(2026, 9, 24):
        vch = (d - dt.timedelta(days=1)).isoformat(); rows = []
        for s in sostav.get(d.isoformat(), []):
            if filtr and not kripto(s): continue
            f = S.P / vch / f"{s}.json"; x = S.ryad(s)
            if not f.exists() or x is None: continue
            a = json.loads(f.read_text())
            if a.get("net") or a["buy"] + a["sell"] <= 0: continue
            i = int(np.searchsorted(x["ts"], S.ms(d)))
            if i >= len(x["ts"]) or x["ts"][i] != S.ms(d) or i < 60: continue
            rows.append((a["buy"] / (a["buy"] + a["sell"]), s, i))
        if len(rows) >= 30:
            rows.sort(); k = len(rows) // 10; legs = []
            for side, part in ((-1, rows[:k]), (+1, rows[-k:])):
                for _, s, i in part:
                    x = S.ryad(s); t_in = x["ts"][i]; t_out = t_in + 7 * DEN
                    j = int(np.searchsorted(x["ts"], t_out, side="right")) - 1
                    if j <= i: continue
                    fund = sum(v for t, v in x["f"] if x["ts"][i] < t <= x["ts"][j])
                    r = side * (x["c"][j] / x["c"][i] - 1) - side * fund - 0.0012
                    legs.append(r)
                    mq = float((INS.get(s) or {}).get("lotSizeFilter", {}).get("minOrderQty", 0) or 0)
                    nogi_vse.append((d.isoformat(), s, side, r, -side * fund, mq * x["c"][i]))
            if legs: ned.append((d.isoformat(), float(np.mean(legs)), k))
        d += dt.timedelta(days=7)
    return ned, nogi_vse

def svodka(ned, nogi):
    r = np.array([w[1] for w in ned]); pol = len(r) // 2
    def st(sel):
        x = np.array([w[1] for w in ned if sel(w[0])])
        return dict(nedel=len(x), bps=round(x.mean() * 1e4, 1) if len(x) else None, t=round(S.nw_t(x), 2) if len(x) > 5 else None)
    out = dict(nedel=len(r), srednee_bps=round(r.mean() * 1e4, 1), t_nw=round(S.nw_t(r), 2),
               polovinki_bps=[round(r[:pol].mean() * 1e4, 1), round(r[pol:].mean() * 1e4, 1)],
               po_godam={g: st(lambda d, g=g: d.startswith(g)) for g in ("2023", "2024", "2025", "2026")},
               do_2026_03_25=st(lambda d: d < "2026-03-25"), s_2026_03_25=st(lambda d: d >= "2026-03-25"),
               fanding_vklad_bps=round(float(np.mean([n[4] for n in nogi])) * 1e4, 2),
               dop_rashody_bps={x: round(r.mean() * 1e4 - x, 1) for x in (5, 10, 20, 30)},
               dolya_nog_minlot_gt_30usdt=round(float(np.mean([n[5] > 30 for n in nogi])), 3),
               nogi_ne_kripto=sum(1 for n in nogi if not kripto(n[1])))
    out["verdikt"] = "CANDIDATE_HIST_PASS" if r.mean() > 0 and out["t_nw"] >= 1.5 and min(out["polovinki_bps"]) > 0 else (
        "FAIL" if r.mean() < 0 and out["t_nw"] <= -1.0 else "UNKNOWN")
    return out

if __name__ == "__main__":
    rez = {}
    for imya, f in (("ORIGINAL_KONTROL", False), ("KRIPTO", True)):
        ned, nogi = progon(f); rez[imya] = svodka(ned, nogi)
    kv = json.loads((LAB / "data/KITY_BYBIT_KVITANCIYA.json").read_text())
    rez["kontrol_sovpadaet_s_kvitanciey"] = (rez["ORIGINAL_KONTROL"]["nedel"] == kv["nedel"] and rez["ORIGINAL_KONTROL"]["srednee_bps"] == kv["srednee_bps"])
    (LAB / "data/KITY_M3_KRIPTO_PERESCHET.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    print(json.dumps(rez, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
