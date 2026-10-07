"""Судья PREREG_KITY_BYBIT_ARHIV_2026_10_07 (заморожен вместе с prereg, ДО данных потока). Один прогон, квитанция.
Повторный прогон после квитанции отказывается."""
import datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parent
P = LAB / "data" / "bybit_potok"; KV = LAB / "data" / "KITY_BYBIT_KVITANCIYA.json"; DEN = 86400000
def ms(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)

def ryad(s, kesh={}):
    if s not in kesh:
        f = LAB / "data" / "pit_daily" / f"{s}.json"
        if not f.exists(): kesh[s] = None
        else:
            d = json.loads(f.read_text()); r = sorted(d["daily"], key=lambda x: int(x[0]))
            kesh[s] = dict(ts=np.array([int(x[0]) for x in r]), c=np.array([float(x[4]) for x in r]),
                           f=sorted((int(t), float(v)) for t, v in d.get("funding", [])))
    return kesh[s]

def nw_t(r, lag=1):
    r = np.asarray(r); n = len(r); e = r - r.mean(); g0 = e @ e / n
    s = g0 + sum(2 * (1 - l / (lag + 1)) * (e[l:] @ e[:-l] / n) for l in range(1, lag + 1))
    return float(r.mean() / np.sqrt(s / n))

def main():
    if KV.exists(): sys.exit("квитанция уже есть — повторный прогон запрещён: " + str(KV))
    sostav = json.loads((LAB / "data/basis/vselennaya_pit_usd50.json").read_text())["sostav"]
    ned, nedel_vsego, h = [], 0, hashlib.sha256()
    d = dt.date(2023, 1, 5)
    while d <= dt.date(2026, 9, 24):
        nedel_vsego += 1; vch = (d - dt.timedelta(days=1)).isoformat(); rows = []
        for s in sostav.get(d.isoformat(), []):
            f = P / vch / f"{s}.json"; x = ryad(s)
            if not f.exists() or x is None: continue
            a = json.loads(f.read_text()); h.update(f.read_bytes())
            if a.get("net") or a["buy"] + a["sell"] <= 0: continue
            i = int(np.searchsorted(x["ts"], ms(d)))
            if i >= len(x["ts"]) or x["ts"][i] != ms(d) or i < 60: continue
            rows.append((a["buy"] / (a["buy"] + a["sell"]), s, i))
        if len(rows) >= 30:
            rows.sort(); k = len(rows) // 10; legs = []
            for side, part in ((-1, rows[:k]), (+1, rows[-k:])):
                for _, s, i in part:
                    x = ryad(s); t_in = x["ts"][i]; t_out = t_in + 7 * DEN
                    j = int(np.searchsorted(x["ts"], t_out, side="right")) - 1
                    if j <= i: continue
                    fund = sum(v for t, v in x["f"] if x["ts"][i] < t <= x["ts"][j])
                    legs.append(side * (x["c"][j] / x["c"][i] - 1) - side * fund - 0.0012)
            if legs: ned.append((d.isoformat(), float(np.mean(legs)), k))
        d += dt.timedelta(days=7)
    r = np.array([w[1] for w in ned]); pol = len(r) // 2
    pokr = len(ned) / nedel_vsego
    res = dict(prereg="PREREG_KITY_BYBIT_ARHIV_2026_10_07.md", kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               nedel=len(ned), nedel_setki=nedel_vsego, pokrytie=round(pokr, 3),
               srednee_bps=round(r.mean() * 1e4, 1) if len(r) else None, t_nw=round(nw_t(r), 2) if len(r) > 5 else None,
               polovinki_bps=[round(r[:pol].mean() * 1e4, 1), round(r[pol:].mean() * 1e4, 1)] if len(r) > 5 else None,
               potok_sha256=h.hexdigest(), nedeli=ned)
    if pokr < 0.9: res["verdikt"] = "BLOCKED_DATA"
    elif r.mean() > 0 and res["t_nw"] >= 1.5 and min(res["polovinki_bps"]) > 0: res["verdikt"] = "CROSS_VENUE_PASS"
    elif r.mean() < 0 and res["t_nw"] <= -1.0: res["verdikt"] = "CROSS_VENUE_OPPOSITE"
    else: res["verdikt"] = "UNKNOWN"
    KV.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "nedeli"}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
