#!/usr/bin/env python3
"""alpaca_treyl_ten.py — хук сторожа: forward-тень 6 рук трейлинга Monthly
(PREREG_ALPACA_H6_TREYL_UTECHKA_I_FORWARD_2026_10_19, часть B + дополнение 1). Без ордеров, без денег.

Когорта сессии s: из журнала H2b (klass FORWARD, s ≥ 2026-10-19) бумаги top18 и setap по убыванию ocenka, до 4.
Журнал когорт `data/alpaca_treyl_ten.jsonl` только дописывается. Ведение рук пересчитывается по последней
запечатанной поставке Codex в `data/alpaca_treyl_ten_svodka.json` (производный файл)."""
from __future__ import annotations
import datetime as dt, hashlib, importlib, json, math, statistics as st, sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(ROOT))
SRC = LAB / "data" / "alpaca_monthly58_daily_v1"
H2B = LAB / "data" / "alpaca_h2b_zhurnal.jsonl"
ZH = LAB / "data" / "alpaca_treyl_ten.jsonl"
SV = LAB / "data" / "alpaca_treyl_ten_svodka.json"
PERVAYA = "2026-10-19"
MEST, GORIZONT, BPS = 4, 22, (20.0, 10.0, 30.0)
VERDIKT_N, PROMEZH = 120, (40, 80)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _jl(p: Path):
    return [json.loads(s) for s in p.read_text().splitlines() if s.strip()] if p.exists() else []


def kogorty_novye():
    est = {z["session"] for z in _jl(ZH)}
    novye = []
    for z in _jl(H2B):
        s = z.get("session", "")
        if s < PERVAYA or s in est or z.get("klass") != "FORWARD" or "oshibka" in z:
            continue
        b = z.get("bumagi", {})
        ok = sorted((k for k, v in b.items() if v.get("top18") and v.get("setap") and v.get("ocenka") is not None),
                    key=lambda k: -b[k]["ocenka"])[:MEST]
        novye.append({"session": s, "entry_session": z.get("entry_session"),
                      "zapisano_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                      "h2b_data_sha256": z.get("data_sha256"), "kod_sha": _sha(Path(__file__)),
                      "kogorta": [{"sym": k, "ocenka": b[k]["ocenka"]} for k in ok]})
        est.add(s)
    if novye:
        with ZH.open("a") as f:
            for z in novye:
                f.write(json.dumps(z, ensure_ascii=False) + "\n")
    return novye


def poslednyaya_postavka():
    for f in sorted(SRC.glob("20??-??-??.json"), reverse=True):
        pech = SRC / f"{f.stem}.delivery.json"
        if pech.exists() and json.loads(pech.read_text()).get("files", {}).get(f.name) == _sha(f):
            return f
    return None


def _atr20(rows, i):
    if i < 20:
        return None
    tr = [max(rows[k].high - rows[k].low, abs(rows[k].high - rows[k - 1].close), abs(rows[k].low - rows[k - 1].close))
          for k in range(i - 19, i + 1)]
    return sum(tr) / 20


def nw_t(xs, lag):
    n = len(xs)
    if n < 3:
        return None
    m = sum(xs) / n; e = [x - m for x in xs]
    g = lambda k: sum(e[i] * e[i - k] for i in range(k, n)) / n
    v = g(0) + 2 * sum((1 - k / (lag + 1)) * g(k) for k in range(1, min(lag, n - 1) + 1))
    return m / math.sqrt(v / n) if v > 0 else None


def vesti(kog, ryady, bp):
    from backtest.alpaca_exact_parity_contract import adverse_fill_price
    from backtest.alpaca_honest_portfolio import quantize_sell_stop
    import research_lab.alpaca_h6_treyl as H6
    out = {"session": kog["session"], "n": len(kog["kogorta"]), "zaversheno": True, "ruki": {}}
    poz = []
    for p in kog["kogorta"]:
        rows = ryady.get(p["sym"]) or []
        idx = {b.session_date.isoformat(): i for i, b in enumerate(rows)}
        i_s, i_v = idx.get(kog["session"]), idx.get(kog.get("entry_session") or "")
        if i_s is None or i_v is None:
            out["zaversheno"] = False; out["zhdyom"] = "vhodnoy_bar"; return out
        a = _atr20(rows, i_s)
        ef = adverse_fill_price(rows[i_v].open, side="buy", cost_bps=bp)
        sig = ef - 2.0 * a if a else -1
        poz.append((p["sym"], rows, i_v, ef, quantize_sell_stop(sig if sig > 0 else ef * 0.95)))
    if not poz:
        out["zaversheno"] = False; out["pusto"] = True; return out
    for nm, ruka in H6.RUKI_B.items():
        doh = []
        for sym, rows, i_v, ef, s0 in poz:
            i_p = i_v + GORIZONT
            r = H6.vesti_poziciyu(rows, i_v, ef, s0, ruka, bp, i_prinud=i_p if i_p < len(rows) else None)
            if r["i_vyhod"] is None:
                out["zaversheno"] = False
                doh.append((rows[-1].close / ef - 1) * 100)
            else:
                doh.append(r["dohod_pct"])
        out["ruki"][nm] = sum(doh) / len(doh)
    return out


def svodka(rez):
    gotovo = [r for r in rez if r.get("zaversheno") and r.get("ruki")]
    n = len(gotovo); sv = {"zaversheno_kogort": n, "vsego_kogort": len(rez), "ruki": {}}
    if not n:
        return sv
    base = [r["ruki"]["A35"] for r in gotovo]
    for nm in gotovo[0]["ruki"]:
        x = [r["ruki"][nm] for r in gotovo]
        d = [a - b for a, b in zip(x, base)]
        q = lambda v: sorted(v)[max(0, int(0.1 * (len(v) - 1)))]
        sv["ruki"][nm] = {"sred_pct": sum(x) / n, "raznica_s_A35_pp": sum(d) / n,
                          "nw_t": nw_t(d, 21) if nm != "A35" else None,
                          "decil_hvost_minus_A35_pp": q(x) - q(base)}
    return sv


def prohod():
    import research_lab.alpaca_h6_treyl as H6
    importlib.reload(H6)                                # сторож долгоживущий: свежий код руки
    novye = kogorty_novye()
    f = poslednyaya_postavka()
    res = {"novyh_kogort": len(novye), "postavka": f.stem if f else None}
    kog = _jl(ZH)
    if not f or not kog:
        res["status"] = "ZHDYOM"; return res
    from backtest.alpaca_exact_parity_contract import DailyBar
    d = json.loads(f.read_text())
    ryady = {s: [DailyBar(session_date=dt.date.fromisoformat(b["session"]), open=b["open"], high=b["high"], low=b["low"],
                          close=b["close"]) for b in sorted(bb, key=lambda x: x["session"])]
             for s, bb in d["history"].items()}
    out = {"prereg": "PREREG_ALPACA_H6_TREYL_UTECHKA_I_FORWARD_2026_10_19", "postavka": f.stem,
           "postavka_sha": _sha(f), "obnovleno_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "bps": {}}
    for bp in BPS:
        rez = [vesti(k, ryady, bp) for k in kog]
        out["bps"][f"{bp:.0f}"] = {"svodka": svodka(rez), "kogorty": rez}
    n = out["bps"]["20"]["svodka"]["zaversheno_kogort"]
    out["etap"] = "VERDIKT" if n >= VERDIKT_N else ("PROMEZHUTOCHNO_OPISANIE" if n >= PROMEZH[0] else "NAKOPLENIE")
    SV.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    res.update(kogort=len(kog), zaversheno=n, etap=out["etap"])
    return res


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
