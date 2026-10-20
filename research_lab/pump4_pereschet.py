#!/usr/bin/env python3
"""pump4_pereschet.py — пересчёт решений тени PUMP4 только по ЗАВЕРШЁННЫМ удержаниям
(PREREG_PUMP4_PLATO_2026_08_31, дополнение 2 от 20.10). Стратегия, стоп ×4, удержание 168, цели, вселенная — без изменений.

Дефект оценщика тени: `simulate` при недостатке баров закрывает сделку по последней цене — открытая позиция
считалась закрытой. Пересчёт: для каждого решения журнала берутся часовые бары Bybit от (ts − 1000 ч) до сейчас
(без текущего незакрытого бара), стратегия прогоняется заново, чтобы восстановить стоп и цели решения; сделка идёт в
замер, только если вышла по стопу/второй цели внутри данных или прошла все 168 баров. Иначе — OTKRYTA.
Контроль — тот же sim_geo, но случайные входы только там, где после входа есть ≥ 168 баров; seed фиксирован.
Решения, которых стратегия при повторе не даёт (NE_VOSPROIZVEDENO), публикуются числом, в замер не идут.

    .venv/bin/python3 research_lab/pump4_pereschet.py
Ордеров нет, ключей нет, только публичные свечи Bybit. Результат: research_lab/results/pump4_pereschet_20261020.json"""
from __future__ import annotations
import importlib, json, math, os, sys, time, urllib.request
from pathlib import Path
import numpy as np

KOREN = Path(__file__).resolve().parents[1]
os.chdir(KOREN); sys.path.insert(0, str(KOREN)); sys.path.insert(0, str(KOREN / "research_lab"))
from research_machine import Store, simulate, pervyy_argument          # noqa: E402
from random_control import sim_geo                                      # noqa: E402

ZHURNAL = Path("research_lab/data/ten_pump4.jsonl")
VYVOD = Path("research_lab/results/pump4_pereschet_20261020.json")
MODUL, KLASS, PFX = "pump_fade_v4r", "PumpFadeV4RStrategy", "PUMP4"
STOP_MULT, HOLD, F1, MAX_LEV, DRAWS, SEED = 4.0, 168, 0.55, 100.0, 10, 20261020
CHAS = 3_600_000


def svechi_okno(sym, start_ms, end_ms):
    out, s = [], start_ms
    while s < end_ms:
        u = (f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60"
             f"&start={s}&end={min(end_ms, s + 999 * CHAS)}&limit=1000")
        r = urllib.request.Request(u, headers={"User-Agent": "pereschet/1.0"})
        with urllib.request.urlopen(r, timeout=25) as f:
            lst = ((json.loads(f.read().decode()).get("result") or {}).get("list") or [])
        part = sorted([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])] for x in lst)
        if not part:
            break
        out.extend(p for p in part if not out or p[0] > out[-1][0])
        s = part[-1][0] + CHAS
        time.sleep(0.15)
    return out


def zaversheno(b, i, r):
    e = i + 1
    if e + HOLD <= len(b):
        return True
    return r["bars"] < len(b) - 1 - e          # вышла по стопу / второй цели внутри данных


def main():
    zap = [json.loads(s) for s in ZHURNAL.open(encoding="utf-8") if s.strip()]
    now = int(time.time() * 1000); konec = (now // CHAS) * CHAS          # последний час ещё не закрыт
    syms = sorted({z["sym"] for z in zap})
    os.environ.update({f"{PFX}_SYMBOL_ALLOWLIST": ",".join(syms), f"{PFX}_ALLOW_LONGS": "1", f"{PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{MODUL}"), KLASS)
    rng = np.random.default_rng(SEED)
    rez, po_sym = [], {}
    for z in zap:
        po_sym.setdefault(z["sym"], []).append(z)
    for sym, zz in po_sym.items():
        t0 = min(z["ts"] for z in zz) - 1000 * CHAS
        try:
            b = [x for x in svechi_okno(sym, t0, konec) if x[0] + CHAS <= now]
        except Exception as e:
            rez += [dict(sym=sym, ts=z["ts"], status="NET_DANNYH", oshibka=type(e).__name__) for z in zz]; continue
        idx = {x[0]: i for i, x in enumerate(b)}
        nuzhno = {z["ts"] for z in zz}
        strat = K(); st = Store(sym); pervyy = sym if pervyy_argument(K) == "symbol" else st
        signaly = {}
        for i in range(200, len(b) - 1):
            st.rows = b[: i + 1]; r_ = b[i]
            try:
                s = strat.maybe_signal(pervyy, r_[0], r_[1], r_[2], r_[3], r_[4], r_[5])
            except Exception:
                continue
            if s is not None and getattr(s, "side", None) in ("long", "short") and r_[0] in nuzhno:
                signaly[r_[0]] = (i, s)
        pool = list(range(200, max(200, len(b) - HOLD - 2)))
        for z in zz:
            zap_r = dict(sym=sym, ts=z["ts"], side=z["side"], R_teni=z.get("R"), zapisano=z["zapisano"],
                         klass="FORWARD" if z["zapisano"] - z["ts"] <= 3 * CHAS else "OOS_REPLAY")
            if z["ts"] not in signaly or signaly[z["ts"]][1].side != z["side"]:
                zap_r["status"] = "NE_VOSPROIZVEDENO"; rez.append(zap_r); continue
            i, s = signaly[z["ts"]]
            r = simulate(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [F1])[0], STOP_MULT, HOLD)
            if r is None or r.get("lev", 0) > MAX_LEV:
                zap_r["status"] = "NE_ISPOLNIMO"; rez.append(zap_r); continue
            if not zaversheno(b, i, r):
                zap_r["status"] = "OTKRYTA"; rez.append(zap_r); continue
            e = b[i + 1][1]; risk = abs(e - (e + (s.sl - e) * STOP_MULT))
            rr = [abs(q - e) / risk for q in (s.tps or [])] if risk > 0 else []
            k1, k2 = (rr + [999.0, 999.0])[:2]
            c = [sim_geo(b, int(rng.choice(pool)), s.side == "short", 1.0 / r["lev"], k1, k2, (s.tp_fracs or [F1])[0], HOLD)
                 for _ in range(DRAWS)] if pool else []
            c = [x for x in c if x is not None]
            zap_r.update(status="ZAKRYTA", R=round(r["R"], 4), ctrl=round(float(np.mean(c)), 4) if c else None, barov=r["bars"])
            rez.append(zap_r)

    def svod(g):
        g = [x for x in g if x["status"] == "ZAKRYTA" and x.get("ctrl") is not None]
        if len(g) < 3:
            return dict(n=len(g))
        R = np.array([x["R"] for x in g]); d = R - np.array([x["ctrl"] for x in g])
        ps = {}
        for x in g: ps.setdefault(x["sym"], []).append(x["R"])
        return dict(n=len(g), sred_R=float(R.mean()), itog_R=float(R.sum()), edzh=float(d.mean()),
                    t_edzh=float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))), monet_v_pluse=sum(np.mean(v) > 0 for v in ps.values()),
                    monet=len(ps))
    out = dict(prereg="PREREG_PUMP4_PLATO_2026_08_31 + дополнение 2", kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               statusy={k: sum(1 for x in rez if x["status"] == k) for k in sorted({x["status"] for x in rez})},
               vse=svod(rez), FORWARD=svod([x for x in rez if x["klass"] == "FORWARD"]),
               OOS_REPLAY=svod([x for x in rez if x["klass"] == "OOS_REPLAY"]), resheniya=rez)
    v = out["vse"]
    if v.get("n", 0) >= 50:
        ok = v["edzh"] > 0 and v["t_edzh"] > 2.0 and v["monet_v_pluse"] * 2 >= v["monet"]
        out["verdikt"] = "PODTVERZHDENA" if ok else ("OPROVERGNUTA" if v["edzh"] <= 0 else "NE_HVATILO_DANNYH")
    else:
        out["verdikt"] = f"NE_HVATILO_DANNYH (закрыто {v.get('n', 0)} из 50)"
    VYVOD.parent.mkdir(parents=True, exist_ok=True); VYVOD.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: out[k] for k in ("statusy", "vse", "FORWARD", "OOS_REPLAY", "verdikt")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
