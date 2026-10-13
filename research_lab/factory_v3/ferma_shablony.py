#!/usr/bin/env python3
"""ferma_shablony.py — интерфейс шаблонов экспериментов Factory V3 (P3). 13.10.2026.

Шаблон = функция f(parametry, dostup) -> dict(t, n, metrika), которую ферма вызывает внутри зарегистрированной попытки.
Окно данных шаблон берёт ТОЛЬКО из dostup (t0..t1); набор признаков — закрытый словарь PRIZNAKI (новый признак = новая
строка кода + запись в реестре, а не параметр-строка от ИИ). Механика сделки, издержки, фандинг и статистика — дословно
из замороженных судей (kity_sudya.sdelka, discovery_paket1.itog с t Ньюи–Уэста лаг 1), поэтому шаблон воспроизводит их числа.

Шаблоны:
  xs_nedelya_binance — недельная кросс-секция PIT топ-50 по OI Binance (скелет KITY M3 / SPOT_POTOK):
      parametry = {"priznak": "m3_perp" | "spot" | "spot_minus_perp", "znak": +1 | -1}
Данные читаются через замороженный kity_sudya.zagruzit() (путь судьи); окно ограничено забором dostup.
"""
import datetime as dt, json, sys
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
    raise KeyError(f"признак {imya} не в закрытом словаре")


PRIZNAKI = ("m3_perp", "spot", "spot_minus_perp")


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
            if v is not None and np.isfinite(v): rows.append((v, s, i))
        if len(rows) < 30: return None
        rows.sort(); k = len(rows) // 10
        leg = [K.sdelka(M[s], i, 7, -znak) for _, s, i in rows[:k]] + [K.sdelka(M[s], i, 7, +znak) for _, s, i in rows[-k:]]
        leg = [r for r in leg if r is not None]
        return float(np.mean(leg)) if leg else None

    sob = [(ts(d), r, None) for d in K.SETKA if a <= d <= b for r in [nedelya(d)] if r is not None]
    it = P.itog(sob, s_kontrolem=False, lag=1)
    return dict(t=it.get("t", 0.0), n=it.get("dney", it.get("n", 0)), metrika=it)
