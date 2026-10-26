#!/usr/bin/env python3
"""Экономика PUMP4 V1 с фактическим фандингом по 84 сделкам эталона (26.10.2026, задание PM P0). V1 не меняется.
Офлайн-повтор той же стратегии на локальных H1 Bybit (data/bybit_fanding_h1_2025_2026 + data/bybit_pump4_okt_2026), тот же цикл подачи,
что в pump4_polnyy_povtor; копия research_machine.simulate, которая дополнительно возвращает бар TP1. Сверка: R и бары каждой сделки
должны совпасть с эталоном results/pump4_polnyy_povtor_20261026T0857Z.json (иначе сделка помечается и в итог не идёт).
Фандинг: выплата T учитывается, если вход < T ≤ начало бара выхода; доля позиции 1.0 до бара TP1 включительно (выплата в начале бара
случается раньше касания цели), затем 1 − f1. Шорт получает +ставку. В R: ставка × доля × плечо (плечо = цена входа / риск).
Проскальзывание — чувствительность 0 / 2 / 5 bps на сторону (× 2 × плечо).
    .venv/bin/python3 research_lab/pump4_fanding_ekonomika.py → results/pump4_fanding_ekonomika_<время>.json"""
import datetime as dt, hashlib, importlib, json, os, statistics as st, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import pump4_pereschet as P, pump4_polnyy_povtor as PP
from research_machine import FEE_BPS_SIDE
H = 3600_000
ETALON = HERE / "results/pump4_polnyy_povtor_20261026T0857Z.json"
D1, D2 = HERE / "data/bybit_fanding_h1_2025_2026", HERE / "data/bybit_pump4_okt_2026"


def sim_tp1(bars, i, side, sl0, tps, f1, mult, hold):
    """Копия research_machine.simulate (логика 1:1) + номер бара TP1."""
    e = i + 1
    if e >= len(bars): return None
    entry = float(bars[e][1]); short = side == "short"
    sl = entry + (sl0 - entry) * mult; risk = (sl - entry) if short else (entry - sl)
    if risk <= 0: return None
    lev = entry / risk; cost = lev * 2 * FEE_BPS_SIDE / 1e4
    tp1, tp2 = (list(tps) + [None, None])[:2]
    stop, rem, gross, tp1_done, j_tp1 = sl, 1.0, 0.0, False, None
    for j in range(e, min(e + hold, len(bars))):
        h, l = float(bars[j][2]), float(bars[j][3])
        if (h >= stop) if short else (l <= stop):
            gross += rem * ((entry - stop) if short else (stop - entry)) / risk
            return dict(R=gross - cost, bars=j - e, lev=lev, e=e, j=j, j_tp1=j_tp1, f1=f1, vyhod="stop")
        if tp1 and not tp1_done and ((l <= tp1) if short else (h >= tp1)):
            gross += f1 * ((entry - tp1) if short else (tp1 - entry)) / risk; rem -= f1; tp1_done = True; j_tp1 = j
        if tp2 and rem > 1e-9 and ((l <= tp2) if short else (h >= tp2)):
            gross += rem * ((entry - tp2) if short else (tp2 - entry)) / risk
            return dict(R=gross - cost, bars=j - e, lev=lev, e=e, j=j, j_tp1=j_tp1, f1=f1, vyhod="tp2")
    j = min(e + hold, len(bars)) - 1; px = float(bars[j][4])
    gross += rem * ((entry - px) if short else (px - entry)) / risk
    return dict(R=gross - cost, bars=j - e, lev=lev, e=e, j=j, j_tp1=j_tp1, f1=f1, vyhod="vremya", po_vremeni=True)


def zagruz(sym):
    h1, fu = {}, {}
    for p in (D1 / f"{sym}.json", D2 / f"{sym}.json"):
        if p.exists():
            z = json.loads(p.read_text())
            for r in z["h1"]: h1[r[0]] = r
            for t, r in z["funding"]: fu[int(t)] = float(r)
    return [h1[k] for k in sorted(h1)], fu


def main():
    et = json.loads(ETALON.read_text()); now = int(dt.datetime.fromisoformat(et["svod"]["kogda_utc"].replace("Z", "+00:00")).timestamp() * 1000)
    ref = {(x["sym"], x["ts"]): x for x in et["sdelki"] if x["status"] == "ZAKRYTA"}
    syms = sorted({k[0] for k in ref})
    univ = json.load(open(HERE / "data/pump4_v1_universe_20261020.json"))["symbols"]
    os.environ.update({f"{P.PFX}_SYMBOL_ALLOWLIST": ",".join(univ), f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS)
    konec = (now // H) * H; out, ne_sovp, net_dannyh = [], [], []
    for sym in syms:
        b0, fu = zagruz(sym)
        b = [x for x in b0 if PP.START - PP.PROGREV_CH * H <= x[0] < konec and x[0] + H <= now]
        if not b: net_dannyh.append(sym); continue
        do = max(x[0] for x in b)
        strat = K(); stor = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else stor
        for i in range(len(b) - 1):
            stor.rows = b[: i + 1]; r_ = b[i]
            try: s = strat.maybe_signal(perv, *r_)
            except Exception: s = None
            if s is None or getattr(s, "side", None) not in ("long", "short") or r_[0] < PP.START or i < 200: continue
            k = (sym, r_[0])
            if k not in ref: continue
            r = sim_tp1(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [P.F1])[0], P.STOP_MULT, P.HOLD)
            x = ref[k]
            if r is None or abs(r["R"] - x["R"]) > 1e-3 or r["bars"] != x["barov"]:
                ne_sovp.append(dict(sym=sym, ts=r_[0], R_et=x["R"], R=(r or {}).get("R"), bars_et=x["barov"], bars=(r or {}).get("bars"))); continue
            t_in, t_out = b[r["e"]][0], b[r["j"]][0]
            t_tp1 = b[r["j_tp1"]][0] if r["j_tp1"] is not None else None
            if t_out > do or (fu and max(fu) < t_out):
                net_dannyh.append(f"{sym}:{r_[0]}"); continue
            f_R, n_vypl = 0.0, 0
            for T, rate in fu.items():
                if t_in < T <= t_out:
                    dolya = 1.0 if (t_tp1 is None or T <= t_tp1) else 1.0 - r["f1"]
                    f_R += (1 if s.side == "short" else -1) * rate * dolya * r["lev"]; n_vypl += 1
            out.append(dict(sym=sym, ts=r_[0], mesyac=time.strftime("%Y-%m", time.gmtime(r_[0] / 1000)), R_posle_komissii=round(r["R"], 4),
                            fanding_R=round(f_R, 4), vyplat=n_vypl, tp1=t_tp1 is not None, vyhod=r["vyhod"], plecho=round(r["lev"], 2),
                            slip_R_per_bps=round(2 * r["lev"] / 1e4, 5)))
    def svod(g, slip):
        if not g: return dict(n=0)
        R = [x["R_posle_komissii"] + x["fanding_R"] - slip * x["slip_R_per_bps"] for x in g]
        return dict(n=len(g), sred_R=round(st.mean(R), 4), itog_R=round(sum(R), 2), ubytochnyh=sum(v < 0 for v in R),
                    hudshiy=round(min(R), 3), med=round(st.median(R), 4), fanding_sred_R=round(st.mean(x["fanding_R"] for x in g), 4))
    rez = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), etalon=ETALON.name,
               etalon_sha256=hashlib.sha256(ETALON.read_bytes()).hexdigest(), kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               sdelok_etalona=len(ref), sverka_ok=len(out), ne_sovpalo=ne_sovp, net_dannyh=net_dannyh,
               do_fandinga=svod([dict(x, fanding_R=0.0) for x in out], 0),
               po_proskalz={f"{sl}bps": dict(vse=svod(out, sl), **{m: svod([x for x in out if x["mesyac"] == m], sl) for m in sorted({x["mesyac"] for x in out})})
                            for sl in (0, 2, 5)},
               dolya_tp1=round(sum(x["tp1"] for x in out) / max(1, len(out)), 3), vyhody={v: sum(x["vyhod"] == v for x in out) for v in ("stop", "tp2", "vremya")})
    f = HERE / time.strftime("results/pump4_fanding_ekonomika_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(svod=rez, sdelki=out), ensure_ascii=False, indent=1))
    print(json.dumps(rez, ensure_ascii=False, indent=1)[:4000]); print("файл:", f)


if __name__ == "__main__":
    main()
