#!/usr/bin/env python3
"""P1 Breakout/Retest — паритет адаптера BREAKOUT_M5_V2 -> event_expansion_retest_long_mtf_v1.

Только механика. Исходы НЕ читаются: нет симуляции выходов, нет цены после known_at плана.
Проверки (на каждый символ, одно окно):
  A  пакет: один длинный префикс, после каждого плана ack и продолжение;
  B  поток: растущий префикс неровными шагами (5м, 15м, 35м, 1ч, сутки-простой),
     состояние сериализуется state_to_json/state_from_json между шагами (рестарт);
  П1 списки планов A и B совпадают побайтно (plan_id связывает источник/агрегацию/уровень/конфиг);
  П2 причинность: для каждого плана known_at <= as_of шага, где он появился (B), и план
     воспроизводится из префикса, обрезанного ровно по known_at (A не видит будущего);
  П3 источник: строки V2 = закрытые M5, без дыр, старт окна на границе H4.
Выход: data/breakout_m5_v2/PARITET.json  (только идентичности и счётчики механики).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from strategies import event_expansion_retest_long_mtf_v1 as mtf  # noqa: E402

DATA = ROOT / "research_lab" / "data" / "breakout_m5_v2"
M5, H4 = 300_000, 14_400_000
PROVIDER_ID = "bybit_v5_kline_linear_m5_breakout_m5_v2"
SHAGI = (1, 12, 48, 288, 7, 96)  # в M5-барах, цикл: 5м, 1ч, 4ч, сутки-простой, 35м, 8ч


def ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)


def zagruzit(sym: str, s_ms: int, po_ms: int) -> list[tuple]:
    rows = []
    for f in sorted((DATA / sym).glob(f"{sym}_*.jsonl.gz")):
        if f.name.endswith(".raw.gz"):
            continue
        with gzip.open(f, "rt") as h:
            for line in h:
                r = json.loads(line)
                ts = int(r[0])
                if s_ms <= ts < po_ms:
                    rows.append((ts, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    rows.sort()
    for a, b in zip(rows, rows[1:]):
        if b[0] - a[0] != M5:
            raise SystemExit(f"{sym}: дыра/дубль {a[0]}->{b[0]}")
    return rows


def plan_obj(p) -> dict:
    d = asdict(p)
    return {k: (v.value if hasattr(v, "value") else v) for k, v in d.items()}


def paket(sym, rows, prov_fp):
    out, state, as_of = [], None, rows[-1][0] + M5
    while True:
        st = mtf.process_closed_m5_prefix(sym, rows, as_of_ms=as_of, provider_identity=PROVIDER_ID,
                                          provider_fingerprint=prov_fp, prior=state)
        state = st.state
        if st.plan is None:
            return out, state
        out.append(plan_obj(st.plan))
        state = mtf.acknowledge_plan(state, st.plan.plan_id)


def potok(sym, rows, prov_fp, start_n):
    cfg = mtf.EventExpansionRetestLongMTFConfigV1()
    out, narusheniy, blob, n, k, vyzovov = [], 0, None, start_n, 0, 0
    while True:
        prior = None if blob is None else mtf.state_from_json(
            blob, expected_provider_fingerprint=prov_fp, expected_cfg=cfg)
        pref = rows[:n]
        as_of = pref[-1][0] + M5
        st = mtf.process_closed_m5_prefix(sym, pref, as_of_ms=as_of, provider_identity=PROVIDER_ID,
                                          provider_fingerprint=prov_fp, prior=prior)
        vyzovov += 1
        state = st.state
        if st.plan is not None:
            if st.plan.known_at_ms > as_of:
                narusheniy += 1
            out.append(plan_obj(st.plan))
            state = mtf.acknowledge_plan(state, st.plan.plan_id)
            blob = mtf.state_to_json(state)
            continue  # тот же as_of: дочитать хвост после плана
        blob = mtf.state_to_json(state)
        if n >= len(rows):
            return out, narusheniy, vyzovov, state
        n = min(len(rows), n + SHAGI[k % len(SHAGI)])
        k += 1


def obrezka(sym, rows, prov_fp, plans):
    """Каждый план воспроизводится из префикса, обрезанного по его known_at."""
    plohih = 0
    t0 = rows[0][0]
    for p in plans:
        n = (p["known_at_ms"] - t0) // M5
        sub, _ = paket(sym, rows[:n], prov_fp)
        if not sub or sub[-1] != p:
            plohih += 1
    return plohih


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s", default="2026-07-11")
    ap.add_argument("--po", default="2026-10-11")
    ap.add_argument("--simvoly", default="")
    ap.add_argument("--vyhod", default="")
    a = ap.parse_args()
    s_ms, po_ms = ms(a.s), ms(a.po)
    if s_ms % H4:
        raise SystemExit("старт окна не на границе H4")
    man = DATA / "MANIFEST.json"
    prov_fp = hashlib.sha256(man.read_bytes()).hexdigest()
    audit = json.loads((DATA / "AUDIT.json").read_text())
    simvoly = a.simvoly.split(",") if a.simvoly else sorted(audit["simvoly"])
    rez = {"chto": "паритет адаптера BREAKOUT_M5_V2 -> event_expansion_retest_long_mtf_v1 (механика, без исходов)",
           "okno": [a.s, a.po], "provider_identity": PROVIDER_ID, "provider_fingerprint_manifest_sha256": prov_fp,
           "strategiya_sha256": hashlib.sha256((ROOT / "strategies/event_expansion_retest_long_mtf_v1.py").read_bytes()).hexdigest(),
           "config_sha256": mtf.EventExpansionRetestLongMTFConfigV1().fingerprint,
           "simvoly": {}, "status": None}
    vse_ok = True
    for sym in simvoly:
        t = time.time()
        rows = zagruzit(sym, s_ms, po_ms)
        if not rows or rows[0][0] != s_ms:
            rez["simvoly"][sym] = {"status": "BLOCKED_DATA", "prichina": "нет полного окна"}
            vse_ok = False
            continue
        a_pl, a_st = paket(sym, rows, prov_fp)
        b_pl, narush, vyz, b_st = potok(sym, rows, prov_fp, start_n=48)
        plohih = obrezka(sym, rows, prov_fp, a_pl)
        sob_ok = (a_st.seen_event_ids == b_st.seen_event_ids
                  and a_st.consumed_retest_ids == b_st.consumed_retest_ids
                  and a_st.acknowledged_plan_ids == b_st.acknowledged_plan_ids)
        ok = (a_pl == b_pl) and sob_ok and narush == 0 and plohih == 0
        vse_ok &= ok
        rez["simvoly"][sym] = {
            "strok_m5": len(rows), "sobytiy": len(a_st.seen_event_ids),
            "retestov": len(a_st.consumed_retest_ids), "sovpadenie_sobytiy": sob_ok,
            "planov_paket": len(a_pl), "planov_potok": len(b_pl),
            "vyzovov_potok": vyz, "sovpadenie_planov": a_pl == b_pl,
            "plan_ids_sha256": hashlib.sha256(json.dumps([p["plan_id"] for p in a_pl]).encode()).hexdigest(),
            "narusheniy_known_at": narush, "ne_vosproizvelis_pri_obrezke": plohih,
            "status": "PASS" if ok else "FAIL", "sek": round(time.time() - t, 1)}
        print(sym, rez["simvoly"][sym], flush=True)
    vsego_planov = sum(v.get("planov_paket", 0) for v in rez["simvoly"].values())
    if vse_ok and vsego_planov < 10:
        vse_ok = None  # паритет на пустом множестве не доказывает механику
    rez["vsego_planov"] = vsego_planov
    rez["status"] = "PASS" if vse_ok else ("UNKNOWN" if vse_ok is None else "FAIL")
    (DATA / (a.vyhod or "PARITET.json")).write_text(json.dumps(rez, ensure_ascii=False, indent=1))
    print("ПАРИТЕТ:", rez["status"])


if __name__ == "__main__":
    main()
