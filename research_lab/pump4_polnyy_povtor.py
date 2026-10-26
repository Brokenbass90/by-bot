#!/usr/bin/env python3
"""pump4_polnyy_povtor.py — экономика PUMP4 V1 по НЕПРЕРЫВНОМУ повтору всех 137 монет вселенной (26.10.2026, Claude).
После находки Codex (тень пропускала свечи → нарушался cooldown 24 → 51 лишний сигнал) прежние оценки по журналу тени невалидны.
Здесь журнал тени не используется вообще: стратегия V1 (pump_fade_v4r, frozen) получает каждую закрытую часовую свечу подряд с прогревом
≥ 1000 ч; учитываются ВСЕ её сигналы с 2026-09-01; сделка — simulate V1 (стоп ×4, цели сигнала, доля 0.55, 168 ч, тейкер 6 bps/сторона);
контроль — sim_geo, 10 случайных входов той же монеты. Фандинг и проскальзывание НЕ учтены (пишутся отдельно Codex).
Ширина (для гипотезы PUMP4_REZHIM_SHIRINA) = число сигналов всех монет этого же повтора в [ts − 24 ч; ts).
    .venv/bin/python3 research_lab/pump4_polnyy_povtor.py → research_lab/results/pump4_polnyy_povtor_<время>.json"""
import collections, importlib, json, math, os, sys, time
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import pump4_pereschet as P
START = 1788220800000                    # 2026-09-01 00:00 UTC — первые учитываемые сигналы
PROGREV_CH = 1200


def main():
    syms = json.load(open(HERE / "data" / "pump4_v1_universe_20261020.json"))["symbols"]
    os.environ.update({f"{P.PFX}_SYMBOL_ALLOWLIST": ",".join(syms), f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS)
    now = int(time.time() * 1000); konec = (now // P.CHAS) * P.CHAS; rng = np.random.default_rng(P.SEED)
    sdelki, propuski, dyry = [], [], {}
    for n, sym in enumerate(syms, 1):
        try: b = [x for x in P.svechi_okno(sym, START - PROGREV_CH * P.CHAS, konec) if x[0] + P.CHAS <= now]
        except Exception as e: propuski.append(sym); continue
        d = sum(1 for i in range(1, len(b)) if b[i][0] - b[i - 1][0] != P.CHAS)
        if d: dyry[sym] = d
        strat = K(); st = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else st
        pool = list(range(200, max(200, len(b) - P.HOLD - 2)))
        for i in range(len(b) - 1):
            st.rows = b[: i + 1]; r_ = b[i]
            try: s = strat.maybe_signal(perv, *r_)
            except Exception: s = None
            if s is None or getattr(s, "side", None) not in ("long", "short") or r_[0] < START or i < 200: continue
            r = P.simulate(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [P.F1])[0], P.STOP_MULT, P.HOLD)
            z = dict(sym=sym, ts=r_[0], side=s.side)
            if r is None or r.get("lev", 0) > P.MAX_LEV: z["status"] = "NE_ISPOLNIMO"
            elif not P.zaversheno(b, i, r): z["status"] = "OTKRYTA"
            else:
                e = b[i + 1][1]; risk = abs(e - (e + (s.sl - e) * P.STOP_MULT))
                rr = [abs(q - e) / risk for q in (s.tps or [])] if risk > 0 else []
                k1, k2 = (rr + [999.0, 999.0])[:2]
                c = [P.sim_geo(b, int(rng.choice(pool)), s.side == "short", 1.0 / r["lev"], k1, k2, (s.tp_fracs or [P.F1])[0], P.HOLD)
                     for _ in range(P.DRAWS)] if pool else []
                c = [x for x in c if x is not None]
                z.update(status="ZAKRYTA", R=round(r["R"], 4), ctrl=round(float(np.mean(c)), 4) if c else None, barov=r["bars"],
                         risk_pct=round(risk / e * 100, 3), komissiya_R=round(r["lev"] * 2 * 6 / 1e4, 4))
            sdelki.append(z)
        print(f"{n}/{len(syms)} {sym}: сигналов {sum(1 for x in sdelki if x['sym'] == sym)}", flush=True)
    ts_all = sorted(x["ts"] for x in sdelki)
    for x in sdelki:
        x["shirina"] = sum(1 for t in ts_all if x["ts"] - 24 * P.CHAS <= t < x["ts"])
    z = [x for x in sdelki if x["status"] == "ZAKRYTA" and x.get("ctrl") is not None]
    def svod(g):
        if len(g) < 3: return dict(n=len(g))
        R = np.array([x["R"] for x in g]); d = R - np.array([x["ctrl"] for x in g])
        dni = collections.defaultdict(list)
        for x, v in zip(g, d): dni[x["ts"] // 86400000].append(v)
        a = np.array([np.mean(v) for v in dni.values()])
        return dict(n=len(g), sred_R=round(float(R.mean()), 4), itog_R=round(float(R.sum()), 2), ubytochnyh=int((R < 0).sum()),
                    hudshiy_R=round(float(R.min()), 3), kontrol=round(float(np.mean([x["ctrl"] for x in g])), 4), prevyshenie=round(float(d.mean()), 4),
                    t_prev_po_dnyam=round(float(a.mean() / (a.std(ddof=1) / math.sqrt(len(a)))), 2) if len(a) > 2 else None, dney=len(a),
                    komissiya_R_sred=round(float(np.mean([x["komissiya_R"] for x in g])), 4), storony=dict(collections.Counter(x["side"] for x in g)))
    out = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), monet=len(syms), propuski=propuski, dyry_v_svechah=dyry,
               statusy=dict(collections.Counter(x["status"] for x in sdelki)), vse=svod(z),
               po_shirine={k: svod([x for x in z if lo <= x["shirina"] <= hi]) for k, (lo, hi) in
                           {"0": (0, 0), "1-2": (1, 2), "3-5": (3, 5), "6+": (6, 10 ** 6)}.items()},
               po_mesyacam={m: svod([x for x in z if time.strftime("%Y-%m", time.gmtime(x["ts"] / 1000)) == m]) for m in
                            sorted({time.strftime("%Y-%m", time.gmtime(x["ts"] / 1000)) for x in z})})
    f = Path(time.strftime("research_lab/results/pump4_polnyy_povtor_%Y%m%dT%H%MZ.json", time.gmtime()))
    f.write_text(json.dumps(dict(svod=out, sdelki=sdelki), ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1)); print("файл:", f)


if __name__ == "__main__":
    main()
