#!/usr/bin/env python3
"""Экран без исходов для KASKAD_MAKER (поправка A1 п.2, п.6): совпадение реальных каскадов со старым ценовым прокси
и задержка доставки WS. Использует только бары ДО входа (b−1, b). Доходностей не считает."""
import json, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import gzip
import kaskad_maker as K

DROP, ZMIN, VW = 1.5, 2.5, 50


def bars_v(sym):
    rows = {}
    for f in sorted((K.M5 / sym).glob(f"{sym}_2026-0[6789].jsonl.gz")):
        for line in gzip.open(f, "rt"):
            if line.strip():
                r = json.loads(line); rows[int(r[0])] = (float(r[4]), float(r[5]))
    ts = sorted(rows); return ts, [rows[t] for t in ts]


def proxy(ts, cv):
    ev = {}
    for i in range(VW + 1, len(ts)):
        pc = cv[i - 1][0]
        if pc <= 0: continue
        ret = (cv[i][0] - pc) / pc * 100
        vols = [cv[j][1] for j in range(i - VW, i)]; m = sum(vols) / VW
        sd = (sum((x - m) ** 2 for x in vols) / VW) ** 0.5 or 1e-9
        if (cv[i][1] - m) / sd < ZMIN: continue
        if ret <= -DROP: ev[ts[i]] = +1      # падение → ликвидировали лонги → покупка
        elif ret >= DROP: ev[ts[i]] = -1
    return ev


def main():
    ev = K.events(); P = {}; nprox = 0
    for s in K.SYMS:
        ts, cv = bars_v(s); p = proxy(ts, cv)
        P[s] = p; nprox += sum(1 for t in p if K.T0 <= t < K.T1)
    hit = sum(1 for s, b, g in ev if any(P[s].get(b + d) == g for d in (-K.BAR, 0)))
    evset = {(s, b) for s, b, _ in ev}
    pok = sum(1 for s in K.SYMS for t, g in P[s].items() if K.T0 <= t < K.T1 and ((s, t) in evset or (s, t + K.BAR) in evset))
    lag = []
    for line in open(K.LIQ):
        try:
            d = json.loads(line)
            if K.T0 <= d["ts_ms"] < K.T1: lag.append(d["recv_ts_ms"] - d["ts_ms"])
        except Exception:
            pass
    lag.sort(); q = lambda p: lag[int(p * (len(lag) - 1))]
    dol = hit / max(1, len(ev))
    rez = dict(kaskadov=len(ev), proksi_v_okne=nprox, kaskadov_sovpalo_s_proksi=hit, dolya=round(dol, 3),
               proksi_pokryto_kaskadami=pok, recv_lag_ms=dict(p50=q(.5), p90=q(.9), p99=q(.99)),
               reshenie="KILL_BEZ_PNL" if dol >= 0.70 else "NEZAVISIM_ODIN_PNL")
    (K.OUT).mkdir(parents=True, exist_ok=True)
    (K.OUT / "EKRAN_PROKSI.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
