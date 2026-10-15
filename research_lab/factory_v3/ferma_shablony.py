#!/usr/bin/env python3
"""ferma_shablony.py — интерфейс шаблонов экспериментов Factory V3 (P3). 13.10.2026.

Шаблон = функция f(parametry, dostup) -> dict(t, n, metrika), которую ферма вызывает внутри зарегистрированной попытки.
Окно данных шаблон берёт ТОЛЬКО из dostup (t0..t1); набор признаков — закрытый словарь PRIZNAKI (новый признак = новая
строка кода + запись в реестре, а не параметр-строка от ИИ). Механика сделки, издержки, фандинг и статистика — дословно
из замороженных судей (kity_sudya.sdelka, discovery_paket1.itog с t Ньюи–Уэста лаг 1), поэтому шаблон воспроизводит их числа.

Шаблоны:
  xs_nedelya_binance — недельная кросс-секция PIT топ-50 по OI Binance (скелет KITY M3 / SPOT_POTOK):
      parametry = {"priznak": "m3_perp" | "spot" | "spot_minus_perp" | "m3_vsplesk" | "pogloshchenie" | glubina_*, "znak": +1 | -1,
                   "zaderzhka": 1 (по умолчанию, вход закрытием d) | 0 (закрытием d−1) | 2 (закрытием d+1)}
      m3_vsplesk (14.10): доля тейкера-покупателя на перпе дня d−1 минус её среднее за 28 предыдущих дней монеты (≥ 20 дней).
      cb_premiya (15.10): премия Coinbase USD к перпу Binance дня d−1 минус её среднее за 28 предыдущих дней (≥ 20);
      min_strok (по умолч. 30) и dolya (по умолч. децили) — параметры заявки, у известных ответов не меняются.
      pogloshchenie (14.10, составной): внутри недели остаток z(доход дня d−1) после проекции на z(доля тейкера дня d−1) — часть
      движения цены, НЕ объяснённая потоком (поглощение пассивной стороной); ортогонален KITY m3 по построению; вход как у KITY.
Данные читаются через замороженный kity_sudya.zagruzit() (путь судьи); окно ограничено забором dostup.
"""
import datetime as dt, json, math, sys
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]
if str(LAB) not in sys.path: sys.path.insert(0, str(LAB))

_KESH = {}


def _dannye():
    if "M" not in _KESH:
        import kity_sudya as K
        def doli(papka):
            r = {}
            for f in (K.B / papka).glob("*.json"):
                r[f.stem] = {K.den(t).isoformat(): tq / qv for t, qv, tq in json.loads(f.read_text()) if qv > 0}
            return r
        _KESH.update(K=K, M=K.zagruzit(), perp=doli("taker"), spot=doli("spot_taker"))
    return _KESH


def _priznak(imya, D):
    perp, spot = D["perp"], D["spot"]
    if imya == "m3_perp": return lambda s, vch: perp.get(s, {}).get(vch)
    if imya == "spot": return lambda s, vch: spot.get(s, {}).get(vch)
    if imya == "spot_minus_perp":
        def f(s, vch):
            a, b = spot.get(s, {}).get(vch), perp.get(s, {}).get(vch)
            return None if a is None or b is None else a - b
        return f
    if imya == "m3_vsplesk":
        import bisect
        dni = D.setdefault("perp_dni", {s_: sorted(v) for s_, v in perp.items()})
        def f(s, vch):
            v, dd = perp.get(s, {}).get(vch), dni.get(s)
            if v is None or not dd: return None
            j = bisect.bisect_left(dd, vch); okno = [perp[s][x] for x in dd[max(0, j - 28):j]]   # строго до vch
            return None if len(okno) < 20 else v - sum(okno) / len(okno)
        return f
    if imya == "pogloshchenie":
        M = D["M"]
        def f(s, vch):
            a, x = perp.get(s, {}).get(vch), M.get(s)
            if a is None or x is None: return None
            d = dt.date.fromisoformat(vch); t = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
            i = int(np.searchsorted(x["ts"], t))
            if i >= len(x["ts"]) or x["ts"][i] != t or i < 1 or x["c"][i - 1] <= 0: return None
            return (float(x["c"][i] / x["c"][i - 1] - 1.0), float(a))          # доход и поток ОДНОГО дня d−1
        return f
    if imya.startswith("glubina_imb"):                     # перекос стакана дня d−1 (dannye_binance_glubina, PREREG_GLUBINA_PEREKOS)
        pole = imya.split("glubina_")[1]
        G = D.setdefault("glubina", {})
        def f(s, vch):
            if s not in G:
                fp = LAB / "data" / "binance_glubina" / f"{s}.json"
                G[s] = json.loads(fp.read_text()) if fp.exists() else {}
            x = G[s].get(vch)
            return None if not x else x.get(pole)
        return f
    if imya == "glubina_ort":                              # PREREG_GLUBINA_PEREKOS_V2: (imb2, поток d−1, доход d−1)
        g, m3, dd = _priznak("glubina_imb2", D), _priznak("m3_perp", D), _priznak("pogloshchenie", D)
        def f(s, vch):
            a, b, c = g(s, vch), m3(s, vch), dd(s, vch)
            return None if a is None or b is None or c is None else (float(a), float(b), float(c[0]))
        return f
    if imya == "up_premiya":                               # PREREG_UPBIT_PREMIYA_XS: премия Upbit KRW к перпу Binance дня d−1 минус
        M = D["M"]; PU = D.setdefault("up_pr", {})        # её среднее за 28 предыдущих дней (≥ 20); курс KRW/USDT общий для всех монет
        def ryad_u(s):
            if s not in PU:
                fp = LAB / "data" / "upbit_d1" / f"{s}.json"
                up = json.loads(fp.read_text()) if fp.exists() else {}
                x = M.get(s); r = {}
                if up and x is not None:
                    for t, c in zip(x["ts"], x["c"]):
                        dd = dt.datetime.fromtimestamp(int(t) / 1000, dt.timezone.utc).date().isoformat()
                        if dd in up and c > 0 and up[dd] > 0: r[dd] = math.log(up[dd] / float(c))
                PU[s] = (sorted(r), r)
            return PU[s]
        import bisect, math
        def f(s, vch):
            dni, r = ryad_u(s)
            if vch not in r: return None
            j = bisect.bisect_left(dni, vch); okno = [r[x] for x in dni[max(0, j - 28):j]]
            return None if len(okno) < 20 else r[vch] - sum(okno) / len(okno)
        return f
    if imya == "cb_premiya":                               # PREREG_COINBASE_PREMIYA_XS: премия Coinbase USD к перпу Binance дня d−1
        M = D["M"]; CB = D.setdefault("coinbase", {}); PR = D.setdefault("cb_pr", {})   # минус её среднее за 28 предыдущих дней (≥ 20)
        def ryad(s):
            if s not in PR:
                fp = LAB / "data" / "coinbase_d1" / f"{s}.json"
                cb = json.loads(fp.read_text()) if fp.exists() else {}
                x = M.get(s); r = {}
                if cb and x is not None:
                    for t, c in zip(x["ts"], x["c"]):
                        dd = dt.datetime.fromtimestamp(int(t) / 1000, dt.timezone.utc).date().isoformat()
                        if dd in cb and c > 0 and cb[dd] > 0: r[dd] = cb[dd] / float(c) - 1.0
                PR[s] = (sorted(r), r)
            return PR[s]
        import bisect
        def f(s, vch):
            dni, r = ryad(s)
            if vch not in r: return None
            j = bisect.bisect_left(dni, vch); okno = [r[x] for x in dni[max(0, j - 28):j]]      # строго до vch
            return None if len(okno) < 20 else r[vch] - sum(okno) / len(okno)
        return f
    if imya == "cb_premiya_shok":                          # POSTMORTEM_COINBASE_PREMIYA_XS: суточный ПРИРОСТ премии p(d−1) − p(d−2)
        base = _priznak("cb_premiya", D); base("BTCUSDT", "2025-01-01")
        def f(s, vch):
            base(s, vch); dni, r = D["cb_pr"].get(s, ([], {}))
            d1 = (dt.date.fromisoformat(vch) - dt.timedelta(days=1)).isoformat()
            return None if vch not in r or d1 not in r else r[vch] - r[d1]
        return f
    raise KeyError(f"признак {imya} не в закрытом словаре")


PRIZNAKI = ("m3_perp", "spot", "spot_minus_perp", "m3_vsplesk", "pogloshchenie", "glubina_imb1", "glubina_imb2", "glubina_imb5",
            "glubina_ort", "cb_premiya", "cb_premiya_shok", "up_premiya")
SOSTAVNYE = {"pogloshchenie", "glubina_ort"}   # значения-кортежи → остаток после проекции внутри недели


def _z(a): a = np.asarray(a, float); sd = a.std(); return (a - a.mean()) / sd if sd > 0 else a * 0


def xs_nedelya_binance(parametry, dostup):
    import discovery_paket1 as P
    D = _dannye(); K, M = D["K"], D["M"]; pr = _priznak(parametry["priznak"], D); znak = int(parametry.get("znak", 1))
    a = dt.datetime.fromtimestamp(dostup.t0 / 1000, dt.timezone.utc).date()
    b = dt.datetime.fromtimestamp(dostup.t1 / 1000, dt.timezone.utc).date()
    def ts(d): return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)

    def nedelya(d):
        vch = (d - dt.timedelta(days=1)).isoformat()
        oi = sorted([(x["met"][vch][4], s) for s, x in M.items() if vch in x["met"] and x["met"][vch][4]], reverse=True)[:50]
        rows = []
        for _, s in oi:
            x = M[s]; i = int(np.searchsorted(x["ts"], ts(d)))
            if i >= len(x["ts"]) or x["ts"][i] != ts(d) or i < 60: continue
            v = pr(s, vch)
            if v is not None and np.all(np.isfinite(v)): rows.append((v, s, i))
        if len(rows) < int(parametry.get("min_strok", 30)): return None
        if parametry["priznak"] == "pogloshchenie":
            zr, zf = _z([v[0] for v, _, _ in rows]), _z([v[1] for v, _, _ in rows])
            zz = zr - (float(np.mean(zr * zf)) * zf)          # доход, ортогональный потоку недели: «цена сильнее/слабее, чем велел поток»
        elif parametry["priznak"] == "glubina_ort":
            y = _z([v[0] for v, _, _ in rows]); X = np.c_[_z([v[1] for v, _, _ in rows]), _z([v[2] for v, _, _ in rows])]
            zz = y - X @ np.linalg.lstsq(X, y, rcond=None)[0]   # перекос, не объяснённый потоком и ценой дня
        if parametry["priznak"] in SOSTAVNYE:
            rows = [(float(z), s, i) for z, (_, s, i) in zip(zz, rows)]
        rows.sort(); k = len(rows) // 10 if "dolya" not in parametry else max(1, int(round(len(rows) * float(parametry["dolya"]), 9)))
        sd = int(parametry.get("zaderzhka", 1)) - 1                     # 1 = закрытие d (эталон KITY); 0 = закрытие d−1; 2 = d+1
        leg = [K.sdelka(M[s], i + sd, 7, -znak) for _, s, i in rows[:k] if 0 <= i + sd < len(M[s]["ts"])] + \
              [K.sdelka(M[s], i + sd, 7, +znak) for _, s, i in rows[-k:] if 0 <= i + sd < len(M[s]["ts"])]
        leg = [r for r in leg if r is not None]
        return float(np.mean(leg)) if leg else None

    sob = [(ts(d), r, None) for d in K.SETKA if a <= d <= b for r in [nedelya(d)] if r is not None]
    it = P.itog(sob, s_kontrolem=False, lag=1)
    return dict(t=it.get("t", 0.0), n=it.get("dney", it.get("n", 0)), metrika=it)


def xs_sintetika(parametry, dostup):
    """Синтетический рынок для калибровки фабрики: 50 монет, недели окна dostup; признак известен ДО недели.
    Истинный спред «верхний дециль − нижний» задан parametry['edge_bps'] (0 = чистый шум), шум откалиброван по KITY M3 (sd недельного спреда ≈ 550 bps).
    Это НЕ стратегия: проверка мощности (находит ли фабрика подложенный эффект) и ложных срабатываний (не находит ли шум)."""
    import math, statistics
    rng = np.random.default_rng(int(parametry["seed"]))
    nedel = max(10, int((dostup.t1 - dostup.t0) / (7 * 86_400_000)))
    n_mon, sigma = 50, float(parametry.get("sigma", 0.176))           # 0.176 ⇒ шум недельного спреда ≈ 550 bps (как у KITY M3)
    edge = parametry.get("edge_bps", 0) / 1e4
    spred = []
    for _ in range(nedel):
        f = rng.standard_normal(n_mon)
        z = (f - f.mean()) / f.std()
        r = sigma * rng.standard_normal(n_mon) + 2 * edge * z / 3.5    # среднее по ногам ≈ edge (определение KITY)
        k = n_mon // 10; o = np.argsort(f)
        spred.append(float(r[o[-k:]].mean() - r[o[:k]].mean()) / 2)
    m = statistics.fmean(spred); sd = statistics.stdev(spred)
    t = m / (sd / math.sqrt(len(spred))) if sd else 0.0
    return dict(t=t, n=len(spred), metrika=dict(edge_bps_ist=parametry.get("edge_bps", 0), edge_bps_izm=round(m * 1e4, 1)))
