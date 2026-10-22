#!/usr/bin/env python3
"""Тень вперёд: BTC/ETH только лонг + CASH по 12-недельному тренду (prereg PREREG_TSMOM_LONG_TEN_2026_10_22.md).
Правило = tsmom_btc_eth.leg(long_only=True): раз в неделю по закрытию воскресенья UTC знак лог-доходности за 12 недель;
> 0 → лонг с весом 0.20/σ(12 нед)·√52 (не больше 1.5), иначе CASH. Расходы 8 bps на сторону от оборота. Половина капитала на монету.
Данные: публичные дневки Bybit spot (без ключей). Без ордеров и LIVE. Пересчёт целиком при каждом запуске — идемпотентно.
Сравнение: «держать с тем же риском» (всегда лонг тем же весом) и CASH (0%)."""
import datetime as dt, json, math, statistics as st, sys, urllib.request
from pathlib import Path
LAB = Path(__file__).resolve().parent
START = dt.date(2026, 10, 25)      # первое решение — по закрытию недели, кончающейся в это воскресенье
COST, TV, CAP, L = 8e-4, 0.20, 1.5, 12
SYMS = ("BTCUSDT", "ETHUSDT")


def dnevki(sym):
    u = f"https://api.bybit.com/v5/market/kline?category=spot&symbol={sym}&interval=D&limit=400"
    req = urllib.request.Request(u, headers={"User-Agent": "research"})
    with urllib.request.urlopen(req, timeout=25) as f:
        lst = json.load(f)["result"]["list"]
    return sorted([int(r[0]), float(r[4])] for r in lst)


def nedeli(rows, segodnya):
    """[(дата воскресенья, close)] только завершённых недель (воскресный дневной бар закрыт)."""
    w = {}
    for ts, c in rows:
        d = dt.datetime.fromtimestamp(ts / 1000, dt.timezone.utc).date()
        if d >= segodnya:          # бар текущего дня ещё не закрыт
            continue
        w[d.isocalendar()[:2]] = (d, c)
    ks = sorted(w)
    vse = [w[k] for k in ks if w[k][0].weekday() == 6]   # неделя закрыта, только если есть бар воскресенья
    return vse


def noga(ned):
    """Возвращает [(дата решения, вес, доходность следующей недели или None, доходность держать)]."""
    px = [c for _, c in ned]; r = [math.log(px[i] / px[i - 1]) for i in range(1, len(px))]
    out, prev, prev_h = [], 0.0, 0.0
    for i in range(L, len(r) + 1):
        d = ned[i][0]
        sig = st.pstdev(r[i - 12:i]) * math.sqrt(52)
        wh = min(CAP, TV / sig) if sig > 0 else 0.0
        w = wh if sum(r[i - L:i]) > 0 else 0.0
        if d < START:
            prev, prev_h = w, wh; continue
        if i < len(r):
            g = math.exp(r[i]) - 1
            ret, reth = w * g - abs(w - prev) * COST, wh * g - abs(wh - prev_h) * COST
        else:
            ret = reth = None
        out.append((d.isoformat(), round(w, 4), ret, reth)); prev, prev_h = w, wh
    return out


def svodka(p):
    if not p: return None
    eq, pk, mdd = 1.0, 1.0, 0.0
    for x in p: eq *= 1 + x; pk = max(pk, eq); mdd = max(mdd, 1 - eq / pk)
    return {"nedel": len(p), "itog_%": round((eq - 1) * 100, 2), "maks_prosadka_%": round(mdd * 100, 2)}


def main():
    segodnya = dt.datetime.now(dt.timezone.utc).date()
    nogi = {s: noga(nedeli(dnevki(s), segodnya)) for s in SYMS}
    data = sorted(set(x[0] for v in nogi.values() for x in v))
    port, hold, zap = [], [], []
    for d in data:
        rows = {s: next((x for x in v if x[0] == d), None) for s, v in nogi.items()}
        zap.append({"reshenie": d, **{s: {"ves": x[1], "dohod": x[2]} for s, x in rows.items() if x}})
        if all(x and x[2] is not None for x in rows.values()):
            port.append(st.mean(x[2] for x in rows.values())); hold.append(st.mean(x[3] for x in rows.values()))
    out = {"kogda": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "start": START.isoformat(),
           "strategiya": svodka(port), "derzhat_tot_zhe_risk": svodka(hold), "cash_%": 0.0,
           "tekushchie_vesa": zap[-1] if zap else None, "nedeli": zap,
           "pravilo_obzora": "без вердикта до 26 недель; основной обзор на 52 неделях (prereg)"}
    f = LAB / "results" / f"tsmom_long_ten_{segodnya:%Y%m%d}.json"
    f.parent.mkdir(exist_ok=True); f.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: out[k] for k in ("strategiya", "derzhat_tot_zhe_risk", "tekushchie_vesa")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
