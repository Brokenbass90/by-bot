#!/usr/bin/env python3
"""pump4_zaderzhka.py — сколько стоит задержка входа PUMP4 (25.10.2026, Claude). Замер, не изменение стратегии.

Вопрос Codex-гейта «публикация ≤ 60 с после закрытия часа»: насколько ухудшается вход, если ордер уходит через 1/2/3/5/10 минут.
Для каждого решения тени (data/ten_pump4.jsonl) стратегия PUMP4 V1 прогоняется по часовым барам Bybit (как в pump4_pereschet),
берутся вход e = open следующего часа и стоп V1 (×4), риск = |e − стоп|. Затем по минутным свечам Bybit — цена открытия минуты
1, 2, 3, 5, 10 после начала часа входа. Стоимость задержки в R = (цена_с_задержкой − e)/риск со знаком против сделки
(для шорта дороже — когда цена ниже). Ордеров и ключей нет, только публичные свечи.
    .venv/bin/python3 research_lab/pump4_zaderzhka.py        → research_lab/results/pump4_zaderzhka_<время>.json"""
import importlib, json, os, sys, time, urllib.request
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import pump4_pereschet as P                                       # chdir в корень, Store, svechi_okno, константы
MIN = 60_000; ZADERZHKI = (1, 2, 3, 5, 10)


def minutki(sym, start_ms):
    u = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=1&start={start_ms}&end={start_ms + 12 * MIN}&limit=20"
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "zaderzhka/1.0"}), timeout=25) as f:
        lst = (json.loads(f.read().decode()).get("result") or {}).get("list") or []
    return {int(x[0]): float(x[1]) for x in lst}


def main():
    zap = [json.loads(s) for s in P.ZHURNAL.open(encoding="utf-8") if s.strip()]
    now = int(time.time() * 1000); konec = (now // P.CHAS) * P.CHAS
    syms = sorted({z["sym"] for z in zap})
    os.environ.update({f"{P.PFX}_SYMBOL_ALLOWLIST": ",".join(syms), f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS)
    po = {}
    for z in zap: po.setdefault(z["sym"], []).append(z)
    rez = []
    for sym, zz in po.items():
        try:
            b = [x for x in P.svechi_okno(sym, min(z["ts"] for z in zz) - 1000 * P.CHAS, konec) if x[0] + P.CHAS <= now]
        except Exception as e:
            print(sym, "нет баров", e); continue
        nuzhno = {z["ts"] for z in zz}; strat = K(); st = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else st
        for i in range(200, len(b) - 1):
            st.rows = b[: i + 1]; r_ = b[i]
            if r_[0] not in nuzhno: 
                try: strat.maybe_signal(perv, *r_)
                except Exception: pass
                continue
            try: s = strat.maybe_signal(perv, *r_)
            except Exception: continue
            z = next(z for z in zz if z["ts"] == r_[0])
            if s is None or s.side != z["side"]: continue
            e = b[i + 1][1]; stop = e + (s.sl - e) * P.STOP_MULT; risk = abs(e - stop)
            if risk <= 0: continue
            try: m = minutki(sym, b[i + 1][0]); time.sleep(0.12)
            except Exception: continue
            znak = 1 if s.side == "long" else -1
            zap_r = dict(sym=sym, ts=r_[0], side=s.side, risk_pct=round(risk / e * 100, 3))
            for d in ZADERZHKI:
                p = m.get(b[i + 1][0] + d * MIN)
                if p: zap_r[f"R_{d}m"] = round(znak * (p - e) / risk * -1, 5)
            rez.append(zap_r)
    out = dict(kogda_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), resheniy=len(rez),
               risk_pct_mediana=float(np.median([r["risk_pct"] for r in rez])) if rez else None)
    for d in ZADERZHKI:
        v = [r[f"R_{d}m"] for r in rez if f"R_{d}m" in r]
        if v: out[f"zaderzhka_{d}m"] = dict(n=len(v), sred_R=round(float(np.mean(v)), 4), mediana_R=round(float(np.median(v)), 4),
                                            hudshie_10proc_R=round(float(np.percentile(v, 10)), 4))
    out["primechanie"] = "R < 0 — задержка ухудшает вход (в единицах риска сделки); PUMP4 forward-преимущество ~+0.3R на сделку"
    f = Path(time.strftime("research_lab/results/pump4_zaderzhka_%Y%m%dT%H%MZ.json", time.gmtime()))
    f.write_text(json.dumps(dict(svod=out, resheniya=rez), ensure_ascii=False, indent=1)); print(json.dumps(out, ensure_ascii=False, indent=1)); print("файл:", f)


if __name__ == "__main__":
    main()
