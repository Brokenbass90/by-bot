#!/usr/bin/env python3
"""spot_potok_sudya.py — судья PnL SPOT_POTOK (PREREG_SPOT_POTOK_TEZIS_2026_10_12.md + PREREG_SPOT_POTOK_PNL).
Скелет дословно как kity_m3_sudya.py (сетка 7 дней, PIT топ-50 по OI d−1, дециль, 12 bps, фандинг Binance, t Ньюи–Уэста лаг 1),
меняется только признак: тот, что выбрал экран (SPOT_IZMERENIYA.json, без доходностей). ОДИН прогон.

    python3 research_lab/spot_potok_sudya.py
"""
import datetime as dt, hashlib, json, sys
import numpy as np
import discovery_paket1 as P
import kity_sudya as K

B = K.B; REZ = B / "spot_rezultat.json"; PRIMARY, REPLIK = K.PRIMARY, K.REPLIK


def doli(papka):
    r = {}
    for f in (B / papka).glob("*.json"):
        r[f.stem] = {K.den(t).isoformat(): tq / qv for t, qv, tq in json.loads(f.read_text()) if qv > 0}
    return r


def main():
    if REZ.exists(): sys.exit("результат SPOT_POTOK уже есть — прогон один")
    izm = json.loads((B / "SPOT_IZMERENIYA.json").read_text()); resh = izm["reshenie"]
    if not resh.startswith("VYBRAN_"): sys.exit(f"экран: {resh} — PnL не запускается")
    M = K.zagruzit(); perp = doli("taker"); spot = doli("spot_taker")
    def ts(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)

    def nedelya(d, priznak, znak):
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        rows = []
        for _, s in oi:
            x = M[s]; i = int(np.searchsorted(x["ts"], ts(d)))
            if i >= len(x["ts"]) or x["ts"][i] != ts(d) or i < 60: continue
            v = priznak(s, x, i, vch)
            if v is not None and np.isfinite(v): rows.append((v, s, i))
        if len(rows) < 30: return None
        rows.sort(); k = len(rows) // 10
        leg = [K.sdelka(M[s], i, 7, -znak) for _, s, i in rows[:k]] + [K.sdelka(M[s], i, 7, +znak) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        return float(np.mean(leg)) if leg else None

    def okno(a, b, priznak, znak):
        return [(ts(d), r, None) for d in K.SETKA if a <= d <= b for r in [nedelya(d, priznak, znak)] if r is not None]

    def f_spot(s, x, i, vch): return spot.get(s, {}).get(vch)
    def f_razn(s, x, i, vch):
        a, b = spot.get(s, {}).get(vch), perp.get(s, {}).get(vch)
        return None if a is None or b is None else a - b
    priznak = f_spot if resh == "VYBRAN_A_spot" else f_razn
    m3 = lambda s, x, i, vch: perp.get(s, {}).get(vch)
    impuls = lambda s, x, i, vch: (x["c"][i - 1] / x["c"][i - 2] - 1) if x["ts"][i] - x["ts"][i - 1] == P.DEN else None

    rez = dict(prereg="PREREG_SPOT_POTOK_PNL_2026_10_12.md", priznak=resh, kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    sp = okno(*PRIMARY, priznak, +1); it = P.itog(sp, s_kontrolem=False, lag=1)
    if it["verdikt"] == "SURVIVED" and it.get("dney", 0) < 52:
        it["verdikt"] = "KILLED"; it["prichina"] = f"недель {it.get('dney')} < 52"
    rez["PRIMARY"] = it
    sr = okno(*REPLIK, priznak, +1); ir = P.itog(sr, s_kontrolem=False, lag=1)
    ir["status"] = ("BLOCKED_DATA" if ir.get("n", 0) < 20 else ("CROSS_PERIOD_PASS" if ir["verdikt"] == "SURVIVED" else
                    ("SAME_SIGN" if ir.get("edge_bps", 0) > 0 else "OPPOSITE")))
    rez["REPLICATION"] = ir
    vse = dict((t, r) for t, r, _ in sp + sr)
    def korr(drugoe):
        d = dict((t, r) for t, r, _ in drugoe); para = [(vse[t], d[t]) for t in vse if t in d]
        return (round(float(np.corrcoef(*zip(*para))[0, 1]), 2) if len(para) > 10 else None), len(para)
    km, nm = korr(okno(*PRIMARY, m3, +1) + okno(*REPLIK, m3, +1))
    ki, ni = korr(okno(*PRIMARY, impuls, +1) + okno(*REPLIK, impuls, +1))
    rez["nezavisimost"] = dict(korr_s_KITY_M3=km, nedel_m=nm, korr_s_impulsom_1d=ki, nedel_i=ni,
                               ok=km is not None and abs(km) < 0.5 and ki is not None and abs(ki) < 0.7)
    if it["verdikt"] != "SURVIVED": st = "PRIMARY_FAIL (постмортем; G6: не более одного претендента)"
    elif ir["status"] == "OPPOSITE": st = "PRIMARY_PASS_BUT_REPLICATION_OPPOSITE"
    elif not rez["nezavisimost"]["ok"]: st = "PRIMARY_PASS_BUT_NOT_INDEPENDENT"
    else: st = "HISTORICAL_REPLICATION_PASS → READY_FOR_BUILD (пакет Codex)" + (" (репликация BLOCKED_DATA)" if ir["status"] == "BLOCKED_DATA" else "")
    rez["status"] = st
    REZ.write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    h = hashlib.sha256()
    for f in sorted((B / "spot_taker").glob("*.json")): h.update(f.read_bytes())
    (B / "SPOT_KVITANCIYA.json").write_text(json.dumps(dict(spot_taker_sha256=h.hexdigest(),
        rezultat_sha256=hashlib.sha256(REZ.read_bytes()).hexdigest(), rezultat=rez), ensure_ascii=False, indent=1))
    for k in ("priznak", "PRIMARY", "REPLICATION", "nezavisimost", "status"): print(k, ":", rez[k])


if __name__ == "__main__":
    main()
