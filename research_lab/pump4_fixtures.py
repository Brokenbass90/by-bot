"""Неизменяемые decision fixtures PUMP4 V1 для проверки signal parity у Codex (20.10.2026).
Источник решений: results/pump4_pereschet_20261020.json (вердикт PASS). Свечи: data/oos_bybit_h1_20261020 (Bybit linear 1h, закрытые).
Для каждой сделки: состояние стратегии строится непрерывным прогоном по закрытым барам с ts − 1000 ч (как в пересчёте),
ровно один вызов maybe_signal на закрытый бар. Выход: results/pump4_fixtures_v1_20261020.json."""
import json, os, sys, hashlib
sys.path.insert(0, "."); sys.path.insert(0, "research_lab")
from research_machine import Store, simulate
from strategies.pump_fade_v4r import PumpFadeV4RStrategy as K
H = 3600000
o = json.load(open("research_lab/results/pump4_pereschet_20261020.json"))
z = [x for x in o["resheniya"] if x["status"] == "ZAKRYTA"]
fx = []
for x in sorted(z, key=lambda q: (q["sym"], q["ts"])):
    p = f"research_lab/data/oos_bybit_h1_20261020/{x['sym']}.json"
    b = json.load(open(p)) if os.path.exists(p) else []
    b = [r for r in b if r[0] >= x["ts"] - 1000 * H]
    idx = next((i for i, r in enumerate(b) if r[0] == x["ts"]), None)
    if idx is None:
        fx.append(dict(sym=x["sym"], ts=x["ts"], status="NET_SVECHEY_V_KESHE")); continue
    s = K(); st = Store(x["sym"]); g = None
    for i in range(200, idx + 1):
        st.rows = b[:i + 1]; gg = s.maybe_signal(x["sym"], *b[i])
        if i == idx: g = gg
    if g is None:
        fx.append(dict(sym=x["sym"], ts=x["ts"], status="NE_VOSPROIZVEDENO_S_OKNA_1000CH")); continue
    e = b[idx + 1][1]; stop4 = e + (g.sl - e) * 4.0; risk = abs(stop4 - e)
    r = simulate(b, idx, g.side, g.sl, list(g.tps), g.tp_fracs[0], 4.0, 168)
    okno = b[:idx + 1]
    fx.append(dict(sym=x["sym"], signal_bar_open_ms=x["ts"], side=g.side, reason=g.reason,
                   signal=dict(entry=g.entry, sl=g.sl, tps=list(g.tps), tp_fracs=list(g.tp_fracs)),
                   ispolnenie_V1=dict(vhod_ref="open бара ts+1h", vhod=e, stop_x4=stop4, tp1=g.tps[0], tp2=g.tps[1],
                                      dolya_tp1=g.tp_fracs[0], ostatok_na_tp2=round(1 - g.tp_fracs[0], 6), uderzhanie_barov=168,
                                      R_pri_6bps=round(r["R"], 6), R_v_verdikte=x["R"]),
                   bary_sha256=hashlib.sha256(json.dumps(okno).encode()).hexdigest(), barov_v_okne=len(okno),
                   status="OK" if abs(r["R"] - x["R"]) < 1e-3 else "R_RASHOZHDENIE"))
out = dict(kod={f: hashlib.sha256(open(f, "rb").read()).hexdigest() for f in
                ("strategies/pump_fade_v4r.py", "strategies/signals.py", "research_lab/research_machine.py",
                 "research_lab/random_control.py", "research_lab/pump4_pereschet.py", "research_lab/ten_pump4.py", "research_lab/pump4_fixtures.py")},
           fixtures=fx, itogo={k: sum(1 for f in fx if f["status"] == k) for k in sorted({f["status"] for f in fx})})
json.dump(out, open("research_lab/results/pump4_fixtures_v1_20261020.json", "w"), ensure_ascii=False, indent=1)
print(out["itogo"])
