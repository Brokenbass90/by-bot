#!/usr/bin/env python3
"""dannye_etf_potoki.py — ПРИЧИННЫЙ ряд дневных притоков спотовых BTC/ETH ETF (PREREG_ETF_POTOK_2026_10_16).

Проблема: публичные таблицы потоков (Farside) правятся задним числом; «исправленная история» = заглядывание вперёд.
Решение: архивные снимки страниц (Wayback Machine, CDX API). Для каждой даты потока берётся значение Total из САМОГО РАННЕГО
снимка, где строка уже была, и момент этого снимка = available_ms (консервативно: опубликовано не позже снимка).
Позднейшие правки пишутся отдельно (для измерения величины правок), в сигнал не идут.
Запуск на Маке (сеть): .venv/bin/python research_lab/fabrika/edinstvennyy_zapusk.py etf -- .venv/bin/python research_lab/fabrika/dannye_etf_potoki.py
Пишет data/etf_potoki/{btc,eth}.json = [{date, first_total_musd, available_ms, snapshot, last_total_musd, revised}] + MANIFEST.json.
Самопроверка разбора: сумма фондов ≈ Total; без неё gotovo=false (ряд не идёт в Фабрику).
"""
import datetime as dt, hashlib, json, re, sys, time, urllib.request
from html.parser import HTMLParser
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; OUT = LAB / "data" / "etf_potoki"; KESH = OUT / "snimki"
STRANICY = {"btc": ["farside.co.uk/?p=997", "farside.co.uk/bitcoin-etf-flow-all-data/", "farside.co.uk/btc/"],
            "eth": ["farside.co.uk/?p=1518", "farside.co.uk/ethereum-etf-flow-all-data/", "farside.co.uk/eth/"]}
MES = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def get(url, raw=False):
    for k in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "trading-os-research/1.0"}), timeout=60) as f:
                b = f.read(); return b if raw else json.loads(b.decode())
        except Exception:
            if k == 4: raise
            time.sleep(3 + 5 * k)


class Tablica(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows, self.row, self.cell, self.in_cell = [], None, "", False
    def handle_starttag(self, tag, a):
        if tag == "tr": self.row = []
        if tag in ("td", "th"): self.in_cell, self.cell = True, ""
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.row is not None: self.row.append(self.cell.strip()); self.in_cell = False
        if tag == "tr" and self.row: self.rows.append(self.row); self.row = None
    def handle_data(self, d):
        if self.in_cell: self.cell += d


def chislo(s):
    s = s.replace(",", "").replace("\xa0", "").strip()
    if s in ("", "-", "–"): return 0.0
    neg = s.startswith("(") and s.endswith(")"); s = s.strip("()")
    try: v = float(s)
    except ValueError: return None
    return -v if neg else v


def data_stroki(s):
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})$", s.strip())
    if not m or m.group(2).lower() not in MES: return None
    return dt.date(int(m.group(3)), MES[m.group(2).lower()], int(m.group(1))).isoformat()


def razobrat(html):
    p = Tablica(); p.feed(html.decode("utf-8", "ignore")); out, bad = {}, 0
    for r in p.rows:
        if len(r) < 3: continue
        d = data_stroki(r[0])
        if not d: continue
        vals = [chislo(x) for x in r[1:]]
        if vals[-1] is None or r[-1].strip() in ("", "-", "–", "—"): continue   # Total ещё не опубликован («-» ≠ 0 для итога)
        fondy = [v for v in vals[:-1] if v is not None]
        if fondy and abs(sum(fondy) - vals[-1]) > max(1.0, 0.02 * abs(vals[-1])): bad += 1
        out[d] = vals[-1]
    return out, bad


def snimki(url):
    q = f"http://web.archive.org/cdx/search/cdx?url={url}&output=json&fl=timestamp,statuscode&filter=statuscode:200&collapse=timestamp:10"
    rows = get(q); return [r[0] for r in rows[1:]] if rows else []


def main():
    OUT.mkdir(parents=True, exist_ok=True); KESH.mkdir(exist_ok=True); man = {}
    for aktiv, urls in STRANICY.items():
        first, last, plohih, vsego = {}, {}, 0, 0
        ts_all = sorted({(ts, u) for u in urls for ts in snimki(u)})
        for ts, u in ts_all:
            fp = KESH / f"{aktiv}_{ts}.html"
            if not fp.exists():
                try: fp.write_bytes(get(f"http://web.archive.org/web/{ts}id_/https://{u}", raw=True)); time.sleep(1.0)
                except Exception: continue
            tab, bad = razobrat(fp.read_bytes()); vsego += len(tab); plohih += bad
            t_ms = int(dt.datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
            for d, v in tab.items():                               # v2: значение дня принимается только из снимка ≥ дата + 30 ч
                t_den = int(dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
                if t_ms < t_den + 30 * 3_600_000: continue          # (день США закрыт, данные фондов дошли) — без частичных итогов
                if d not in first: first[d] = (v, t_ms, ts)
                last[d] = v
        ryad = [dict(date=d, first_total_musd=first[d][0], available_ms=first[d][1], snapshot=first[d][2], last_total_musd=last[d],
                     revised=abs(last[d] - first[d][0]) > 0.05) for d in sorted(first)]
        (OUT / f"{aktiv}.json").write_text(json.dumps(ryad))
        lag = sorted((r["available_ms"] - int(dt.datetime.fromisoformat(r["date"]).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)) / 86_400_000 for r in ryad)
        man[aktiv] = dict(snimkov=len(ts_all), dney=len(ryad), s=ryad[0]["date"] if ryad else None, po=ryad[-1]["date"] if ryad else None,
                          dolya_pravok=round(sum(r["revised"] for r in ryad) / max(1, len(ryad)), 3),
                          zaderzhka_dostupnosti_dney_mediana=round(lag[len(lag) // 2], 2) if lag else None,
                          zaderzhka_p90=round(lag[int(len(lag) * 0.9)], 2) if lag else None,
                          dolya_strok_s_raskhozhdeniem_summy=round(plohih / max(1, vsego), 4))
        print(aktiv, man[aktiv], flush=True)
    ok = man.get("btc", {}).get("dney", 0) >= 300 and man["btc"]["dolya_strok_s_raskhozhdeniem_summy"] < 0.05 and \
         (man["btc"]["zaderzhka_dostupnosti_dney_mediana"] or 99) <= 4
    h = hashlib.sha256(b"".join((OUT / f"{a}.json").read_bytes() for a in STRANICY if (OUT / f"{a}.json").exists())).hexdigest()
    (OUT / "MANIFEST.json").write_text(json.dumps(dict(man, sha256=h, gotovo=ok, sobrano=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                                                       pravilo="first_total из самого раннего архивного снимка не раньше дата+30ч; available_ms = момент снимка; «-» в Total = не опубликовано", pravilo_versiya=2), ensure_ascii=False, indent=1))
    print("gotovo", ok)


if __name__ == "__main__":
    main()
