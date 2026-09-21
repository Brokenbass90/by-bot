"""poly_priznaki.py — POLY_SENTIMENT_V1: признаки из рынков предсказаний. Заморожено в PREREG_POLY_V1.

Для дня t (признак известен на закрытие дня t, используются точки истории с ts < t+1 день):
  для каждого рынка из маппинга (poly_map.json), который на t уже начался и ещё не закончился,
  и у которого вероятность сутки назад была в [0.03, 0.97] (событие ещё не решено):
      вклад = знак_категории × (p(t) − p(t − 24 ч))
  risk_on[получатель] = среднее вкладов рынков этого получателя (kripto / akcii), n = число рынков.
  Рынки за 24 ч до своей даты окончания не участвуют (скачок разрешения — не информация о режиме).
Веса равные: итоговый объём рынка известен только задним числом, поэтому им не взвешиваем.
Рынок без категории в маппинге не участвует вообще.
"""
from __future__ import annotations
import datetime as dt, json
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parents[1]
IST = LAB / "data/poly/istoriya"
MAP = Path(__file__).resolve().parent / "poly_map.json"
DEN, CHAS = 86400000, 3600000


def _ms(s):
    if not s:
        return None
    try:
        return int(dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return None


def _p_do(ryad_t, ryad_p, t_ms):
    """последняя цена со временем < t_ms"""
    i = int(np.searchsorted(ryad_t, t_ms, side="left")) - 1
    return ryad_p[i] if i >= 0 else None


def priznaki(dates):
    if not IST.exists() or not any(IST.glob("*.json")):
        raise FileNotFoundError("нет истории Polymarket: poly_sbor.py --katalog и --istoriya")
    kat = json.loads(MAP.read_text())["kategorii"]
    rynki = []
    for f in IST.glob("*.json"):
        d = json.loads(f.read_text())
        if not d.get("ryad") or d.get("kat") not in kat:
            continue
        t = np.array([x[0] * 1000 for x in d["ryad"]], dtype=np.int64); p = np.array([x[1] for x in d["ryad"]])
        o = np.argsort(t)
        rynki.append((t[o], p[o], _ms(d.get("start")), _ms(d.get("konec")), kat[d["kat"]]))
    out = {}
    for T in dates:
        T = int(T); konec_dnya = T + DEN
        vklad = {"kripto": [], "akcii": []}
        for t, p, st, kn, K in rynki:
            if st is not None and st >= T:
                continue
            if kn is not None and kn - 24 * CHAS <= konec_dnya:
                continue
            p1, p0 = _p_do(t, p, konec_dnya), _p_do(t, p, konec_dnya - 24 * CHAS)
            if p1 is None or p0 is None or not (0.03 <= p0 <= 0.97):
                continue
            for pol in K["poluchateli"]:
                if pol in vklad:
                    vklad[pol].append(K["znak"] * (p1 - p0))
        out[T] = {pol: (float(np.mean(v)) if v else None, len(v)) for pol, v in vklad.items()}
    return out


def samoproverka():
    import tempfile
    global IST
    stary = IST; IST = Path(tempfile.mkdtemp()); d = IST; bad = 0
    try:
        T0 = 1700000000000 // DEN * DEN
        ryad = [((T0 + i * CHAS) // 1000, 0.4 if i < 24 * 6 else 0.6) for i in range(24 * 20)]   # скачок в начале дня 6
        (d / "a.json").write_text(json.dumps({"kat": "fed_snizhenie", "start": None, "konec": None, "ryad": ryad}))
        dates = [T0 + k * DEN for k in range(10)]
        v = [priznaki(dates)[t]["kripto"][0] for t in dates]
        ok = v[0] is None and all(abs(x) < 1e-12 for x in v[1:6]) and abs(v[6] - 0.2) < 1e-9 and abs(v[7]) < 1e-12
        bad += not ok; print(f"  {'PASS' if ok else 'FAIL'}  скачок виден в свой день, не раньше")
        (d / "b.json").write_text(json.dumps({"kat": "recessiya", "start": None, "konec": None,
                                              "ryad": [((T0 + i * CHAS) // 1000, 0.99) for i in range(480)]}))
        ok = priznaki(dates)[dates[3]]["kripto"][1] == 1; bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  решённый рынок (p≈0.99) не участвует")
        (d / "c.json").write_text(json.dumps({"kat": "sport", "ryad": ryad}))
        ok = priznaki(dates)[dates[3]]["kripto"][1] == 1; bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  рынок без маппинга не участвует")
        (d / "e.json").write_text(json.dumps({"kat": "kripto_cena", "start": None, "konec": None, "ryad": ryad}))
        f = priznaki(dates); ok = f[dates[5]]["akcii"][1] == 1 and f[dates[5]]["kripto"][1] == 2; bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  крипто-цена не идёт в признак акций")
        kon = dt.datetime.fromtimestamp((T0 + 4 * DEN) / 1000, dt.timezone.utc).isoformat()
        (d / "g.json").write_text(json.dumps({"kat": "fed_povyshenie", "start": None, "konec": kon, "ryad": ryad}))
        f = priznaki(dates); ok = f[dates[2]]["kripto"][1] == 2 and f[dates[1]]["kripto"][1] == 3; bad += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  за 24 ч до окончания рынок выпадает")
    finally:
        IST = stary
    return bad


if __name__ == "__main__":
    raise SystemExit(1 if samoproverka() else 0)
