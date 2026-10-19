#!/usr/bin/env python3
"""poly_yes_ten.py — хук сторожа: тень PREREG_POLY_YES_PEREPLATA_VPERED_2026_10_19 (+ дополнение 1). Только данные, ордеров нет.

Решение принимается ЖИВЬЁМ на проходе сторожа, если до момента «расчёт − 24 ч» не больше 35 мин в любую сторону:
  фильтр по YES-стакану из последнего снимка `data/poly/snimki` (середина ∈ [0.05, 0.95]);
  цена входа — ЛУЧШИЙ ASK В СТАКАНЕ ТОКЕНА NO (CLOB /book), объём на нём ≥ 10 $ → статус VHOD (исполнимо по котировке);
  нет NO-стакана/объёма → NO_LIQUIDITY; ошибка сети → NET_STAKANA (в вывод не идут).
Исход — ОФИЦИАЛЬНОЕ разрешение Polymarket (Gamma: closed + outcomePrices); цена Bybit-перпа (kripto_atlas) — только сверка.
Всё append-only в data/poly_yes_ten.jsonl. Доход до 30 событий не считается и не показывается.
  python3 research_lab/fabrika/poly_yes_ten.py --proba   # проверка сети/стаканов на одном рынке, ничего не пишет"""
import datetime as dt, glob, json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"
ZH = D / "poly_yes_ten.jsonl"; NY = ZoneInfo("America/New_York")
GAMMA, CLOB = "https://gamma-api.polymarket.com", "https://clob.polymarket.com"
AKTIV = {"Bitcoin": "BTCUSDT", "Ethereum": "ETHUSDT", "Solana": "SOLUSDT", "XRP": "XRPUSDT"}
RX = re.compile(r"^Will the price of (Bitcoin|Ethereum|Solana|XRP) be above \$([\d,]+(?:\.\d+)?) on ([A-Z][a-z]+) (\d{1,2})\?$")
OKNO_MS, ISHOD_MS, POLOSA, MIN_USD = 35 * 60_000, 10 * 60_000, 0.003, 10.0
ZAMOROZKA_MS = 1792406621844     # заморозка prereg (3a71dc6): раньше — не решения
MES = {m: i for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September",
                                   "October", "November", "December"], 1)}


def get(base, path, **q):
    url = f"{base}{path}" + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={"User-Agent": "research-readonly/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def js(x):
    return json.loads(x) if isinstance(x, str) else x


def rynok_gamma(cid):
    r = get(GAMMA, "/markets", condition_ids=cid)
    r = r if isinstance(r, list) else (r or {}).get("data", [])
    return r[0] if r else None


def raschet_ms(mes, den, t_ms):
    t = dt.datetime.fromtimestamp(t_ms / 1000, NY)
    for god in (t.year, t.year + 1):
        r = dt.datetime(god, MES[mes], int(den), 12, 0, tzinfo=NY)
        if r.timestamp() * 1000 > t_ms - 3 * 86400_000:
            return int(r.timestamp() * 1000)
    return None


def zhurnal():
    return [json.loads(s) for s in ZH.read_text().splitlines() if s.strip()] if ZH.exists() else []


def poslednie_snimki(fayly):
    """conditionId → последняя запись YES-стакана (по последнему файлу снимков)."""
    out = {}
    for f in fayly:
        for s in open(f):
            if '"strike"' in s:
                z = json.loads(s)
                if RX.match(z.get("vopros") or ""):
                    out[z["conditionId"]] = z
    return out


NOTIONAL_USD, STAROST_MS, PROTIVORECHIE = 10.0, 5 * 60_000, 0.05
# комиссия тейкера Polymarket (docs.polymarket.com/trading/fees): fee = shares × feeRate × p × (1 − p); крипто feeRate 0.07.
# Стресс: feeRate 0.10 (поле Gamma takerBaseFee = 1000 толкуется как 1000 bps) + 1 ¢.
FEE_RATE, FEE_RATE_STRESS = 0.07, 0.10


def razobrat_stakan_no(b, no_token, cid, seychas_ms, bid_yes=None):
    """CLOB-снимок стакана NO → цена исполнения покупки на NOTIONAL_USD. Порядок уровней в ответе не важен:
    asks сортируются по цене возрастанию, bids — убыванию. size — в токенах (shares), доллары = price × size.
    Возвращает (dict, None) или (None, причина пропуска). Подмены формулой 1 − YES нет."""
    import hashlib
    raw = json.dumps(b, sort_keys=True).encode()
    meta = dict(no_token=no_token, book_sha256=hashlib.sha256(raw).hexdigest(), book_ts=b.get("timestamp"),
                book_market=b.get("market"), book_asset=b.get("asset_id"), tick_size=b.get("tick_size"),
                min_order_size=b.get("min_order_size"))
    if b.get("asset_id") and str(b["asset_id"]) != str(no_token):
        return None, "TOKEN_NE_SOVPAL"
    if b.get("market") and str(b["market"]).lower() != str(cid).lower():
        return None, "RYNOK_NE_SOVPAL"
    try:
        ts = int(b.get("timestamp")) if b.get("timestamp") else None
    except ValueError:
        ts = None
    if ts is None or seychas_ms - ts > STAROST_MS:
        return None, "STAKAN_USTAREL"
    asks = sorted((float(a["price"]), float(a["size"])) for a in b.get("asks") or [] if float(a["size"]) > 0)
    bids = sorted(((float(x["price"]), float(x["size"])) for x in b.get("bids") or [] if float(x["size"]) > 0), reverse=True)
    if not asks:
        return None, "NO_LIQUIDITY"
    if bids and bids[0][0] >= asks[0][0]:
        return None, "STAKAN_PERESECHEN"
    if bid_yes is not None and abs(asks[0][0] - (1 - bid_yes)) > PROTIVORECHIE:
        return None, "PROTIVORECHIE_YES_NO"
    nado, kupleno, potr = NOTIONAL_USD, 0.0, 0.0
    for p, sz in asks:
        voz = min(sz, (nado - potr) / p)
        kupleno += voz; potr += voz * p
        if potr >= nado - 1e-9:
            break
    if potr < nado - 1e-9:
        return None, "NO_LIQUIDITY"
    mos = float(b.get("min_order_size") or 0)
    if kupleno < mos:
        return None, "MENSHE_MIN_ORDERA"
    meta.update(best_ask_no=asks[0][0], razmer_best_ask_tokenov=asks[0][1], razmer_best_ask_usd=round(asks[0][0] * asks[0][1], 2),
                vwap_no_10usd=round(potr / kupleno, 6), tokenov_na_10usd=round(kupleno, 4), urovney_ask=len(asks),
                best_bid_no=bids[0][0] if bids else None, asks_top5=asks[:5])
    return meta, None


def stakan_no(cid, gamma_fn=rynok_gamma, book_fn=lambda t: get(CLOB, "/book", token_id=t), seychas_ms=None, bid_yes=None):
    m = gamma_fn(cid)
    if not m:
        return None, "NET_RYNKA"
    toks, outc = js(m.get("clobTokenIds")) or [], js(m.get("outcomes")) or []
    no = next((t for t, o in zip(toks, outc) if str(o).lower() == "no"), None)
    if not no or len(toks) != 2:
        return None, "NET_TOKENA_NO"
    b = book_fn(no) or {}
    st, osh = razobrat_stakan_no(b, no, cid, seychas_ms or int(time.time() * 1000), bid_yes)
    if st:
        st["gamma_indikativno"] = dict(outcomePrices=m.get("outcomePrices"), endDate=m.get("endDate"),
                                       feesEnabled=m.get("feesEnabled"), takerBaseFee=m.get("takerBaseFee"))
    return st, osh


def resheniya(est, snimki, seychas_ms, stakan_fn=stakan_no):
    out = []
    for cid, z in snimki.items():
        m = RX.match(z["vopros"])
        if cid in est or z["t"] < ZAMOROZKA_MS:
            continue
        r = raschet_ms(m.group(3), m.group(4), z["t"])
        if r is None or abs(seychas_ms - (r - 86400_000)) > OKNO_MS:
            continue
        bids = [b for b in z.get("bids") or [] if b[1] > 0]; asks = [a for a in z.get("asks") or [] if a[1] > 0]
        bb = max(bids)[0] if bids else None; ba = min(asks)[0] if asks else None
        zap = dict(tip="reshenie", conditionId=cid, sobytie=f"{m.group(1)}|{dt.datetime.fromtimestamp(r / 1000, NY).date()}",
                   aktiv=m.group(1), X=float(m.group(2).replace(",", "")), raschet_ms=r, snimok_yes_ms=z["t"],
                   best_bid_yes=bb, best_ask_yes=ba, reshenie_ms=seychas_ms,
                   zapisano_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        mid = (bb + ba) / 2 if bb is not None and ba is not None else None
        if mid is None or not 0.05 <= mid <= 0.95:
            zap["status"] = "VNE_DIAPAZONA"; out.append(zap); continue
        try:
            st, osh = stakan_fn(cid, seychas_ms=seychas_ms, bid_yes=bb)
        except Exception as e:
            st, osh = None, f"NET_STAKANA: {type(e).__name__}"
        if st is None:
            zap["status"] = osh
        else:
            g = st.get("gamma_indikativno") or {}
            ed = g.get("endDate")
            try:
                ed_ms = int(dt.datetime.fromisoformat(ed.replace("Z", "+00:00")).timestamp() * 1000) if ed else None
            except ValueError:
                ed_ms = None
            if ed_ms is not None and abs(ed_ms - r) > 3600_000:
                zap.update(st, status="VREMYA_RASHODITSYA", endDate_ms=ed_ms)
            else:
                p = st["vwap_no_10usd"]; fe = g.get("feesEnabled") is not False      # неизвестно → считаем, что комиссия есть
                cena = p + (FEE_RATE * p * (1 - p) if fe else 0.0)
                cena_s = p + (FEE_RATE_STRESS * p * (1 - p) if fe else 0.0) + 0.01
                zap.update(st, status="VHOD", cena_no=round(cena, 6), cena_no_stress=round(cena_s, 6), komissiya_vklyuchena=fe,
                           mid_yes=round(mid, 4), zerkalo_no_tolko_sravnenie=round(1 - bb, 4) if bb is not None else None)
        out.append(zap)
    return out


def ishody(Z, seychas_ms, gamma_fn=rynok_gamma):
    est = {z["conditionId"] for z in Z if z.get("tip") == "ishod"}
    nado = [z for z in Z if z.get("tip") == "reshenie" and z.get("status") == "VHOD" and z["conditionId"] not in est
            and seychas_ms > z["raschet_ms"] + ISHOD_MS]
    out = []
    for z in nado:
        try:
            m = gamma_fn(z["conditionId"])
        except Exception:
            continue                                       # сеть — повторим на следующем проходе
        if not m or not m.get("closed"):
            continue
        outc = js(m.get("outcomes")) or []; pr = [float(x) for x in js(m.get("outcomePrices")) or []]
        if len(pr) != len(outc) or max(pr, default=0) < 0.99:
            continue                                       # ещё не разрешён однозначно
        no_vyigral = next((p for p, o in zip(pr, outc) if str(o).lower() == "no"), 0.0) >= 0.99
        out.append(dict(tip="ishod", conditionId=z["conditionId"], status="OK", istochnik="polymarket_resolution",
                        umaResolutionStatus=m.get("umaResolutionStatus"), outcomePrices=m.get("outcomePrices"),
                        no_vyigral=no_vyigral, dohod=((1 if no_vyigral else 0) - z["cena_no"]) / z["cena_no"],
                        dohod_stress=((1 if no_vyigral else 0) - z.get("cena_no_stress", z["cena_no"] + 0.01)) / z.get("cena_no_stress", z["cena_no"] + 0.01),
                        sverka_bybit=sverka(z), zapisano_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
    return out


def sverka(z):
    best = None
    for f in sorted(glob.glob(str(D / "kripto_atlas" / "sbor_*.jsonl")))[-5:]:
        for s in open(f):
            if f'"{AKTIV[z["aktiv"]]}"' in s:
                x = json.loads(s)
                if x.get("b") and x.get("a") and (best is None or abs(x["t"] - z["raschet_ms"]) < abs(best[0] - z["raschet_ms"])):
                    best = (x["t"], (x["b"] + x["a"]) / 2)
    if not best or abs(best[0] - z["raschet_ms"]) > ISHOD_MS:
        return None
    return dict(cena=best[1], yes_po_bybit=best[1] > z["X"], neyasno=abs(best[1] / z["X"] - 1) < POLOSA)


def prohod():
    Z = zhurnal(); est = {z["conditionId"] for z in Z if z.get("tip") == "reshenie"}
    seychas = int(time.time() * 1000)
    sn = poslednie_snimki(sorted(glob.glob(str(D / "poly" / "snimki" / "*.jsonl")))[-1:])
    nov = resheniya(est, sn, seychas)
    ish = ishody(Z + nov, seychas)
    if nov or ish:
        with ZH.open("a") as f:
            for z in nov + ish:
                f.write(json.dumps(z, ensure_ascii=False) + "\n")
    vse = Z + nov + ish
    res = {r["conditionId"]: r["sobytie"] for r in vse if r.get("tip") == "reshenie"}
    sob = {res[i["conditionId"]] for i in vse if i.get("tip") == "ishod" and i.get("status") == "OK"}
    return {"novyh_resheniy": len(nov), "vhodov": sum(1 for z in nov if z.get("status") == "VHOD"), "novyh_ishodov": len(ish),
            "sobytiy_s_ishodom": len(sob), "vorota": 30}


if __name__ == "__main__":
    if "--proba" in sys.argv:
        sn = poslednie_snimki(sorted(glob.glob(str(D / "poly" / "snimki" / "*.jsonl")))[-1:])
        cid = next(iter(sn), None); print("рынок:", sn[cid]["vopros"] if cid else None)
        if cid:
            print("NO-стакан:", stakan_no(cid)); m = rynok_gamma(cid); print("gamma closed/outcomePrices:", m and (m.get("closed"), m.get("outcomePrices")))
        # пример решения на рынке в диапазоне (как его записала бы тень), без записи в журнал
        for cid, z in sn.items():
            bids = [b for b in z.get("bids") or [] if b[1] > 0]; asks = [a for a in z.get("asks") or [] if a[1] > 0]
            if bids and asks and 0.05 <= (max(bids)[0] + min(asks)[0]) / 2 <= 0.95:
                print("рынок в диапазоне:", z["vopros"], "| YES bid/ask", max(bids)[0], min(asks)[0])
                print(json.dumps(stakan_no(cid, bid_yes=max(bids)[0]), ensure_ascii=False, indent=1)); break
    else:
        print(json.dumps(prohod(), ensure_ascii=False))
