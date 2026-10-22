#!/usr/bin/env python3
"""poly_spravedlivaya_ten.py — хук сторожа: тень PREREG_POLY_SPRAVEDLIVAYA_TEN_2026_10_22. Только данные: ордеров, кошельков, ключей нет.

На проходе сторожа, если до «расчёт − 24 ч» ≤ 35 мин: для каждого рынка лестницы «X выше $K в 12:00 ET»
  S — середина bid/ask Bybit-перпа (публичный /v5/market/tickers), σ — 168 закрытых часовых лог-доходностей Bybit (×√8760),
  τ — фактическое время до расчёта; p* = N(d2), d2 = (ln(S/K) − σ²τ/2)/(σ√τ);
  цены покупки YES и NO на 10 $ — VWAP по живым стаканам CLOB каждого токена + комиссия 0.07·v(1−v) (стресс: 0.10 и +1 ¢);
  хедж: статическая дельта цифрового опциона, номинал = токены · φ(d2)/(σ√τ) (в $), перп Bybit, тейкер 0.055 % на вход и выход;
  ожидаемый доход стороны на 1 $ = p_стороны*/цена − 1 − расход_хеджа/10 $; вход в сторону с большим ожиданием, если оно > 0 ПРИ СТРЕССЕ.
Исход — официальное разрешение Polymarket; результат хеджа — по цене Bybit в момент расчёта. Доход до 30 событий не показывается.
Журнал append-only: data/poly_spravedlivaya_ten.jsonl (поля dohod/dohod_stress — с хеджем, как у судьи poly_yes_verdikt)."""
import datetime as dt, glob, json, math, sys, time
from pathlib import Path
from statistics import NormalDist
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poly_yes_ten as Y
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"
ZH = D / "poly_spravedlivaya_ten.jsonl"
BYBIT = "https://api.bybit.com"
ZAMOROZKA_MS = 1792672201000          # коммит prereg 85803c8 (22.10.2026 12:30 UTC)
NOTIONAL, FEE, FEE_S, SPRED_S, HEDGE_FEE = 10.0, 0.07, 0.10, 0.01, 0.00055
ND = NormalDist()


def zhurnal():
    return [json.loads(s) for s in ZH.read_text().splitlines() if s.strip()] if ZH.exists() else []


def bybit_S(sym, get=Y.get):
    r = get(BYBIT, "/v5/market/tickers", category="linear", symbol=sym)["result"]["list"][0]
    return (float(r["bid1Price"]) + float(r["ask1Price"])) / 2


def bybit_sigma(sym, seychas_ms, get=Y.get):
    lst = get(BYBIT, "/v5/market/kline", category="linear", symbol=sym, interval="60", limit=200)["result"]["list"]
    bars = sorted((int(x[0]), float(x[4])) for x in lst if int(x[0]) + 3600_000 <= seychas_ms)[-169:]   # только закрытые
    if len(bars) < 169: return None
    r = [math.log(bars[i][1] / bars[i - 1][1]) for i in range(1, len(bars))]
    m = sum(r) / len(r); return math.sqrt(sum((x - m) ** 2 for x in r) / (len(r) - 1)) * math.sqrt(8760)


def model(S, K, sigma, tau):
    d2 = (math.log(S / K) - sigma * sigma * tau / 2) / (sigma * math.sqrt(tau))
    return ND.cdf(d2), math.exp(-d2 * d2 / 2) / math.sqrt(2 * math.pi), d2


def cena(v, fee, spred=0.0):
    q = v + spred; return q + fee * q * (1 - q)


def reshit(p_star, phi, sigma, tau, vw_yes, vw_no):
    """Чистая функция решения (тестируется без сети). Возвращает dict с ожиданиями и выбранной стороной (или None)."""
    hedge_frac = (phi / (sigma * math.sqrt(tau))) * 2 * HEDGE_FEE        # на 1 токен-$ выплаты; ниже переводим на 1 $ вложений
    out = {}
    for st, v, p in (("YES", vw_yes, p_star), ("NO", vw_no, 1 - p_star)):
        if v is None: continue
        for kl, f, s in (("", FEE, 0.0), ("_stress", FEE_S, SPRED_S)):
            c = cena(v, f, s); tok = NOTIONAL / c
            out[f"ev_{st}{kl}"] = p / c - 1 - tok * hedge_frac / NOTIONAL
            out[f"cena_{st}{kl}"] = c
    kand = [(out[f"ev_{s}_stress"], s) for s in ("YES", "NO") if f"ev_{s}_stress" in out]
    best = max(kand) if kand else None
    out["storona"] = best[1] if best and best[0] > 0 else None
    return out


def kniga(token, cid, seychas_ms, get=Y.get):
    b = get(Y.CLOB, "/book", token_id=token) or {}
    st, osh = Y.razobrat_stakan_no(b, token, cid, seychas_ms)          # общий разбор: VWAP покупки на 10 $ по глубине
    return st, osh


def resheniya(est, snimki, seychas_ms, get=Y.get):
    out, kesh = [], {}
    for cid, z in snimki.items():
        m = Y.RX.match(z["vopros"])
        if cid in est or z["t"] < ZAMOROZKA_MS or not ZAMOROZKA_MS: continue
        r = Y.raschet_ms(m.group(3), m.group(4), z["t"])
        if r is None or abs(seychas_ms - (r - 86400_000)) > Y.OKNO_MS: continue
        aktiv = m.group(1); sym = Y.AKTIV[aktiv]; K = float(m.group(2).replace(",", ""))
        zap = dict(tip="reshenie", conditionId=cid, sobytie=f"{aktiv}|{dt.datetime.fromtimestamp(r / 1000, Y.NY).date()}", aktiv=aktiv, X=K,
                   raschet_ms=r, reshenie_ms=seychas_ms, zapisano_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
        try:
            if sym not in kesh: kesh[sym] = (bybit_S(sym, get), bybit_sigma(sym, seychas_ms, get))
            S, sg = kesh[sym]
            if not sg: raise ValueError("SIGMA")
            tau = (r - seychas_ms) / (365 * 86400_000); p_star, phi, d2 = model(S, K, sg, tau)
            g = Y.rynok_gamma(cid, get_fn=get); toks, outc = Y.js(g.get("clobTokenIds")) or [], Y.js(g.get("outcomes")) or []
            tk = {str(o).lower(): t for t, o in zip(toks, outc)}
            sy, oy = kniga(tk["yes"], cid, seychas_ms, get); sn, on = kniga(tk["no"], cid, seychas_ms, get)
        except Exception as e:
            zap["status"] = f"NET_DANNYH: {type(e).__name__}"; out.append(zap); continue
        d = reshit(p_star, phi, sg, tau, sy and sy["vwap_no_10usd"], sn and sn["vwap_no_10usd"])
        zap.update(S=S, sigma=sg, tau=tau, p_star=p_star, d2=d2, vwap_yes=sy and sy["vwap_no_10usd"], vwap_no=sn and sn["vwap_no_10usd"],
                   book_yes_sha=sy and sy["book_sha256"], book_no_sha=sn and sn["book_sha256"], prichina_yes=oy, prichina_no=on, **d)
        if d["storona"]:
            c = d[f"cena_{d['storona']}"]; tok = NOTIONAL / c
            delta_usd = tok * phi / (sg * math.sqrt(tau))                     # $ на 1 единицу относительного движения S
            zap.update(status="VHOD", tokenov=tok, hedge_notional_usd=delta_usd, hedge_napravlenie="SHORT" if d["storona"] == "YES" else "LONG",
                       hedge_rashod_usd=delta_usd * 2 * HEDGE_FEE)
        else:
            zap["status"] = "NET_PREIMUSHCHESTVA"
        out.append(zap)
    return out


def bybit_S_v(sym, t_ms, get=Y.get):
    lst = get(BYBIT, "/v5/market/kline", category="linear", symbol=sym, interval="1", start=t_ms - 60_000, end=t_ms + 60_000, limit=5)["result"]["list"]
    x = min(lst, key=lambda x: abs(int(x[0]) - t_ms)); return float(x[1]) if abs(int(x[0]) - t_ms) <= 60_000 else None


def ishody(Z, seychas_ms, get=Y.get):
    est = {z["conditionId"] for z in Z if z.get("tip") == "ishod"}
    out = []
    for z in [z for z in Z if z.get("tip") == "reshenie" and z.get("status") == "VHOD" and z["conditionId"] not in est and seychas_ms > z["raschet_ms"] + Y.ISHOD_MS]:
        try:
            m = Y.rynok_gamma(z["conditionId"], get_fn=get); S1 = bybit_S_v(Y.AKTIV[z["aktiv"]], z["raschet_ms"], get)
        except Exception:
            continue
        if not m or not m.get("closed") or S1 is None: continue
        outc = Y.js(m.get("outcomes")) or []; pr = [float(x) for x in Y.js(m.get("outcomePrices")) or []]
        if len(pr) != len(outc) or max(pr, default=0) < 0.99: continue
        yes_win = next((p for p, o in zip(pr, outc) if str(o).lower() == "yes"), 0.0) >= 0.99
        vypl = 1.0 if (yes_win == (z["storona"] == "YES")) else 0.0
        hod = S1 / z["S"] - 1; hedge = (-1 if z["hedge_napravlenie"] == "SHORT" else 1) * z["hedge_notional_usd"] * hod - z["hedge_rashod_usd"]
        res = {}
        for kl in ("", "_stress"):
            c = z[f"cena_{z['storona']}{kl}"]; tok = NOTIONAL / c
            res["dohod" + kl] = (tok * vypl - NOTIONAL + hedge) / NOTIONAL
        out.append(dict(tip="ishod", conditionId=z["conditionId"], status="OK", istochnik="polymarket_resolution", yes_vyigral=yes_win,
                        S_raschet=S1, hedge_usd=hedge, dohod_bez_hedzha=(NOTIONAL / z[f"cena_{z['storona']}"] * vypl - NOTIONAL) / NOTIONAL,
                        zapisano_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **res))
    return out


def prohod():
    Z = zhurnal(); est = {z["conditionId"] for z in Z if z.get("tip") == "reshenie"}; seychas = int(time.time() * 1000)
    sn = Y.poslednie_snimki(sorted(glob.glob(str(D / "poly" / "snimki" / "*.jsonl")))[-1:])
    nov = resheniya(est, sn, seychas); ish = ishody(Z + nov, seychas)
    if nov or ish:
        with ZH.open("a") as f:
            for z in nov + ish: f.write(json.dumps(z, ensure_ascii=False) + "\n")
    return {"novyh_resheniy": len(nov), "vhodov": sum(1 for z in nov if z.get("status") == "VHOD"), "novyh_ishodov": len(ish)}


if __name__ == "__main__":
    if "--proba" in sys.argv:          # проверка сети и расчёта на одном рынке, окно игнорируется, НИЧЕГО НЕ ПИШЕТ
        sn = Y.poslednie_snimki(sorted(glob.glob(str(D / "poly" / "snimki" / "*.jsonl")))[-1:])
        for cid, z in sn.items():
            m = Y.RX.match(z["vopros"]); r = Y.raschet_ms(m.group(3), m.group(4), z["t"])
            if r and r > time.time() * 1000:
                old = Y.OKNO_MS, ZAMOROZKA_MS; Y.OKNO_MS, ZAMOROZKA_MS = 10 ** 13, 1   # только для пробы: окно и заморозка не проверяются
                try: print(json.dumps(resheniya(set(), {cid: z}, int(time.time() * 1000)), ensure_ascii=False, indent=1))
                finally: Y.OKNO_MS, ZAMOROZKA_MS = old
                break
    else:
        print(json.dumps(prohod(), ensure_ascii=False))
