#!/usr/bin/env python3
"""nochnoy_fx_cost_gate.py — ворота полных издержек для NOCHNOY_DREYF fx7 long (CONFIRMED 01.10).

ЗАМОРОЖЕНО 2026-10-01 ДО получения данных брокера. Сигнал, часы, параметры и корзина из 7 пар не меняются;
подмножество пар — только отдельной новой предрегистрацией.

Сделки: замороженный механизм (mehanizmy NOCHNOY_DREYF, long, рынок fx7_glub_utc) на всей глубине
2018-12-24…2023-07-01 (O2+O1+O3), каждая сделка с часом входа и выхода. Валовой доход — в bps от входа.
Бары MT5 — цены Bid: лонг входит по Ask = Bid + спред, выходит по Bid.

Издержки на сделку (всё в долях цены входа):
  спред     = p75 спреда брокера в час входа (UTC, отдельно лето/зима по переводу часов США)
  проскальз = 0.5 × медианного спреда часа входа + 0.5 × медианного спреда часа выхода
  комиссия  = 2 × commission_usd_per_lot_side / номинал лота в USD
  своп      = swap_long за каждую ночь, если позиция открыта в момент переката (17:00 Нью-Йорка) или вход
              совпадает с ним; тройной своп в день swap_3day
Вердикт:
  INSUFFICIENT_DATA — нет спецификации или спредов по любой из 7 пар, или в истории спредов нет хотя бы
                      одного летнего и одного зимнего месяца
  NET_EXECUTABLE    — средний чистый доход корзины > 0, t по датам входа ≥ 2.0 на всей глубине,
                      И средний чистый доход > 0 на O3
  NOT_EXECUTABLE    — иначе
Вход (кладёт владелец / мост MT5 с БОЕВОГО счёта, не MetaQuotes-Demo):
  data/fx_broker/spec.json  {"broker":..,"server":..,"vremya":"mt5_eet"|"utc",
                             "<SYM>": {"point":..,"contract_size":..,"swap_long":..,"swap_mode":"points"|"money_per_lot",
                                       "swap_3day":2,"commission_usd_per_lot_side":..}}
  data/fx_broker/<SYM>.json {"ts":[мс, время сервера], "spread_points":[...]}   часовые бары, поле spread из copy_rates
    python3 research_lab/nochnoy_fx_cost_gate.py
"""
import glob, json, math, sys, calendar, datetime as dt
from pathlib import Path
import numpy as np

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB / "fabrika"))
from mehanizmy import MEHANIZMY, RYNKI, mt5_v_utc        # noqa: E402

PARY = ["AUDUSD", "EURUSD", "GBPUSD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY"]
BROKER = LAB / "data/fx_broker"; CH = 3600000; DEN = 86400000


def leto_ssha(t_ms):
    d = dt.datetime.utcfromtimestamp(t_ms / 1000).date(); y = d.year
    mar = [w[6] for w in calendar.monthcalendar(y, 3) if w[6]][1]
    nov = [w[6] for w in calendar.monthcalendar(y, 11) if w[6]][0]
    return dt.date(y, 3, mar) <= d < dt.date(y, 11, nov)


def perekat(t_ms):
    """момент переката (17:00 Нью-Йорка) в сутки, начинающиеся в t_ms (UTC)"""
    d = t_ms - t_ms % DEN
    return d + (21 if leto_ssha(t_ms) else 22) * CH


def sdelki():
    """замороженный механизм, с часом выхода (та же логика, что begun_meh.sim)"""
    M = MEHANIZMY["NOCHNOY_DREYF"]; R = RYNKI["fx7_glub_utc"]
    lo = min(a for a, _ in R["okna"].values()); hi = max(b for _, b in R["okna"].values()); o3 = R["okna"]["O3"]
    out = []
    for fp in sorted(glob.glob(str(LAB / R["papka"] / "*.npz"))):
        sym = Path(fp).stem; d = np.load(fp); ts = mt5_v_utc(d["ts"])
        o, h, l, c, v = (np.ascontiguousarray(d["ohlcv"][:, j], dtype=np.float64) for j in range(5))
        L, S, a = M["fn"](o, h, l, c, v, ts); blok = -1
        for i in np.flatnonzero(L):
            if i < 250 or i <= blok or i >= len(ts) - 1 or not (a[i] > 0) or not (lo <= ts[i] < hi):
                continue
            e = i + 1; entry = o[e]; risk = entry * M["stop"] * a[i] / entry
            sl, tp1, tp2 = entry - risk, entry + M["rr1"] * risk, entry + M["rr2"] * risk
            rem, gross, done, j_exit = 1.0, 0.0, False, None
            for j in range(e, min(e + M["hold"], len(o))):
                if l[j] <= sl:
                    gross += rem * (sl - entry); j_exit = j; rem = 0; break
                if not done and h[j] >= tp1:
                    gross += M["f1"] * (tp1 - entry); rem -= M["f1"]; done = True
                if rem > 1e-9 and h[j] >= tp2:
                    gross += rem * (tp2 - entry); j_exit = j; rem = 0; break
            if rem > 0:
                j_exit = min(e + M["hold"], len(o)) - 1; gross += rem * (c[j_exit] - entry)
            blok = i + M["hold"] // 4
            out.append(dict(sym=sym, t_vhod=int(ts[e]), t_vyhod=int(ts[j_exit]) + CH, cena=entry,
                            gross=gross / entry, o3=o3[0] <= ts[i] < o3[1]))
    return out


def ny_close_v_utc(ts):
    """сервер «нью-йоркского закрытия»: UTC+3 в летнее время США (2-е вс марта — 1-е вс ноября), иначе UTC+2"""
    ts = np.asarray(ts, dtype=np.int64); out = ts - 2 * 3600000
    for y in range(1990, 2100):
        vs = lambda m, n: [w[6] for w in calendar.monthcalendar(y, m) if w[6]][n]
        a = int(dt.datetime(y, 3, vs(3, 1), 2 + 2, tzinfo=dt.timezone.utc).timestamp() * 1000)   # 02:00 NY → время сервера
        b = int(dt.datetime(y, 11, vs(11, 0), 2 + 3, tzinfo=dt.timezone.utc).timestamp() * 1000)
        msk = (ts >= a) & (ts < b)
        out[msk] = ts[msk] - 3 * 3600000
    return out


def zagruzit_brokera():
    sp = BROKER / "spec.json"
    if not sp.exists():
        return None, "нет data/fx_broker/spec.json"
    spec = json.load(open(sp)); tab = {}
    for s in PARY:
        f = BROKER / f"{s}.json"
        need = ("point", "contract_size", "swap_long", "swap_mode", "swap_3day", "commission_usd_per_lot_side")
        if s not in spec or not all(k in spec[s] for k in need) or not f.exists():
            return None, f"нет спецификации или спредов для {s}"
        z = json.load(open(f)); ts = np.array(z["ts"], dtype=np.int64)
        vr = spec.get("vremya")             # 02.10: правило времени сервера — явное, определено выгрузкой, без умолчаний
        if vr == "mt5_eet":
            ts = mt5_v_utc(ts)
        elif vr == "ny_close":
            ts = ny_close_v_utc(ts)
        elif vr != "utc":
            return None, f"время сервера брокера не определено ({vr}) — спреды по часам UTC не разложить"
        sprd = np.array(z["spread_points"], float) * spec[s]["point"]
        leto = np.array([leto_ssha(int(t)) for t in ts]); chas = (ts // CH) % 24
        if not leto.any() or leto.all():
            return None, f"{s}: в истории спредов нет и летнего, и зимнего периода"
        tab[s] = {}
        for lt in (True, False):
            for hh in range(24):
                m = (leto == lt) & (chas == hh)
                if m.sum() >= 5:
                    tab[s][(lt, hh)] = (float(np.median(sprd[m])), float(np.percentile(sprd[m], 75)))
    return (spec, tab), None


def izderzhki(t, spec, tab):
    s = t["sym"]; sp = spec[s]; lt = leto_ssha(t["t_vhod"])
    hv, hx = (t["t_vhod"] // CH) % 24, (t["t_vyhod"] // CH) % 24
    if (lt, hv) not in tab[s] or (leto_ssha(t["t_vyhod"]), hx) not in tab[s]:
        return None
    med_v, p75_v = tab[s][(lt, hv)]; med_x, _ = tab[s][(leto_ssha(t["t_vyhod"]), hx)]
    p = t["cena"]
    spred = p75_v / p
    proskalz = 0.5 * med_v / p + 0.5 * med_x / p
    nominal_usd = sp["contract_size"] * (p if s.endswith("USD") else 1.0)
    komissiya = 2 * sp["commission_usd_per_lot_side"] / nominal_usd
    nochey = 0; pk = perekat(t["t_vhod"])
    for k in range(3):
        r = pk + k * DEN
        if t["t_vhod"] <= r < t["t_vyhod"]:
            nochey += 3 if dt.datetime.utcfromtimestamp(r / 1000).weekday() == sp["swap_3day"] else 1
    if sp["swap_mode"] == "points":
        svop = sp["swap_long"] * sp["point"] / p
    elif sp["swap_mode"] == "money_per_lot":
        svop = sp["swap_long"] / nominal_usd
    else:
        return None
    return spred + proskalz + komissiya - nochey * svop        # swap_long < 0 — это издержка


def verdikt():
    br, oshibka = zagruzit_brokera()
    if br is None:
        return {"verdikt": "INSUFFICIENT_DATA", "prichina": oshibka}
    spec, tab = br; T = sdelki(); net = []
    for t in T:
        k = izderzhki(t, spec, tab)
        if k is None:
            return {"verdikt": "INSUFFICIENT_DATA", "prichina": f"нет спреда брокера для часа сделки {t['sym']}"}
        net.append((t["t_vhod"] // DEN, t["gross"] - k, t["o3"], t["gross"]))
    po = {}
    for d, x, _, _ in net:
        po.setdefault(d, []).append(x)
    v = np.array([np.mean(q) for q in po.values()]); tt = v.mean() / (v.std(ddof=1) / math.sqrt(len(v)))
    vse = np.array([x for _, x, _, _ in net]); o3 = np.array([x for _, x, f, _ in net if f])
    ok = vse.mean() > 0 and tt >= 2.0 and o3.mean() > 0
    return {"verdikt": "NET_EXECUTABLE" if ok else "NOT_EXECUTABLE", "sdelok": len(net),
            "valovoy_bps": round(float(np.mean([g for *_, g in net])) * 1e4, 2),
            "chistyy_bps": round(float(vse.mean()) * 1e4, 2), "t_po_datam": round(float(tt), 2),
            "chistyy_O3_bps": round(float(o3.mean()) * 1e4, 2)}


if __name__ == "__main__":
    print(json.dumps(verdikt(), ensure_ascii=False))
