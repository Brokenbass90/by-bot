#!/usr/bin/env python3
"""alpaca_h2b_zhurnal.py — хук сторожа: PIT-журнал ежедневного рейтинга Monthly для H2b вперёд
(PREREG_ALPACA_H2B_STAB_FORWARD_2026_10_19). Только данные, без доходностей, без ордеров.

Источник: ежедневная поставка Codex `data/alpaca_monthly58_daily_v1/<сессия>.json` (вселенная Monthly 58, печать
`<сессия>.delivery.json` с SHA). По каждой новой запечатанной сессии считается замороженной логикой
backtest/alpaca_honest_portfolio.py: здоровье и место, прошёл ли сетап, оценка кандидата, STAB21 (доля из 21 последних
сессий, когда бумага была в top-18 по здоровью И в сетапе) — для ВСЕХ допустимых бумаг, включая отвергнутых.
Журнал `data/alpaca_h2b_zhurnal.jsonl` только дописывается; уже записанная сессия не пересчитывается."""
from __future__ import annotations
import datetime as dt, hashlib, json, math, sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[1]; ROOT = LAB.parent
sys.path.insert(0, str(ROOT))
SRC = LAB / "data" / "alpaca_monthly58_daily_v1"
ZH = LAB / "data" / "alpaca_h2b_zhurnal.jsonl"
HP_PUT = ROOT / "backtest" / "alpaca_honest_portfolio.py"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def uzhe():
    if not ZH.exists():
        return set()
    return {json.loads(s)["session"] for s in ZH.read_text().splitlines() if s.strip()}


def snimok(d):
    import backtest.alpaca_honest_portfolio as HP
    from backtest.alpaca_exact_parity_contract import DailyBar
    ses = d["session_date"]
    ryady = {s: [DailyBar(session_date=dt.date.fromisoformat(b["session"]), open=b["open"], high=b["high"], low=b["low"],
                          close=b["close"]) for b in sorted(bb, key=lambda x: x["session"]) if b["session"] <= ses]
             for s, bb in d["history"].items()}
    sessii = sorted({b.session_date for r in ryady.values() for b in r})

    def den(sd):
        h = {s: r[:sum(1 for b in r if b.session_date <= sd)] for s, r in ryady.items()}
        h = {s: r for s, r in h.items() if r and r[-1].session_date == sd and s not in ("SPY", "QQQ")}
        zd = {s: HP._universe_health(r) for s, r in h.items()}
        ok = sorted(((s, v) for s, v in zd.items() if math.isfinite(v)), key=lambda x: -x[1])
        mesto = {s: i + 1 for i, (s, _) in enumerate(ok)}
        top = {s for s, _ in ok[:18]}
        kand = {s: HP._v38_candidate(s, h[s]) for s in h}
        return h, zd, mesto, top, kand

    poslednie = [x for x in sessii if x <= dt.date.fromisoformat(ses)][-21:]
    cnt = {}
    for sd in poslednie:
        _, _, _, top, kand = den(sd)
        for s in top:
            if kand.get(s) is not None:
                cnt[s] = cnt.get(s, 0) + 1
    h, zd, mesto, top, kand = den(dt.date.fromisoformat(ses))
    rows = {s: {"health": (zd[s] if math.isfinite(zd[s]) else None), "mesto": mesto.get(s), "top18": s in top,
                "setap": kand[s] is not None, "ocenka": (kand[s].score if kand[s] is not None else None),
                "stab21": cnt.get(s, 0) / 21} for s in sorted(h)}
    return rows, len(poslednie)


def prohod(maks=5):
    est = uzhe(); novye = []
    for f in sorted(SRC.glob("20??-??-??.json")):
        ses = f.stem
        if ses in est or len(novye) >= maks:
            continue
        pech = SRC / f"{ses}.delivery.json"
        zap = {"session": ses, "zapisano_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
        if not pech.exists():
            continue                                   # поставка ещё не запечатана — ждём
        p = json.loads(pech.read_text())
        if p.get("files", {}).get(f.name) != _sha(f):
            zap["oshibka"] = "SHA файла не совпал с печатью поставки"; novye.append(zap); continue
        d = json.loads(f.read_text())
        rows, n = snimok(d)
        avail = d.get("source_available_ms")
        zap.update(istochnik_sha=_sha(f), data_sha256=d.get("data_sha256"), source_available_ms=avail,
                   entry_session=d.get("entry_session"),
                   mesyachnyy_signal=bool(d.get("entry_session") and d["entry_session"][:7] != ses[:7]),
                   pozdno=bool(avail and dt.datetime.now(dt.timezone.utc).timestamp() * 1000 - avail > 36 * 3600 * 1000),
                   sessiy_v_stab=n, kod={"alpaca_honest_portfolio": _sha(HP_PUT), "h2b_zhurnal": _sha(Path(__file__))},
                   bumagi=rows)
        novye.append(zap)
    if novye:
        with ZH.open("a") as fz:
            for z in novye:
                fz.write(json.dumps(z, ensure_ascii=False) + "\n")
    return {"novyh": len(novye), "sessii": [z["session"] for z in novye], "oshibok": sum(1 for z in novye if "oshibka" in z)}


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
