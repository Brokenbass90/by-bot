#!/usr/bin/env python3
"""demo_otchety.py — пять образцов Reporting V1. KITY — НАСТОЯЩАЯ квитанция 16.10 (Codex evidence); Alpaca-сделки — ДЕМО на реальных барах NET."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import sobytiya_v1 as S, karta_sdelki as KS, karta_korzina as KK, karta_portfel as KP, tekst_tg as T


def main(bars_net, kity_terminal, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    r = json.loads(Path(bars_net).read_text())["records"]; bars = [[x["t"], x["o"], x["h"], x["l"], x["c"]] for x in r][-70:]
    e, x = bars[-45], bars[-12]
    zakr = dict(sleeve="ALPACA", strategy="NET_DYNAMIC", venue="Alpaca", symbol="NET", side="long", qty=0.325, ccy="USD",
                entry=dict(t_ms=e[0], px=e[4]), stop_px=round(e[4] * 0.892, 2), exit=dict(t_ms=x[0], px=x[4], reason="храповик стопа"),
                fees=0.0, funding=0.0, slippage_bps=1.2, status="CLOSED", demo=True, pnl_net=round((x[4] - e[4]) * 0.325, 4), evidence_id="demo")
    KS.risovat(zakr, bars, out / "1_alpaca_zakryta.png")
    otkr = dict(zakr, exit=None, status="OPEN", pnl_net=None, entry=dict(t_ms=bars[-20][0], px=bars[-20][4]), stop_px=round(bars[-20][4] * 0.892, 2))
    KS.risovat(otkr, bars, out / "2_alpaca_otkryta.png")
    d = json.loads(Path(kity_terminal).read_text()); ev = S.iz_kity_terminal(d)
    fsf = [z for z in ev if z["type"] == "FAILED_SAFE_FLAT"][0]; acc = [z for z in ev if z["type"] == "ACCOUNTING_FINAL"][0]
    KK.risovat(fsf, out / "3_kity_failed_safe_flat.png")
    KK.risovat(dict(acc, legs=[l for l in acc["legs"] if l["status"].startswith("FILLED")]), out / "4_kity_korzina_uchet.png")
    KP.risovat(dict(data="16.10.2026", ccy="USD", metka="ОБРАЗЕЦ", rukava=[
        dict(sleeve="ALPACA", venue="Alpaca", mode="LIVE", otkryto=1, risk_otkr=round((311.222 - 277.69) * 0.325167779, 2), realiz_den=0.0,
             nerealiz=None, zdorove="защита ✓", zametka="NET 0.325 @ 311.22, стоп 277.69; текущей цены в research-данных нет → н/д"),
        dict(sleeve="KITY", venue="Bybit", mode="LIVE", otkryto=0, risk_otkr=0.0, realiz_den=float(acc["net_pnl"]), nerealiz=0.0,
             zdorove="плоский ✓", zametka="micro-тест исполнения 6/10, авто-закрытие"),
        dict(sleeve="ELDER/HEDGE", venue="Bybit", mode="SHADOW", otkryto=0, risk_otkr=None, realiz_den=None, nerealiz=None, zdorove="тень"),
        dict(sleeve="BRAIN", venue="—", mode="SHADOW", otkryto=0, risk_otkr=None, realiz_den=None, nerealiz=None, zdorove="копит записи")]),
        out / "5_portfel_den.png")
    (out / "podpisi.txt").write_text("\n\n".join(T.podpis(z) for z in ev), encoding="utf-8")
    return [str(p) for p in sorted(out.glob("*.png"))]


if __name__ == "__main__":
    print(main(*sys.argv[1:4]))
