#!/usr/bin/env python3
"""Очищенный набор для замороженного P_AKC_OSTATOCHNYY_MOMENT (PREREG 24.09, e29b100) из глубокого архива 25.09.
Бары НЕ меняются (используются файлы глубокого архива как есть, их SHA фиксируются). Меняется только членство:
  1) карантин архива (38) — исключён целиком;
  2) SPCX — нет файла (ошибка поставки bar_invalid) — исключён;
  3) разрыв тождества: любой однодневный скачок закрытия ×4 или ÷4 → членство прерывается с сессии скачка
     и возобновляется через 61 сессию (прогрев беты 60 дней) — бумага до и после считается разными;
  4) делистинг — как в исходном правиле (бар существует и дата не позже delisted_utc).
Правило 3 детерминировано и задано ДО расчёта любой доходности по этому тесту."""
import hashlib, json, math, os, sys
from pathlib import Path
L = Path(__file__).resolve().parents[1]
SRC = L / "data/alpaca_pit_daily_deep_20260925"; OUT = L / "data/alpaca_pit_akc_v2_20261019"
POROG = math.log(4); PROGREV = 61


def main():
    mi = json.loads((SRC / "membership_intervals.json").read_text())
    kar = {q if isinstance(q, str) else q["symbol"] for q in mi["quarantined"]}
    delist = {x["symbol"]: x.get("delisted_utc") for x in mi["intervals"]}
    vse_daty = set(); fayly = {}; razryvy = {}; pervyy = {}
    bars = {}
    for f in sorted((SRC / "bars").glob("*.json")):
        b = f.read_bytes(); fayly[f.name] = hashlib.sha256(b).hexdigest()
        r = json.loads(b)["records"]; bars[f.stem] = [x["t"] for x in r]
        vse_daty |= {x["t"] for x in r}
        pervyy[f.stem] = r[0]["t"] if r else None
        rz = [b2["t"] for a, b2 in zip(r, r[1:]) if a["c"] > 0 and b2["c"] > 0 and abs(math.log(b2["c"] / a["c"])) > POROG]
        if rz:
            razryvy[f.stem] = rz
    daty = sorted(vse_daty); idx = {t: i for i, t in enumerate(daty)}
    intervaly, isklyucheno = [], {}
    for s in sorted(set(delist) | set(bars)):
        if s in kar:
            isklyucheno[s] = "karantin_arhiva"; continue
        if s not in bars:
            isklyucheno[s] = "net_fayla_bar_invalid"; continue
        okna_isk = [[t, daty[min(len(daty) - 1, idx[t] + PROGREV)]] for t in razryvy.get(s, [])]
        intervaly.append(dict(symbol=s, delisted_utc=delist.get(s), pervyy_bar_ms=pervyy[s], okna_isklyucheniya_ms=okna_isk))
    po_godam = {}
    for s, ts in bars.items():
        if s in kar:
            continue
        for y in sorted({__import__("datetime").datetime.utcfromtimestamp(t / 1000).year for t in ts}):
            po_godam[y] = po_godam.get(y, 0) + 1
    man = dict(istochnik="data/alpaca_pit_daily_deep_20260925", istochnik_manifest_state="FETCH_INCOMPLETE (единственная ошибка: SPCX)",
               pravilo_razryva="однодневный |ln(c_t/c_t-1)| > ln 4 → исключение [скачок, скачок+61 сессия]", progrev=PROGREV,
               fayly_sha256=fayly, intervaly=intervaly, isklyucheno=isklyucheno,
               razryvy={k: v for k, v in razryvy.items() if k not in kar},
               bumag_s_barami_po_godam=po_godam,
               ogranicheniya=["пул выбран в 2024–2026 частично по текущей ликвидности: бумаги, исчезнувшие до 2024-08, отсутствуют (выживаемость)",
                              "корректировка сплитов сегодняшняя, не vintage", "переименования не склеены (asof=-): разрывы ловит правило 3"])
    body = json.dumps(man, ensure_ascii=False, sort_keys=True, indent=1)
    (OUT / "membership_v2.json").write_text(body)
    sha = hashlib.sha256(body.encode()).hexdigest()
    (OUT / "SHA256.txt").write_text(f"{sha}  membership_v2.json\n")
    print(json.dumps(dict(sha=sha, intervalov=len(intervaly), isklyucheno=len(isklyucheno), s_razryvami=len(man["razryvy"]),
                          po_godam=po_godam), ensure_ascii=False))


if __name__ == "__main__":
    main()
