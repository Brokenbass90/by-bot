import sys, json, statistics as st
sys.path.insert(0, ".")
sys.argv = ["x", "--vyvod", "/dev/null"]
exec(open(sys.argv_path if False else "/sessions/" + __import__("os").environ["HOME"].split("/sessions/")[1] + "/mnt/bybit-bot-clean-v28/research_lab/alpaca_weekly_fill.py").read().split("def main():")[0])
from pathlib import Path
cfg = json.loads(Path("configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json").read_text())
clusters = [{str(x) for x in g} for g in cfg["clusters"]]
syrye, _ = chasovye(Path("data_cache/equities_daily_10y")); p = v_dnevnye(syrye)
sessii = [b.session_date for b in p["SPY"]]; okno = [s for s in sessii if NACH <= s <= KON]
posl = {}
for i, s in enumerate(sessii): posl[s.strftime("%Y-%m")] = i
rasp = [(sessii[i], sessii[i + 1]) for i in sorted(posl.values()) if i + 1 < len(sessii) and okno[0] <= sessii[i + 1] <= okno[-1]]
resh = _decisions("v38_successor_gated", p, rasp, clusters)
z = dvizhok_x(p, okno, resh, initial_capital=1000.0, target_gross_exposure=0.70, cost_bps_per_side=20.0,
              policy=LiveProtectionDailyProxy(initial_stop_anchor="entry_fill"), mest=4)
eq = z["daily_equity"]; S = lambda s: SECTOR_MAP.get(s, "unknown")
def mx(pos):
    c = {}
    for s in pos: c[S(s)] = c.get(S(s), 0) + 1
    return max(c.values()) if c else 0
dni2 = [r for r in eq if mx(r["positions"]) >= 2]
out = {"dney": len(eq), "dney_2_v_odnom_sektore": len(dni2), "dolya": round(len(dni2) / len(eq), 3)}
# сделки: делила ли позиция сектор с другой на входе
pos_by = {r["session"]: r["positions"] for r in eq}
par, solo = [], []
for t in z["trades"]:
    ps = pos_by.get(t["entry_session"], [])
    (par if sum(S(x) == S(t["symbol"]) for x in ps) >= 2 else solo).append(t)
f = lambda L: {"n": len(L), "sred_pct": round(st.mean(x["return_pct"] for x in L), 2), "pnl_usd": round(sum(x["pnl"] for x in L), 1)} if L else None
out["sdelki_s_parnym_sektorom"] = f(par); out["sdelki_odinochnye"] = f(solo)
# худшие 3 эпизода просадки и сектора
pk, pkd, ep = 0, None, []
e = [float(r["equity"]) for r in eq]
cur = None
for i, x in enumerate(e):
    if x >= pk:
        if cur and cur["dd"] > 0.05: ep.append(cur)
        pk, pkd, cur = x, i, None
    else:
        dd = 1 - x / pk
        if cur is None or dd > cur["dd"]: cur = {"pik": eq[pkd]["session"], "dno": eq[i]["session"], "dd": dd, "i0": pkd, "i1": i}
if cur and cur["dd"] > 0.05: ep.append(cur)
ep = sorted(ep, key=lambda c: -c["dd"])[:5]
for c in ep:
    tr = [t for t in z["trades"] if eq[c["i0"]]["session"] <= t["exit_session"] <= eq[c["i1"]]["session"]]
    sek = {}
    for t in tr: sek[S(t["symbol"])] = round(sek.get(S(t["symbol"]), 0) + t["pnl"], 1)
    c.update(dd=round(c["dd"] * 100, 1), ubytok_po_sektoram=dict(sorted(sek.items(), key=lambda x: x[1])[:4]),
             dney_2_v_sektore=sum(mx(eq[k]["positions"]) >= 2 for k in range(c["i0"], c["i1"] + 1)), dney=c["i1"] - c["i0"] + 1)
    del c["i0"], c["i1"]
out["hudshie_prosadki"] = ep
print(json.dumps(out, ensure_ascii=False, indent=1))
json.dump(out, open(sys.argv[0] if False else __import__("os").environ["HOME"] + "/mnt/bybit-bot-clean-v28/research_lab/results/alpaca_weekly_fill_20261026/sektora_monthly.json", "w"), ensure_ascii=False, indent=1)
