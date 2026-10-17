#!/usr/bin/env python3
"""liq_v2_1_konveyer.py — обработка ленты ликвидаций V2.1 для LIQ_OTSKOK_4H_V2 (prereg + поправка A1). 17.10.2026.

Только ЧТЕНИЕ снимков Codex (`data/liq_v2_1/normalized-*.jsonl`, неизменяемые). Цены и исходы НЕ читаются.
Шаги: фильтр эпохи → дедупликация по raw_item_canonical_sha256 → QA (поздние, UNKNOWN-часы) → часовые суммы →
события BASE по prereg → ворота источника → `data/liq_v2_1/VOROTA.json` и `sobytiya_BASE.jsonl`.

Метки событий (не смешивать):
  V_EPOHE_RETRO — событие найдено по суточному снимку ПОСЛЕ факта. Это не проспективное решение: на нём можно считать
                  ворота источника, но не CONFIRM. Проспективные решения требуют живой ленты (решение до h+1ч+2мин).
"""
import glob, json, sys
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parents[1]; D = LAB / "data/liq_v2_1"
H, MIN, DEN = 3_600_000, 60_000, 86_400_000
EPOHA_MANIFEST = "46895caaef1e1689cd4224a544bb3e3287f41ef8a8a4ad702fd403cdcc2a4ddd"
EPOHA_START_MS = 1791966934223            # 2026-10-14 08:35:34.223 UTC (квитанция Codex)
PROGREV = 14 * DEN; POROG_USD = 50_000.0; KRAT = 3.0; PERC = 99.0; OPOZD = 2 * MIN
VOROTA = dict(min_sobytiy=200, min_sutok=20, min_monet=15, maks_dolya_pozdnih=0.05)


def zagruzit(puti):
    vse, dubl, chuzhie = {}, 0, 0
    for p in puti:
        for s in Path(p).read_text().splitlines():
            if not s.strip(): continue
            z = json.loads(s)
            if z.get("source_manifest_sha256") != EPOHA_MANIFEST: chuzhie += 1; continue
            k = z["raw_item_canonical_sha256"]
            if k in vse: dubl += 1; continue
            vse[k] = z
    return list(vse.values()), dubl, chuzhie


def sobytiya(zapisi, do_ms):
    """BASE по prereg. do_ms — момент, до которого лента известна (последний снимок)."""
    pozd = [z for z in zapisi if z["t_available_ms"] - z["ts_ms"] > OPOZD]
    neizv = [z for z in zapisi if z.get("causal_clock_status", "").startswith("UNKNOWN")]
    ok = [z for z in zapisi if z not in neizv]
    chas = {}
    for z in ok:
        h = z["ts_ms"] // H * H; key = (z["symbol"], h)
        a = chas.setdefault(key, [0.0, 0.0, 0])
        if z["t_available_ms"] <= h + H + 2 * MIN:          # причинность: успело к решению
            a[0 if z["side"] == "long" else 1] += float(z["usd"])
        else:
            a[2] += 1
    out = []
    monety = sorted({s for s, _ in chas})
    h0 = EPOHA_START_MS // H * H + H                       # первый полный час эпохи
    for s in monety:
        for h in range(h0 + PROGREV, do_ms - H + 1, H):
            if h + H + 2 * MIN > do_ms: break
            ist = range(h - PROGREV, h, H)
            L = np.array([[chas.get((s, x), (0, 0))[0], chas.get((s, x), (0, 0))[1]] for x in ist])
            ll, ls = chas.get((s, h), (0.0, 0.0, 0))[:2]
            for st, cur, opp, col in (("LONG_LIQ", ll, ls, 0), ("SHORT_LIQ", ls, ll, 1)):
                if cur >= POROG_USD and cur >= np.percentile(L[:, col], PERC) and cur >= KRAT * opp:
                    out.append(dict(symbol=s, chas_ms=h, tip=st, usd=round(cur, 2), protiv_usd=round(opp, 2),
                                    reshenie_ms=h + H + 2 * MIN, storona=1 if st == "LONG_LIQ" else -1, metka="V_EPOHE_RETRO"))
    return out, dict(zapisey=len(zapisi), pozdnih=len(pozd), unknown_chasy=len(neizv),
                     dolya_pozdnih=round(len(pozd) / max(1, len(zapisi)), 4))


def vorota(sob, qa, polnota="UNKNOWN_NO_SEQUENCE_OR_BACKFILL"):
    sut = len({e["chas_ms"] // DEN for e in sob}); mon = len({e["symbol"] for e in sob})
    if qa["dolya_pozdnih"] > VOROTA["maks_dolya_pozdnih"]: st = "FAIL_QA"
    elif len(sob) >= VOROTA["min_sobytiy"] and sut >= VOROTA["min_sutok"] and mon >= VOROTA["min_monet"]: st = "PASS"
    else: st = "NOT_YET"
    return dict(status=st, sobytiy_BASE=len(sob), sutok=sut, monet=mon, qa=qa, polnota_lenty=polnota,
                progrev_do_ms=EPOHA_START_MS + PROGREV, trebovaniya=VOROTA)


def prohod(puti=None):
    """Хук сторожа: пересчёт ворот по всем снимкам (дёшево; цены и исходы не читаются)."""
    puti = puti or sorted(glob.glob(str(D / "normalized-*.jsonl")))
    if not puti: return dict(status="NET_SNIMKOV")
    zap, dubl, chuzhie = zagruzit(puti)
    do_ms = max(z["t_available_ms"] for z in zap) if zap else EPOHA_START_MS
    sob, qa = sobytiya(zap, do_ms); qa.update(dubley_svernuto=dubl, chuzhaya_epoha=chuzhie, snimkov=len(puti))
    v = vorota(sob, qa); v["lenta_do_ms"] = do_ms
    D.mkdir(parents=True, exist_ok=True)
    (D / "VOROTA.json").write_text(json.dumps(v, ensure_ascii=False, indent=1))
    with open(D / "sobytiya_BASE.jsonl", "w") as f:
        for e in sob: f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return dict(status=v["status"], sobytiy=v["sobytiy_BASE"], sutok=v["sutok"], monet=v["monet"])


if __name__ == "__main__":
    puti = sys.argv[1:] or sorted(glob.glob(str(D / "normalized-*.jsonl")))
    if not puti: print(json.dumps(dict(status="NET_SNIMKOV", put=str(D)), ensure_ascii=False)); sys.exit(0)
    zap, dubl, chuzhie = zagruzit(puti)
    do_ms = max(z["t_available_ms"] for z in zap) if zap else EPOHA_START_MS
    sob, qa = sobytiya(zap, do_ms); qa.update(dubley_svernuto=dubl, chuzhaya_epoha=chuzhie, snimkov=len(puti))
    v = vorota(sob, qa); v["lenta_do_ms"] = do_ms
    D.mkdir(parents=True, exist_ok=True)
    (D / "VOROTA.json").write_text(json.dumps(v, ensure_ascii=False, indent=1))
    with open(D / "sobytiya_BASE.jsonl", "w") as f:
        for e in sob: f.write(json.dumps(e, ensure_ascii=False) + "\n")
    print(json.dumps(v, ensure_ascii=False))
