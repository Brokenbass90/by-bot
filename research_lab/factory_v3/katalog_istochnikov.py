#!/usr/bin/env python3
"""katalog_istochnikov.py — машинный каталог источников данных Фабрики (16.10.2026).
Для ЛОКАЛЬНЫХ источников история и покрытие ИЗМЕРЯЮТСЯ по файлам (ничего не выдумывается); для планируемых —
status PLANNED и history "НЕ ПРОВЕРЕНО". Пишет data/factory_v3/KATALOG_ISTOCHNIKOV.json.
    python3 research_lab/factory_v3/katalog_istochnikov.py
"""
import datetime as dt, json, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"


def _d(ms): return dt.datetime.fromtimestamp(int(ms) / 1000, dt.timezone.utc).date().isoformat()


def izmerit(papka, tip):
    p = D / papka; fs = [f for f in p.glob("*") if f.is_file() and f.suffix in (".json", ".npz") and f.name != "MANIFEST.json"]
    if not fs: return dict(instrumentov=0, s=None, po=None)
    s, po = [], []
    for f in fs:
        try:
            if tip == "npz":
                t = np.load(f)["ts"]; s.append(_d(t[0])); po.append(_d(t[-1]))
            elif tip == "kline":
                x = json.loads(f.read_text()); s.append(_d(x[0][0])); po.append(_d(x[-1][0]))
            elif tip == "dnevnoy_slovar":
                x = json.loads(f.read_text()); k = sorted(q for q in x if len(q) == 10 and q[4] == "-")
                if k: s.append(k[0]); po.append(k[-1])
            elif tip == "taker":
                x = json.loads(f.read_text()); s.append(_d(x[0][0])); po.append(_d(x[-1][0]))
        except Exception:
            continue
    return dict(instrumentov=len(fs), s=min(s) if s else None, po=max(po) if po else None, s_mediana=sorted(s)[len(s) // 2] if s else None)


LOKALNYE = [
    dict(id="binance_perp_d1", papka="binance_kity/klines", tip="kline", ploshchadka="Binance USDT-perp", polya=["o", "h", "l", "c", "v(база)"],
         chastota="1d", zaderzhka="T+0 закрытие дня UTC", riski="вселенная — монеты, доступные на дату (PIT по OI среды); делистинги в архиве есть",
         limity="data.binance.vision публично", semyi=["импульс/разворот (KILL)", "объём", "доля площадки (знаменатель)"]),
    dict(id="binance_metrics_w", papka="binance_kity/metrics", tip="dnevnoy_slovar", ploshchadka="Binance", polya=["toptrader_ls_acc", "toptrader_ls_pos", "ls_global", "taker_ls_vol", "OI"],
         chastota="1 раз в неделю (среда)", zaderzhka="T+0", riski="только среды — для других дней недели вселенная берётся с прошлой среды",
         limity="публично", semyi=["толпа/позиции (KILL: TOLPA_XS, KITY_POZICII)", "OI (KILL: OI_CROWDING, OI_KVINTIL)"]),
    dict(id="binance_funding", papka="binance_kity/funding", tip="kline", ploshchadka="Binance", polya=["funding_rate"], chastota="8h",
         zaderzhka="известен в момент начисления", riski="—", limity="публично", semyi=["carry (KILL: FUNDING_CARRY_XS, CARRY_BASKET)"]),
    dict(id="binance_taker_d1", papka="binance_kity/taker", tip="taker", ploshchadka="Binance perp", polya=["taker_buy_quote", "quote_vol"], chastota="1d",
         zaderzhka="T+0", riski="—", limity="публично", semyi=["поток агрессора (KITY — PASS)", "всплеск (KILL)", "поглощение (KILL)"]),
    dict(id="binance_spot_taker_d1", papka="binance_kity/spot_taker", tip="taker", ploshchadka="Binance spot", polya=["taker_buy_quote", "quote_vol"],
         chastota="1d", zaderzhka="T+0", riski="—", limity="публично", semyi=["спот-поток (KILL: SPOT_POTOK)"]),
    dict(id="binance_bookdepth_d1", papka="binance_glubina", tip="dnevnoy_slovar", ploshchadka="Binance perp", polya=["imb1", "imb2", "imb5"],
         chastota="1d снимки", zaderzhka="T+0", riski="снимок дня, не поток", limity="публично", semyi=["перекос стакана (KILL: GLUBINA)"]),
    dict(id="bybit_h1_137", papka="h1", tip="npz", ploshchadka="Bybit perp", polya=["ohlcv"], chastota="1h", zaderzhka="закрытие часа",
         riski="137 монет, отбор по ликвидности на дату сборки (возможен survivorship)", limity="публично", semyi=["Elder (KILL standalone)", "ATT1 (KILL)", "часовые шаблоны"]),
    dict(id="coinbase_d1", papka="coinbase_d1", tip="dnevnoy_slovar", ploshchadka="Coinbase USD", polya=["close"], chastota="1d", zaderzhka="T+0",
         riski="листинги Coinbase позже Binance — короткие ряды", limity="публично, 10 rps", semyi=["премия (KILL)"]),
    dict(id="upbit_d1", papka="upbit_d1", tip="dnevnoy_slovar", ploshchadka="Upbit KRW", polya=["close"], chastota="1d", zaderzhka="T+0",
         riski="KRW, капитальный контроль", limity="публично", semyi=["премия (KILL)"]),
    dict(id="obem_coinbase_d1", papka="obem_coinbase_d1", tip="dnevnoy_slovar", ploshchadka="Coinbase USD", polya=["volume(база)"], chastota="1d",
         zaderzhka="T+0", riski="—", limity="публично", semyi=["доля площадки в объёме (в тесте)"]),
    dict(id="obem_upbit_d1", papka="obem_upbit_d1", tip="dnevnoy_slovar", ploshchadka="Upbit KRW", polya=["volume(база)"], chastota="1d",
         zaderzhka="T+0", riski="—", limity="публично", semyi=["доля площадки в объёме (в тесте)"]),
    dict(id="fx7_h1", papka="fx_h1", tip="npz", ploshchadka="MT5 демо (метки переведены в UTC)", polya=["ohlcv"], chastota="1h", zaderzhka="закрытие часа",
         riski="демо-котировки, спред не доказан", limity="нужен MT5", semyi=["ночной дрейф FX (CONFIRMED, исполнимость BLOCKED)"]),
    dict(id="gold_h1", papka="gold_h1", tip="npz", ploshchadka="золото", polya=["ohlcv"], chastota="1h", zaderzhka="закрытие часа", riski="—",
         limity="—", semyi=["ночной дрейф золота (KILL)", "лондонский пробой (KILL)"]),
    dict(id="deribit_dvol", papka="deribit", tip="dvol", ploshchadka="Deribit", polya=["DVOL ohlc"], chastota="1h", zaderzhka="закрытие часа",
         riski="только BTC/ETH", limity="публично", semyi=["премия за страх (KILL: V1/V2)"]),
]
PLANIRUEMYE = [
    dict(id="etf_btc_eth_flows", ploshchadka="эмитенты спотовых ETF (публичные таблицы потоков)", polya=["net_flow_usd по фонду"], chastota="1d",
         zaderzhka="публикуется после закрытия США (T+0 вечер / T+1)", riski="ревизии задним числом — хранить первую публикацию",
         limity="без ключа", semyi=["институциональный спрос → рынок (контекст Brain)"]),
    dict(id="stablecoin_supply", ploshchadka="DefiLlama stablecoins (бесплатный эндпоинт)", polya=["supply по цепочкам"], chastota="1d",
         zaderzhka="T+0/T+1", riski="ревизии; эмиссия ≠ покупка", limity="бесплатно", semyi=["новые деньги (близко к KILL NOVYE_DENGI — проверить отличие)"]),
    dict(id="hyperliquid_funding_oi", ploshchadka="Hyperliquid info API", polya=["funding (история)", "OI (только текущий)"], chastota="1h",
         zaderzhka="T+0", riski="история OI недоступна → только вперёд", limity="публично", semyi=["миграция плеча на DEX", "межплощадочный funding (близко к XEX_FUNDING)"]),
    dict(id="liq_v2", ploshchadka="Bybit ликвидации (сборщик Codex V2.1)", polya=["side", "qty", "px", "t"], chastota="поток",
         zaderzhka="секунды", riski="полнота V1 BLOCKED; V2.1 копится с 14.10", limity="VPS", semyi=["вынужденный поток (LIQ_OTSKOK_4H_V2 — ждёт данных)"]),
    dict(id="basis_spot_perp", ploshchadka="Bybit/Binance spot+perp", polya=["basis"], chastota="1h/1d", zaderzhka="T+0",
         riski="—", limity="публично", semyi=["basis (KILL: BASIS, BASIS_SPOT_PERP, TERM_*)"]),
]


def main():
    out = []
    for z in LOKALNYE:
        if z["tip"] == "dvol":
            ry = {}
            for f in (D / z["papka"]).glob("dvol_*.json"):
                r = json.loads(f.read_text())["ryad"]; ry[f.stem] = (_d(r[0][0]), _d(r[-1][0]))
            st = dict(instrumentov=len(ry), s=min(v[0] for v in ry.values()), po=max(v[1] for v in ry.values()))
        else:
            st = izmerit(z["papka"], z["tip"])
        out.append(dict({k: v for k, v in z.items() if k != "tip"}, status="LOCAL" if st["instrumentov"] else "NET_FAYLOV",
                        istoriya=st, istoriya_proverena=True))
    for z in PLANIRUEMYE:
        out.append(dict(z, status="PLANNED", istoriya="НЕ ПРОВЕРЕНО", istoriya_proverena=False))
    put = D / "factory_v3" / "KATALOG_ISTOCHNIKOV.json"
    put.write_text(json.dumps(dict(sobrano=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), istochniki=out), ensure_ascii=False, indent=1))
    for z in out:
        print(z["id"], z["status"], z["istoriya"] if isinstance(z["istoriya"], str) else (z["istoriya"]["instrumentov"], z["istoriya"]["s"], z["istoriya"]["po"]))


if __name__ == "__main__":
    main()
