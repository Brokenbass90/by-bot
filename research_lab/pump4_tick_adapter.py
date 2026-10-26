#!/usr/bin/env python3
"""Эталонный адаптер нативного стопа PUMP4 под шаг цены Bybit (26.10.2026, Claude research; для порта Codex в ORDERS_OFF). V1 не меняется.
Правила (риск никогда не растёт):
  * стоп округляется ТОЛЬКО к цене входа (шорт — вниз к тику, лонг — вверх); геометрия триггера: шорт-стоп > текущей цены, лонг-стоп < неё;
  * цели — тоже к входу (шорт — вверх к тику, лонг — вниз): выход раньше, не позже;
  * объём = floor(риск $ / риск на единицу после округления) до qtyStep; меньше minOrderQty или номинал < minNotionalValue → BLOCK
    (объём не увеличивается);
  * TP1-часть = floor(объём × f1) до qtyStep; если TP1-часть или остаток < minOrderQty → флаг TP1_NE_DELITSYA (закрывающие ордера
    освобождены от min notional, но не от min qty — замечание Codex).
Прогон: .venv/bin/python3 research_lab/pump4_tick_adapter.py [--risk 3]   (сеть: публичный instruments-info Bybit, на Mac)
→ results/pump4_tick_adapter_<время>.json; тесты: fabrika/test_pump4_tick_adapter.py"""
import argparse, collections, hashlib, importlib, json, os, sys, time, urllib.request
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))


def _q(x, step, rounding):
    x, step = Decimal(str(x)), Decimal(str(step))
    return (x / step).to_integral_value(rounding=rounding) * step


def okruglit(side, entry, stop, tps, tick, qty_step, min_qty, min_notional, risk_usd, last_price, f1=0.55):
    short = side == "short"
    st = _q(stop, tick, ROUND_FLOOR if short else ROUND_CEILING)
    E = Decimal(str(entry)); S0 = Decimal(str(stop)); last = Decimal(str(last_price))
    tp = [_q(t, tick, ROUND_CEILING if short else ROUND_FLOOR) for t in tps]
    out = dict(stop_ref=float(S0), stop=float(st), tps_ref=list(tps), tps=[float(t) for t in tp], status="OK", flagi=[])
    if short and not (E < st <= S0): out["status"] = "BLOCK_STOP_GEOMETRIYA"; return out
    if not short and not (S0 <= st < E): out["status"] = "BLOCK_STOP_GEOMETRIYA"; return out
    if (short and st <= last) or (not short and st >= last): out["status"] = "BLOCK_TRIGGER_ZA_CENOY"; return out
    na_ed = abs(E - st)
    qty = _q(Decimal(str(risk_usd)) / na_ed, qty_step, ROUND_FLOOR)
    out.update(qty=float(qty), risk_usd=float(qty * na_ed), notional=float(qty * E),
               stop_sdvig_tikov=int(abs(S0 - st) / Decimal(str(tick))), risk_umenshen_dolya=float(1 - na_ed / abs(E - S0)))
    if qty < Decimal(str(min_qty)): out["status"] = "BLOCK_MIN_QTY"; return out
    if qty * E < Decimal(str(min_notional)): out["status"] = "BLOCK_MIN_NOTIONAL"; return out
    q1 = _q(qty * Decimal(str(f1)), qty_step, ROUND_FLOOR); ost = qty - q1
    out.update(qty_tp1=float(q1), qty_ostatok=float(ost))
    if q1 < Decimal(str(min_qty)) or ost < Decimal(str(min_qty)): out["flagi"].append("TP1_NE_DELITSYA")
    assert qty * na_ed <= Decimal(str(risk_usd)) + Decimal("1e-12")
    return out


def instrumenty():
    out, cur = {}, ""
    while True:
        u = "https://api.bybit.com/v5/market/instruments-info?category=linear&limit=1000" + (f"&cursor={cur}" if cur else "")
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "research/1.0"}), timeout=25) as r:
            res = json.loads(r.read())["result"]
        for x in res["list"]:
            out[x["symbol"]] = dict(tick=x["priceFilter"]["tickSize"], qty_step=x["lotSizeFilter"]["qtyStep"],
                                    min_qty=x["lotSizeFilter"]["minOrderQty"], min_notional=x["lotSizeFilter"].get("minNotionalValue", "5"))
        cur = res.get("nextPageCursor") or ""
        if not cur: return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--risk", type=float, default=3.0); a = ap.parse_args()
    import pump4_fanding_ekonomika as FE, pump4_pereschet as P, pump4_polnyy_povtor as PP
    ins = instrumenty()
    et = json.loads(FE.ETALON.read_text()); ref = {(x["sym"], x["ts"]): x for x in et["sdelki"] if x["status"] == "ZAKRYTA"}
    import datetime as dt
    now = int(dt.datetime.fromisoformat(et["svod"]["kogda_utc"].replace("Z", "+00:00")).timestamp() * 1000); H = FE.H; konec = now // H * H
    univ = json.load(open(HERE / "data/pump4_v1_universe_20261020.json"))["symbols"]
    os.environ.update({f"{P.PFX}_SYMBOL_ALLOWLIST": ",".join(univ), f"{P.PFX}_ALLOW_LONGS": "1", f"{P.PFX}_ALLOW_SHORTS": "1"})
    K = getattr(importlib.import_module(f"strategies.{P.MODUL}"), P.KLASS); rez = []
    for sym in sorted({k[0] for k in ref}):
        b0, _ = FE.zagruz(sym); b = [x for x in b0 if PP.START - PP.PROGREV_CH * H <= x[0] < konec and x[0] + H <= now]
        strat = K(); stor = P.Store(sym); perv = sym if P.pervyy_argument(K) == "symbol" else stor
        for i in range(len(b) - 1):
            stor.rows = b[: i + 1]; r_ = b[i]
            try: s = strat.maybe_signal(perv, *r_)
            except Exception: s = None
            if s is None or (sym, r_[0]) not in ref or i < 200: continue
            entry = float(b[i + 1][1]); stop = entry + (s.sl - entry) * P.STOP_MULT
            if sym not in ins: rez.append(dict(sym=sym, ts=r_[0], status="NET_INSTRUMENTA")); continue
            o = okruglit(s.side, entry, stop, list(s.tps or []), last_price=entry, risk_usd=a.risk, f1=(s.tp_fracs or [P.F1])[0], **ins[sym])
            rez.append(dict(sym=sym, ts=r_[0], side=s.side, entry=entry, **ins[sym], **o))
    svod = dict(sdelok=len(rez), statusy=dict(collections.Counter(x["status"] for x in rez)),
                flagi=dict(collections.Counter(f for x in rez for f in x.get("flagi", []))), risk_usd=a.risk,
                stop_sdvig_tikov_max=max((x.get("stop_sdvig_tikov", 0) for x in rez), default=0),
                risk_umenshen_dolya_max=max((x.get("risk_umenshen_dolya", 0) for x in rez), default=0),
                notional_med=sorted(x["notional"] for x in rez if "notional" in x)[len(rez) // 2] if rez else None,
                kod_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    f = HERE / time.strftime("results/pump4_tick_adapter_%Y%m%dT%H%MZ.json", time.gmtime())
    f.write_text(json.dumps(dict(svod=svod, sdelki=rez), ensure_ascii=False, indent=1)); print(json.dumps(svod, ensure_ascii=False, indent=1)); print("файл:", f)


if __name__ == "__main__":
    main()
