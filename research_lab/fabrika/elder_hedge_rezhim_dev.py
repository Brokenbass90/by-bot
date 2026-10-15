#!/usr/bin/env python3
"""elder_hedge_rezhim_dev.py — единственный прогон PREREG_ELDER_CRASH_HEDGE_REZHIM_2026_10_15.md (вариант: ELDER только при REZHIM_V1 ≠ BULL_TREND)."""
import bisect, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(LAB / "fabrika")); sys.path.insert(0, str(LAB / "os2"))
import elder_hedge_dev as E                      # noqa: E402
OUT = LAB / "data" / "elder_hist_dev" / "HEDGE_REZHIM_ITOG.json"


def main():
    if OUT.exists(): sys.exit("HEDGE_REZHIM_ITOG.json уже есть — прогон один")
    import rezhim_v1
    d = np.load(LAB / "data" / "h1" / "BTCUSDT.npz"); ts = d["ts"].astype(np.int64); o = d["ohlcv"].astype(float)
    rv = dict(zip(ts.tolist(), rezhim_v1.metki(ts, o)))
    bull = {"vsego": 0, "bull": 0, "unknown": 0}
    src = LAB / "data" / "elder_hist_dev" / "sdelki.jsonl"; tmp = LAB / "data" / "elder_hist_dev" / "_sdelki_rezhim.jsonl"
    with open(tmp, "w") as f:
        for l in open(src):
            x = json.loads(l)
            if not x.get("ispolnen") or x.get("nezaversheno"): continue
            m = rv.get(int(x["ts"])); bull["vsego"] += 1
            if m is None: bull["unknown"] += 1
            if m == "BULL_TREND": bull["bull"] += 1; continue
            f.write(l)
    orig = E.elder_nedeli
    def elder_nedeli(nedeli, _p=tmp):
        out = {d_: 0.0 for d_ in nedeli}; starts = [E.ms(d_) for d_ in nedeli]
        for l in open(_p):
            x = json.loads(l); t = x["ts"] + (1 + x["bar_CONTROL"]) * E.H; j = bisect.bisect_right(starts, t) - 1
            if 0 <= j and t < starts[j] + 7 * E.DEN: out[nedeli[j]] += x["R_CONTROL"]
        return out
    E.elder_nedeli = elder_nedeli; E.OUT = OUT
    E.main()
    it = json.loads(OUT.read_text()); it["prereg"] = "PREREG_ELDER_CRASH_HEDGE_REZHIM_2026_10_15.md"; it["filtr_rezhima"] = bull
    it["VERDIKT"] = it["VERDIKT"].replace("ELDER_CRASH_HEDGE_DEV", "ELDER_CRASH_HEDGE_REZHIM_DEV")
    OUT.write_text(json.dumps(it, ensure_ascii=False, indent=1)); print("ФИЛЬТР:", bull, it["VERDIKT"])


if __name__ == "__main__":
    main()
