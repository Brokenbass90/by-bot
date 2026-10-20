#!/usr/bin/env python3
"""brain_kity_rezhim.py — Brain-тень: метка режима волатильности BTC для каждой недели KITY (гипотеза KITY_NIZKAYA_VOL,
DIAGNOZ_INPLAY_KITY_2026_10_20, порог заморожен 0.427 годовых). Только метка, без прав над LIVE/ордерами.
Вход: data/kity_bybit_ten/<дата>/signal.json; дневки BTC Binance-перп: архив binance_kity + продолжение binance_d1_vpered.
Выход: data/brain_shadow_v1/kity_rezhim.jsonl (append-only, одна запись на неделю, записывается до исхода недели)."""
import datetime as dt, json, math, statistics as st
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"
POROG = 0.427
ZH = D / "brain_shadow_v1" / "kity_rezhim.jsonl"


def btc_zakrytiya():
    out = {}
    for p in (D / "binance_kity" / "klines" / "BTCUSDT.json", D / "binance_d1_vpered" / "klines" / "BTCUSDT.json"):
        if p.exists():
            for r in json.loads(p.read_text()):
                out[dt.datetime.utcfromtimestamp(r[0] / 1000).date()] = r[4]
    return out


def vol28(bc, d):
    dd = [bc[d - dt.timedelta(i)] / bc[d - dt.timedelta(i + 1)] - 1 for i in range(1, 29)
          if d - dt.timedelta(i) in bc and d - dt.timedelta(i + 1) in bc]           # только закрытые дни ДО даты сигнала
    return st.stdev(dd) * math.sqrt(365) if len(dd) >= 20 else None


def prohod():
    est = {json.loads(s)["d"] for s in ZH.read_text().splitlines() if s.strip()} if ZH.exists() else set()
    bc = btc_zakrytiya(); novye = []
    for p in sorted((D / "kity_bybit_ten").glob("20??-??-??/signal.json")):
        d = p.parent.name
        if d in est: continue
        v = vol28(bc, dt.date.fromisoformat(d))
        novye.append(dict(d=d, vol28=None if v is None else round(v, 4), rezhim=None if v is None else ("NIZKAYA" if v < POROG else "VYSOKAYA"),
                          porog=POROG, zapisano_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
    if novye:
        ZH.parent.mkdir(parents=True, exist_ok=True)
        with ZH.open("a") as f:
            for z in novye: f.write(json.dumps(z, ensure_ascii=False) + "\n")
    return {"novyh": len(novye), "posledniy": novye[-1] if novye else None}


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
