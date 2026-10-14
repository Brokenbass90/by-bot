#!/usr/bin/env python3
"""kity_dosie.py — автосборка досье канарейки KITY_BYBIT (каркас KITY_BYBIT_CANARY_DOSIE_KARKAS_2026_10_12), 14.10.2026.
Цель: в день второй квитанции (≈ 23.10) досье собирается ОДНОЙ командой, без новой недели работы. Только чтение файлов тени и
квитанций; ничего не решает за владельца. Статус: DOSIE_READY (все C1/C2 PASS) или BLOCKED с точным списком чего не хватает.
    .venv/bin/python research_lab/kity_dosie.py 2026-10-15 2026-10-22 [--c2 <codex-2026-10-15.json> <codex-2026-10-22.json>]
"""
import argparse, datetime as dt, json, sys
from pathlib import Path
LAB = Path(__file__).resolve().parent; D = LAB / "data" / "kity_bybit_ten"
NOTIONAL, NOG = 100, 8


def nedelya(d, c2_put):
    p = D / d; f = {}
    for k in ("signal", "vhod", "kvitanciya_C1", "snimok_2355"):
        x = p / f"{k}.json"; f[k] = json.loads(x.read_text()) if x.exists() else None
    c2 = json.loads(Path(c2_put).read_text()) if c2_put and Path(c2_put).exists() else None
    c1s = (f["kvitanciya_C1"] or {}).get("status", "НЕТ КВИТАНЦИИ")
    c2s = (c2 or {}).get("status", (c2 or {}).get("verdict", "НЕТ C2"))
    sig, vh = f["signal"] or {}, f["vhod"] or {}
    nogi = [(n["s"], "L") for n in sig.get("long", [])] + [(n["s"], "S") for n in sig.get("short", [])]
    ins = sig.get("instrumenty", {}); poz = {x["s"]: x for x in vh.get("pozicii", [])}
    stroki = [f"| {s} | {sd} | {ins.get(s, {}).get('min_qty')} | {ins.get(s, {}).get('step')} | {ins.get(s, {}).get('min_notional')} | "
              f"{poz.get(s, {}).get('cena_vhoda')} | {poz.get(s, {}).get('lot_ok')} |" for s, sd in nogi]
    return dict(d=d, c1=c1s, c2=c2s, monet=sig.get("monet_s_priznakom"), nogi=len(nogi), stroki=stroki)


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("d1"); ap.add_argument("d2"); ap.add_argument("--c2", nargs=2, default=[None, None])
    a = ap.parse_args(argv); W = [nedelya(a.d1, a.c2[0]), nedelya(a.d2, a.c2[1])]
    ne_hvataet = [f"{w['d']}: C1 = {w['c1']}" for w in W if w["c1"] != "OPERATIONAL_PASS"] + \
                 [f"{w['d']}: C2 = {w['c2']}" for w in W if str(w["c2"]).upper() not in ("C2_PASS", "PASS")]
    status = "DOSIE_READY" if not ne_hvataet else "BLOCKED"
    md = [f"# Досье канарейки KITY_BYBIT — {status} (собрано {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')})", "",
          "PnL недель — не аргумент досье. Решение и размер — только GO владельца; исполнение — Codex (orders-OFF до GO).", ""]
    for w in W:
        md += [f"## Неделя {w['d']}: C1 {w['c1']} · C2 {w['c2']} · монет с признаком {w['monet']} · ног {w['nogi']}", "",
               "| нога | сторона | minOrderQty | qtyStep | minNotional | цена входа | лот при $100 |", "|---|---|---|---|---|---|---|", *w["stroki"], ""]
    md += ["## Предложение размера (решает владелец)", f"${NOTIONAL} на ногу × {NOG} ног (4L/4S) ≈ ${NOTIONAL * NOG} брутто, нетто-нейтрально;",
           "плечо не выше 1× на ногу; R5 (две операционные FAIL подряд) — автоматический стоп новых входов на стороне исполнения.", "",
           "## Чего не хватает", *([f"- {x}" for x in ne_hvataet] or ["- ничего: можно готовить orders-OFF пакет Codex → GO владельца"]),
           "", "## Вне исследования (проверить ДО 23.10, иначе это последовательный блокер)",
           "- счёт владельца на Bybit: доступны ли USDT-перпы (шорт-ноги!) для его юрисдикции/сущности (Bybit EU — деривативы ограничены);",
           "- исполнитель KITY у Codex: вход закрытием d, выход закрытием d+7, 8 ног, R5 — собран и прогнан на сохранённых payload-ах."]
    out = LAB / f"DOSIE_KITY_BYBIT_{a.d2}.md"; out.write_text("\n".join(md) + "\n"); print(status); print("\n".join(ne_hvataet)); print(out)
    return 0 if status == "DOSIE_READY" else 2


if __name__ == "__main__":
    sys.exit(main())
