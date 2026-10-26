#!/usr/bin/env python3
"""brain_shadow_v1.py — Brain Shadow v1 (15.10.2026). Причинная тень аллокатора. НИКАКИХ полномочий над ордерами и риском.

Каждый проход: (1) собрать возможности из живых теней (только поля решения, исходы не читаются),
(2) записать OpportunityRecord V2 c ContextRecord, (3) принять решения двух ЗАМОРОЖЕННЫХ политик на одних и тех же
возможностях, капитале и ограничениях: BASELINE_V1 и BRAIN_V1, (4) отдельно и позже прикрепить исходы, где они разрешены.
Исходы Elder ETS2M под ЭМБАРГО до закрытия судьи 900 (prereg ETS2M_V2): не читаются и не прикрепляются.

    python3 research_lab/factory_v3/brain_shadow_v1.py            # один проход
    python3 research_lab/factory_v3/brain_shadow_v1.py --cikl     # раз в час, только ручной screen через edinstvennyy_zapusk
Данные: research_lab/data/brain_shadow_v1/{opportunities,decisions,joins}.jsonl
"""
import argparse, datetime as dt, hashlib, json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; LAB = HERE.parent; D = LAB / "data"
sys.path.insert(0, str(HERE))
import opportunity_v2 as V2                                    # noqa: E402

PAPKA = D / "brain_shadow_v1"
H, DEN = 3_600_000, 86_400_000
U = V2.UNKNOWN

# ---------- ЗАМОРОЖЕНО. Любое изменение = новая версия политики (новый policy_sha), старые решения не пересчитываются.
PRIORY = {
    "KITY_BYBIT": dict(gross=44.0, unc=25.0, fee=12.0, spread=3.0, slip=3.0, funding=0.0, horizon=8 * DEN,
                       ref="ITOG_KITY_ZADERZHKA_2026_10_14 лаг1: спред L−S +74.4 (t 1.18) / +103.2 (t 2.59) bps/нед → нога ≈ половина",
                       status="HIST_DEV_PASS; PROSPECTIVE_PENDING(C1–C3)"),
    "ELDER_ETS2S": dict(R=0.031, R_se=0.024, fee_bps=7.0, spread=0.0, slip=2.0, funding=0.0, horizon=342 * H,
                        ref="POSTMORTEM_ELDER_HIST_DEV_2026_10_15: CONTROL +0.031R, σ недели 1.28",
                        status="HIST_DEV_KILL; PROSPECTIVE_PENDING(ETS2M 900)"),
}
RISK = dict(total=20.0, sleeve=10.0, symbol=1.0, cluster=6.0, stale_ms=6 * 3_600_000)   # v1.1: сигнал, доступный позже 6 ч после наблюдения, — не причинный       # единицы риска; кластер = (рукав, сторона) — прокси корреляции
BRAIN = dict(k_unc=0.5, masshtab=20.0, k_klaster=6.0, oborot=0.5)
POLICY_SHA = hashlib.sha256(json.dumps([PRIORY, RISK, BRAIN, "v1"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _sha(b): return hashlib.sha256(b).hexdigest()
def _ms(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


# ---------- ContextRecord v1: только СУЩЕСТВУЮЩИЕ признаки, без нового классификатора и без ретюнинга.
#   rezhim_v1      — замороженный REZHIM_V1 (os2/rezhim_v1.py, замок REZHIM_V1_ZAMOK.json) = живой bot/regime_orchestrator:
#                    BULL_TREND / BEAR_TREND / NEUTRAL по закрытым 4h BTC; дыра → UNKNOWN.
#   btc_rezhim     — метка лаборатории osi.metka_rezhima: (close−EMA200)/EMA200 BTC h1, пороги ±0.02.
#   btc_ret_24h/168h — доходность BTC по закрытым барам. funding/oi — UNKNOWN (источника в тени нет).
def kontekst_fabrika(btc_bary):
    if not btc_bary or len(btc_bary) < 400:
        return lambda t: kontekst(t, None)
    import numpy as np
    sys.path.insert(0, str(LAB / "os2"))
    try:
        import rezhim_v1
        ts = np.array([x[0] for x in btc_bary], dtype=np.int64); o = np.array([x[1:6] for x in btc_bary], dtype=float)
        rv = dict(zip(ts.tolist(), rezhim_v1.metki(ts, o)))
    except Exception:
        rv = {}
    return lambda t: kontekst(t, btc_bary, rv)


def kontekst(t_obs_ms, btc_bary, rv=None):
    ctx = _kontekst_v1(t_obs_ms, btc_bary, rv)
    try:                                                     # 17.10 BRAIN_V2 этап 1: Context Engine — только запись, решения не меняет
        import importlib, kontekst_v2; importlib.reload(kontekst_v2); ctx = kontekst_v2.dopolnit(ctx, t_obs_ms, btc_bary)
    except Exception as e:
        ctx = dict(ctx, kontekst_v2=dict(oshibka=str(e)[:160]))
    return ctx


def _kontekst_v1(t_obs_ms, btc_bary, rv=None):
    ctx = dict(schema="ContextRecord v1", rezhim_v1=U, btc_rezhim=U, btc_otkl_ema200=U, btc_ret_24h=U, btc_ret_168h=U, bar_ts=U,
               source="bybit_kline_60 BTCUSDT" if btc_bary else U, funding=U, oi=U)
    if not btc_bary: return ctx
    b = [x for x in btc_bary if x[0] + H <= t_obs_ms]                    # только закрытые к наблюдению бары
    if len(b) < 400: return ctx
    c = [float(x[4]) for x in b]; a = 2.0 / 201; e = c[0]
    for x in c[1:]: e = a * x + (1 - a) * e
    o = (c[-1] - e) / e
    ctx.update(btc_otkl_ema200=round(o, 5), btc_ret_24h=round(c[-1] / c[-25] - 1, 5), btc_ret_168h=round(c[-1] / c[-169] - 1, 5),
               bar_ts=int(b[-1][0]), btc_rezhim="тренд-" if o < -0.02 else "флет-" if o < 0 else "флет+" if o < 0.02 else "тренд+",
               rezhim_v1=(rv or {}).get(int(b[-1][0])) or U)
    return ctx


# ---------- Источники. Читаются ТОЛЬКО поля решения.
def iz_kity(btc):
    out = []
    for dp in sorted((D / "kity_bybit_ten").glob("20*")):
        sp = dp / "signal.json"
        if not sp.exists(): continue
        raw = sp.read_bytes(); s = json.loads(raw); d = dt.date.fromisoformat(s["d"]); P = PRIORY["KITY_BYBIT"]
        t_av = int(dt.datetime.fromisoformat(s["vychisleno"]).timestamp() * 1000); t_obs = _ms(d) - 1
        for side, nogi in ((1, s["long"]), (-1, s["short"])):
            for n in nogi:
                out.append(V2.vozmozhnost(source_ref=f"data/kity_bybit_ten/{s['d']}/signal.json", source_sha256=_sha(raw),
                                          t_observation_ms=t_obs, t_available_ms=t_av, t_decision_ms=t_av, sleeve="KITY_BYBIT",
                                          mechanism="KITY_TAKER_XS", version="ten_v1", symbol=n["s"], side=side, horizon_ms=P["horizon"],
                                          context=btc(t_obs), features=dict(taker=n["taker"], monet=s["monet_s_priznakom"]),
                                          exp_gross_bps=P["gross"], cost_fee_bps=P["fee"], cost_spread_bps=P["spread"], cost_slip_bps=P["slip"],
                                          cost_funding_bps=P["funding"], uncertainty_bps=P["unc"], prior_ref=P["ref"], prior_status=P["status"]))
    return out


POLYA_ELDER = ("ts", "sym", "side", "zapisano", "vovremya", "zapozdanie_ch")      # исходы (R и пр.) НЕ читаются


def iz_elder(btc):
    """v1.2 (16.10): источник — ПЕРВАЯ запись живой тени ETS2S (data/ten_ETS2S.jsonl, пишется в момент обнаружения сигнала),
    а не yadro/ETS2M/vhody.jsonl: ядро переносит входы с задержкой 25–280 ч, и все такие записи были не причинными.
    Стоп в момент обнаружения ещё не записан → ожидаемый край UNKNOWN (BRAIN_V1 воздерживается, BASELINE/HEDGE считают в единицах)."""
    p = D / "ten_ETS2S.jsonl"; out = []; vidennye = set()
    if not p.exists(): return out
    P = PRIORY["ELDER_ETS2S"]
    for l in open(p, encoding="utf-8"):
        if not l.strip(): continue
        x = json.loads(l); klyuch = (x.get("sym"), int(x.get("ts", 0)))
        if klyuch in vidennye or x.get("side") not in ("long", "short"): continue
        vidennye.add(klyuch); x = {k: x.get(k) for k in POLYA_ELDER}
        t_obs = int(x["ts"]) + H; t_av = max(t_obs, int(x["zapisano"]))
        out.append(V2.vozmozhnost(source_ref=f"data/ten_ETS2S.jsonl#{x['sym']}:{x['ts']}",
                                  source_sha256=_sha(json.dumps(x, sort_keys=True).encode()), t_observation_ms=t_obs, t_available_ms=t_av,
                                  t_decision_ms=t_av, sleeve="ELDER", mechanism="ELDER_ETS2S", version="ETS2S_live", symbol=x["sym"],
                                  side=1 if x["side"] == "long" else -1, horizon_ms=P["horizon"], context=btc(t_obs),
                                  features=dict(vovremya=x["vovremya"], zapozdanie_ch=x["zapozdanie_ch"]),
                                  exp_gross_bps=U, cost_fee_bps=P["fee_bps"], cost_spread_bps=P["spread"], cost_slip_bps=P["slip"],
                                  cost_funding_bps=P["funding"], uncertainty_bps=U, prior_ref=P["ref"], prior_status=P["status"]))
    return out


# ---------- Risk Engine (детерминированный, общий для обеих политик) и политики
def prichinno(o):
    return not o.get("late", False) and o["t_available_ms"] - o["t_observation_ms"] <= RISK["stale_ms"]


def otkryto(hr, policy, t, vklyuchaya_budushchie=False):
    opp = {z["opp_id"]: z for z in hr.opp.zapisi}; out = []
    for d in hr.dec.zapisi:
        if d["policy"] != policy or d["allocation_units"] <= 0: continue
        o = opp[d["opp_id"]]
        if not prichinno(o): continue                 # бэкфилл и устаревшие сигналы не занимают риск-бюджет
        if (vklyuchaya_budushchie or o["t_decision_ms"] <= t) and t < o["t_decision_ms"] + o["horizon_ms"]:
            out.append((o, d["allocation_units"]))
    return out


def risk_engine(v, zhelaemo, otkr):
    ogr, u = [], zhelaemo
    def sm(f): return sum(a for o, a in otkr if f(o))
    for imya, ost in (("total", RISK["total"] - sm(lambda o: True)),
                      ("sleeve", RISK["sleeve"] - sm(lambda o: o["sleeve"] == v["sleeve"])),
                      ("symbol", RISK["symbol"] - sm(lambda o: o["symbol"] == v["symbol"])),
                      ("cluster", RISK["cluster"] - sm(lambda o: o["sleeve"] == v["sleeve"] and o["side"] == v["side"]))):
        if u > ost: u = max(0.0, ost); ogr.append(f"cap_{imya}")
    return round(u, 4), ogr


def baseline_v1(v, otkr):
    return 1.0, []


def brain_v1(v, otkr):
    if "KILL" in v["prior_status"]: return 0.0, ["prior_kill"]
    if U in (v["exp_net_bps"], v["uncertainty_bps"]): return 0.0, ["unknown_edge"]
    zatraty = v["cost_fee_bps"] + v["cost_spread_bps"] + v["cost_slip_bps"] + v["cost_funding_bps"]
    if v["exp_net_bps"] < BRAIN["oborot"] * zatraty: return 0.0, ["turnover_hurdle"]
    skor = v["exp_net_bps"] - BRAIN["k_unc"] * v["uncertainty_bps"]
    if skor <= 0: return 0.0, ["uncertainty_penalty"]
    n_kl = sum(a for o, a in otkr if o["sleeve"] == v["sleeve"] and o["side"] == v["side"])
    return min(1.0, skor / BRAIN["masshtab"]) / (1.0 + n_kl / BRAIN["k_klaster"]), ["correlation_penalty"] if n_kl else []


def hedge_v1(v, otkr):
    """ELDER_CRASH_HEDGE (PREREG_ELDER_CRASH_HEDGE_REZHIM_2026_10_15, HIST DEV PASS): KITY как BRAIN_V1; Elder — страховка,
    1 ед., только если REZHIM_V1 на наблюдении ≠ BULL_TREND (UNKNOWN → берём, как в prereg). Добавлена 15.10 как третья политика;
    решения BASELINE_V1/BRAIN_V1 не меняются (их policy_sha прежний)."""
    if v["sleeve"] == "ELDER":
        return (0.0, ["hedge_off_bull"]) if v["context"].get("rezhim_v1") == "BULL_TREND" else (1.0, ["hedge_on"])
    return brain_v1(v, otkr)


POLITIKI = {"BASELINE_V1": baseline_v1, "BRAIN_V1": brain_v1, "HEDGE_V1": hedge_v1}
HEDGE_SHA = hashlib.sha256(json.dumps([POLICY_SHA, "HEDGE_V1", "elder_if_rezhim_v1_not_BULL_TREND", 1.0], sort_keys=True).encode()).hexdigest()
SHA = {"BASELINE_V1": POLICY_SHA, "BRAIN_V1": POLICY_SHA, "HEDGE_V1": HEDGE_SHA}
try:                                                   # 17.10 BRAIN_V2_DET — четвёртая политика (PREREG_BRAIN_V2_DET_2026_10_17); первые три не меняются
    import importlib, brain_v2 as _B2; importlib.reload(_B2)
    POLITIKI["BRAIN_V2_DET"] = lambda v, otkr: _B2.brain_v2_det(v, otkr, brain_v1)
    SHA["BRAIN_V2_DET"] = _B2.SHA
except Exception:
    pass


# ---------- 26.10 BRAIN_V3 (задание PM 26.10): только ДОПУЩЕННЫЕ ноги (KITY, PUMP4, MONTHLY) и CASH (= неразмещённые единицы).
# Политики V1/V2 не меняются и решают только по своим рукавам (KITY_BYBIT, ELDER). V3 — отдельная пара с собственным sha:
#   BASELINE_V3 — фиксированное распределение: 1 ед. на возможность (через тот же Risk Engine);
#   BRAIN_V3    — та же логика brain_v1 (без новых параметров) с приорами V3. Неизвестный фандинг PUMP4 → край UNKNOWN → 0 (CASH).
# Техническая приёмка ≠ экономическая оценка: экономика — не раньше ~12 недель общих исходов.
RUKAVA_V1 = {"KITY_BYBIT", "ELDER"}
RUKAVA_V3 = {"KITY_BYBIT", "PUMP4", "MONTHLY"}
PRIORY_V3 = {
    "PUMP4": dict(R=0.061, R_se=0.055, fee=12.0, spread=0.0, slip=2.0, funding=U, horizon=168 * H,
                  ref="PUMP4_POLNYY_POVTOR_ITOG_2026_10_26: 84 сд. +0.061R (тейкер), превышение +0.127R t 2.3; фандинг не учтён",
                  status="HIST_INCONCLUSIVE; PROSPECTIVE_PENDING"),
}
SHA_V3 = hashlib.sha256(json.dumps([PRIORY_V3, PRIORY["KITY_BYBIT"], RISK, BRAIN, "v3"], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
POLITIKI_V3 = {"BASELINE_V3": baseline_v1, "BRAIN_V3": brain_v1}


def iz_pump4(btc, put=None):
    """Источник — append-only журнал проспективных сигналов непрерывного повтора (pump4_polnyy_povtor.zhurnal_vpered).
    t_obs = закрытие сигнального часа, t_av = момент обнаружения ежедневным прогоном. Обнаружение позже 6 ч → не причинно
    (честно: для причинных PUMP4-возможностей нужен ежечасный производитель Codex — join-контракт)."""
    p = put or (D / "pump4_vpered_zhurnal.jsonl"); out = []
    if not p.exists(): return out
    P = PRIORY_V3["PUMP4"]
    for l in open(p, encoding="utf-8"):
        if not l.strip(): continue
        x = json.loads(l)
        if x.get("vid") != "SIGNAL": continue
        t_obs = int(x["ts"]) + H; t_av = max(t_obs, int(x["uvideno_ms"]))
        rp = x.get("risk_pct")
        g = P["R"] * rp * 100 if isinstance(rp, (int, float)) else U
        u = P["R_se"] * rp * 100 if isinstance(rp, (int, float)) else U
        out.append(V2.vozmozhnost(source_ref=f"data/pump4_vpered_zhurnal.jsonl#{x['sym']}:{x['ts']}", source_sha256=x["sha256"],
                                  t_observation_ms=t_obs, t_available_ms=t_av, t_decision_ms=t_av, sleeve="PUMP4", mechanism="PUMP_FADE_V4R",
                                  version="V1_frozen", symbol=x["sym"], side=1 if x["side"] == "long" else -1, horizon_ms=P["horizon"],
                                  context=btc(t_obs), features=dict(zapazdyvanie_ch=x.get("zapazdyvanie_ch")),
                                  exp_gross_bps=g, cost_fee_bps=P["fee"], cost_spread_bps=P["spread"], cost_slip_bps=P["slip"],
                                  cost_funding_bps=P["funding"], uncertainty_bps=u, prior_ref=P["ref"], prior_status=P["status"]))
    return out


def prikrepit_pump4(hr, seychas=None, put=None):
    """Исход PUMP4 — строка ISHOD журнала вперёд: R × риск % → bps на номинал (после тейкера, БЕЗ фандинга — помечено в source_ref)."""
    p = put or (D / "pump4_vpered_zhurnal.jsonl"); n = 0
    if not p.exists(): return 0
    po = {(z["symbol"], z["t_observation_ms"] - H): z for z in hr.opp.zapisi if z["sleeve"] == "PUMP4"}
    for l in open(p, encoding="utf-8"):
        x = json.loads(l)
        if x.get("vid") != "ISHOD" or not isinstance(x.get("risk_pct"), (int, float)): continue
        o = po.get((x["sym"], int(x["ts"])))
        if o is None: continue
        if hr.prikrepit_ishod(o["opp_id"], int(x["uvideno_ms"]), round(x["R"] * x["risk_pct"] * 100, 3),
                              f"data/pump4_vpered_zhurnal.jsonl#ISHOD:{x['sym']}:{x['ts']} (без фандинга)", x["sha256"], seychas): n += 1
    return n


def prohod(hr=None, btc=None, seychas=None):
    if hr is None:                                   # один писатель: цепочка хешей не переживает двух одновременных проходов
        import fcntl
        PAPKA.mkdir(parents=True, exist_ok=True); fd = open(PAPKA / ".lock", "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return dict(status="ZANYATO", prichina="другой проход Brain Shadow держит замок")
        try:
            return _prohod(V2.Hranilishche(PAPKA), btc, seychas)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN); fd.close()
    return _prohod(hr, btc, seychas)


def _prohod(hr, btc=None, seychas=None):
    if btc is None:
        try:
            sys.path.insert(0, str(LAB)); from ten import svechi; btc = svechi("BTCUSDT")
        except Exception:
            btc = None
    btc = kontekst_fabrika(btc)
    novye = [z for z in (hr.dobavit_vozmozhnost(v, seychas) for v in
                         sorted(iz_kity(btc) + iz_elder(btc) + iz_pump4(btc), key=lambda v: (v["t_decision_ms"], v["sleeve"], v["symbol"]))) if z]
    resh = 0
    t0 = novye[0]["t_decision_ms"] if novye else 0
    VSE = {**POLITIKI, **POLITIKI_V3}; SHA_VSE = {**SHA, **{k: SHA_V3 for k in POLITIKI_V3}}
    otkr = {imya: otkryto(hr, imya, t0, vklyuchaya_budushchie=True) for imya in VSE}
    for v in novye:
        t = v["t_decision_ms"]
        for imya, f in VSE.items():
            if (imya in POLITIKI and v["sleeve"] not in RUKAVA_V1) or (imya in POLITIKI_V3 and v["sleeve"] not in RUKAVA_V3):
                continue
            otkr[imya] = [(o, a) for o, a in otkr[imya] if o["t_decision_ms"] + o["horizon_ms"] > t]
            tek = [(o, a) for o, a in otkr[imya] if o["t_decision_ms"] <= t]
            if not prichinno(v):
                zh, ogr1 = 0.0, ["ne_prichinno"]
            else:
                zh, ogr1 = f(v, tek)
            u, ogr2 = risk_engine(v, zh, tek)
            hr.dobavit_reshenie(v["opp_id"], imya, SHA_VSE[imya], u, ogr1 + ogr2, seychas); resh += 1
            if u > 0: otkr[imya].append((v, u))
    ish = prikrepit_kity(hr, seychas) + prikrepit_pump4(hr, seychas)
    return dict(novyh=len(novye), resheniy=resh, ishodov=ish, late=sum(1 for z in hr.opp.zapisi if z["late"]), vsego=len(hr.opp.zapisi))


def prikrepit_kity(hr, seychas=None):
    """Исход KITY — из vyhod.json тени после закрытия недели (доход ноги в долях → bps). Elder — ЭМБАРГО."""
    n = 0; po = {(z["source_ref"], z["symbol"], z["side"]): z for z in hr.opp.zapisi if z["sleeve"] == "KITY_BYBIT"}
    for dp in sorted((D / "kity_bybit_ten").glob("20*")):
        vp = dp / "vyhod.json"
        if not vp.exists(): continue
        raw = vp.read_bytes(); vy = json.loads(raw)
        for nog in vy.get("nogi", []):
            o = po.get((f"data/kity_bybit_ten/{dp.name}/signal.json", nog["s"], nog["side"]))
            if o is None or nog.get("dohod") is None: continue
            if hr.prikrepit_ishod(o["opp_id"], o["t_decision_ms"] + o["horizon_ms"], round(float(nog["dohod"]) * 1e4, 3),
                                  f"data/kity_bybit_ten/{dp.name}/vyhod.json", _sha(raw), seychas): n += 1
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--cikl", action="store_true"); ap.add_argument("--pauza", type=int, default=3600)
    a = ap.parse_args()
    while True:
        print(time.strftime("%Y-%m-%d %H:%M:%S"), json.dumps(prohod(), ensure_ascii=False), flush=True)
        if not a.cikl: break
        time.sleep(a.pauza)
