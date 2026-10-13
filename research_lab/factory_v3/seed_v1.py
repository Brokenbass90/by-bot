#!/usr/bin/env python3
"""seed_v1.py — первичное наполнение реестра V1 (13.10.2026). Запускается ОДИН раз (отказ, если журнал не пуст).
Кладбище: data/reestr.json (NEGATIVE) + generator/kladbische.json + вердикты 11–12.10. Живые линии — как наследие с документом.
Окна: исторические крипто-окна — только DEV (многократно просмотрены); подтверждение — будущее окно; дальше — HOLDOUT."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from reestr_v1 import Reestr, TERMINAL

LAB = Path(__file__).resolve().parents[1]


def main(put=None):
    r = Reestr(put)
    if r.put.exists() and r.put.read_text().strip():
        sys.exit("реестр уже наполнен — сид запускается один раз")
    semi = {}
    for x in json.loads((LAB / "data" / "reestr.json").read_text()):
        if (x.get("sostoyanie") or x.get("state")) == "NEGATIVE":
            semi.setdefault(str(x["id"]).split("__")[0], x.get("imya") or x["id"])
    for x in json.loads((LAB / "generator" / "kladbische.json").read_text()):
        semi.setdefault(x["semya"], x.get("prichina") or x["semya"])
    segodnya = {
        "LOZHNYY_PROBOY": "ложный пробой уровня, H1 крипта; вариант NEUTRAL FAIL_TERMINAL_KILL 12.10 (6091e14)",
        "KASKAD_LIKVIDACIY": "каскады ликвидаций Bybit, продолжение/отскок 30 мин, maker-вход; FAIL 12.10 (79b4b0a)",
        "SPOT_POTOK": "доля агрессора на споте Binance, недельная кросс-секция; B и A FAIL 12.10 (36ab6ff)",
    }
    semi.update(segodnya)
    snyato = {"FORCED_FLOW_LIQ": "KILL снят 12.10 (POPRAVKA_FORCED_FLOW_LIQ_DEFEKT_STORONY): дефект стороны в источнике"}
    for s in snyato: semi.pop(s, None)
    for s, op in sorted(semi.items()):
        r.semya(s, op, status=TERMINAL, istochnik="seed_v1: reestr.json / kladbische.json / вердикты 12.10")
    zhivye = [  # (семья, гипотеза, механизм, источники, статус, документ)
        ("KITY", "KITY_M3_BYBIT_TEN", "за агрессивным потоком тейкеров d−1, недельная, PIT топ-50, Bybit-native тень", ["bybit_kline", "bybit_oi"], "SHADOW", "PREREG_KITY_BYBIT_TEN_2026_10_11.md"),
        ("ELDER", "ETS2M_V2", "Элдер три экрана, когорта по времени обнаружения", ["bybit_kline"], "SHADOW", "PREREG_ETS2M_V2_VPERED_2026_10_11.md + POPRAVKA_A1"),
        ("BOUNCE", "BOUNCE1", "отскок от поддержки H1, BTC/ETH", ["bybit_kline"], "SHADOW", "PREREG_BOUNCE1_KEEP_KILL_2026_10_11.md"),
        ("BOUNCE", "BOUNCE1_8", "отскок от поддержки H1, 8 монет", ["bybit_kline"], "SHADOW", "PREREG_BOUNCE1_KEEP_KILL_2026_10_11.md (A1)"),
        ("BREAKOUT", "BREAKOUT_TOP50", "event expansion retest long MTF, Bybit OI топ-50 (DEV_EARLY: DEPRIORITIZE)", ["bybit_kline_m5"], "SHADOW", "PREREG_BREAKOUT_TEN_TOP50_2026_10_12.md"),
        ("ALPACA", "ALPACA_NET_DYNAMIC", "акции США, Alpaca; PAPER-цикл 12–13.10, LIVE ждёт финальности и GO", ["alpaca"], "SHADOW", "Codex ALPACA_DYNAMIC_LIVE_READINESS_2026_10_13.md"),
        ("FORCED_FLOW_LIQ", "LIQ_OTSKOK_4H_V2", "отскок 4 ч после реальных ликвидаций; только на исправленном сборщике V2, ≥ 200 событий вперёд", ["bybit_liquidations_v2"], "NEW", "POPRAVKA_FORCED_FLOW_LIQ_DEFEKT_STORONY_2026_10_12.md"),
    ]
    for s, g, meh, ist, st, dok in zhivye:
        if s not in r.sostoyanie()["semi"]:
            r.semya(s, meh, istochnik="seed_v1")
        r.gipoteza(g, s, meh, ist)
        if st != "NEW":
            r.nasledie(g, st, dok)
    r.okno("KRIPTO_D1_2021H2_2022", "binance/bybit D1", "2021-07-01", "2022-12-31", "DEV", byudzhet=300)
    r.okno("KRIPTO_D1_2023_2026Q3", "binance/bybit D1 (многократно просмотрено)", "2023-01-01", "2026-09-30", "DEV", byudzhet=300)
    r.okno("KRIPTO_H1M5_2023_2026Q3", "bybit H1/M5 (многократно просмотрено)", "2023-01-01", "2026-09-30", "DEV", byudzhet=300)
    r.okno("KRIPTO_FWD_2026Q4", "вперёд: тени и сборщики", "2026-10-13", "2026-12-31", "CONFIRM", byudzhet=20)
    r.okno("KRIPTO_FWD_2027H1", "вперёд: резерв", "2027-01-01", "2027-06-30", "HOLDOUT")
    print(json.dumps(r.svodka(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
