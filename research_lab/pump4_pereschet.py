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
VYVOD = Path(os.environ.get("PUMP4_VYVOD") or time.strftime("research_lab/results/pump4_pereschet_%Y%m%dT%H%MZ.json", time.gmtime()))   # вердиктный файл 20261020 не перезаписывается
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


V2_FUNDING_S = 1792454400000          # 2026-10-20 00:00 UTC: фандинг для V2 наблюдается только у решений после этого момента


def funding_pered(sym, ts):
    """Последняя ставка фандинга Bybit до момента решения (наблюдение для PUMP4 V2, на V1 не влияет)."""
    u = f"https://api.bybit.com/v5/market/funding/history?category=linear&symbol={sym}&endTime={ts}&limit=1"
    try:
        r = urllib.request.Request(u, headers={"User-Agent": "pereschet/1.0"})
        with urllib.request.urlopen(r, timeout=20) as f:
            lst = ((json.loads(f.read().decode()).get("result") or {}).get("list") or [])
        return (float(lst[0]["fundingRate"]), int(lst[0]["fundingRateTimestamp"])) if lst else None
    except Exception:
        return None


def _py(o):
    """numpy-скаляры → обычные числа для JSON."""
    return o.item() if hasattr(o, "item") else str(o)


V2_START = 1792497600000               # 2026-10-20 12:00 UTC — prereg PREREG_PUMP4_V2_VYHOD: только новые решения
V2_TP2_R = 0.9


def simulate_v2(bars, i, side, sl0, tps, f1, mult, hold):
    """PUMP4 V2 (prereg PREREG_PUMP4_V2_VYHOD_2026_10_20): вход, стоп ×4, первая цель и её доля — как V1 (из сигнала, как в
    simulate); отличие одно — после первой цели стоп остатка переносится на вход (действует со СЛЕДУЮЩЕГО бара), вторая цель
    0.9R. Внутри бара стоп раньше целей (консервативно), как в simulate. Расходы — те же."""
    from research_machine import FEE_BPS_SIDE
    e = i + 1
    if e >= len(bars):
        return None
    entry = float(bars[e][1]); short = side == "short"
    sl = entry + (sl0 - entry) * mult
    risk = (sl - entry) if short else (entry - sl)
    if risk <= 0:
        return None
    lev = entry / risk; cost = lev * 2 * FEE_BPS_SIDE / 1e4
    tp1 = (list(tps) + [None])[0]
    tp2 = entry - V2_TP2_R * risk if short else entry + V2_TP2_R * risk
    stop, rem, gross, tp1_done, be_next = sl, 1.0, 0.0, False, False
    for j in range(e, min(e + hold, len(bars))):
        h, l = float(bars[j][2]), float(bars[j][3])
        if be_next:
            stop = entry; be_next = False
        if (h >= stop) if short else (l <= stop):
            gross += rem * ((entry - stop) if short else (stop - entry)) / risk
            return dict(R=gross - cost, bars=j - e, lev=lev)
        if tp1 and not tp1_done and ((l <= tp1) if short else (h >= tp1)):
            gross += f1 * ((entry - tp1) if short else (tp1 - entry)) / risk
            rem -= f1; tp1_done = True; be_next = True
        if rem > 1e-9 and ((l <= tp2) if short else (h >= tp2)):
            gross += rem * ((entry - tp2) if short else (tp2 - entry)) / risk
            return dict(R=gross - cost, bars=j - e, lev=lev)
    j = min(e + hold, len(bars)) - 1; px = float(bars[j][4])
    gross += rem * ((entry - px) if short else (px - entry)) / risk
    return dict(R=gross - cost, bars=j - e, lev=lev)


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
            if z["ts"] >= V2_START:                                    # парная V2 на тех же решениях (только новые)
                r2 = simulate_v2(b, i, s.side, s.sl, list(s.tps or []), (s.tp_fracs or [F1])[0], STOP_MULT, HOLD)
                if r2 is not None:
                    zap_r["v2"] = dict(R=round(r2["R"], 4), zaversheno=bool(zaversheno(b, i, r2)), barov=r2["bars"])
            if r is None or r.get("lev", 0) > MAX_LEV:
                zap_r["status"] = "NE_ISPOLNIMO"; rez.append(zap_r); continue
            if not zaversheno(b, i, r):
                if z["ts"] >= V2_FUNDING_S:
                    zap_r["v2_funding"] = funding_pered(sym, z["ts"])
                zap_r["status"] = "OTKRYTA"; rez.append(zap_r); continue
            e = b[i + 1][1]; risk = abs(e - (e + (s.sl - e) * STOP_MULT))
            rr = [abs(q - e) / risk for q in (s.tps or [])] if risk > 0 else []
            k1, k2 = (rr + [999.0, 999.0])[:2]
            c = [sim_geo(b, int(rng.choice(pool)), s.side == "short", 1.0 / r["lev"], k1, k2, (s.tp_fracs or [F1])[0], HOLD)
                 for _ in range(DRAWS)] if pool else []
            c = [x for x in c if x is not None]
            if z["ts"] >= V2_FUNDING_S:
                zap_r["v2_funding"] = funding_pered(sym, z["ts"])
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
                    t_edzh=float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))), monet_v_pluse=int(sum(np.mean(v) > 0 for v in ps.values())),
                    monet=len(ps))
    out = dict(prereg="PREREG_PUMP4_PLATO_2026_08_31 + дополнение 2", kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               statusy={k: sum(1 for x in rez if x["status"] == k) for k in sorted({x["status"] for x in rez})},
               vse=svod(rez), FORWARD=svod([x for x in rez if x["klass"] == "FORWARD"]),
               OOS_REPLAY=svod([x for x in rez if x["klass"] == "OOS_REPLAY"]), resheniya=rez)
    pary = [x for x in rez if x.get("status") == "ZAKRYTA" and (x.get("v2") or {}).get("zaversheno")]
    if pary:
        d = np.array([x["v2"]["R"] - x["R"] for x in pary])
        nd = {}
        for x in pary: nd.setdefault(x["ts"] // (7 * 86400000), [0.0, 0.0]); nd[x["ts"] // (7 * 86400000)][0] += x["v2"]["R"]; nd[x["ts"] // (7 * 86400000)][1] += x["R"]
        out["V2_pary"] = dict(prereg="PREREG_PUMP4_V2_VYHOD_2026_10_20", n=len(pary), sred_V1=float(np.mean([x["R"] for x in pary])),
                              sred_V2=float(np.mean([x["v2"]["R"] for x in pary])), raznica=float(d.mean()),
                              t=float(d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))) if len(d) > 2 and d.std(ddof=1) > 0 else None,
                              hudshaya_nedelya_V2_minus_V1=float(min(a - b for a, b in nd.values())),
                              etap="VERDIKT_50" if len(pary) >= 50 else "NAKOPLENIE")
    else:
        out["V2_pary"] = dict(n=0, etap="NAKOPLENIE")
    v = out["vse"]
    if v.get("n", 0) >= 50:
        ok = v["edzh"] > 0 and v["t_edzh"] > 2.0 and v["monet_v_pluse"] * 2 >= v["monet"]
        out["verdikt"] = "PODTVERZHDENA" if ok else ("OPROVERGNUTA" if v["edzh"] <= 0 else "NE_HVATILO_DANNYH")
    else:
        out["verdikt"] = f"NE_HVATILO_DANNYH (закрыто {v.get('n', 0)} из 50)"
    VYVOD.parent.mkdir(parents=True, exist_ok=True); VYVOD.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=_py))
    print(json.dumps({k: out[k] for k in ("statusy", "vse", "FORWARD", "OOS_REPLAY", "verdikt", "V2_pary")}, ensure_ascii=False, indent=1, default=_py))


if __name__ == "__main__":
    main()
