#!/usr/bin/env python3
"""inventar.py — реестр ВСЕХ ног проекта (Trading OS v2, шаг B1). Только чтение репозитория, исходов не считает.
Карточки: ручные (проверенные доказательства) + автоматические для каждого модуля strategies/*.py
(ищем упоминания в reports/, docs/, research_lab/ — чтобы ничего не потерялось). Пишет INVENTAR_NOG.json и .md.
Ручные карточки — в KARTOCHKI ниже; автокарточка модуля без ручной = статус NE_PROVERENO (ждёт аудита B1)."""
import json, re, subprocess, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
POLYA = ["chto_lovit", "storona", "rezhim", "edge", "ispolnenie", "izderzhki", "status", "dokazatelstva"]

KARTOCHKI = {
 "KITY_M3_POTOK": dict(rynok="крипта Binance USDT-M", modul="research_lab/kity_m3_ten.py", chto_lovit="продолжение за агрессивным потоком тейкеров d−1, недельно, PIT топ-50",
   storona="long+short (дециль k=n//10)", rezhim="UNKNOWN (по годам 2023 +30, 2024 +37, 2025 +183, 2026 +185 bps — режимный разбор B3)",
   edge="PRIMARY +103 bps/нед t2.59; репл. SAME_SIGN +74", ispolnenie="orders-off у Codex, паритет 251 вектора PASS; тень с 08.10",
   izderzhki="12 bps круг + фандинг заложены", status="READY_FOR_BUILD → canary-ворота 09.10",
   dokazatelstva=["research_lab/data/binance_kity/M3_KVITANCIYA.json", "research_lab/data/binance_kity/KITY_M3_RISK_PROFIL.json"]),
 "REBALANCING_PRESSURE": dict(rynok="индексы US30 (FxPro CFD)", modul="research_lab/rebalancing_pressure.py", chto_lovit="конец месяца против перекоса акции−облигации",
   storona="long/short индекса", rezhim="не крипто-режим; календарный", edge="PRIMARY +42.7 bps/соб t2.06; HOLDOUT +12.5 SAME_SIGN",
   ispolnenie="тень rebal_ten; пакет Codex после 30.10", izderzhki="US30 круг 0.36 bps", status="READY_FOR_BUILD (на грани), вперёд 26–30.10",
   dokazatelstva=["research_lab/data/REBALANCING_KVITANCIYA.json"]),
 "ALPACA": dict(rynok="акции США", modul="scripts/alpaca_adaptive_paper.py (Codex)", chto_lovit="v38/SPY200 селектор, месячный → динамическая замена",
   storona="long", rezhim="фильтр SPY200 внутри", edge="история 14.48%/г DD 7.57% PF 1.81", ispolnenie="LIVE (CRWD, META) с защитой",
   izderzhki="учтены Codex", status="LIVE; Dynamic V1 → PAPER/LIVE GO", dokazatelstva=["bybit-bot-recovery-20260824/reports/ALPACA_DYNAMIC_V1_DELIVERY_2026_10_06.md"]),
 "ETS2M": dict(rynok="крипта Bybit", modul="strategies/elder_triple_screen_v2.py + research_lab/yadro.py", chto_lovit="Elder triple screen, исполнимая версия ETS2S",
   storona="long+short", rezhim="UNKNOWN", edge="ETS2S информация +0.0668R 4.22σ; деньги — вердикт ETS2M", ispolnenie="тень ядра",
   izderzhki="в ядре", status="вердикт 10.10 19:00 UTC", dokazatelstva=["research_lab/data/yadro/ETS2M/", "research_lab/PREREG_TRI_TENI_2026_09_15.md"]),
 "ATT1": dict(rynok="крипта Bybit", modul="strategies/alt_trendline_touch_v1.py / att1_live.py", chto_lovit="касание наклонной линии тренда, шорт",
   storona="short", rezhim="аудит 14.08: bull +1.26R/91 PF1.03, neutral +5.57R/252 PF1.04, bear −11.36R/35 PF0.51; оркестратор 08: флет-",
   edge="слабый: PF ≈1.03–1.04 в хороших режимах; reserved OOS 29.08 FAIL_CLOSED", ispolnenie="BLOCKED_DATA (транспорт CTS; 48ч-терминал 06.10)",
   izderzhki="чувствителен", status="CONDITIONAL_CANDIDATE: edge по режиму и исполнение — раздельно",
   dokazatelstva=["reports/evidence/ATT1_BULL_REGIME_AND_LOSS_AUDIT_20260814.json", "research_lab/orch.log"]),
 "SBR1": dict(rynok="крипта Bybit major8", modul="strategies/sloped_break_retest_v1.py", chto_lovit="пробой наклонного уровня с ретестом, лонг",
   storona="long", rezhim="флет+ (оркестратор 08)", edge="история 2023–25 64 сделки +24.26R PF2.06; reserved OOS 16 сделок −3.31R (LOW_N)",
   ispolnenie="тень на VPS с 24.08, журнал 40 768 событий, сделок 0", izderzhki="?", status="INCONCLUSIVE_LOW_N",
   dokazatelstva=["research_lab/results/att1_sbr1_presealed_economics_diagnostic_20260823/receipt.json"]),
 "BOUNCE1": dict(rynok="крипта BTC/ETH", modul="strategies/bounce1_live.py", chto_lovit="отскок от уровня", storona="long?",
   rezhim="UNKNOWN", edge="3 окна по 120 дн. все +, 41 сделка, PF 1.86/3.35/2.39", ispolnenie="тень не развёрнута (02.08)",
   izderzhki="?", status="PASS_TO_PROSPECTIVE_RISK_ZERO", dokazatelstva=["reports/releases/BOUNCE1_MAJORS_EXACT_REPLAY_PASS_2026_08_02.json"]),
}

_KORPUS = None
def korpus():
    """Один проход: все .md/.json ≤ 3 МБ в reports/, docs/, research_lab/ (без data/)."""
    global _KORPUS
    if _KORPUS is None:
        _KORPUS = []
        for kor in ("reports", "docs", "research_lab"):
            for f in (ROOT / kor).rglob("*"):
                if f.suffix not in (".md", ".json") or "/data/" in str(f) or not f.is_file(): continue
                try:
                    if f.stat().st_size > 3_000_000: continue
                    _KORPUS.append((str(f.relative_to(ROOT)), f.stat().st_mtime, f.read_text(errors="ignore")))
                except OSError: pass
    return _KORPUS

def upominaniya(imya):
    return [p for p, t, txt in sorted(korpus(), key=lambda x: -x[1]) if imya in txt]

def main():
    inv = {"sozdano": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "nogi": {}}
    for k, v in KARTOCHKI.items():
        inv["nogi"][k] = {**v, "istochnik": "ручная (проверено)"}
    for f in sorted((ROOT / "strategies").glob("*.py")):
        if f.name.startswith("__"): continue
        m = f.stem
        if any(m in (v.get("modul") or "") for v in KARTOCHKI.values()): continue
        up = upominaniya(m)
        inv["nogi"][m] = dict(rynok="?", modul=f"strategies/{f.name}", chto_lovit="?", storona="?", rezhim="?", edge="?",
                              ispolnenie="?", izderzhki="?", status="NE_PROVERENO (B1)", upominaniy=len(up), dokazatelstva=up[:5],
                              istochnik="авто")
    # механизмы фабрики (без модуля в strategies/): реестр 23.09 + реестр контроллера
    for r in json.loads((ROOT / "research_lab/data/reestr.json").read_text()):
        if r["id"] in inv["nogi"]: continue
        inv["nogi"][r["id"]] = dict(rynok="?", modul="реестр фабрики", chto_lovit=r.get("imya", "?"), storona="?", rezhim="?",
            edge=r.get("edzh", "?"), ispolnenie="?", izderzhki=r.get("izderzhki", "?"), status=r.get("sostoyanie", "?"),
            dokazatelstva=[r.get("svidetelstvo", "")], istochnik="data/reestr.json")
    for k, r in json.loads((ROOT / "research_lab/data/fabrika_xs/REESTR_STRATEGIY.json").read_text())["zapisi"].items():
        if k in inv["nogi"]: continue
        inv["nogi"][k] = dict(rynok=r.get("dannye", "?"), modul="реестр контроллера", chto_lovit=r.get("mehanizm", "?"), storona="?",
            rezhim="?", edge=r.get("metriki", "?"), ispolnenie="?", izderzhki="?", status=r.get("verdikt", "?"),
            dokazatelstva=[r.get("kvitanciya", ""), r.get("prereg", "")], istochnik="REESTR_STRATEGIY.json")
    (Path(__file__).parent / "INVENTAR_NOG.json").write_text(json.dumps(inv, ensure_ascii=False, indent=1))
    L = ["# INVENTAR_NOG — все ноги проекта (вид; правится через inventar.py)", f"Сгенерировано {inv['sozdano']}.", "",
         "| нога | рынок | что ловит | сторона | режим | edge | исполнение | статус |", "|---|---|---|---|---|---|---|---|"]
    for k, v in inv["nogi"].items():
        L.append(f"| {k} | {v['rynok']} | {v['chto_lovit']} | {v['storona']} | {v['rezhim']} | {v['edge']} | {v['ispolnenie']} | {v['status']}"
                 + (f" ({v['upominaniy']} упом.)" if 'upominaniy' in v else "") + " |")
    (Path(__file__).parent / "INVENTAR_NOG.md").write_text("\n".join(L) + "\n")
    print("ног:", len(inv["nogi"]), "| ручных:", len(KARTOCHKI), "| без доказательств в отчётах:",
          sum(1 for v in inv["nogi"].values() if v.get("upominaniy") == 0))

if __name__ == "__main__":
    main()
