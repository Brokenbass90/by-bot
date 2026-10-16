#!/usr/bin/env python3
"""karta_portfel.py — ежедневная сводка портфеля по рукавам (одна картинка для TG и веба). Числа — из журналов рукавов."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from stil import C, znak


def risovat(svodka, put):
    """svodka = {data, ccy, rukava: [{sleeve, venue, mode, otkryto, risk_otkr, realiz_den, nerealiz, izderzhki, zdorove, zametka}], itog_mode}"""
    R = svodka["rukava"]; H = 2.2 + 0.42 * len(R); fig = plt.figure(figsize=(8, H), dpi=160); fig.patch.set_facecolor(C["bg"])
    def t(x, y, s, **kw):
        kw.setdefault("color", C["ink"]); kw.setdefault("fontsize", 9.5); fig.text(x / 8, y / H, s, va="top", **kw)
    y = H - 0.3
    t(0.2, y, f"ПОРТФЕЛЬ · {svodka['data']}", fontsize=12.5, weight="bold"); t(7.8, y, svodka.get("metka", ""), fontsize=9, color=C["muted"], ha="right", weight="bold"); y -= 0.42
    real = sum(r["realiz_den"] for r in R if r.get("realiz_den") is not None and r["mode"] == "LIVE")
    risk = sum(r["risk_otkr"] for r in R if r.get("risk_otkr") is not None and r["mode"] == "LIVE")
    t(0.2, y, f"Реализовано за день (LIVE): {znak(real, svodka['ccy'], 2)}    Открытый риск до стопов: {risk:,.2f} {svodka['ccy']}", fontsize=10); y -= 0.45
    kol = [0.2, 1.55, 2.45, 3.05, 4.0, 5.1, 6.3]
    for x, z in zip(kol, ("рукав", "режим", "откр.", "риск", "реализ.", "нереализ.", "здоровье")):
        t(x, y, z, fontsize=8.5, color=C["muted"])
    y -= 0.3
    for r in R:
        col = C["ink"] if r["mode"] == "LIVE" else C["muted"]
        f = lambda v, nd=2: "н/д" if v is None else f"{v:+,.{nd}f}"
        for x, z in zip(kol, (f"{r['sleeve']} ({r['venue']})", r["mode"], str(r.get("otkryto", 0)), "—" if r.get("risk_otkr") is None else f"{r['risk_otkr']:,.2f}",
                              f(r.get("realiz_den"), 4), f(r.get("nerealiz")), r.get("zdorove", ""))):
            t(x, y, z, fontsize=9, color=col)
        if r.get("zametka"): t(1.55, y - 0.2, r["zametka"], fontsize=7, color=C["muted"])
        y -= 0.42
    t(0.2, 0.3, "Числа — из журналов исполнения рукавов (та же основа, что для налогового учёта). Тени (SHADOW) денег не двигают.",
      fontsize=7, color=C["muted"])
    fig.savefig(put, facecolor=C["bg"]); plt.close(fig); return put
