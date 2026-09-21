#!/usr/bin/env python3
"""begun_bull.py — переходник для crypto_bull_continuation_v1 (Bull Continuation).

Ничего в стратегии и контракте исполнения не меняется. Используются ровно
те файлы, хеши которых закреплены в предрегистрации Codex от 1 сентября:
  strategies/event_expansion_retest_long_mtf_v1.py   2b3cb32d…
  bot/event_long_execution_v1.py                     8179b14f…
  bot/level_snapshot_v1.py                           b776d2db…
Прогонщик сверяет хеши перед стартом и отказывается работать при расхождении.

Сигналы: process_closed_m5_prefix по непрерывным кускам M5 (кусок начинается
на границе H4, как требует контракт); каждый план подтверждается
acknowledge_plan, затем следующий проход с сохранённым состоянием.
Исполнение: simulate_frozen_long_plan_v1, сценарий base (6+2 б.п. на сторону).
Фандинг НЕ передаётся: удержание не больше 8 часов (96×M5), максимум одно
начисление. Это записано как ограничение.
Контроль: для каждого плана 20 случайных входов в той же монете, в тот же
30-дневный месяц, на границе M15, с тем же расстоянием до стопа в долях цены,
через тот же simulate_frozen_long_plan_v1.

Окна обнаружения: O2 = 2024-03…2024-12, O1 = 2025-01…2025-09 (M5 preholdout).
Подтверждение: M5 после 2025-10-01 из data/m5_posle/ (пока нет — ждём данных).
"""
from __future__ import annotations
import argparse, glob, hashlib, json, math, os, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np

DIR = Path(__file__).resolve().parent; LAB = DIR.parent; ROOT = LAB.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(DIR))
M5, M15, H4 = 300_000, 900_000, 14_400_000
ZAKREP = {"strategies/event_expansion_retest_long_mtf_v1.py": "2b3cb32d32a87c62",
          "bot/event_long_execution_v1.py": "8179b14f5dccefb2",
          "bot/level_snapshot_v1.py": "b776d2db30b35063"}
OKNA_DISC = {"O1": (1735689600000, 1759276800000), "O2": (1709251200000, 1735689600000)}
OKNO_PODTV = {"VSE": (1759276800000, 10**14)}
PAPKA = {"discovery": LAB / "data/bybit_wide137_m5_preholdout_20240301_20250930",
         "confirmation": LAB / "data/m5_posle"}
DRAWS = 20


def proverit_heshi():
    for f, h in ZAKREP.items():
        got = hashlib.sha256((ROOT / f).read_bytes()).hexdigest()[:16]
        if got != h:
            raise SystemExit(f"ХЕШ НЕ СОВПАЛ: {f} {got} вместо {h} — прогон запрещён")


def kuski(rows):
    """непрерывные куски, каждый начинается на границе H4"""
    out, cur = [], []
    for r in rows:
        if cur and r[0] - cur[-1][0] != M5:
            out.append(cur); cur = []
        if not cur and r[0] % H4:
            continue
        cur.append(r)
    if cur:
        out.append(cur)
    return [k for k in out if len(k) >= 3000]


KUSOK, PROGREV_M5 = 20000, 3000        # ≈70 дней + ≈10 дней прогрева


def narezat(k_rows):
    """Режем длинный непрерывный кусок на окна KUSOK с прогревом PROGREV_M5.
    Планы из зоны прогрева отбрасываются: их находит предыдущее окно.
    Эквивалентность с одним проходом проверена (--proverka_narezki)."""
    out, start = [], 0
    while start < len(k_rows):
        a = max(0, start - PROGREV_M5)
        while a < start and k_rows[a][0] % H4:
            a += 1
        if start - a < PROGREV_M5 // 2 and start > 0:
            a = max(0, start - PROGREV_M5)
            while k_rows[a][0] % H4:
                a -= 1
        out.append((a, start, min(len(k_rows), start + KUSOK)))
        start += KUSOK
    return out


def plany(sym, k_rows, fpr, schema, rezat=True):
    from strategies.event_expansion_retest_long_mtf_v1 import process_closed_m5_prefix, acknowledge_plan
    res, sboi = [], 0
    for a, lo, hi in (narezat(k_rows) if rezat else [(0, 0, len(k_rows))]):
        seg = k_rows[a:hi]; st = None; gran = k_rows[lo][0]
        while True:
            try:
                s = process_closed_m5_prefix(sym, seg, as_of_ms=seg[-1][0] + M5, provider_identity=schema,
                                             provider_fingerprint=fpr, prior=st)
            except Exception:
                sboi += 1; break
            st = s.state
            if s.plan is None:
                break
            st = acknowledge_plan(st, s.plan.plan_id)
            if s.plan.valid_from_m5_open_ts_ms >= gran:
                res.append(s.plan)
    return res, sboi


def odin_simvol(args):
    fp, etap, seed = args
    from strategies.event_expansion_retest_long_mtf_v1 import STRATEGY_NAME
    from bot.event_long_execution_v1 import make_frozen_long_plan_v1, simulate_frozen_long_plan_v1
    d = json.load(open(fp)); sym = d["symbol"]; fpr = d["payload_sha256"]
    rows = [[int(r["ts_ms"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
             float(r["volume"])] for r in d["records"]]
    rng = np.random.default_rng(seed)
    real, ctrl, sboi = [], [], 0

    def sim(plan, k_rows, i0):
        sl = k_rows[i0:i0 + 100]
        rc = simulate_frozen_long_plan_v1(plan, sl, as_of_ms=sl[-1][0] + M5, scenario="base")
        return rc.net_r if rc.entry_ts is not None else None

    for k_rows in kuski(rows):
        idx = {r[0]: i for i, r in enumerate(k_rows)}
        pl, sb = plany(sym, k_rows, fpr, d.get("schema_id", "bybit_public_m5"))
        sboi += sb
        for p in pl:
            i0 = idx.get(p.valid_from_m5_open_ts_ms)
            if i0 is None or i0 + 97 >= len(k_rows):
                continue
            try:
                fz = make_frozen_long_plan_v1(event_id=p.event_id, level_id=p.level_id, strategy=STRATEGY_NAME,
                                              symbol=sym, signal_open_ts=p.bos_bar_open_ts_ms,
                                              entry_reference=p.entry_reference, frozen_stop=p.stop_price,
                                              source_fingerprint=p.m15_source_sha256)
                r = sim(fz, k_rows, i0)
            except Exception:
                sboi += 1; continue
            if r is None:
                continue
            stop_frac = (p.entry_reference - p.stop_price) / p.entry_reference
            mes = p.valid_from_m5_open_ts_ms // (30 * 86400000)
            pool = [i for i, rr in enumerate(k_rows) if rr[0] % M15 == 0 and rr[0] // (30 * 86400000) == mes
                    and 4 <= i < len(k_rows) - 100]
            cr = []
            for _ in range(DRAWS if len(pool) >= 5 else 0):
                j = int(rng.choice(pool)); ref = k_rows[j][1]
                try:
                    fzc = make_frozen_long_plan_v1(event_id=f"ctrl{j}", level_id="ctrl", strategy=STRATEGY_NAME,
                                                   symbol=sym, signal_open_ts=k_rows[j][0] - M15,
                                                   entry_reference=ref, frozen_stop=ref * (1 - stop_frac),
                                                   source_fingerprint=p.m15_source_sha256)
                    x = sim(fzc, k_rows, j)
                except Exception:
                    x = None
                cr.append(x)
            real.append((p.valid_from_m5_open_ts_ms, r)); ctrl.append(cr)
    return sym, real, ctrl, sboi


def okno(R, C):
    R = np.array(R)
    if len(R) < 2:
        return {"n": int(len(R)), "kontrol_sobran": False}
    by_draw = [[c[i] for c in C if i < len(c) and c[i] is not None] for i in range(DRAWS)]
    cm = np.array([np.mean(x) for x in by_draw if len(x) > 10])
    if len(cm) < 5:
        return {"n": int(len(R)), "kontrol_sobran": False}
    edge = float(R.mean() - cm.mean()); se = math.sqrt(R.std(ddof=1) ** 2 / len(R) + cm.var(ddof=1))
    return {"n": int(len(R)), "kontrol_sobran": True, "mean": float(R.mean()), "ctrl": float(cm.mean()),
            "edge": edge, "se": se, "z": edge / se if se > 0 else 0.0, "summa_R": float(R.sum())}


def _proverka(args):
    fp, = args
    d = json.load(open(fp)); sym = d["symbol"]
    rows = [[int(r["ts_ms"]), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
             float(r["volume"])] for r in d["records"]]
    A, B = set(), set()
    for k in kuski(rows):
        a, _ = plany(sym, k, d["payload_sha256"], d.get("schema_id", "bybit_public_m5"), rezat=False)
        b, _ = plany(sym, k, d["payload_sha256"], d.get("schema_id", "bybit_public_m5"), rezat=True)
        A |= {(x.valid_from_m5_open_ts_ms, round(x.stop_price, 10)) for x in a}
        B |= {(x.valid_from_m5_open_ts_ms, round(x.stop_price, 10)) for x in b}
    return sym, sorted(A), sorted(B)


def proverka_narezki(simvoly, vyhod, potokov):
    """ПАРИТЕТ: планы при нарезке окнами должны совпасть с одним проходом целиком."""
    files = [str(PAPKA["discovery"] / s / f"{s}.json") for s in simvoly]
    rez = {"tip": "proverka_narezki", "simvoly": {}, "sovpadayut": True, "planov": 0}
    with ProcessPoolExecutor(max_workers=potokov) as ex:
        for sym, A, B in ex.map(_proverka, [(f,) for f in files]):
            ok = A == B; rez["sovpadayut"] &= ok; rez["planov"] += len(A)
            rez["simvoly"][sym] = {"odin_prohod": len(A), "narezka": len(B), "sovpadayut": ok,
                                   "tolko_v_odnom": [list(x) for x in sorted(set(A) - set(B))][:5],
                                   "tolko_v_narezke": [list(x) for x in sorted(set(B) - set(A))][:5]}
            print(f"... {sym}: один проход {len(A)}, нарезка {len(B)}, {'совпадают' if ok else 'РАЗНЫЕ'}", flush=True)
    tmp = Path(vyhod + ".tmp"); tmp.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); tmp.replace(vyhod)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--param", required=True); ap.add_argument("--vyhod", required=True)
    ap.add_argument("--limit", type=int, default=0); ap.add_argument("--potokov", type=int, default=0)
    a = ap.parse_args(); p = json.loads(a.param); etap = p.get("etap", "discovery")
    proverit_heshi()
    potokov = a.potokov or max(1, min(4, (os.cpu_count() or 2) - 2))
    if p.get("proverka_narezki"):
        return proverka_narezki(p["simvoly"], a.vyhod, potokov)
    files = sorted(glob.glob(str(PAPKA[etap] / "*" / "*USDT.json")))
    if a.limit:
        files = files[: a.limit]
    OK = OKNA_DISC if etap == "discovery" else OKNO_PODTV
    R = {w: [] for w in OK}; C = {w: [] for w in OK}; sboi = 0
    zadachi = [(f, etap, 7 + i) for i, f in enumerate(files)]
    with ProcessPoolExecutor(max_workers=potokov) as ex:
        for k, (sym, real, ctrl, sb) in enumerate(ex.map(odin_simvol, zadachi)):
            sboi += sb
            for (ts, r), cr in zip(real, ctrl):
                for w, (lo, hi) in OK.items():
                    if lo <= ts < hi:
                        R[w].append(r); C[w].append(cr)
            print(f"... {k+1}/{len(files)} {sym}: планов {len(real)}", flush=True)
    rez = {"param": p, "etap": etap, "monet": len(files), "sboev": sboi,
           "ogranichenie": "фандинг не передан (удержание ≤ 8 ч)",
           "okna": {w: okno(R[w], C[w]) for w in OK}}
    tmp = Path(a.vyhod + ".tmp"); tmp.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); tmp.replace(a.vyhod)
    print("готово, сделок по окнам:", {w: x["n"] for w, x in rez["okna"].items()}, "сбоев:", sboi)


if __name__ == "__main__":
    main()
