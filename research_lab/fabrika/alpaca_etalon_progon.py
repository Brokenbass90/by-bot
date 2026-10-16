#!/usr/bin/env python3
"""Исполняемый эталон Alpaca baseline для parity (только чтение, без брокера).

Источник кода: bybit-bot-recovery-20260824 @ 2e68b1f (ветка claude/alpaca-2026-09-07),
распакованный `git archive 2e68b1f | tar -x -C <koren>`.
Данные: runtime/equities_1h_parity_20260710 (59 файлов *_M5.csv, sha вселенной 36da070b…).

    python3 alpaca_etalon_progon.py --koren <archive> --dannye <equities_1h_parity_20260710> --vyhod <dir>

Сравнивать сделки по ядру (symbol, entry/exit session, fills/qty до 1e-9, reason):
полные float-хэши зависят от PYTHONHASHSEED на уровне последнего бита.
"""
import argparse, hashlib, json, sys
from datetime import date
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--koren", required=True); ap.add_argument("--dannye", required=True)
ap.add_argument("--vyhod", required=True); ap.add_argument("--anchor", default="entry_fill")
a = ap.parse_args()
K = Path(a.koren).resolve(); sys.path.insert(0, str(K))
import backtest.alpaca_honest_portfolio as hp
from research_lab.alpaca_dannye import chasovye, v_dnevnye
from scripts.run_alpaca_honest_diagnostic import _decisions

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

D = Path(a.dannye)
cfgp = K / "configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json"
cfg = json.loads(cfgp.read_text())
clusters = [{str(x) for x in g} for g in cfg["clusters"]]
syrye, _ = chasovye(D); p = v_dnevnye(syrye)
sessii = [b.session_date for b in p["SPY"]]
nach, kon = date(2024, 8, 1), date(2026, 7, 11)
okno = [s for s in sessii if nach <= s < kon]
posl = {}
for i, s in enumerate(sessii):
    posl[s.strftime("%Y-%m")] = i          # последняя завершённая сессия месяца
rasp = [(sessii[i], sessii[i + 1]) for i in sorted(posl.values())
        if i + 1 < len(sessii) and nach <= sessii[i + 1] < kon]   # (сигнал, вход = следующая сессия)
resh = _decisions("v38_successor_gated", p, rasp, clusters)
pol = hp.LiveProtectionDailyProxy(initial_stop_anchor=a.anchor)
z = hp.simulate_live_protection_daily_proxy(p, okno, resh, initial_capital=1000.0,
        target_gross_exposure=0.70, cost_bps_per_side=10.0, policy=pol)
tr = list(z["trades"])
core = [(t["symbol"], t["entry_session"], t["exit_session"], round(t["entry_fill"], 9),
         round(t["exit_fill"], 9), round(t["qty"], 9), t["reason"]) for t in tr]
h = hashlib.sha256()
for f in sorted(D.glob("*_M5.csv")):
    h.update(f.name.encode()); h.update(sha(f).encode())
fayly = ["backtest/alpaca_honest_portfolio.py", "backtest/alpaca_exact_parity_contract.py",
         "backtest/alpaca_bakeoff_v2_contract.py", "research_lab/alpaca_dannye.py",
         "research_lab/alpaca_tozhdestvo_v1.py", "scripts/run_alpaca_honest_diagnostic.py",
         "strategies/alpaca_dynamic_v4_event.py", "research_lab/alpaca_dvizhok_x_v1.py"]
ETALON = {
    "schema": "alpaca_etalon_parity_v1", "source_commit": "2e68b1f (claude/alpaca-2026-09-07)",
    "runner": "backtest.alpaca_honest_portfolio.simulate_live_protection_daily_proxy",
    "selection": "scripts.run_alpaca_honest_diagnostic._decisions('v38_successor_gated')",
    "code_sha256": {f: sha(K / f) for f in fayly if (K / f).exists()},
    "config_sha256": {str(cfgp.relative_to(K)): sha(cfgp)},
    "universe": {"faylov": len(list(D.glob("*_M5.csv"))), "sha256": h.hexdigest(),
                 "agregaciya": "research_lab.alpaca_dannye.v_dnevnye (часовые → дневные)"},
    "params": {"window": "2024-08-01..2026-07-11 excl", "initial_capital": 1000.0,
               "target_gross_exposure": 0.70, "cost_bps_per_side": 10.0, "slots": 4,
               "policy": {k: getattr(pol, k) for k in pol.__dataclass_fields__}},
    "summary": {k: v for k, v in z.items() if not isinstance(v, (list, dict))},
    "trades_core_sha16": hashlib.sha256(json.dumps(core).encode()).hexdigest()[:16],
}
V = Path(a.vyhod); V.mkdir(parents=True, exist_ok=True)
(V / "ETALON.json").write_text(json.dumps(ETALON, ensure_ascii=False, indent=1, default=str))
(V / "sdelki.json").write_text(json.dumps(tr, ensure_ascii=False, indent=0, default=str))
(V / "resheniya.json").write_text(json.dumps(z.get("decisions", []), ensure_ascii=False, default=str))
print(json.dumps({"summary": ETALON["summary"], "core": ETALON["trades_core_sha16"]}, default=str))
