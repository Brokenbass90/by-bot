#!/usr/bin/env python3
"""liq_renorm_dev_v2.py — LIQ_RENORMALIZED_DEV_V2: перенормализация СЫРЫХ полей старой ленты V1 по семантике V2 (14.10.2026).
Источник: runtime/liquidations/bybit_liquidations.jsonl (scripts/collect_bybit_liquidations.py @4abf8f9, только чтение).
Берутся только сырые S (поле order_side — дословно Buy/Sell из S), T (ts_ms; подстановки времени приёма нет ни в одной записи),
symbol, v (qty), p (price), время приёма. Старое поле side, старые вердикты и PnL НЕ используются.
V2: S=Buy → ликвидирован ЛОНГ, S=Sell → ШОРТ. Дыры: глобальная тишина ленты > 30 мин (все 12 символов) = UNKNOWN-интервал.
Пишет data/liq_renorm_dev_v2/{events_v2.jsonl, dyry.json, MANIFEST.json}. Исходы не читаются.
"""
import hashlib, json
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; SRC = LAB.parent / "runtime" / "liquidations" / "bybit_liquidations.jsonl"
OUT = LAB / "data" / "liq_renorm_dev_v2"; TISHINA_MS = 30 * 60_000


def main():
    raw = SRC.read_bytes(); OUT.mkdir(parents=True, exist_ok=True)
    ev, prov = [], dict(zapisey=0, s_buy=0, s_sell=0, t_ravno_priemu=0, nevalid=0)
    for l in raw.decode().splitlines():
        if not l.strip(): continue
        r = json.loads(l); prov["zapisey"] += 1
        S, T, q, p = r.get("order_side"), r.get("ts_ms"), r.get("qty"), r.get("price")
        if S not in ("Buy", "Sell") or not isinstance(T, int) or not q or not p or q <= 0 or p <= 0: prov["nevalid"] += 1; continue
        if T == r.get("recv_ts_ms"): prov["t_ravno_priemu"] += 1
        prov["s_buy" if S == "Buy" else "s_sell"] += 1
        side = "long" if S == "Buy" else "short"
        kan = json.dumps(dict(S=S, T=T, p=p, s=r["symbol"], v=q), sort_keys=True, separators=(",", ":"))
        ev.append(dict(schema="BYBIT_ALL_LIQUIDATION_SOURCE_V2", versiya="V1_RENORM_DEV_V2", ts_ms=T, symbol=r["symbol"], side=side,
                       raw_position_side=S, qty=q, price=p, usd=round(q * p, 8), t_available_ms=r["recv_ts_ms"],
                       raw_item_canonical_sha256=hashlib.sha256(kan.encode()).hexdigest()))
    ev.sort(key=lambda e: e["t_available_ms"])
    dyry = [(a["t_available_ms"], b["t_available_ms"]) for a, b in zip(ev, ev[1:]) if b["t_available_ms"] - a["t_available_ms"] > TISHINA_MS]
    with open(OUT / "events_v2.jsonl", "w") as f:
        for e in ev: f.write(json.dumps(e, separators=(",", ":")) + "\n")
    (OUT / "dyry.json").write_text(json.dumps(dyry))
    man = dict(dataset="LIQ_RENORMALIZED_DEV_V2", istochnik=str(SRC.relative_to(LAB.parent)), istochnik_sha256=hashlib.sha256(raw).hexdigest(),
               kollektor="scripts/collect_bybit_liquidations.py @4abf8f9 (min_usd=0, T из биржи, S дословно)", provenance=prov,
               simvolov=len({e["symbol"] for e in ev}), t_pervyy=ev[0]["ts_ms"], t_posledniy=ev[-1]["ts_ms"],
               dyr_unknown=len(dyry), dyry_chasov=round(sum(b - a for a, b in dyry) / 3.6e6, 1),
               semantika="V2: S=Buy → long ликвидирован; S=Sell → short", events_sha256=hashlib.sha256((OUT / "events_v2.jsonl").read_bytes()).hexdigest())
    (OUT / "MANIFEST.json").write_text(json.dumps(man, ensure_ascii=False, indent=1)); print(json.dumps(man, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
