#!/usr/bin/env python3
"""binance_d1_vpered.py — хук сторожа: ежедневное продолжение дневных данных Binance после архива (20.10.2026).

Архив `data/binance_kity/{klines,taker,spot_taker}` заморожен манифестом (sha файлов) и НЕ меняется. Новые закрытые дни
UTC пишутся отдельно, только дописыванием, в `data/binance_d1_vpered/{klines,taker,spot_taker}/<SYM>.json` в том же
формате: klines [t,o,h,l,c,v], taker/spot_taker [t, quote_volume, taker_buy_quote_volume].
Источник: публичный REST Binance (/fapi/v1/klines — перп, /api/v3/klines — спот), без ключей. Деньги, ордера — нет.
QA паритета: последний день архива (2026-09-30) запрашивается повторно и сверяется с архивом (журнал `parnost`).
Журнал проходов `data/binance_d1_vpered.jsonl`. Пауза между запросами, лимит запросов за проход."""
from __future__ import annotations
import datetime as dt, json, os, sys, time, urllib.error, urllib.request
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]
ARH = LAB / "data" / "binance_kity"
OUT = LAB / "data" / "binance_d1_vpered"
ZH = LAB / "data" / "binance_d1_vpered.jsonl"
SOST = OUT / "sostoyanie.json"
DEN_MS = 86_400_000
MAKS_ZAPROSOV, PAUZA = 400, 0.25
URL = {"perp": "https://fapi.binance.com/fapi/v1/klines", "spot": "https://api.binance.com/api/v3/klines"}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "research-d1/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _jl(p: Path):
    return json.loads(p.read_text()) if p.exists() else []


def _zapisat(p: Path, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp"); tmp.write_text(json.dumps(rows)); os.replace(tmp, p)


def poslednij_ts(vid, sym):
    """Последний день: сначала в продолжении, иначе в архиве."""
    for base in (OUT, ARH):
        v = _jl(base / vid / f"{sym}.json")
        if v:
            return int(v[-1][0])
    return None


def klines(rynok, sym, start_ms, get=_get):
    return get(f"{URL[rynok]}?symbol={sym}&interval=1d&startTime={start_ms}&limit=100")


def razobrat(k, seychas_ms):
    """Только закрытые дни. Возврат (kl [t,o,h,l,c,v], tk [t,qv,tq])."""
    kl, tk = [], []
    for r in k:
        t = int(r[0])
        if t + DEN_MS > seychas_ms:
            continue
        kl.append([t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])])
        tk.append([t, float(r[7]), float(r[10])])
    return kl, tk


def simvoly():
    return sorted(f.stem for f in (ARH / "taker").glob("*.json"))


def prohod(seychas=None, get=_get, maks=MAKS_ZAPROSOV, pauza=PAUZA):
    t0 = seychas or dt.datetime.now(dt.timezone.utc); now_ms = int(t0.timestamp() * 1000)
    vchera = (now_ms // DEN_MS - 1) * DEN_MS
    sost = json.loads(SOST.read_text()) if SOST.exists() else {"net_na_binance": {}, "parnost": None}
    zaprosov, dopisano, oshibki = 0, 0, []
    if (sost.get("parnost") or {}).get("status") not in ("PASS", "FAIL"):   # сеть была недоступна — повторить
        sost["parnost"] = parnost(get)
    for sym in simvoly():
        for rynok, vid in (("perp", "taker"), ("spot", "spot_taker")):
            if sost["net_na_binance"].get(f"{rynok}:{sym}"):
                continue
            last = poslednij_ts(vid, sym)
            if last is None or last >= vchera or zaprosov >= maks:
                continue
            try:
                k = klines(rynok, sym, last + DEN_MS, get); zaprosov += 1
            except urllib.error.HTTPError as e:
                zaprosov += 1
                if e.code == 400:                                      # нет такого символа / делистинг
                    sost["net_na_binance"][f"{rynok}:{sym}"] = t0.date().isoformat()
                else:
                    oshibki.append(f"{rynok}:{sym}: HTTP {e.code}")
                continue
            except Exception as e:
                zaprosov += 1; oshibki.append(f"{rynok}:{sym}: {type(e).__name__}"); continue
            kl, tk = razobrat(k, now_ms)
            kl = [r for r in kl if r[0] > last]; tk = [r for r in tk if r[0] > last]
            if tk:
                p = OUT / vid / f"{sym}.json"; _zapisat(p, _jl(p) + tk); dopisano += len(tk)
                if rynok == "perp":
                    p = OUT / "klines" / f"{sym}.json"; _zapisat(p, _jl(p) + kl)
            if pauza:
                time.sleep(pauza)
    SOST.parent.mkdir(parents=True, exist_ok=True); SOST.write_text(json.dumps(sost, ensure_ascii=False, indent=1))
    z = {"kogda": t0.isoformat(timespec="seconds"), "zaprosov": zaprosov, "dopisano_dney": dopisano,
         "oshibok": len(oshibki), "primery_oshibok": oshibki[:5], "parnost": sost["parnost"],
         "vchera": dt.datetime.fromtimestamp(vchera / 1000, dt.timezone.utc).date().isoformat()}
    with ZH.open("a") as f:
        f.write(json.dumps(z, ensure_ascii=False) + "\n")
    return {k: z[k] for k in ("zaprosov", "dopisano_dney", "oshibok", "vchera")} | {"parnost": (sost["parnost"] or {}).get("status")}


def parnost(get=_get, simv=("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT")):
    """Последний день архива из REST против архива: относительное расхождение quote/taker объёмов."""
    out, hudshee = {}, 0.0
    for s in simv:
        for rynok, vid in (("perp", "taker"), ("spot", "spot_taker")):
            a = _jl(ARH / vid / f"{s}.json")
            if not a:
                continue
            t, qv, tq = a[-1]
            try:
                k = klines(rynok, s, int(t), get)
            except Exception as e:
                out[f"{rynok}:{s}"] = f"oshibka {type(e).__name__}"; continue
            r = next((x for x in k if int(x[0]) == int(t)), None)
            if r is None:
                out[f"{rynok}:{s}"] = "net_dnya"; continue
            d = max(abs(float(r[7]) - qv) / max(qv, 1e-9), abs(float(r[10]) - tq) / max(tq, 1e-9))
            out[f"{rynok}:{s}"] = round(d, 8); hudshee = max(hudshee, d)
    ok = [v for v in out.values() if isinstance(v, float)]
    return {"status": ("PASS" if ok and hudshee <= 1e-6 else ("FAIL" if ok else "UNKNOWN")), "hudshee": hudshee, "po_simvolam": out}


if __name__ == "__main__":
    if "--proba" in sys.argv:                          # одна проверка сети и паритета, без записи
        print(json.dumps(parnost(), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(prohod(), ensure_ascii=False))
