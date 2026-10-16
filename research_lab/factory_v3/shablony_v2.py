#!/usr/bin/env python3
"""shablony_v2.py — новые шаблоны Фабрики (16.10.2026). Недельная кросс-секция (ferma_shablony) не меняется.
Та же дисциплина: шаблон вызывается фермой только внутри зарегистрированной попытки, данные — только окна dostup (t0..t1),
знак, порог и удержание — из спецификации (замораживаются в реестре до прогона), издержки — явно, в bps на круг.

  odin_aktiv_chas — ОДИН инструмент, часовые бары: сигнал на закрытии бара i (только прошлое), вход открытием i+1,
                    выход закрытием i+hold; сделки не перекрываются. parametry: simvol | sintetika, priznak ("dohod_n" | "chas"),
                    n, porog, chas, znak (+1/−1), hold, izderzhki_bps.
  sobytie         — событийное исследование: момент события причинный (t_ms — когда событие стало известно), вход открытием
                    первого бара после события, удержание posle баров; события одной монеты не перекрываются; контроль —
                    случайные бары той же монеты вне окон событий (kontrol_k на событие, фиксированное зерно);
                    результат = событие − контроль, после издержек. parametry: sobytiya (список {t_ms, simvol} или путь), posle,
                    znak, izderzhki_bps, kontrol_k, zerno | sintetika.
Оба возвращают dict(t, n, metrika) с половинами по времени.
"""
import json, math
from pathlib import Path
import numpy as np
LAB = Path(__file__).resolve().parents[1]
H = 3_600_000


def _bary(simvol, dostup, sint=None):
    """[ts, o, h, l, c] часовые; sint = {seed, n, edge_bps, chas | sobytiya} — синтетика для калибровки шаблона."""
    if sint is not None:
        rng = np.random.default_rng(int(sint["seed"])); n = int(sint.get("n", 20000)); t0 = dostup.t0 - dostup.t0 % H
        r = rng.standard_normal(n) * float(sint.get("sigma_bps", 60)) / 1e4
        ts = t0 + H * np.arange(n)
        if sint.get("chas") is not None:                                      # подложенный эффект: после бара часа chas — дрейф
            hrs = (ts // H) % 24; idx = np.flatnonzero(hrs == int(sint["chas"]))
            for i in idx:
                r[i + 1:i + 1 + int(sint.get("hold", 4))] += float(sint.get("edge_bps", 0)) / 1e4 / int(sint.get("hold", 4))
        c = 100 * np.exp(np.cumsum(r)); o = np.concatenate([[100.0], c[:-1]])
        b = np.c_[ts, o, np.maximum(o, c), np.minimum(o, c), c]
    else:
        d = np.load(LAB / "data" / "h1" / f"{simvol}.npz"); ts = d["ts"].astype(np.int64); x = d["ohlcv"].astype(float)
        b = np.c_[ts, x[:, 0], x[:, 1], x[:, 2], x[:, 3]]
    m = (b[:, 0] >= dostup.t0) & (b[:, 0] <= dostup.t1)
    return b[m]


def _itog(r, ts):
    r = np.asarray(r, float)
    if len(r) < 3: return dict(t=0.0, n=int(len(r)), metrika=dict(n=int(len(r)), prichina="мало сделок"))
    sd = r.std(ddof=1); t = float(r.mean() / (sd / math.sqrt(len(r)))) if sd > 0 else 0.0
    pol = len(r) // 2
    return dict(t=t, n=int(len(r)), metrika=dict(n=int(len(r)), edge_bps=round(float(r.mean()), 2), t=round(t, 2),
                                                 polovinki_bps=[round(float(r[:pol].mean()), 2), round(float(r[pol:].mean()), 2)],
                                                 dolya_plyus=round(float((r > 0).mean()), 3), s=int(ts[0]), po=int(ts[-1])))


def odin_aktiv_chas(parametry, dostup):
    p = parametry; b = _bary(p.get("simvol"), dostup, p.get("sintetika"))
    o, c, ts = b[:, 1], b[:, 4], b[:, 0].astype(np.int64)
    hold, znak, izd = int(p["hold"]), int(p["znak"]), float(p["izderzhki_bps"])
    if znak not in (1, -1) or hold < 1: raise ValueError("znak ±1, hold ≥ 1")
    r, kogda, i = [], [], int(p.get("n", 1))
    while i + hold < len(b):
        if p["priznak"] == "chas":
            sig = (ts[i] // H) % 24 == int(p["chas"])
        elif p["priznak"] == "dohod_n":
            n = int(p["n"]); sig = c[i - n] > 0 and (c[i] / c[i - n] - 1) * 1e4 > float(p["porog"])
        else:
            raise KeyError(f"признак {p['priznak']} не в словаре шаблона")
        if sig and ts[i + hold] - ts[i] == hold * H:                          # без дыр внутри удержания
            r.append(znak * (c[i + hold] / o[i + 1] - 1) * 1e4 - izd); kogda.append(ts[i]); i += hold
        else:
            i += 1
    return _itog(r, kogda or [0])


def sobytie(parametry, dostup):
    p = parametry; posle, znak, izd = int(p["posle"]), int(p["znak"]), float(p["izderzhki_bps"])
    sob = p.get("sobytiya")
    if isinstance(sob, str): sob = json.loads((LAB / sob).read_text())
    sint = p.get("sintetika")
    if sint is not None:                                                    # синтетика: события в случайные часы, подложенный дрейф
        rng = np.random.default_rng(int(sint["seed"]) + 7)
        b0 = _bary("SINT", dostup, dict(sint, chas=None)); n = len(b0)
        idx = np.sort(rng.choice(np.arange(50, n - posle - 2), size=int(sint.get("sobytiy", 200)), replace=False))
        r_ = np.diff(np.log(b0[:, 4]), prepend=np.log(b0[0, 4]))
        for i in idx: r_[i + 1:i + 1 + posle] += float(sint.get("edge_bps", 0)) / 1e4 / posle
        c = b0[0, 4] * np.exp(np.cumsum(r_) - r_[0]); o = np.concatenate([[c[0]], c[:-1]])
        dannye = {"SINT": np.c_[b0[:, 0], o, c, c, c]}; sob = [dict(t_ms=int(b0[i, 0]) + 1, simvol="SINT") for i in idx]
    else:
        dannye = {}
    rng = np.random.default_rng(int(p.get("zerno", 20261016))); k = int(p.get("kontrol_k", 3))
    abn, raw, kogda, posl = [], [], [], {}
    for e in sorted(sob, key=lambda z: z["t_ms"]):
        s = e["simvol"]
        if s not in dannye: dannye[s] = _bary(s, dostup)
        b = dannye[s]; ts = b[:, 0].astype(np.int64)
        i = int(np.searchsorted(ts, int(e["t_ms"]), side="left"))          # первый бар, открывшийся не раньше момента события
        if i + posle > len(b) or (s in posl and i <= posl[s]): continue     # конец данных / перекрытие с прошлым событием монеты
        posl[s] = i + posle - 1
        r_e = znak * (b[i + posle - 1, 4] / b[i, 1] - 1) * 1e4
        zapret = np.zeros(len(b), bool)
        for z in sob:
            if z["simvol"] == s:
                j = int(np.searchsorted(ts, int(z["t_ms"]))); zapret[max(0, j - posle):j + posle] = True
        pool = np.flatnonzero(~zapret[:len(b) - posle])
        if len(pool) < k: continue
        ctrl = [znak * (b[j + posle - 1, 4] / b[j, 1] - 1) * 1e4 for j in rng.choice(pool, size=k, replace=False)]
        abn.append(r_e - float(np.mean(ctrl)) - 0.0); raw.append(r_e - izd); kogda.append(int(ts[i]))
    rez = _itog(abn, kogda or [0])
    rez["metrika"].update(syroy_posle_izderzhek_bps=round(float(np.mean(raw)), 2) if raw else None, sobytiy_vzyato=len(abn),
                          sobytiy_vsego=len(sob))
    return rez
