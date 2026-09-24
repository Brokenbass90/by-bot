#!/usr/bin/env python3
"""begun_sensor.py — есть ли информация в признаке: разделяет ли он дни.

Вопрос не «сколько заработали», а «отличаются ли дни, когда признак выше нуля».
Корзина: равные доли всех монет вселенной на дату (топ-50 по OI в долларах).
Считается доходность корзины за следующие H дней (с издержками входа и выхода).

    эдж = средняя доходность дней с признаком > 0 − средняя по ВСЕМ дням
    значимость: перестановочный тест — 2000 раз случайно выбираем столько же дней
                (блоками по H дней, чтобы не разрывать перекрытие) и смотрим,
                как часто случайная выборка даёт эдж не меньше нашего.

Этапы: discovery — только до даты раздела рынка; confirmation — только после.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))
import portfeli  # noqa: E402
PERESTANOVOK = 2000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--param", required=True); ap.add_argument("--vyhod", required=True)
    a = ap.parse_args(); p = json.loads(a.param); etap = p.get("etap", "discovery")
    H = int(p.get("gorizont", 3))
    ry = p.get("rynok", "kripto_pit50_poly")
    imya_pr = p.get("priznak", "POLY")
    if ry not in portfeli.RYNKI_P or imya_pr not in portfeli.PRIZNAKI_DNYA:
        Path(a.vyhod).write_text(json.dumps({"param": p, "okna": {"VSE": {"n": 0}},
                                             "net_dannyh": f"нет рынка {ry} или признака {imya_pr}"}, ensure_ascii=False))
        print("нет такого рынка/признака"); return
    try:
        R = portfeli.RYNKI_P[ry]()
        POLY = portfeli.PRIZNAKI_DNYA[imya_pr](R)
    except FileNotFoundError as e_:
        Path(a.vyhod).write_text(json.dumps({"param": p, "okna": {"VSE": {"n": 0}}, "net_dannyh": str(e_)},
                                            ensure_ascii=False))
        print("нет данных:", e_); return
    dates, C, M, fee = R["dates"], R["C"], R["M"], R["fee_bps"]
    r = np.full(len(dates), np.nan)
    for t in range(len(dates) - H):
        el = M[t] & np.isfinite(C[t]) & np.isfinite(C[t + H])
        if el.sum() >= 10:
            r[t] = float(np.mean(C[t + H, el] / C[t, el] - 1)) - 2 * fee / 1e4
    ok = np.isfinite(r) & np.isfinite(POLY)
    if etap == "discovery":
        ok &= dates < R["razdel"]
    else:
        ok &= dates >= R["razdel"]
    idx = np.flatnonzero(ok)
    rng = np.random.default_rng(7)

    def proba(sel_idx, vse_idx):
        if len(sel_idx) < 20:
            return {"n": len(sel_idx), "n_eff": round(len(sel_idx) / H, 1)}
        nash = float(r[sel_idx].mean() - r[vse_idx].mean())
        bloki = [vse_idx[i:i + H] for i in range(0, len(vse_idx), H)]
        nuzhno = max(1, round(len(sel_idx) / H))
        hvost = 0
        for _ in range(PERESTANOVOK):
            vyb = np.concatenate([bloki[i] for i in rng.choice(len(bloki), size=nuzhno, replace=False)])
            hvost += (r[vyb].mean() - r[vse_idx].mean()) >= nash
        p_znach = (hvost + 1) / (PERESTANOVOK + 1)
        return {"n": int(len(sel_idx)), "n_eff": round(len(sel_idx) / H, 1), "edge": nash,
                "p": float(p_znach), "t": float(-math.log10(max(p_znach, 1e-9)))}

    def okno(i):
        s = i[POLY[i] > 0]
        return proba(s, i)
    h = len(idx) // 2
    rez = {"param": p, "etap": etap, "gorizont": H, "rynok": ry, "priznak": imya_pr,
           "okna": {"VSE": okno(idx), "H1": okno(idx[:h]), "H2": okno(idx[h:])},
           "dney_vsego": int(len(idx)), "dney_priznak_polozhitelen": int((POLY[idx] > 0).sum()),
           "chlenov_s_cenoy_mediana": 1.0}
    tmp = Path(a.vyhod + ".tmp"); tmp.write_text(json.dumps(rez, ensure_ascii=False, indent=1)); tmp.replace(a.vyhod)
    print("готово, дней:", len(idx), "из них признак > 0:", rez["dney_priznak_polozhitelen"])


if __name__ == "__main__":
    main()
