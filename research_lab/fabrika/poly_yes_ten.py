#!/usr/bin/env python3
"""poly_yes_ten.py — хук сторожа: тень PREREG_POLY_YES_PEREPLATA_VPERED_2026_10_19. Только данные, ордеров нет.
Решения пишутся до расчёта, исходы — после, всё append-only в data/poly_yes_ten.jsonl. Доход до 30 событий не считается."""
import datetime as dt, glob, json, re
from pathlib import Path
from zoneinfo import ZoneInfo
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"
ZH = D / "poly_yes_ten.jsonl"; NY = ZoneInfo("America/New_York")
AKTIV = {"Bitcoin": "BTCUSDT", "Ethereum": "ETHUSDT", "Solana": "SOLUSDT", "XRP": "XRPUSDT"}
RX = re.compile(r"^Will the price of (Bitcoin|Ethereum|Solana|XRP) be above \$([\d,]+(?:\.\d+)?) on ([A-Z][a-z]+) (\d{1,2})\?$")
OKNO_MS, ISHOD_MS, POLOSA, MIN_USD = 20 * 60_000, 10 * 60_000, 0.003, 10.0
ZAMOROZKA_MS = 1792406621844     # момент заморозки prereg: снимки раньше — не решения (задним числом)
MES = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September",
                                   "October", "November", "December"], 1)}


def raschet_ms(mes, den, t_ms):
    t = dt.datetime.fromtimestamp(t_ms / 1000, NY)
    for god in (t.year, t.year + 1):
        r = dt.datetime(god, MES[mes], int(den), 12, 0, tzinfo=NY)
        if r.timestamp() * 1000 > t_ms - 3 * 86400_000:
            return int(r.timestamp() * 1000)
    return None


def zhurnal():
    return [json.loads(s) for s in ZH.read_text().splitlines() if s.strip()] if ZH.exists() else []


def resheniya(est, fayly):
    lučshie = {}
    for f in fayly:
        for s in open(f):
            if '"strike"' not in s:
                continue
            z = json.loads(s); m = RX.match(z.get("vopros") or "")
            if not m or z["conditionId"] in est or z["t"] < ZAMOROZKA_MS:
                continue
            r = raschet_ms(m.group(3), m.group(4), z["t"])
            if r is None:
                continue
            d = abs(z["t"] - (r - 86400_000))
            if d <= OKNO_MS and (z["conditionId"] not in lučshie or d < lučshie[z["conditionId"]][0]):
                lučshie[z["conditionId"]] = (d, z, m, r)
    out = []
    for cid, (d, z, m, r) in lučshie.items():
        bids = [b for b in z.get("bids") or [] if b[1] > 0]; asks = [a for a in z.get("asks") or [] if a[1] > 0]
        bb = max(bids, key=lambda b: b[0]) if bids else None; ba = min(asks, key=lambda a: a[0]) if asks else None
        zap = dict(tip="reshenie", conditionId=cid, sobytie=f"{m.group(1)}|{dt.datetime.fromtimestamp(r / 1000, NY).date()}",
                   aktiv=m.group(1), X=float(m.group(2).replace(",", "")), raschet_ms=r, snimok_ms=z["t"],
                   best_bid_yes=bb[0] if bb else None, best_ask_yes=ba[0] if ba else None,
                   zapisano_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        mid = (bb[0] + ba[0]) / 2 if bb and ba else None
        if mid is None or not 0.05 <= mid <= 0.95:
            zap["status"] = "VNE_DIAPAZONA"
        elif bb[0] * bb[1] < MIN_USD:
            zap["status"] = "NO_LIQUIDITY"
        else:
            zap.update(status="VHOD", cena_no=round(1 - bb[0], 4), mid_yes=round(mid, 4))
        out.append(zap)
    return out


def ishody(Z, seychas_ms):
    est = {z["conditionId"] for z in Z if z.get("tip") == "ishod"}
    nado = [z for z in Z if z.get("tip") == "reshenie" and z.get("status") == "VHOD" and z["conditionId"] not in est
            and seychas_ms > z["raschet_ms"] + ISHOD_MS]
    if not nado:
        return []
    ceny = {}
    for f in sorted(glob.glob(str(D / "kripto_atlas" / "sbor_*.jsonl")))[-6:]:
        for s in open(f):
            if '"BTCUSDT"' in s or '"ETHUSDT"' in s or '"SOLUSDT"' in s or '"XRPUSDT"' in s:
                z = json.loads(s)
                if z.get("s") in AKTIV.values() and z.get("b") and z.get("a"):
                    ceny.setdefault(z["s"], []).append((z["t"], (z["b"] + z["a"]) / 2))
    out = []
    for z in nado:
        ryad = ceny.get(AKTIV[z["aktiv"]], [])
        bl = min(ryad, key=lambda x: abs(x[0] - z["raschet_ms"]), default=None)
        if bl is None or abs(bl[0] - z["raschet_ms"]) > ISHOD_MS:
            if seychas_ms > z["raschet_ms"] + 3 * 86400_000:
                out.append(dict(tip="ishod", conditionId=z["conditionId"], status="NET_CENY")); 
            continue
        c = bl[1]
        if abs(c / z["X"] - 1) < POLOSA:
            out.append(dict(tip="ishod", conditionId=z["conditionId"], status="NEYASNO", cena=c)); continue
        yes = c > z["X"]
        out.append(dict(tip="ishod", conditionId=z["conditionId"], status="OK", yes=yes, cena=c, cena_t=bl[0],
                        dohod=((0 if yes else 1) - z["cena_no"]) / z["cena_no"],
                        dohod_stress=((0 if yes else 1) - (z["cena_no"] + 0.01)) / (z["cena_no"] + 0.01)))
    return out


def prohod():
    Z = zhurnal(); est = {z["conditionId"] for z in Z if z.get("tip") == "reshenie"}
    fs = sorted(glob.glob(str(D / "poly" / "snimki" / "*.jsonl")))[-3:]
    nov = resheniya(est, fs)
    ish = ishody(Z + nov, int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000))
    if nov or ish:
        with ZH.open("a") as f:
            for z in nov + ish:
                f.write(json.dumps(z, ensure_ascii=False) + "\n")
    vse = Z + nov + ish
    sob = {next(r["sobytie"] for r in vse if r.get("tip") == "reshenie" and r["conditionId"] == i["conditionId"])
           for i in vse if i.get("tip") == "ishod" and i.get("status") == "OK"}
    return {"novyh_resheniy": len(nov), "vhodov": sum(1 for z in nov if z.get("status") == "VHOD"), "novyh_ishodov": len(ish),
            "sobytiy_s_ishodom": len(sob), "vorota": 30}


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
