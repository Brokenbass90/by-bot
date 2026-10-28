#!/usr/bin/env python3
"""razbor_sdelok.py — «под лупой»: графики и автоматическая классификация сделок PUMP4 и SHORT_HVOST (28.10.2026, Claude). Read-only.
Для каждой сделки с H1 в кэше (data/h1_kesh_att1, 09–17.10): MFE/MAE в R (PUMP4) или % (SHORT_HVOST), время до стопа, тип исхода:
  VHOD_RANO — против нас ≥ 1R (PUMP4) / ≥ 15 % (SH) в первые 6 ч: памп ещё не выдохся;  OTDALI_PRIBYL — был плюс ≥ 1R / ≥ 10 %, закрыли хуже;
  MEDLENNYY — без резких движений; HOROSHAYA — прибыль. Сводка по типам — что чинить: вход (ждать истощения) или выход (фиксация).
Графики (свечи H1 −48 ч…+выход+12 ч, вход/стоп/выход, объём, рост за 24 ч, режим BTC, разброс альтов): 8 худших и 4 лучших каждой ноги.
Выход: razbor/*.png, razbor/RAZBOR.md.   python3 research_lab/razbor_sdelok.py"""
import collections, glob, json, sys, time
from pathlib import Path
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
HERE = Path(__file__).resolve().parent; H = 3600000; OUT = HERE / "razbor"; OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(HERE / "fabrika")); sys.path.insert(0, str(HERE))
import brain_zhurnal_nog as BZ

def bary(sym):
    p = HERE / "data" / "h1_kesh_att1" / f"{sym}.json"
    if not p.exists(): return None
    d = json.load(open(p)); d = d if isinstance(d, list) else d.get("h1") or []
    return {int(x[0]): [int(x[0])] + [float(v) for v in x[1:6]] for x in d}

def main():
    mt = BZ.metki_btc(); Z = json.loads((HERE / "data" / "brain_shadow_v1" / "zrenie_dni.json").read_text())
    S = []
    p = json.load(open(sorted(glob.glob(str(HERE / "results" / "pump4_polnyy_povtor_*.json")))[-1]))["sdelki"]
    for x in p:
        if x.get("R") is None: continue
        S.append(dict(noga="PUMP4", sym=x["sym"], t0=x["ts"] + H, t1=x["ts"] + (x["barov"] + 1) * H, rez=x["R"], stop_pct=x["risk_pct"], sh=x.get("shirina")))
    for x in json.load(open(sorted(glob.glob(str(HERE / "results" / "short_hvost_uderzhanie_*.json")))[-1]))["sdelki"]:
        S.append(dict(noga="SHORT_HVOST", sym=x["sym"], t0=x["ts"], t1=x["ts"] + 15 * H, rez=x["16"]["net_hedzh"] / 100, stop_pct=80.0, sh=None))
    tipy = collections.defaultdict(collections.Counter); rows = []
    for s in S:
        b = bary(s["sym"])
        if not b or s["t0"] not in b: continue
        e = b[s["t0"]][1]; ed = e * s["stop_pct"] / 100 if s["noga"] == "PUMP4" else e * 0.01      # ед.: R для PUMP4, 1 % для SH
        put = [b[t] for t in range(s["t0"], s["t1"] + H, H) if t in b]
        if not put: continue
        mae = (max(x[2] for x in put) - e) / ed; mfe = (e - min(x[3] for x in put)) / ed
        rano = [b[t] for t in range(s["t0"], s["t0"] + 6 * H, H) if t in b]; mae6 = (max(x[2] for x in rano) - e) / ed if rano else 0
        porog_rano, porog_plus = (1.0, 1.0) if s["noga"] == "PUMP4" else (15.0, 10.0)
        if s["rez"] > 0: tip = "HOROSHAYA"
        elif mae6 >= porog_rano: tip = "VHOD_RANO"
        elif mfe >= porog_plus: tip = "OTDALI_PRIBYL"
        else: tip = "MEDLENNYY"
        tipy[s["noga"]][tip] += 1
        d = time.strftime("%Y-%m-%d", time.gmtime(s["t0"] / 1000)); z = Z.get(str(s["t0"] // 864e5 * 864e5 - 864e5).split(".")[0]) or {}
        rows.append(dict(s, tip=tip, mae=round(mae, 2), mfe=round(mfe, 2), mae6=round(mae6, 2), d=d, rezhim=mt.get(s["t0"] // H * H - 2 * H, "?"),
                         disp=z.get("disp_ret"), rost24=round((e / b[s["t0"] - 24 * H][4] - 1) * 100, 1) if s["t0"] - 24 * H in b else None, b=b, e=e, ed=ed))
    md = ["# Разбор сделок под лупой (автоматически, `razbor_sdelok.py`) — H1 в кэше по 17.10", "",
          "Типы убытков: **VHOD_RANO** — памп ещё не выдохся (против нас ≥ 1R / ≥ 15 % в первые 6 ч) → чинить ВХОД (ждать истощения);",
          "**OTDALI_PRIBYL** — был плюс ≥ 1R / ≥ 10 %, закрыли хуже → чинить ВЫХОД; **MEDLENNYY** — без резких движений → слабый сигнал.", ""]
    for n, c in tipy.items(): md.append(f"- {n}: " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
    md += ["", "| нога | монета | дата | итог | тип | против нас (макс) | в нашу сторону (макс) | рост 24 ч до входа % | режим BTC | разброс альтов | график |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for n in ("PUMP4", "SHORT_HVOST"):
        g = sorted([r for r in rows if r["noga"] == n], key=lambda r: r["rez"]); vyb = g[:8] + g[-4:]
        for r in vyb:
            f = f'{n}_{r["sym"]}_{r["d"]}.png'
            ts = [t for t in range(r["t0"] - 48 * H, r["t1"] + 13 * H, H) if t in r["b"]]
            fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True, gridspec_kw=dict(height_ratios=[3, 1]))
            for i, t in enumerate(ts):
                o, hh, l, c, v = r["b"][t][1:6]; col = "#2a9d8f" if c >= o else "#e76f51"
                a1.vlines(i, l, hh, color=col, lw=1); a1.vlines(i, min(o, c), max(o, c), color=col, lw=4); a2.bar(i, v, color=col)
            iv = ts.index(r["t0"]); ivy = min(len(ts) - 1, ts.index(r["t1"]) if r["t1"] in ts else len(ts) - 1)
            a1.axvline(iv, color="k", ls="--", lw=1); a1.axvline(ivy, color="grey", ls=":", lw=1)
            a1.axhline(r["e"], color="k", lw=0.8); a1.axhline(r["e"] + (r["ed"] if n == "PUMP4" else r["e"] * 0.8), color="r", lw=0.8, ls="--")
            a1.set_title(f'{n} {r["sym"]} {r["d"]} | итог {r["rez"]:+.2f}{"R" if n == "PUMP4" else "%"} | {r["tip"]} | рост 24ч {r["rost24"]}% | BTC {r["rezhim"]}', fontsize=9)
            fig.tight_layout(); fig.savefig(OUT / f, dpi=80); plt.close(fig)
            md.append(f'| {n} | {r["sym"]} | {r["d"]} | {r["rez"]:+.2f} | {r["tip"]} | {r["mae"]} | {r["mfe"]} | {r["rost24"]} | {r["rezhim"]} | {r["disp"]} | razbor/{f} |')
    md += ["", "Чего не хватает для полного разбора (инструменты): стакан/глубина в момент входа по монете; OI и ликвидации по часам; фандинг по часам;",
           "спот против перпа (кто толкает памп); новости/листинги по монете; данные после 17.10 в кэше (обновить H1 на Mac)."]
    (OUT / "RAZBOR.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:12]))

if __name__ == "__main__":
    main()
