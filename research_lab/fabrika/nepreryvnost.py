#!/usr/bin/env python3
"""nepreryvnost.py — контроль непрерывности конвейера (17.10.2026, по требованию PM). Хук сторожа, раз в час.
Только читает и пишет отчёт data/storozh/NEPRERYVNOST.json; НИЧЕГО не перезапускает и не останавливает.
Проверяет: пропуски часовых проходов компонентов, устаревшие данные, ошибки хуков, дубликаты решений, остановку источников.
Мёртвый сам сторож отсюда не виден — это ловят внешние проверки (сводка владельцу, проверки Claude по расписанию)."""
import datetime as dt, json, re, time
from pathlib import Path
LAB = Path(__file__).resolve().parents[1]; D = LAB / "data"; H = 3600
LOG = D / "storozh/storozh.log"; OUT = D / "storozh/NEPRERYVNOST.json"


def _ts(s):
    return dt.datetime.fromisoformat(s).timestamp()


def iz_zhurnala(seychas, okno_ch=6):
    """Последний успешный и последний ошибочный проход каждого компонента за okno_ch часов."""
    out = {}
    if not LOG.exists(): return out
    for s in LOG.read_text().splitlines()[-3000:]:
        m = re.match(r"(\S+) (хук (\S+?)(?::| не прошёл)|brain_shadow(?::| не прошёл)|etf_vpered(?::| не прошёл)|конвейер не прошёл)", s)
        if not m: continue
        try: t = _ts(m.group(1))
        except ValueError: continue
        if seychas - t > okno_ch * H: continue
        imya = m.group(3) or m.group(2).split(":")[0].split(" не")[0]
        z = out.setdefault(imya, dict(posl_ok=None, posl_oshibka=None, prohodov=0))
        if "не прошёл" in s: z["posl_oshibka"] = t
        else: z["posl_ok"] = t; z["prohodov"] += 1
    return out


def vozrast_ch(p, seychas):
    return round((seychas - p.stat().st_mtime) / H, 2) if p.exists() else None


def proverki(seychas=None):
    seychas = seychas or time.time(); rez = {}
    for imya, z in iz_zhurnala(seychas).items():
        st = "OK"
        if z["posl_ok"] is None or seychas - z["posl_ok"] > 2.2 * H: st = "PROPUSK_PROHODA"
        if z["posl_oshibka"] and (z["posl_ok"] is None or z["posl_oshibka"] > z["posl_ok"]): st = "OSHIBKA"
        rez[f"prohod/{imya}"] = dict(status=st, prohodov_6ch=z["prohodov"],
                                     posl_ok_ch_nazad=round((seychas - z["posl_ok"]) / H, 2) if z["posl_ok"] else None)
    # ASM1_FIKS: свежесть баров и дубли решений
    s = D / "asm1_fiks/sostoyanie.json"
    if s.exists():
        st = json.loads(s.read_text()); posl = max(st.values()) / 1000 if st else 0
        vozr = (seychas - posl) / H                      # бар ts = открытие; закрытый к проходу бар на 1–2 ч старше
        res = D / "asm1_fiks/resheniya.jsonl"
        kl = [(r["symbol"], r["bar_ms"]) for r in map(json.loads, res.read_text().splitlines())] if res.exists() else []
        rez["dannye/asm1_fiks"] = dict(status="OK" if vozr <= 3.2 and len(kl) == len(set(kl)) else ("DUBLI" if len(kl) != len(set(kl)) else "STALE"),
                                       monet=len(st), posl_bar_ch_nazad=round(vozr, 2), resheniy=len(kl))
    for imya, p, maks in (("dannye/brain_opportunities", D / "brain_shadow_v1/opportunities.jsonl", 26),
                          ("dannye/btc_h1_live", D / "etf_premiya/btc_h1_live.json", 3.2),
                          ("dannye/etf_ten", D / "etf_premiya/ten_ETF_PREMIYA.jsonl", 80)):
        v = vozrast_ch(p, seychas)
        rez[imya] = dict(status="NET_FAYLA" if v is None else ("OK" if v <= maks else "STALE"), vozrast_ch=v, maks_ch=maks)
    snimki = sorted((D / "liq_v2_1").glob("normalized-*.jsonl"))
    if not snimki:
        rez["istochnik/liq_v2_1"] = dict(status="BLOCKED", prichina="нет снимков Codex (ZAPROS_CODEX_LIQ_EKSPORT_2026_10_17.md)")
    else:
        v = vozrast_ch(snimki[-1], seychas)
        rez["istochnik/liq_v2_1"] = dict(status="OK" if v <= 30 else "STALE", vozrast_ch=v, snimkov=len(snimki))
    return rez


def prohod():
    rez = proverki(); plohie = {k: v["status"] for k, v in rez.items() if v["status"] not in ("OK",)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(kogda=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), proverki=rez,
                                   ne_ok=plohie), ensure_ascii=False, indent=1))
    return dict(ne_ok=plohie, vsego=len(rez))


if __name__ == "__main__":
    print(json.dumps(prohod(), ensure_ascii=False))
