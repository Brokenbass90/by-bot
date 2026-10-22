"""Аудит экономики POLY_NO_SEREDINA (поручение PM 22.10). Те же правила prereg 6c9f620, без новых фильтров."""
import collections, datetime as dt, json, math, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, poly_favorit_sutki as P
K = "open@ts"; STAKE = 10.0; DEP = 500.0
H = P.h1(); rez = []
for z in P.rynki():
    if not 0.20 < z["p"] < 0.80: continue
    y, ist, _ = P.ishod(z, H, K)
    if y is None: continue
    q = (1 - z["p"]) + 0.01; fee = 0.07 * q * (1 - q); cena = q + fee
    tok = STAKE / cena                      # $10 = цена токенов + комиссия
    vypl = tok * (1 - y)
    z.update(y=y, ist=ist, cena=cena, fee_usd=tok * fee, tok=tok, pnl=vypl - STAKE, roi=(vypl - STAKE) / STAKE, T=z["konec"] - 86400)
    a0, a1 = P.cena_h1(H, z["aktiv"], z["T"], K), P.cena_h1(H, z["aktiv"], z["konec"], K)
    z["ret24"] = (a1 / a0 - 1) if a0 and a1 else None
    rez.append(z)
rez.sort(key=lambda z: z["konec"])
out = {}
# 1. сверка
ev = collections.defaultdict(list)
for z in rez: ev[z["sobytie"]].append(z)
out["sverka"] = dict(sdelok=len(rez), pribyl_usd=round(sum(z["pnl"] for z in rez), 2), sred_roi_na_sdelku=round(np.mean([z["roi"] for z in rez]), 4),
    sred_po_sobytiyam=round(np.mean([np.mean([z["roi"] for z in v]) for v in ev.values()]), 4), sobytiy=len(ev),
    sdelok_v_sobytii=dict(collections.Counter(len(v) for v in ev.values())),
    roi_sobytiy_1_sdelka=round(np.mean([v[0]["roi"] for v in ev.values() if len(v) == 1]), 4),
    roi_sobytiy_2plus=round(np.mean([np.mean([z["roi"] for z in v]) for v in ev.values() if len(v) > 1]), 4),
    komissii_usd=round(sum(z["fee_usd"] for z in rez), 2), vyigryshey=sum(z["y"] == 0 for z in rez))
# 2. денежный журнал: вход в T, выплата в konec
sob = sorted([(z["T"], 0, z) for z in rez] + [(z["konec"], 1, z) for z in rez], key=lambda x: (x[0], -x[1]))  # выплаты раньше входов в ту же секунду
cash, otkr, peak_used, mx_otkr, propusk, eq_min, cnt = DEP, 0, 0.0, 0, 0, DEP, []
vzyato = set()
for t, k, z in sob:
    if k == 0:
        if cash >= STAKE: cash -= STAKE; otkr += 1; vzyato.add(id(z))
        else: propusk += 1
    elif id(z) in vzyato:
        cash += z["tok"] * (1 - z["y"]); otkr -= 1
    mx_otkr = max(mx_otkr, otkr); peak_used = max(peak_used, otkr * STAKE); cnt.append(otkr)
    eq_min = min(eq_min, cash + otkr * STAKE)
out["kapital"] = dict(itog_usd=round(cash, 2), maks_odnovremenno=mx_otkr, pik_zanyato_usd=peak_used, propushcheno_iz_za_deneg=propusk,
    min_kapital_po_stoimosti_vhoda=round(eq_min, 2), zagruzka_srednyaya_dolya=round(np.mean(cnt) * STAKE / DEP, 3))
# 3. кластеры по датам: блочный бутстрэп по датам
dates = collections.defaultdict(list)
for z in rez: dates[z["sobytie"].split("|")[1]].append(z)
dk = sorted(dates); rng = random.Random(20261022); bs = []
for _ in range(5000):
    s = [rng.choice(dk) for _ in dk]; pn = [z["pnl"] for d in s for z in dates[d]]
    bs.append(sum(pn) / (len(pn) * STAKE))
bs.sort()
dsum = [sum(z["pnl"] for z in dates[d]) for d in dk]
out["klastery"] = dict(dat=len(dk), sdelok_na_datu_sred=round(len(rez) / len(dk), 2), roi_95_dov_interval=[round(bs[125], 4), round(bs[4875], 4)],
    dolya_butstrep_le_0=round(sum(x <= 0 for x in bs) / len(bs), 4), top5_dat_dolya_pribyli=round(sum(sorted(dsum)[-5:]) / sum(dsum), 3),
    top10_dat_dolya_pribyli=round(sum(sorted(dsum)[-10:]) / sum(dsum), 3))
# 4. экспозиция к рынку: регрессия ROI сделки на доходность актива за 24ч
X = [(z["ret24"], z["roi"]) for z in rez if z["ret24"] is not None]
x = np.array([a for a, _ in X]); y = np.array([b for _, b in X]); A = np.vstack([np.ones_like(x), x]).T
b, *_ = np.linalg.lstsq(A, y, rcond=None); r2 = 1 - ((y - A @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()
up = [z["roi"] for z in rez if z["ret24"] is not None and z["ret24"] > 0]; dn = [z["roi"] for z in rez if z["ret24"] is not None and z["ret24"] <= 0]
out["rynok"] = dict(n=len(X), svobodnyy_chlen_roi_pri_nulevom_dvizhenii=round(b[0], 4), beta_na_24ch=round(b[1], 3), R2=round(r2, 3),
    roi_kogda_aktiv_ros=round(np.mean(up), 4), n_ros=len(up), roi_kogda_padal=round(np.mean(dn), 4), n_padal=len(dn))
mes = collections.defaultdict(float)
for z in rez: mes[dt.datetime.utcfromtimestamp(z["konec"]).strftime("%Y-%m")] += z["pnl"]
out["bez_noyabrya_2025_usd"] = round(sum(v for k, v in mes.items() if k != "2025-11"), 2)
out["po_mesyacam_usd"] = {k: round(v, 1) for k, v in sorted(mes.items())}
print(json.dumps(out, ensure_ascii=False, indent=1))
Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1))
