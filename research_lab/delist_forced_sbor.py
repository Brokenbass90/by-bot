#!/usr/bin/env python3
"""delist_forced_sbor.py — DELIST_FORCED, шаг 1: проверка осуществимости (27.10.2026, Claude). Только публичные API Bybit, без ключей.
Механизм: объявленный делистинг перпа → держатели обязаны закрыть позиции к дате; маркет-мейкеры уходят из стакана.
Скрипт: (1) собирает объявления Bybit о делистингах; (2) вытаскивает символы USDT-перпов; (3) для каждого пытается скачать H1 от −7 дней
до даты делистинга (если биржа ещё отдаёт историю). Пишет data/delist_forced/ (сырьё) и печатает частоту и покрытие.
    Mac:  .venv/bin/python3 research_lab/delist_forced_sbor.py"""
import json, re, time, urllib.request
from pathlib import Path
D = Path(__file__).resolve().parent / "data" / "delist_forced"; D.mkdir(parents=True, exist_ok=True)
H = 3600000

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "research-readonly/1.0"}), timeout=25) as r:
        return json.loads(r.read())

def obyavleniya():
    out = []
    for page in range(1, 60):
        x = get(f"https://api.bybit.com/v5/announcements/index?locale=en-US&type=delistings&page={page}&limit=20")
        lst = (x.get("result") or {}).get("list") or []
        if not lst: break
        out += lst; time.sleep(0.2)
    return out

def svechi(sym, t0, t1):
    out, s = [], t0
    while s < t1:
        x = get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval=60&start={s}&end={min(t1, s + 999 * H)}&limit=1000")
        lst = sorted([[int(r[0])] + [float(v) for v in r[1:6]] for r in ((x.get("result") or {}).get("list") or [])])
        if not lst: break
        out += [r for r in lst if not out or r[0] > out[-1][0]]; s = lst[-1][0] + H; time.sleep(0.12)
    return out

def main():
    ob = obyavleniya(); (D / "obyavleniya.json").write_text(json.dumps(ob, ensure_ascii=False))
    sob = []
    for a in ob:
        t_ob = int(a.get("dateTimestamp") or a.get("publishTime") or 0)
        txt = f"{a.get('title','')} {a.get('description','')}"
        if not re.search(r"perpetual|contract|derivative", txt, re.I): continue
        for sym in sorted(set(re.findall(r"\b([A-Z0-9]{2,20}USDT)\b", txt))):
            sob.append(dict(sym=sym, t_obyavleniya=t_ob, t_konec=int(a.get("endDateTimestamp") or 0), zagolovok=a.get("title"), url=a.get("url")))
    for s in sob:
        t1 = s["t_konec"] if s["t_konec"] > s["t_obyavleniya"] else s["t_obyavleniya"] + 14 * 24 * H
        try: b = svechi(s["sym"], s["t_obyavleniya"] - 7 * 24 * H, t1)
        except Exception as e: b = []; s["oshibka"] = str(e)[:100]
        s["barov"] = len(b)
        if b: (D / f"{s['sym']}_{s['t_obyavleniya']}.json").write_text(json.dumps(b))
    (D / "sobytiya.json").write_text(json.dumps(sob, ensure_ascii=False, indent=1))
    po_g = {}
    for s in sob: po_g.setdefault(time.strftime("%Y", time.gmtime(s["t_obyavleniya"] / 1000)), []).append(s)
    print("объявлений о делистинге:", len(ob), "| событий перпов:", len(sob), "| с ценами H1:", sum(1 for s in sob if s["barov"] > 24))
    for g, v in sorted(po_g.items()): print(g, "событий", len(v), "с ценами", sum(1 for s in v if s["barov"] > 24))
    print("данные:", D)

if __name__ == "__main__": main()
