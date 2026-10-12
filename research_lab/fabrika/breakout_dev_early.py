#!/usr/bin/env python3
"""Breakout DEV_EARLY_SIGNAL (PREREG_BREAKOUT_DEV_EARLY_2023_2024H1_2026_10_12.md, коммит bc442fe). Один прогон.
    python3 research_lab/fabrika/breakout_dev_early.py --zadacha SEG SYM     # одна монета × сегмент → часть
    python3 research_lab/fabrika/breakout_dev_early.py --itog                # сборка и вердикт по замороженному критерию
"""
import argparse, dataclasses, glob, hashlib, json, math, sys, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(LAB)); sys.path.insert(0, str(LAB / "fabrika"))
from strategies import event_expansion_retest_long_mtf_v1 as mtf
from bot.event_long_mtf_execution_bridge_v2 import bridge_mtf_research_plan_v2
from bot import event_long_execution_v1 as ex
from breakout_paritet_v2 import zagruzit, ms
from breakout_ten import rezhim_iz_btc

M5, H4, D = 300_000, 14_400_000, 86_400_000
SEG = {"2023H1": ("2023-01-01", "2023-07-01"), "2023H2": ("2023-07-01", "2024-01-01"), "2024H1": ("2024-01-01", "2024-07-01")}
DATA = LAB / "data" / "breakout_m5_v2"; OUT = LAB / "data" / "breakout_dev_early"
PROV_ID = "bybit_v5_kline_linear_m5_breakout_m5_v2"


def fanding(sym, t_vhod, t_konec):
    S = sorted((int(t), float(v)) for t, v in json.load(open(LAB / "data/pit_daily" / f"{sym}.json"))["funding"])
    ts = [t for t, _ in S]; do = [t for t in ts if t <= t_vhod]; posle = [t for t in ts if t >= t_konec]
    if len(do) < 11 or not posle: return None, "kalendar_ne_zakryt"
    inter = sorted(b - a for a, b in zip(do[-11:-1], do[-10:])); g0 = (inter[4] + inter[5]) / 2
    okno = [t for t in ts if do[-1] <= t <= posle[0]]
    if any(b - a > g0 for a, b in zip(okno, okno[1:])): return None, "dyra_kalendarya"
    fp = hashlib.sha256((LAB / "data/pit_daily" / f"{sym}.json").read_bytes()).hexdigest()
    return [ex.make_historical_funding_event_v1(symbol=sym, timestamp_ms=t, signed_rate=v, source_fingerprint=fp)
            for t, v in S if t_vhod < t <= t_konec], "ok"


def zadacha(seg, sym):
    s0, s1 = ms(SEG[seg][0]), ms(SEG[seg][1])
    pervyy = ms(json.load(open(DATA / "AUDIT.json"))["simvoly"][sym]["s"][:10]) + D     # первая ПОЛНАЯ дата
    src0 = max(s0 - 40 * D, pervyy); src0 = -(-src0 // H4) * H4
    otsechka = max(s0, src0 + 40 * D); kon = s1 + D
    rez = dict(seg=seg, sym=sym, src0=src0, otsechka=otsechka, sdelki=[], planov_vsego=0, planov_v_okne=0, bridge_fail=0)
    if otsechka >= s1:
        rez["propusk"] = "монеты нет в сегменте с прогревом"; return rez
    rows = zagruzit(sym, src0, kon)
    btc = zagruzit("BTCUSDT", src0, kon); rfn = rezhim_iz_btc(btc)
    fp = hashlib.sha256((DATA / "MANIFEST.json").read_bytes()).hexdigest()
    state, as_of = None, rows[-1][0] + M5
    while True:
        st = mtf.process_closed_m5_prefix(sym, rows, as_of_ms=as_of, provider_identity=PROV_ID, provider_fingerprint=fp, prior=state)
        state = st.state
        if st.plan is None: break
        p = st.plan; rez["planov_vsego"] += 1
        if otsechka <= p.valid_from_m5_open_ts_ms < s1:
            rez["planov_v_okne"] += 1
            try:
                fpl = bridge_mtf_research_plan_v2(p, state, raw_closed_m5=rows[:state.source_count]).frozen_plan
            except Exception as e:
                rez["bridge_fail"] += 1; rez.setdefault("bridge_oshibki", []).append(str(e)[:120])
            else:
                i0 = (fpl.valid_from_ts - rows[0][0]) // M5; okno = rows[i0:i0 + 97]; t1 = okno[-1][0] + M5
                ev, prich = fanding(sym, fpl.valid_from_ts, t1)
                z = dict(sym=sym, seg=seg, valid_from=fpl.valid_from_ts, rezhim=rfn(p.known_at_ms), fanding=prich)
                for sc in ("base", "stress"):
                    rc = ex.simulate_frozen_long_plan_v1(fpl, okno, as_of_ms=t1, funding_events=ev or (), scenario=sc)
                    z[sc] = dict(status=rc.status, exit=rc.exit_reason, net_r=rc.net_r)
                rez["sdelki"].append(z)
        state = mtf.acknowledge_plan(state, p.plan_id)
    return rez


def itog():
    chasti = [json.load(open(f)) for f in sorted(glob.glob(str(OUT / "chast_*.json")))]
    ozhid = len(SEG) * 13
    vse = [z for c in chasti for z in c["sdelki"]]
    fu = [z for z in vse if z["fanding"] != "ok"]
    zakr = [z for z in vse if z["fanding"] == "ok" and z["base"]["status"] == "filled_closed"]
    otk = [z for z in vse if z["fanding"] == "ok" and z["base"]["status"] != "filled_closed"]
    r = [z["base"]["net_r"] for z in zakr]; n = len(r)
    mean = sum(r) / n if n else None
    pf = (sum(x for x in r if x > 0) / -sum(x for x in r if x < 0)) if any(x < 0 for x in r) else None
    bf = sum(c["bridge_fail"] for c in chasti)
    if len(chasti) != ozhid: verdikt = "NEPOLNO"
    elif bf or (vse and len(fu) / len(vse) > 0.05): verdikt = "BLOCKED_DATA"
    elif n < 20: verdikt = "UNINFORMATIVE"
    elif mean < 0 and pf is not None and pf < 0.9: verdikt = "DEPRIORITIZE"
    else: verdikt = "CONTINUE_SHADOW"
    def opis(sub):
        x = [z["base"]["net_r"] for z in sub]
        return dict(n=len(x), sred=round(sum(x) / len(x), 4) if x else None)
    rez = dict(prereg="PREREG_BREAKOUT_DEV_EARLY_2023_2024H1_2026_10_12.md @ bc442fe", chastey=len(chasti), ozhidalos=ozhid,
               verdikt=verdikt, n=n, sred_net_r=None if mean is None else round(mean, 4), pf=None if pf is None else round(pf, 3),
               summa_r=round(sum(r), 3), funding_unknown=len(fu), otkazy_kontrakta=len(otk), bridge_fail=bf,
               opisatelno=dict(stress_sred=round(sum(z["stress"]["net_r"] for z in zakr) / n, 4) if n else None,
                               ne_bear=opis([z for z in zakr if z["rezhim"] in ("BULL_TREND", "NEUTRAL")]),
                               po_segmentam={s: opis([z for z in zakr if z["seg"] == s]) for s in SEG},
                               vyhody={e: sum(1 for z in zakr if z["base"]["exit"] == e) for e in sorted({z["base"]["exit"] or "" for z in zakr})},
                               po_monetam={s: opis([z for z in zakr if z["sym"] == s]) for s in sorted({z["sym"] for z in zakr})}))
    (OUT / "ITOG.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1)); print(json.dumps(rez, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--zadacha", nargs=2); ap.add_argument("--itog", action="store_true"); a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.itog: itog()
    else:
        f = OUT / f"chast_{a.zadacha[0]}_{a.zadacha[1]}.json"
        if f.exists(): print("уже есть", f.name); sys.exit(0)
        t = time.time(); rez = zadacha(*a.zadacha); rez["sek"] = round(time.time() - t, 1)
        f.write_text(json.dumps(rez, ensure_ascii=False)); print(a.zadacha, "планов в окне", rez["planov_v_okne"], "сек", rez["sek"])
