#!/usr/bin/env python3
"""kripto_atlas_sbor.py — сбор атласа издержек Bybit linear (Фабрика V2, требование G2). Только публичные данные, без ключей.
Раз в 15 минут снимок /v5/market/tickers: bid1/ask1, размеры верхнего уровня, оборот 24ч → data/kripto_atlas/sbor_YYYY-MM-DD.jsonl.
--atlas строит data/kripto_atlas/ATLAS.json: по символу медиана/p75 спреда (bps), медиана глубины верхнего уровня ($),
по часам UTC, число снимков. Атлас — данные, не гипотеза; ничего не тестирует.
    .venv/bin/python research_lab/fabrika/kripto_atlas_sbor.py --cikl      # копить (≥ 7 суток до первого атласа)
    .venv/bin/python research_lab/fabrika/kripto_atlas_sbor.py --atlas
"""
import argparse, datetime as dt, json, statistics, time, urllib.request
from collections import defaultdict
from pathlib import Path
D = Path(__file__).resolve().parents[1] / "data" / "kripto_atlas"


def snimok():
    req = urllib.request.Request("https://api.bybit.com/v5/market/tickers?category=linear", headers={"User-Agent": "research-paper"})
    with urllib.request.urlopen(req, timeout=30) as r: j = json.loads(r.read())
    t = int(time.time() * 1000); out = []
    for x in j["result"]["list"]:
        try:
            b, a = float(x["bid1Price"]), float(x["ask1Price"])
            if b <= 0 or a <= 0 or a < b: continue
            out.append(dict(t=t, s=x["symbol"], b=b, a=a, bq=float(x.get("bid1Size") or 0), aq=float(x.get("ask1Size") or 0),
                            to=float(x.get("turnover24h") or 0)))
        except (KeyError, ValueError): continue
    D.mkdir(parents=True, exist_ok=True)
    with open(D / f"sbor_{dt.datetime.utcnow():%Y-%m-%d}.jsonl", "a") as f:
        for z in out: f.write(json.dumps(z) + "\n")
    return len(out)


def atlas():
    sp, gl, ch = defaultdict(list), defaultdict(list), defaultdict(lambda: defaultdict(list))
    for f in sorted(D.glob("sbor_*.jsonl")):
        for l in open(f):
            z = json.loads(l); m = (z["a"] + z["b"]) / 2; bps = (z["a"] - z["b"]) / m * 1e4
            sp[z["s"]].append(bps); gl[z["s"]].append(min(z["bq"] * z["b"], z["aq"] * z["a"]))
            ch[z["s"]][dt.datetime.utcfromtimestamp(z["t"] / 1000).hour].append(bps)
    rez = {}
    for s, v in sp.items():
        v = sorted(v); rez[s] = dict(n=len(v), spred_med_bps=round(statistics.median(v), 3), spred_p75_bps=round(v[int(.75 * (len(v) - 1))], 3),
                                     glubina_med_usd=round(statistics.median(gl[s]), 1),
                                     po_chasam_med={h: round(statistics.median(x), 3) for h, x in sorted(ch[s].items())})
    (D / "ATLAS.json").write_text(json.dumps(dict(postroeno=dt.datetime.utcnow().isoformat(), simvolov=len(rez), atlas=rez), indent=1))
    print("символов", len(rez))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--cikl", action="store_true"); ap.add_argument("--atlas", action="store_true"); a = ap.parse_args()
    if a.atlas: atlas()
    else:
        while True:
            try: print(dt.datetime.utcnow().isoformat(timespec="seconds"), "снимок", snimok(), flush=True)
            except Exception as e: print("ошибка", type(e).__name__, str(e)[:120], flush=True)
            if not a.cikl: break
            time.sleep(900 - time.time() % 900 + 20)
