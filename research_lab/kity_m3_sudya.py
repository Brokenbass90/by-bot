#!/usr/bin/env python3
"""kity_m3_sudya.py — судья PREREG_KITY_M3_POTOK_2026_10_04.md. Закоммичен ДО загрузки данных M3.
ОДИН прогон: data/binance_kity/m3_rezultat.json + M3_KVITANCIYA.json (sha256 данных); повтор запрещён.

    python3 research_lab/kity_m3_sudya.py
"""
import datetime as dt, hashlib, json, sys
import numpy as np
import discovery_paket1 as P
import kity_sudya as K

B = K.B
REZ = B / "m3_rezultat.json"
PRIMARY, REPLIK = K.PRIMARY, K.REPLIK


def main():
    if REZ.exists():
        sys.exit("результат M3 уже есть — прогон один")
    if not (B / "taker_gotovo.json").exists():
        sys.exit("нет taker_gotovo.json — загрузка M3 не закончена")
    M = K.zagruzit()
    for s, x in M.items():
        f = B / "taker" / f"{s}.json"
        tk = {}
        if f.exists():
            for t, qv, tq in json.loads(f.read_text()):
                if qv > 0:
                    tk[K.den(t).isoformat()] = tq / qv
        x["taker"] = tk
    def ts(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)

    def nedelya(d, priznak, znak):
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        rows = []
        for _, s in oi:
            x = M[s]; i = int(np.searchsorted(x["ts"], ts(d)))
            if i >= len(x["ts"]) or x["ts"][i] != ts(d) or i < 60:
                continue
            v = priznak(x, i, vch)
            if v is not None and np.isfinite(v):
                rows.append((v, s, i))
        if len(rows) < 30:
            return None
        rows.sort(); k = len(rows) // 10
        leg = [K.sdelka(M[s], i, 7, -znak) for _, s, i in rows[:k]] + [K.sdelka(M[s], i, 7, +znak) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        return float(np.mean(leg)) if leg else None

    def okno(a, b, priznak, znak):
        return [(ts(d), r, None) for d in K.SETKA if a <= d <= b for r in [nedelya(d, priznak, znak)] if r is not None]

    m3 = lambda x, i, vch: x["taker"].get(vch)
    tolpa = lambda x, i, vch: x["met"][vch][0]
    impuls = lambda x, i, vch: (x["c"][i - 1] / x["c"][i - 2] - 1) if x["ts"][i] - x["ts"][i - 1] == P.DEN else None

    # ворота данных ДО PnL: ≥ 90% недель PRIMARY с ≥ 30 монетами с признаком M3
    def pokryto(d):
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        return sum(1 for _, s in oi if vch in M[s]["taker"]) >= 30
    ned = [d for d in K.SETKA if PRIMARY[0] <= d <= PRIMARY[1]]
    dolya = sum(map(pokryto, ned)) / len(ned)
    print(f"ворота данных M3: покрыто {dolya:.0%} недель PRIMARY")
    if dolya < 0.9:
        sys.exit("BLOCKED_DATA: покрытие < 90% — чинить данные, судья не запускался")
    rez = dict(prereg="PREREG_KITY_M3_POTOK_2026_10_04.md", kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    sp = okno(*PRIMARY, m3, +1); it = P.itog(sp, s_kontrolem=False, lag=1)
    if it["verdikt"] == "SURVIVED" and it.get("dney", 0) < 52:
        it["verdikt"] = "KILLED"; it["prichina"] = f"недель {it.get('dney')} < 52"
    rez["PRIMARY"] = it
    sr = okno(*REPLIK, m3, +1); ir = P.itog(sr, s_kontrolem=False, lag=1)
    ir["status"] = ("BLOCKED_DATA" if ir.get("n", 0) < 20 else ("CROSS_PERIOD_PASS" if ir["verdikt"] == "SURVIVED" else
                    ("SAME_SIGN" if ir.get("edge_bps", 0) > 0 else "OPPOSITE")))
    rez["REPLICATION"] = ir
    vse = dict((t, r) for t, r, _ in sp + sr)
    def korr(drugoe):
        d = dict((t, r) for t, r, _ in drugoe); para = [(vse[t], d[t]) for t in vse if t in d]
        return (round(float(np.corrcoef(*zip(*para))[0, 1]), 2) if len(para) > 10 else None), len(para)
    kt, nt = korr(okno(*PRIMARY, tolpa, -1) + okno(*REPLIK, tolpa, -1))
    ki, ni = korr(okno(*PRIMARY, impuls, +1) + okno(*REPLIK, impuls, +1))
    rez["nezavisimost"] = dict(korr_s_TOLPA=kt, nedel_t=nt, korr_s_impulsom_1d=ki, nedel_i=ni,
                               ok=kt is not None and abs(kt) < 0.5 and ki is not None and abs(ki) < 0.7)
    if it["verdikt"] != "SURVIVED":
        st = "KITY_FAMILY_KILLED (бюджет спасения исчерпан)"
    elif ir["status"] == "OPPOSITE":
        st = "PRIMARY_PASS_BUT_REPLICATION_OPPOSITE"
    elif not rez["nezavisimost"]["ok"]:
        st = "PRIMARY_PASS_BUT_NOT_INDEPENDENT"
    else:
        st = "HISTORICAL_REPLICATION_PASS → READY_FOR_BUILD (пакет Codex)" + (" (репликация BLOCKED_DATA)" if ir["status"] == "BLOCKED_DATA" else "")
    rez["status"] = st
    REZ.write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    h = hashlib.sha256()
    for f in sorted((B / "taker").glob("*.json")):
        h.update(f.read_bytes())
    (B / "M3_KVITANCIYA.json").write_text(json.dumps(dict(taker_sha256=h.hexdigest(),
        manifest_kity_sha256=hashlib.sha256((B / "manifest.json").read_bytes()).hexdigest(),
        rezultat_sha256=hashlib.sha256(REZ.read_bytes()).hexdigest(), rezultat=rez), ensure_ascii=False, indent=1))
    for k in ("PRIMARY", "REPLICATION", "nezavisimost", "status"):
        print(k, ":", rez[k])


if __name__ == "__main__":
    main()
