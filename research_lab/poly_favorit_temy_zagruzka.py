"""Загрузчик для PREREG_POLY_FAVORIT_VSE_TEMY_2026_10_26 (публичные API Polymarket, без ключей). Запуск из корня (≈ 20–40 мин, можно прерывать):
    .venv/bin/python3 research_lab/poly_favorit_temy_zagruzka.py → research_lab/data/poly_favorit_temy/rynki.jsonl"""
import datetime as dt, json, random, re, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE / "fabrika"))
import poly_sbor as S
OUT = HERE / "data" / "poly_favorit_temy"; OUT.mkdir(parents=True, exist_ok=True); F = OUT / "rynki.jsonl"
KRIPTO = re.compile(r"bitcoin|ethereum|solana|xrp|\bbtc\b|\beth\b|crypto|token|price of|doge|memecoin|airdrop|fdv", re.I)
TEMY = [("sports", re.compile(r"\bvs\.?\b|nba|nfl|nhl|mlb|ufc|premier league|champions league|la liga|serie a|bundesliga|f1|grand prix|world cup|"
                              r"super bowl|tennis|open\b|match|game \d|win the .*(cup|title|series|championship)|o/u|spread|score", re.I)),
        ("geopolitics", re.compile(r"ceasefire|war|invade|invasion|strike|missile|military|nato|russia|ukraine|israel|iran|gaza|china|taiwan|"
                                   r"north korea|sanction|troops|peace deal|hostage", re.I)),
        ("economy", re.compile(r"\bfed\b|interest rate|rate cut|bps|inflation|cpi|gdp|recession|unemployment|jobs report|tariff|s&p|nasdaq|stock", re.I)),
        ("politics", re.compile(r"election|president|senate|house|governor|mayor|primary|nominee|nomination|vote|parliament|prime minister|"
                                r"democrat|republican|trump|biden|harris|poll|cabinet|impeach", re.I))]


def tema(m):
    s = " ".join([m.get("question") or ""] + [(e.get("title") or "") + " " + " ".join(e.get("tags") or []) for e in m.get("events") or []])
    for t, rx in TEMY:
        if rx.search(s): return t
    return "other"


def main():
    gotovo = {json.loads(l)["id"] for l in F.open()} if F.exists() else set()
    kand = []
    for f in sorted((S.OUT / "katalog").glob("*.jsonl")):
        for l in open(f):
            m = json.loads(l)
            if not m.get("closed"): continue
            try:
                kon = dt.datetime.fromisoformat((m.get("endDate") or "").replace("Z", "+00:00")); obem = float(m.get("volume") or 0)
            except Exception: continue
            if not (dt.datetime(2024, 1, 1, tzinfo=dt.timezone.utc) <= kon <= dt.datetime(2026, 10, 20, tzinfo=dt.timezone.utc)) or obem < 1e5: continue
            if [str(o).lower() for o in (S.js(m.get("outcomes")) or [])] != ["yes", "no"]: continue
            if KRIPTO.search((m.get("question") or "") + " " + " ".join((e.get("title") or "") for e in m.get("events") or [])): continue
            kand.append(m)
    print("кандидатов:", len(kand), flush=True)
    random.Random(20261026).shuffle(kand); kand = kand[:3000]
    for n, m in enumerate(kand, 1):
        if m["id"] in gotovo: continue
        kon = int(dt.datetime.fromisoformat(m["endDate"].replace("Z", "+00:00")).timestamp())
        tok = (S.js(m.get("clobTokenIds")) or [None])[0]
        h = S.get(S.CLOB, "/prices-history", market=tok, startTs=kon - 48 * 3600, endTs=kon + 3600, fidelity=60) or {}
        g = S.get(S.GAMMA, f"/markets/{m['id']}") or {}
        pr = S.js(g.get("outcomePrices")) or []
        z = dict(id=m["id"], vopros=m.get("question"), sobytie=((m.get("events") or [{}])[0]).get("id"), tema=tema(m), konec=kon,
                 obem=float(m.get("volume") or 0), ryad=[[int(x["t"]), float(x["p"])] for x in h.get("history", [])],
                 itog=[float(x) for x in pr] if pr else None)
        with F.open("a") as fh: fh.write(json.dumps(z, ensure_ascii=False) + "\n")
        if n % 100 == 0: print(f"  {n}/{len(kand)}", flush=True)
        time.sleep(S.PAUZA)
    print("готово:", F)


if __name__ == "__main__":
    main()
