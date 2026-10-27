#!/usr/bin/env python3
"""short_hvost_mae.py — защита SHORT_HVOST от катастрофы (27.10.2026, Claude; требование PM №4). Только чтение публичных свечей Bybit.
Для КАЖДОГО закрытого шорта хвоста из двух теней фандинга (вся эпоха с 08.2026, включая выборку поиска — это диагностика риска, не вердикт)
качает H1 монеты на 17 ч от события и считает максимальный ход против шорта (MAE = max high / цена входа − 1).
Печатает распределение MAE и что дал бы далёкий стоп +30 % (выход 1.30 × 1.05). Правила SHORT_HVOST НЕ меняет.
    Mac:  .venv/bin/python3 research_lab/short_hvost_mae.py"""
import json, sys, time, urllib.request, statistics as st
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE)); import fanding_hvost as F
H = 3600000
def svechi(sym, t0, t1):
    u = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60&start={t0}&end={t1}&limit=40"
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r:
        return sorted([[int(x[0])] + [float(v) for v in x[1:5]] for x in (json.loads(r.read()).get("result") or {}).get("list") or []])
def main():
    u = {}
    for fn in F.LEDGERY:
        for l in open(F.ROOT / fn):
            r = json.loads(l)
            if r.get("record_type") == "outcome" and r.get("status") == "closed" and r.get("side") == -1 and r.get("symbol") not in F.NE_HVOST:
                u[(r["symbol"], r["event_ts"])] = r
    rows = []
    for (s, t), r in sorted(u.items(), key=lambda kv: kv[0][1]):
        try: b = svechi(s, t, t + 17 * H); time.sleep(0.12)
        except Exception as e: rows.append(dict(sym=s, ts=t, oshibka=str(e)[:80])); continue
        if not b: rows.append(dict(sym=s, ts=t, oshibka="нет свечей")); continue
        vh = b[0][1]; mae = max(x[2] for x in b[:17]) / vh - 1
        net = r["net_btc_hedged_bps"] - F.SHTRAF_BPS
        net_stop = (-(0.30 * 1.05 + 0.05) * 1e4 - F.SHTRAF_BPS) if mae >= 0.30 else net
        rows.append(dict(sym=s, ts=t, mae_pct=round(mae * 100, 2), net_bps=round(net, 1), net_so_stopom_bps=round(net_stop, 1), posle_zamorozki=t >= F.ZAMOROZKA_MS))
    ok = [x for x in rows if "mae_pct" in x]; m = sorted(x["mae_pct"] for x in ok)
    out = dict(sobytiy=len(rows), s_cenami=len(ok), mae_mediana=st.median(m), mae_p90=m[int(0.9 * len(m))], mae_max=m[-1],
               dolya_mae_ge={p: round(sum(1 for v in m if v >= p) / len(m), 3) for p in (10, 20, 30, 50, 100)},
               net_bez_stopa_sred=round(st.fmean(x["net_bps"] for x in ok), 1), net_so_stopom_sred=round(st.fmean(x["net_so_stopom_bps"] for x in ok), 1),
               hudshie=sorted(ok, key=lambda x: -x["mae_pct"])[:5])
    f = HERE / "results" / time.strftime("short_hvost_mae_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(svod=out, sobytiya=rows), ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1)); print("файл:", f)
if __name__ == "__main__": main()
