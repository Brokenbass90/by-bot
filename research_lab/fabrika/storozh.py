#!/usr/bin/env python3
"""storozh.py — сторож теней и проверка данных (Factory operational hardening, 13.10.2026). ТОЛЬКО ЧТЕНИЕ.
Ничего не останавливает, не чинит и не трогает правила/исходы. Пишет data/storozh/OTCHET.json и строку в storozh.log.

Проверки:
  ЖУРНАЛЫ (реестр активных: data/storozh/aktivnye.json, иначе список по умолчанию):
    STALE        — файл не обновлялся дольше max(3 × собственного ритма, 30 мин); ритм = медиана интервалов между
                   метками времени в журнале (не зависит от часового пояса); свежесть — по mtime файла.
    DVOYNOY      — одинаковые строки «пульс/проход» с одной меткой времени (признак двух процессов, как Breakout 12.10).
    OSHIBKI      — Traceback / Error / Operation not permitted / СТОП за последние 3 ч журнала.
  ДАННЫЕ:
    breakout_ten/m5/*.jsonl — дубли, порядок, шаг 5 мин.
    единицы времени в jsonl — мкс (> 1e14) вместо мс.
    ликвидации — семантика стороны против цены (доля «long» на баре роста > 0.6 ⇒ SIDE_INVERTED).
Запуск: разово `python3 research_lab/fabrika/storozh.py`; в screen `... storozh.py --cikl` (раз в час).
"""
import datetime as dt, fcntl, json, os, re, statistics, sys, time
from collections import Counter
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent; D = LAB / "data"; OUT = D / "storozh"
TS = re.compile(r"(20\d\d-\d\d-\d\d)[ T](\d\d:\d\d(?::\d\d)?)")
OSH = re.compile(r"Traceback|Error|Operation not permitted|СТОП")
BENIGN = re.compile(r"HTTP Error 404")                     # закрытые рынки Polymarket и т.п. — не сбой
AKTIVNYE = D / "storozh" / "aktivnye.json"              # реестр того, что ДОЛЖНО работать (правится руками)
AKTIVNYE_DEFAULT = ["kripto_atlas", "kity_m3_ten", "kity_bybit_ten", "ten_ETS2S", "yadro_ETS2M", "breakout_ten",
                    "bounce_ten_BOUNCE1", "bounce_ten_BOUNCE1_8", "ten_ATT1", "ten_SILA", "rebal_ten", "poly/snimki"]
OKNO = 3 * 3600                                          # ошибки/двойники смотрим только за последние 3 ч журнала


def metki(lines):
    out = []
    for l in lines:
        m = TS.search(l)
        if m:
            s = m.group(1) + " " + m.group(2) + (":00" if len(m.group(2)) == 5 else "")
            try: out.append(dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S").timestamp())
            except ValueError: pass
    return out


def zhurnal(p, now):
    try: lines = p.read_text(errors="replace").splitlines()[-400:]
    except Exception as e: return dict(status="NECHITAEM", detal=str(e)[:80])
    puls_t = sorted(set(metki([l for l in lines if "пульс" in l or "проход" in l or "снимок" in l])))
    t = puls_t if len(puls_t) >= 4 else sorted(set(metki(lines)))
    d = [b - a for a, b in zip(t, t[1:]) if b - a >= 60]
    ritm = statistics.median(d) if len(d) >= 3 else None
    posl, svezhie, tek = (max(t) if t else None), [], None   # строки последних OKNO секунд (по часам самого журнала)
    for l in lines:
        m = metki([l]); tek = m[0] if m else tek
        if posl is None or (tek is not None and tek >= posl - OKNO): svezhie.append(l)
    lines = svezhie
    vozrast = now - p.stat().st_mtime
    porog = max(3 * ritm, 1800) if ritm else 3 * 3600
    puls = [l for l in lines if TS.search(l) and ("пульс" in l or "проход" in l)]
    dvoy = sum(c - 1 for c in Counter(puls[-60:]).values() if c > 1)
    osh = [l for l in lines if OSH.search(l) and not BENIGN.search(l)]
    flagi = []
    if vozrast > porog: flagi.append("STALE")
    if dvoy: flagi.append("DVOYNOY")
    if osh: flagi.append("OSHIBKI")
    return dict(status="OK" if not flagi else "+".join(flagi), vozrast_min=round(vozrast / 60), ritm_min=round(ritm / 60) if ritm else None,
                porog_min=round(porog / 60), dvoynyh_pulsov=dvoy, oshibok=len(osh), primer=(osh[-1][:140] if osh else None))


def ts_pervyy(obj):
    if isinstance(obj, list) and obj and isinstance(obj[0], (int, float)): return obj[0]
    if isinstance(obj, dict):
        for k in ("ts", "ts_ms", "t", "time", "start"):
            if isinstance(obj.get(k), (int, float)): return obj[k]
    return None


def edinicy(p):
    try:
        with open(p) as f:
            for _, l in zip(range(50), f):
                v = ts_pervyy(json.loads(l)) if l.strip().startswith(("[", "{")) else None
                if v and v > 1e14: return "MKS_VMESTO_MS"
                if v and 1e12 < v < 1e14: return "OK_MS"
    except Exception: return None
    return None


def breakout_m5():
    rez = {}
    for f in sorted((D / "breakout_ten" / "m5").glob("*.jsonl")):
        ts = [json.loads(l)[0] for l in open(f) if l.strip()]
        dub = len(ts) - len(set(ts)); nazad = sum(1 for a, b in zip(ts, ts[1:]) if b <= a)
        dyry = sum(1 for a, b in zip(ts, ts[1:]) if b - a > 300_000)
        if dub or nazad or dyry: rez[f.stem] = dict(dubley=dub, nazad=nazad, dyr=dyry)
    return dict(status="OK" if not rez else "DEFEKT", monet_s_defektom=len(rez), primer=dict(list(rez.items())[:3]))


def likvidacii_storona():
    """Доля корзин с перевесом 'long' на баре РОСТА (BTC, M5 из breakout_ten). Норма < 0.4; > 0.6 ⇒ сторона перевёрнута."""
    lf = ROOT / "runtime" / "liquidations" / "bybit_liquidations.jsonl"; mf = D / "breakout_ten" / "m5" / "BTCUSDT.jsonl"
    if not lf.exists() or not mf.exists(): return dict(status="NET_DANNYH")
    bars = {r[0]: r for r in (json.loads(l) for l in open(mf) if l.strip())}
    kor = {}
    for l in open(lf):
        try: e = json.loads(l)
        except Exception: continue
        if e.get("symbol") != "BTCUSDT": continue
        b = int(e["ts_ms"]) // 300_000 * 300_000; k = kor.setdefault(b, [0.0, 0.0]); k[e.get("side") != "long"] += float(e.get("usd") or 0)
    vverh = [lo > sh for b, (lo, sh) in kor.items() if b in bars and bars[b][4] > bars[b][1] and max(lo, sh) >= 50_000]
    vniz = [lo > sh for b, (lo, sh) in kor.items() if b in bars and bars[b][4] < bars[b][1] and max(lo, sh) >= 50_000]
    if len(vverh) + len(vniz) < 30: return dict(status="MALO_NABLYUDENIY", n=len(vverh) + len(vniz))
    d = sum(vverh) / max(1, len(vverh))
    return dict(status="SIDE_INVERTED" if d > 0.6 else ("OK" if d < 0.4 else "NEYASNO"), dolya_long_na_roste=round(d, 2),
                n=len(vverh) + len(vniz), svezhest_dney=round((time.time() - lf.stat().st_mtime) / 86400, 1))


def zamki():
    """Замки лаунчера edinstvennyy_zapusk: занят = процесс жив. Свободный замок у активной тени — признак смерти."""
    out = {}
    for p in sorted((D / "locks").glob("*.lock")) if (D / "locks").exists() else []:
        fd = os.open(p, os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); fcntl.flock(fd, fcntl.LOCK_UN); out[p.stem] = "SVOBODEN"
        except BlockingIOError:
            out[p.stem] = "ZANYAT"
        finally:
            os.close(fd)
    svobodny = [k for k, v in out.items() if v == "SVOBODEN" and not k.startswith("test")]
    return dict(status="OK" if not svobodny else "WARN", zamki=out, svobodny=svobodny)


def prohod():
    now = time.time()
    spisok = json.loads(AKTIVNYE.read_text()) if AKTIVNYE.exists() else AKTIVNYE_DEFAULT
    zh = {}
    for imya in spisok:
        p = D / f"{imya}.log"
        zh[imya] = zhurnal(p, now) if p.exists() else dict(status="NET_ZHURNALA")
    jsonl = [p for p in D.rglob("*.jsonl") if now - p.stat().st_mtime < 86400 and "m5_bak" not in str(p)][:300]
    ed = {str(p.relative_to(D)): e for p in jsonl for e in [edinicy(p)] if e == "MKS_VMESTO_MS"}
    try:                                                    # Data QA V1 (factory_v3) — единая библиотека проверок
        sys.path.insert(0, str(LAB / "factory_v3")); import data_qa_v1
        dannye = data_qa_v1.proverit_vse()
    except Exception as e:
        dannye = dict(data_qa=dict(status="OSHIBKA_PROVERKI", detal=str(e)[:200]))
    dannye["edinicy_vremeni_jsonl"] = dict(status="OK" if not ed else "DEFEKT", fayly=ed)
    dannye["zamki"] = zamki()
    rez = dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), zhurnaly=zh, dannye=dannye)
    trevogi = [f"{k}: {v['status']}" for k, v in zh.items() if v["status"] != "OK"]
    trevogi += [f"dannye/{k}: {v['status']}" for k, v in rez["dannye"].items() if v["status"] not in ("OK", "NET_DANNYH", "MALO")]
    rez["trevogi"] = trevogi
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "OTCHET.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    with open(OUT / "storozh.log", "a") as f:
        f.write(f"{rez['kogda']} журналов {len(zh)}, тревог {len(trevogi)}: {'; '.join(trevogi)[:900]}\n")
    return rez


if __name__ == "__main__":
    if "--cikl" in sys.argv:
        while True:
            try: prohod()
            except Exception as e:
                OUT.mkdir(parents=True, exist_ok=True)
                with open(OUT / "storozh.log", "a") as f: f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat()} сбой сторожа: {e}\n")
            time.sleep(3600)
    r = prohod(); print("\n".join(r["trevogi"]) or "тревог нет")
