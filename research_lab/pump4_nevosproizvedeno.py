#!/usr/bin/env python3
"""pump4_nevosproizvedeno.py — почему 85 из 158 решений тени PUMP4 не воспроизводятся повтором (26.10.2026, Claude). Только диагностика.
Для каждого решения NE_VOSPROIZVEDENO из последнего pump4_pereschet: стратегия V1 прогоняется заново с разным прогревом
(начало за 300 / 1000 / 2000 / 4000 ч до сигнала, всегда свежий объект стратегии) по тем же публичным часовым барам Bybit.
Классы: VOSPR_PRI_PROGREVE_X (сигнал появился при другом прогреве → причина в состоянии стратегии: cooldown/буферы),
SDVIG_CHASA (сигнал той же стороны в ±2 ч), DRUGAYA_STORONA, NET_BAROV (нет бара сигнала в данных), NE_VOSPR (нигде).
Для воспроизведённых при другом прогреве считается R V1 тем же simulate — видно, хуже ли «потерянные» решения.
    .venv/bin/python3 research_lab/pump4_nevosproizvedeno.py → research_lab/results/pump4_nevosproizvedeno_<время>.json"""
import collections, glob, importlib, json, os, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import pump4_pereschet as P

def main():
    f = sorted(glob.glob("research_lab/results/pump4_pereschet_2*.json"))[-1]
    nv = [x for x in json.load(open(f))["resheniya"] if x["status"] == "NE_VOSPROIZVEDENO"]
    zap = [json.loads(s) for s in P.ZHURNAL.open(encoding="utf-8") if s.strip()]
    os.environ.update({f"{P.PFX}_SYMBOL_ALLOWLIST": ",".join(sorted({z['sym'] for z in zap})), f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS)
    now = int(time.time() * 1000); konec = (now // P.CHAS) * P.CHAS; rez = []
    po = collections.defaultdict(list)
    for x in nv: po[x["sym"]].append(x)
    for sym, xs in po.items():
        try: b = [r for r in P.svechi_okno(sym, min(x["ts"] for x in xs) - 4100 * P.CHAS, konec) if r[0] + P.CHAS <= now]
        except Exception as e: rez += [dict(sym=sym, ts=x["ts"], klass="NET_DANNYH") for x in xs]; continue
        idx = {r[0]: i for i, r in enumerate(b)}
        for x in xs:
            out = dict(sym=sym, ts=x["ts"], side=x["side"], klass="NE_VOSPR", klass_okno={})
            if x["ts"] not in idx: out["klass"] = "NET_BAROV"; rez.append(out); continue
            i_sig = idx[x["ts"]]
            for W in (300, 1000, 2000, 4000):
                i0 = max(0, i_sig - W); strat = K(); st = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else st
                sig = {}
                for i in range(i0, min(len(b) - 1, i_sig + 3)):
                    st.rows = b[: i + 1]; r_ = b[i]
                    try: s = strat.maybe_signal(perv, *r_)
                    except Exception: s = None
                    if s is not None and getattr(s, "side", None) in ("long", "short") and abs(i - i_sig) <= 2: sig[i - i_sig] = s
                if 0 in sig and sig[0].side == x["side"]:
                    k = "VOSPR"; r = P.simulate(b, i_sig, sig[0].side, sig[0].sl, list(sig[0].tps or []), (sig[0].tp_fracs or [P.F1])[0], P.STOP_MULT, P.HOLD)
                    if r and P.zaversheno(b, i_sig, r): out.setdefault("R_pri_progreve", {})[W] = round(r["R"], 4)
                elif any(s.side == x["side"] for s in sig.values()): k = "SDVIG_CHASA"
                elif sig: k = "DRUGAYA_STORONA"
                else: k = "NET"
                out["klass_okno"][W] = k
            ks = out["klass_okno"]
            out["klass"] = next((f"VOSPR_PRI_PROGREVE_{W}" for W in (300, 1000, 2000, 4000) if ks.get(W) == "VOSPR"), None) or \
                           ("SDVIG_CHASA" if "SDVIG_CHASA" in ks.values() else "DRUGAYA_STORONA" if "DRUGAYA_STORONA" in ks.values() else "NE_VOSPR")
            rez.append(out); time.sleep(0.05)
    sv = dict(vsego=len(rez), klassy=dict(collections.Counter(r["klass"] for r in rez)))
    Rs = [v for r in rez for v in list((r.get("R_pri_progreve") or {}).values())[:1]]
    if Rs: sv["R_vosstanovlennyh"] = dict(n=len(Rs), sred=round(sum(Rs) / len(Rs), 4), ubytochnyh=sum(1 for v in Rs if v < 0))
    o = Path(time.strftime("research_lab/results/pump4_nevosproizvedeno_%Y%m%dT%H%MZ.json", time.gmtime()))
    o.write_text(json.dumps(dict(svod=sv, resheniya=rez), ensure_ascii=False, indent=1)); print(json.dumps(sv, ensure_ascii=False, indent=1)); print("файл:", o)

if __name__ == "__main__":
    main()
