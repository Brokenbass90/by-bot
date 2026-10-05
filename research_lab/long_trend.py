#!/usr/bin/env python3
"""long_trend.py — судья PREREG_LONG_TREND_BTC_ETH_2026_10_05.md. Один прогон; повтор запрещён.
    python3 research_lab/long_trend.py
"""
import datetime as dt, hashlib, json, sys
from pathlib import Path
import numpy as np
import discovery_paket1 as P

D = Path(__file__).resolve().parent / "data" / "binance_kity"
REZ = D / "long_trend_rezultat.json"
AKTIVY = ("BTCUSDT", "ETHUSDT"); LOOK, HOLD, KOM = 28, 7, 0.0012
OKNA = {"PRIMARY": ("2021-12-02", "2024-12-26"), "HOLDOUT": ("2025-01-02", "2026-09-23")}
SETKA = [dt.date(2021, 7, 1) + dt.timedelta(days=7 * k) for k in range(400)]


def ms(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def main():
    if REZ.exists():
        sys.exit("результат уже есть — прогон один")
    X = {}
    for s in AKTIVY:
        kl = np.array(json.loads((D / "klines" / f"{s}.json").read_text()), dtype=float)
        fr = np.array(json.loads((D / "funding" / f"{s}.json").read_text()), dtype=float)
        X[s] = dict(ts=kl[:, 0].astype(np.int64), c=kl[:, 4], fts=fr[:, 0].astype(np.int64), fr=fr[:, 1])
    def idx(x, d):
        i = int(np.searchsorted(x["ts"], ms(d))); return i if i < len(x["ts"]) and x["ts"][i] == ms(d) else None
    nedeli = []
    poz = {s: False for s in AKTIVY}
    for d in SETKA:
        if not (OKNA["PRIMARY"][0] <= d.isoformat() <= OKNA["HOLDOUT"][1]):
            continue
        st, bh = [], []
        for s in AKTIVY:
            x = X[s]; i = idx(x, d); j = idx(x, d + dt.timedelta(days=HOLD)); i0 = idx(x, d - dt.timedelta(days=LOOK))
            if None in (i, j, i0):
                st = None; break
            r = x["c"][j] / x["c"][i] - 1 - P.fand(x, x["ts"][i], x["ts"][j])
            bh.append(r)
            novaya = x["c"][i] / x["c"][i0] - 1 > 0
            izd = (KOM / 2) * (novaya != poz[s])            # вход или выход на этой неделе
            poz[s] = novaya
            st.append((r if novaya else 0.0) - izd)
        if st is None:
            continue
        nedeli.append(dict(d=d.isoformat(), t=ms(d), strat=float(np.mean(st)), bh=float(np.mean(bh))))
    def sharp(v): v = np.array(v); return float(v.mean() / v.std(ddof=1) * np.sqrt(52)) if len(v) > 2 and v.std() > 0 else 0.0
    rez = dict(prereg="PREREG_LONG_TREND_BTC_ETH_2026_10_05.md", kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    for imya, (a, b) in OKNA.items():
        w = [x for x in nedeli if a <= x["d"] <= b]
        it = P.itog([(x["t"], x["strat"], None) for x in w], s_kontrolem=False, lag=1)
        it.update(nedel=len(w), sharp_strat=round(sharp([x["strat"] for x in w]), 2), sharp_kupi_derzhi=round(sharp([x["bh"] for x in w]), 2),
                  dolya_v_rynke=round(float(np.mean([x["strat"] != 0 for x in w])), 2))
        rez[imya] = it
    p, h = rez["PRIMARY"], rez["HOLDOUT"]
    ok = (p["verdikt"] == "SURVIVED" and p["sharp_strat"] > p["sharp_kupi_derzhi"]
          and h.get("edge_bps", -1) > 0 and h["sharp_strat"] >= h["sharp_kupi_derzhi"])
    rez["verdikt"] = "FEASIBILITY_PASS" if ok else "KILL"
    REZ.write_text(json.dumps(dict(rez, nedeli=nedeli), ensure_ascii=False, indent=1))
    (D / "LONG_TREND_KVITANCIYA.json").write_text(json.dumps(dict(rezultat_sha256=hashlib.sha256(REZ.read_bytes()).hexdigest(),
        manifest_kity_sha256=hashlib.sha256((D / "manifest.json").read_bytes()).hexdigest(), rezultat=rez), ensure_ascii=False, indent=1))
    print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
