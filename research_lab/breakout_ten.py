#!/usr/bin/env python3
"""breakout_ten.py — проспективная тень P1 Breakout/Retest (event_expansion_retest_long_mtf_v1 as is) на Bybit linear OI top-50.
Только публичные данные Bybit, без ключей и заявок. Prereg: research_lab/PREREG_BREAKOUT_TEN_TOP50_2026_10_12.md.
Цепочка (вся заморожена до этой тени, паритет PASS — data/breakout_m5_v2/PARITET_ITOG.json):
  закрытые M5 → process_closed_m5_prefix (state/outbox, рестарт через state_to_json) → bridge_mtf_research_plan_v1
  → simulate_frozen_long_plan_v1 (вход ровно next M5 open, стоп первым, 1R/2R 50/50, 96 M5; base 6+2 bps/сторона, stress 10+5).
Фандинг — Bybit funding/history, календарь по A6 (Brain V2) без подстановки нуля. Контекст — REZHIM_V1 A1 по BTC H1 из тех же M5.
Эпоха и вселенная фиксируются при первом запуске --cikl в data/breakout_ten/EPOHA.json.
    .venv/bin/python research_lab/breakout_ten.py --proverka
    .venv/bin/python research_lab/breakout_ten.py --cikl
"""
import argparse, dataclasses, datetime as dt, hashlib, json, sys, time, urllib.parse, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parent; ROOT = LAB.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(LAB))
from strategies import event_expansion_retest_long_mtf_v1 as mtf
from bot.event_long_mtf_execution_bridge_v1 import bridge_mtf_research_plan_v1
from bot import event_long_execution_v1 as ex
# ИЗВЕСТНЫЙ ДЕФЕКТ (12.10, передан Codex): bridge сверяет provenance.output_sha256 (весь H1-агрегат) с level.source_bars_sha256
# (только окно lookback, level_snapshot_v1 стр. 810/877) → на реальной истории > окна каждый план BLOCKED. Тень пишет планы и
# state_pri_plane; после исправленной версии bridge — запуск с --perebridge, сделки досчитываются из сохранённых M5.
from os2.rezhim_v1 import metki

M5, M15, H, H4, D = 300_000, 900_000, 3_600_000, 14_400_000, 86_400_000
TOP = 50; PROGREV_DNEY = 40; PROVIDER_ID = "bybit_v5_kline_linear_m5_live_breakout_ten"
DIR = LAB / "data" / "breakout_ten"; M5DIR = DIR / "m5"; STDIR = DIR / "state"
PLANY = DIR / "plany.jsonl"; SDELKI = DIR / "sdelki.jsonl"; EPOHA = DIR / "EPOHA.json"
FUNDING_ZHDAT = D  # если календарь фандинга не закрылся через сутки после окна — FUNDING_UNKNOWN


def utc(): return dt.datetime.now(dt.timezone.utc)
def log(*a): print(utc().isoformat(timespec="seconds"), *a, flush=True)
def sha(b): return hashlib.sha256(b).hexdigest()
def sha_file(p): return sha(Path(p).read_bytes())


def get(put, **p):
    url = "https://api.bybit.com" + put + "?" + urllib.parse.urlencode(p)
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-paper"}), timeout=30) as r:
                raw = r.read(); j = json.loads(raw); time.sleep(0.12)
                if j.get("retCode") == 0: return j["result"], raw
        except Exception: pass
        time.sleep(5 * (k + 1))
    raise RuntimeError(f"Bybit не ответил {put} {p.get('symbol', '')}")


def jl_append(p, obj):
    with open(p, "a") as f: f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n")


def jl_read(p):
    if not Path(p).exists(): return []
    return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]


# ---------- вселенная и эпоха ----------
def vselennaya(src0):
    tick, _ = get("/v5/market/tickers", category="linear")
    instr, _ = get("/v5/market/instruments-info", category="linear", limit=1000)
    zapusk = {x["symbol"]: int(x.get("launchTime") or 0) for x in instr["list"]
              if x.get("status") == "Trading" and x.get("contractType") == "LinearPerpetual" and x.get("quoteCoin") == "USDT"}
    kand = sorted(((float(t.get("openInterestValue") or 0), t["symbol"]) for t in tick["list"]
                   if t["symbol"] in zapusk and zapusk[t["symbol"]] <= src0), reverse=True)
    return [s for _, s in kand[:TOP]], {"tickers_sha256": sha(json.dumps(tick, sort_keys=True).encode()),
                                        "oi_top": [[s, v] for v, s in kand[:TOP]]}


def epoha_init():
    if EPOHA.exists(): return json.loads(EPOHA.read_text())
    DIR.mkdir(parents=True, exist_ok=True); M5DIR.mkdir(exist_ok=True); STDIR.mkdir(exist_ok=True)
    now = int(time.time() * 1000)
    ep = (now // H4 + 1) * H4                              # следующая граница H4: планы с valid_from ≥ ep
    src0 = (ep - PROGREV_DNEY * D) // H4 * H4
    sim, sn = vselennaya(src0)
    if "BTCUSDT" not in sim: sim = sim[:-1] + ["BTCUSDT"]  # BTC нужен для REZHIM; правило заранее
    e = {"epoha_ms": ep, "epoha_utc": dt.datetime.utcfromtimestamp(ep / 1000).isoformat(), "src0_ms": src0,
         "simvoly": sim, "snimok_oi": sn, "zapisano": utc().isoformat(),
         "kod_sha256": sha_file(__file__),
         "strategiya_sha256": sha_file(ROOT / "strategies/event_expansion_retest_long_mtf_v1.py"),
         "bridge_sha256": sha_file(ROOT / "bot/event_long_mtf_execution_bridge_v1.py"),
         "execution_sha256": sha_file(ROOT / "bot/event_long_execution_v1.py"),
         "agregaciya_sha256": sha_file(ROOT / "bot/closed_bar_aggregation_v1.py"),
         "uroven_sha256": sha_file(ROOT / "bot/level_snapshot_v1.py"),
         "rezhim_sha256": sha_file(LAB / "os2/rezhim_v1.py"),
         "config_sha256": mtf.EventExpansionRetestLongMTFConfigV1().fingerprint,
         "provider_fingerprint": sha(f"{PROVIDER_ID}|src0={src0}".encode())}
    EPOHA.write_text(json.dumps(e, ensure_ascii=False, indent=1))
    return e


# ---------- M5 ----------
def m5_obnovit(sym, src0):
    p = M5DIR / f"{sym}.jsonl"; rows = [tuple(r) for r in jl_read(p)]
    now = int(time.time() * 1000); konec = now // M5 * M5            # бар закрыт ⇔ ts + M5 ≤ now
    nach = rows[-1][0] + M5 if rows else src0
    novye = []
    while nach + M5 <= konec:
        r, _ = get("/v5/market/kline", category="linear", symbol=sym, interval="5", start=nach,
                   end=min(konec - 1, nach + 999 * M5), limit=1000)
        b = sorted((int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])) for x in r["list"])
        b = [x for x in b if nach <= x[0] and x[0] + M5 <= konec]
        if not b: break
        novye += b; nach = b[-1][0] + M5
    pred = rows[-1][0] if rows else src0 - M5
    for x in novye:
        if x[0] != pred + M5:
            raise RuntimeError(f"{sym}: дыра M5 {pred}->{x[0]} — символ пропущен в этом цикле")
        pred = x[0]
    with open(p, "a") as f:
        for x in novye: f.write(json.dumps(list(x)) + "\n")
    return rows + novye


# ---------- оркестратор ----------
def plan_obj(x):
    return {k: (v.value if hasattr(v, "value") else v) for k, v in dataclasses.asdict(x).items()}


def oblozhit(sym, rows, ep, cfg, uzhe, rezhim_fn):
    sp = STDIR / f"{sym}.json"
    blob = sp.read_text() if sp.exists() else None
    as_of = rows[-1][0] + M5
    while True:
        prior = None if blob is None else mtf.state_from_json(blob, expected_provider_fingerprint=ep["provider_fingerprint"], expected_cfg=cfg)
        st = mtf.process_closed_m5_prefix(sym, rows, as_of_ms=as_of, provider_identity=PROVIDER_ID,
                                          provider_fingerprint=ep["provider_fingerprint"], prior=prior, cfg=cfg)
        state = st.state
        if st.plan is not None:
            if st.plan.plan_id not in uzhe:
                fp, most = None, "ok"
                try: fp = bridge_mtf_research_plan_v1(st.plan, state).frozen_plan
                except Exception as e: most = f"BLOCKED: {type(e).__name__}: {str(e)[:160]}"
                jl_append(PLANY, {"plan_id": st.plan.plan_id, "symbol": sym, "known_at_ms": st.plan.known_at_ms,
                                  "valid_from_ms": st.plan.valid_from_m5_open_ts_ms,
                                  "v_epohe": st.plan.valid_from_m5_open_ts_ms >= ep["epoha_ms"],
                                  "rezhim": rezhim_fn(st.plan.known_at_ms), "zapisano": utc().isoformat(),
                                  "mtf_plan": plan_obj(st.plan), "bridge": most,
                                  "frozen_plan": plan_obj(fp) if fp else None,
                                  "state_pri_plane": mtf.state_to_json(state)})   # для повторного bridge после исправления
                uzhe.add(st.plan.plan_id)
                log("план", sym, st.plan.plan_id, "v_epohe" if st.plan.valid_from_m5_open_ts_ms >= ep["epoha_ms"] else "progrev", most[:60])
            state = mtf.acknowledge_plan(state, st.plan.plan_id)
            blob = mtf.state_to_json(state); sp.write_text(blob)
            continue
        sp.write_text(mtf.state_to_json(state)); return


# ---------- режим ----------
def rezhim_iz_btc(rows_btc):
    gr = {}
    for r in rows_btc: gr.setdefault(r[0] // H * H, []).append(r)
    ts, o = [], []
    for h in sorted(gr):
        g = gr[h]
        if [x[0] for x in g] != [h + k * M5 for k in range(12)]: continue
        ts.append(h); o.append([g[0][1], max(x[2] for x in g), min(x[3] for x in g), g[-1][4], sum(x[5] for x in g)])
    lab = dict(zip(ts, metki(ts, o)))
    def fn(known_at):
        return lab.get(known_at // H * H - H) or "UNKNOWN"   # последний закрытый час к known_at
    return fn


# ---------- фандинг (A6) ----------
def fanding_sobytiya(sym, t_vhod, t_konec):
    r, raw = get("/v5/market/funding/history", category="linear", symbol=sym,
                 startTime=t_vhod - 6 * D, endTime=t_konec + D, limit=200)
    S = sorted((int(x["fundingRateTimestamp"]), float(x["fundingRate"])) for x in r.get("list", []))
    ts = [t for t, _ in S]
    do = [t for t in ts if t <= t_vhod]; posle = [t for t in ts if t >= t_konec]
    if len(do) < 11 or not posle: return None, "kalendar_ne_zakryt"
    s_a, s_b = do[-1], posle[0]
    inter = [b - a for a, b in zip(do[-11:-1], do[-10:])]
    g0 = sorted(inter)[len(inter) // 2] if len(inter) % 2 else sum(sorted(inter)[4:6]) / 2
    okno = [t for t in ts if s_a <= t <= s_b]
    if any(b - a > g0 for a, b in zip(okno, okno[1:])): return None, "dyra_kalendarya"
    fp = sha(raw)
    ev = []
    for t, v in S:
        if t_vhod < t <= t_konec:
            if not abs(v) < 0.1: return None, "nechislovaya_stavka"
            ev.append(ex.make_historical_funding_event_v1(symbol=sym, timestamp_ms=t, signed_rate=v, source_fingerprint=fp))
    return ev, "ok"


def zakryt_sdelki(rows_by_sym, now_ms):
    gotovo = {z["plan_id"] for z in jl_read(SDELKI)}
    posl = {}
    for p in jl_read(PLANY): posl[p["plan_id"]] = p
    for p in posl.values():
        if p["plan_id"] in gotovo or not p["v_epohe"] or not p.get("frozen_plan"): continue
        rows = rows_by_sym.get(p["symbol"])
        if not rows: continue
        i0 = (p["valid_from_ms"] - rows[0][0]) // M5
        if i0 < 0 or i0 + 97 > len(rows): continue                # ещё нет 96 M5 после входа
        okno = rows[i0:i0 + 97]; as_of = okno[-1][0] + M5
        fp = ex.FrozenLongPlanV1(**p["frozen_plan"])
        ev, prich = fanding_sobytiya(p["symbol"], fp.valid_from_ts, as_of)
        if ev is None and prich == "kalendar_ne_zakryt" and now_ms < as_of + FUNDING_ZHDAT: continue
        z = {"plan_id": p["plan_id"], "symbol": p["symbol"], "rezhim": p["rezhim"], "valid_from_ms": p["valid_from_ms"],
             "zapisano": utc().isoformat(), "fanding": prich}
        for sc in ("base", "stress"):
            rc = ex.simulate_frozen_long_plan_v1(fp, okno, as_of_ms=as_of, funding_events=ev or (), scenario=sc)
            z[sc] = {"status": rc.status, "exit_reason": rc.exit_reason, "net_r": rc.net_r, "gross_r": rc.gross_r,
                     "fee_r": rc.fee_cost_r, "slip_r": rc.slippage_cost_r, "funding_r": rc.funding_pnl_r,
                     "receipt_sha256": rc.receipt_sha256}
        if ev is None: z["status"] = "FUNDING_UNKNOWN"
        else: z["status"] = z["base"]["status"]
        jl_append(SDELKI, z); log("сделка", p["symbol"], p["plan_id"], z["status"])


def perebridge(ep):
    """После исправления bridge (Codex): повторный bridge из сохранённого state_pri_plane; журнал append-only, побеждает последняя запись."""
    cfg = mtf.EventExpansionRetestLongMTFConfigV1(); n = 0
    posl = {}
    for p in jl_read(PLANY): posl[p["plan_id"]] = p
    for p in posl.values():
        if p.get("frozen_plan"): continue
        st = mtf.state_from_json(p["state_pri_plane"], expected_provider_fingerprint=ep["provider_fingerprint"], expected_cfg=cfg)
        plan = [x for x in st.plan_outbox if x.plan_id == p["plan_id"]][0]
        try: fp = bridge_mtf_research_plan_v1(plan, st).frozen_plan
        except Exception as e: log("bridge всё ещё", p["plan_id"], str(e)[:120]); continue
        q = dict(p); q.update(bridge="ok", frozen_plan=plan_obj(fp), zapisano=utc().isoformat()); jl_append(PLANY, q); n += 1
    log("перебридж:", n)


def shag(ep):
    cfg = mtf.EventExpansionRetestLongMTFConfigV1()
    uzhe = {p["plan_id"] for p in jl_read(PLANY)}
    rows_by = {}
    for s in ep["simvoly"]:
        try: rows_by[s] = m5_obnovit(s, ep["src0_ms"])
        except Exception as e: log("данные", s, type(e).__name__, str(e)[:160])
    rfn = rezhim_iz_btc(rows_by.get("BTCUSDT", []))
    for s, rows in rows_by.items():
        if not rows: continue
        try: oblozhit(s, rows, ep, cfg, uzhe, rfn)
        except Exception as e: log("оркестратор", s, type(e).__name__, str(e)[:200])
    zakryt_sdelki(rows_by, int(time.time() * 1000))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--cikl", action="store_true"); ap.add_argument("--proverka", action="store_true")
    ap.add_argument("--perebridge", action="store_true"); a = ap.parse_args()
    if a.proverka:
        now = int(time.time() * 1000); src0 = (now - PROGREV_DNEY * D) // H4 * H4
        sim, _ = vselennaya(src0)
        r, _ = get("/v5/market/kline", category="linear", symbol="BTCUSDT", interval="5", limit=5)
        ev, prich = fanding_sobytiya("BTCUSDT", now // H * H - 3 * D, now // H * H - 2 * D)
        print("вселенная:", len(sim), sim[:8], "…"); print("M5 BTC последних:", len(r["list"])); print("фандинг календарь:", prich, len(ev or []))
        print("ПРОВЕРКА: OK" if len(sim) == TOP and r["list"] and prich == "ok" else "ПРОВЕРКА: FAIL"); return
    if a.perebridge: perebridge(json.loads(EPOHA.read_text())); return
    ep = epoha_init(); log("эпоха", ep["epoha_utc"], "символов", len(ep["simvoly"]))
    while True:
        t = time.time()
        try: shag(ep)
        except Exception as e: log("ошибка шага:", type(e).__name__, str(e)[:200])
        log("пульс: жив", f"{time.time() - t:.0f}с")
        if not a.cikl: break
        time.sleep(3600 - time.time() % 3600 + 120)                  # каждый час, через 2 мин после закрытия


if __name__ == "__main__":
    main()
