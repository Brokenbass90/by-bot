#!/usr/bin/env python3
"""data_qa_v1.py — Data QA V1 (Factory V3, слой 0). 13.10.2026. ТОЛЬКО ЧТЕНИЕ, без доходностей и решений.

Ловит классы дефектов, которые реально стоили нам денег/времени:
  • дубли / обратный ход / дыры времени      (Breakout 12.10: двойной процесс → 13 058 дублей → сутки слепоты)
  • единицы времени мкс вместо мс              (спот Binance с 2025-01)
  • семантика стороны против цены              (ликвидации: Bybit S=Buy ⇒ лонг; сборщик писал наоборот)
  • вырожденная экономика                       (SF3: плечо 6068, +373R; ворота A7 — плечо ≤ 100)
  • перекрещенный стакан / цены вне диапазона  (атлас издержек, Polymarket)
  • застывший источник                          (последняя запись старше допустимого)
Реестр источников ISTOCHNIKI — единая точка: новый сборщик/тень = одна запись. Большие файлы читаются с хвоста.

    python3 research_lab/factory_v3/data_qa_v1.py          # отчёт → data/factory_v3/data_qa_otchet.json
"""
import glob, json, math, os, time
from collections import Counter, defaultdict
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent; D = LAB / "data"
M5 = 300_000


# ---------- примитивы (чистые функции, покрыты тестами) ----------
def edinicy(ts):
    v = [x for x in ts if isinstance(x, (int, float)) and x > 0]
    if not v: return "?"
    m = sorted(v)[len(v) // 2]
    return "us" if m > 1e14 else ("ms" if m > 1e11 else ("s" if m > 1e8 else "?"))


def ryad(ts, shag=None):
    """Дубли, обратный ход, дыры (если задан шаг)."""
    dub = len(ts) - len(set(ts))
    nazad = sum(1 for a, b in zip(ts, ts[1:]) if b < a)
    dyry = sum(1 for a, b in zip(ts, ts[1:]) if shag and b - a > shag)
    return dict(dubley=dub, nazad=nazad, dyr=dyry)


def svezhest_min(ts_ms, now=None):
    return round(((now or time.time() * 1000) - ts_ms) / 60000, 1) if ts_ms else None


def storona_protiv_ceny(korziny, bary, min_usd=50_000):
    """korziny: {bucket_ts: (usd_long, usd_short)} где 'long' = ликвидирован лонг (должен быть на баре ПАДЕНИЯ);
    bary: {ts: (o, c)}. Возвращает долю корзин с перевесом long на барах роста (норма < 0.4; > 0.6 ⇒ перевёрнуто)."""
    vverh = [lo > sh for b, (lo, sh) in korziny.items() if b in bary and bary[b][1] > bary[b][0] and max(lo, sh) >= min_usd]
    if len(vverh) < 15: return dict(status="MALO", n=len(vverh))
    d = sum(vverh) / len(vverh)
    return dict(status="SIDE_INVERTED" if d > 0.6 else ("OK" if d < 0.4 else "NEYASNO"), dolya_long_na_roste=round(d, 2), n=len(vverh))


def hvost(p, n=20000):
    """Последние n строк файла без чтения целиком."""
    with open(p, "rb") as f:
        f.seek(0, os.SEEK_END); size = f.tell(); blok = min(size, max(65536, n * 400))
        f.seek(size - blok); data = f.read().decode("utf-8", "replace").splitlines()
    if blok < size: data = data[1:]
    out = []
    for l in data[-n:]:
        try: out.append(json.loads(l))
        except Exception: pass
    return out


# ---------- проверки источников ----------
def q_m5_papka(cfg):
    defekt = {}; posl = 0
    for f in sorted(glob.glob(str(D / cfg["papka"] / "*.jsonl"))):
        with open(f) as fh: rows = [json.loads(l) for l in fh if l.strip()]
        ts = [r[0] for r in rows]; posl = max(posl, ts[-1] if ts else 0)
        r = ryad(ts, M5); r["edinicy"] = edinicy(ts)
        plohie = sum(1 for x in rows if not (x[3] <= min(x[1], x[4]) and x[2] >= max(x[1], x[4])))
        if r["dubley"] or r["nazad"] or r["dyr"] or r["edinicy"] != "ms" or plohie:
            defekt[Path(f).stem] = dict(r, ohlc_narusheniy=plohie)
    return dict(status="DEFEKT" if defekt else "OK", monet_s_defektom=len(defekt), primer=dict(list(defekt.items())[:3]), posl_ms=posl)


def q_atlas(cfg):
    f = sorted(glob.glob(str(D / "kripto_atlas" / "sbor_*.jsonl")))
    if not f: return dict(status="NET_DANNYH")
    rows = hvost(f[-1], 30000); po = defaultdict(list)
    for r in rows: po[r["s"]].append(r["t"])
    perekr = sum(1 for r in rows if not (0 < r["b"] <= r["a"]))
    nazad = sum(ryad(v)["nazad"] for v in po.values())
    return dict(status="DEFEKT" if perekr or nazad else "OK", strok=len(rows), perekreshchen=perekr, nazad=nazad,
                edinicy=edinicy([r["t"] for r in rows]), posl_ms=max(r["t"] for r in rows) if rows else None)


def q_poly(cfg):
    f = sorted(glob.glob(str(D / "poly" / "snimki" / "*.jsonl")))
    if not f: return dict(status="NET_DANNYH")
    rows = hvost(f[-1], 5000); vne, perekr = 0, 0
    for r in rows:
        b = [float(x["price"]) for x in (r.get("bids") or []) if isinstance(x, dict) and "price" in x]
        a = [float(x["price"]) for x in (r.get("asks") or []) if isinstance(x, dict) and "price" in x]
        vne += any(not 0 <= p <= 1 for p in b + a)
        perekr += bool(b and a and max(b) > min(a))
    return dict(status="DEFEKT" if vne or perekr else "OK", strok=len(rows), cena_vne_0_1=vne, perekreshchen=perekr,
                edinicy=edinicy([r["t"] for r in rows]), posl_ms=max(r["t"] for r in rows) if rows else None)


def q_ishody(cfg):
    p = D / cfg["fayl"]
    if not p.exists(): return dict(status="NET_DANNYH")
    rows = hvost(p, 20000); kl = cfg.get("kluch", ("id",))
    fin = [r for r in rows if not (cfg.get("tolko_final") and r.get("zhdyot"))]   # «ждёт» + итог — норма; два итога — дефект
    ids = [tuple(r.get(k) for k in kl) for r in fin if all(r.get(k) is not None for k in kl)]
    R = [r.get("R") for r in rows if r.get("R") is not None]
    plohie = sum(1 for x in R if not math.isfinite(x) or abs(x) > cfg.get("max_abs_R", 30))
    plecho = sum(1 for r in rows if (r.get("plecho") or 0) > 100)
    dub = len(ids) - len(set(ids))
    st = "DEFEKT" if (plohie or dub) else ("WARN" if plecho else "OK")
    return dict(status=st, strok=len(rows), R_vyrozhdennyh=plohie, plecho_bolshe_100=plecho, dubley_id=dub,
                edinicy=edinicy([r.get("ts") for r in rows]), posl_ms=max((r.get("zapisano") or r.get("ts") or 0) for r in rows) if rows else None)


def q_likvidacii(cfg):
    lf = ROOT / "runtime" / "liquidations" / "bybit_liquidations.jsonl"; mf = D / "breakout_ten" / "m5" / "BTCUSDT.jsonl"
    if not lf.exists() or not mf.exists(): return dict(status="NET_DANNYH")
    with open(mf) as fh: bary = {r[0]: (r[1], r[4]) for r in (json.loads(l) for l in fh if l.strip())}
    kor = {}
    for e in hvost(lf, 200000):
        if e.get("symbol") != "BTCUSDT": continue
        b = int(e["ts_ms"]) // M5 * M5; k = kor.setdefault(b, [0.0, 0.0]); k[e.get("side") != "long"] += float(e.get("usd") or 0)
    r = storona_protiv_ceny({b: tuple(v) for b, v in kor.items()}, bary)
    posl = hvost(lf, 1)
    r["posl_ms"] = int(posl[-1]["ts_ms"]) if posl else None
    return r


ISTOCHNIKI = [
    dict(imya="breakout_ten_m5", f=q_m5_papka, papka="breakout_ten/m5", max_vozrast_min=130),
    dict(imya="kripto_atlas", f=q_atlas, max_vozrast_min=60),
    dict(imya="poly_snimki", f=q_poly, max_vozrast_min=60),
    dict(imya="ETS2M_ishody", f=q_ishody, fayl="yadro/ETS2M/ishody.jsonl", kluch=("id", "dvigatel"), max_vozrast_min=240),
    dict(imya="ETS2S_signaly", f=q_ishody, fayl="ten_ETS2S.jsonl", kluch=("ts", "sym", "side"), tolko_final=True, max_vozrast_min=360),
    dict(imya="ATT1_signaly", f=q_ishody, fayl="ten_ATT1.jsonl", kluch=("ts", "sym", "side"), tolko_final=True, max_vozrast_min=360),
    dict(imya="likvidacii_bybit", f=q_likvidacii, max_vozrast_min=None),   # сборщик остановлен 13.09; ждём V2 от Codex
]


def proverit_vse(now_ms=None):
    now_ms = now_ms or time.time() * 1000; out = {}
    for c in ISTOCHNIKI:
        try: r = c["f"](c)
        except Exception as e: r = dict(status="OSHIBKA_PROVERKI", detal=f"{type(e).__name__}: {e}"[:200])
        v = svezhest_min(r.get("posl_ms"), now_ms)
        if v is not None:
            r["vozrast_min"] = v
            if c.get("max_vozrast_min") and v > c["max_vozrast_min"] and r["status"] == "OK": r["status"] = "STALE"
        out[c["imya"]] = r
    return out


if __name__ == "__main__":
    rez = proverit_vse(); (D / "factory_v3").mkdir(parents=True, exist_ok=True)
    (D / "factory_v3" / "data_qa_otchet.json").write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    for k, v in rez.items(): print(f"{k:20s} {v['status']:16s} {json.dumps({x: y for x, y in v.items() if x not in ('status', 'primer')}, ensure_ascii=False)[:150]}")
