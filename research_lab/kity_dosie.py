#!/usr/bin/env python3
"""kity_dosie.py — автосборка досье канарейки KITY_BYBIT (каркас KITY_BYBIT_CANARY_DOSIE_KARKAS_2026_10_12), 14.10.2026.
Цель: в день второй квитанции (≈ 23.10) досье собирается ОДНОЙ командой, без новой недели работы. Только чтение файлов тени и
квитанций; ничего не решает за владельца. Статус: DOSIE_READY (все C1/C2 PASS) или BLOCKED с точным списком чего не хватает.
    .venv/bin/python research_lab/kity_dosie.py 2026-10-15 2026-10-22 [--c2 <codex-2026-10-15.json> <codex-2026-10-22.json>]
"""
import argparse, datetime as dt, hashlib, json, sys
from pathlib import Path
LAB = Path(__file__).resolve().parent; D = LAB / "data" / "kity_bybit_ten"
NOTIONAL = 100


def korzina(sig, vh):
    """Validate the actual frozen n//10 basket, never pad/drop research legs."""
    n = sig.get("monet_s_priznakom")
    if type(n) is not int or not 30 <= n <= 50:
        raise ValueError("BASKET_FEATURE_COUNT")
    k = n // 10
    longs, shorts = sig.get("long"), sig.get("short")
    if not isinstance(longs, list) or not isinstance(shorts, list) or len(longs) != k or len(shorts) != k:
        raise ValueError("BASKET_CARDINALITY")
    expected = [(x["s"], side) for side, rows in [(1, longs), (-1, shorts)] for x in rows]
    if len({x for x, _ in expected}) != 2*k:
        raise ValueError("BASKET_DUPLICATE_SYMBOL")
    rows = vh.get("pozicii", [])
    actual = [(x["s"], x["side"]) for x in rows]
    if sig.get("d") != vh.get("d") or len(actual) != 2*k or set(actual) != set(expected):
        raise ValueError("ENTRY_BASKET_MISMATCH")
    return dict(nogi=2*k, long_count=k, short_count=k)


def nedelya(d, c2_put, c2_readback=None, c2_readback_pin=None):
    p = D / d; f = {}
    for k in ("signal", "vhod", "kvitanciya_C1", "snimok_2355"):
        x = p / f"{k}.json"; f[k] = json.loads(x.read_text()) if x.exists() else None
    c2 = json.loads(Path(c2_put).read_text()) if c2_put and Path(c2_put).exists() else None
    c1s = (f["kvitanciya_C1"] or {}).get("status", "НЕТ КВИТАНЦИИ")
    c2s = (c2 or {}).get("status", (c2 or {}).get("verdict", "НЕТ C2"))
    sig, vh = f["signal"] or {}, f["vhod"] or {}
    nogi = [(n["s"], "L") for n in sig.get("long", [])] + [(n["s"], "S") for n in sig.get("short", [])]
    ins = sig.get("instrumenty", {}); poz = {x["s"]: x for x in vh.get("pozicii", [])}
    problemy = []
    try:
        counts = korzina(sig, vh)
    except (ValueError, KeyError, TypeError) as exc:
        counts = dict(nogi=len(nogi), long_count=0, short_count=0)
        problemy.append(str(exc))
    if sig.get("d") != d or vh.get("d") != d:
        problemy.append("SESSION_MISMATCH")
    if c2s == "C2_PASS_MATCH_ONLY":
        raw_pin = hashlib.sha256((p / "signal.json").read_bytes()).hexdigest() if f["signal"] is not None else None
        bound = False
        if c2.get("schema") == "KITY_C2_ACTUAL_SIGNAL_MATCH_V1":
            bound = c2.get("d") == d and c2.get("compared_inputs", {}).get("signal.json") == raw_pin
        elif c2.get("schema") == "KITY_BYBIT_C2_PUBLIC_PARITY_RECEIPT_V1" and c2_readback and c2_readback_pin:
            raw = Path(c2_readback).read_bytes()
            if hashlib.sha256(raw).hexdigest() == c2_readback_pin:
                rb = json.loads(raw)
                record = rb.get("files", {}).get("signal.json", {})
                bound = (c2.get("day") == d and rb.get("schema") == "KITY_C2_EXTERNAL_COMPARISON_INPUTS_READBACK_V1"
                         and record.get("sha256") == raw_pin and record.get("source_unchanged_during_read") is True)
        if (not bound or c2.get("long") != [x["s"] for x in sig.get("long", [])]
                or c2.get("short") != [x["s"] for x in sig.get("short", [])]):
            problemy.append("C2_RAW_SIGNAL_PIN_OR_BASKET_MISMATCH")
    stroki = [f"| {s} | {sd} | {ins.get(s, {}).get('min_qty')} | {ins.get(s, {}).get('step')} | {ins.get(s, {}).get('min_notional')} | "
              f"{poz.get(s, {}).get('cena_vhoda')} | {poz.get(s, {}).get('lot_ok')} |" for s, sd in nogi]
    return dict(d=d, c1=c1s, c2=c2s, monet=sig.get("monet_s_priznakom"), stroki=stroki, problemy=problemy, **counts)


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("d1"); ap.add_argument("d2"); ap.add_argument("--c2", nargs=2, default=[None, None])
    ap.add_argument("--c2-readback", nargs=2, default=[None, None])
    ap.add_argument("--c2-readback-sha256", nargs=2, default=[None, None])
    a = ap.parse_args(argv)
    W = [nedelya(d, a.c2[i], a.c2_readback[i], a.c2_readback_sha256[i]) for i, d in enumerate((a.d1, a.d2))]
    ne_hvataet = [f"{w['d']}: C1 = {w['c1']}" for w in W if w["c1"] != "OPERATIONAL_PASS"] + \
                 [f"{w['d']}: C2 = {w['c2']}" for w in W if str(w["c2"]).upper() not in ("C2_PASS_MATCH_ONLY",)]
    ne_hvataet += [f"{w['d']}: {reason}" for w in W for reason in w["problemy"]]
    if a.d1 == a.d2:
        ne_hvataet.append("TWO_DISTINCT_WEEKS_REQUIRED")
    status = "DOSIE_READY" if not ne_hvataet else "BLOCKED"
    md = [f"# Досье канарейки KITY_BYBIT — {status} (собрано {dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')})", "",
          "DOSIE_READY не является финансовым допуском: это только входные C1/C2. Экономика, расходы, защита, account-owner и GO — отдельные gates. PnL недель — не аргумент досье. Решение и размер — только GO владельца; исполнение — Codex (orders-OFF до GO).", ""]
    for w in W:
        md += [f"## Неделя {w['d']}: C1 {w['c1']} · C2 {w['c2']} · монет с признаком {w['monet']} · ног {w['nogi']}", "",
               "| нога | сторона | minOrderQty | qtyStep | minNotional | цена входа | лот при $100 |", "|---|---|---|---|---|---|---|", *w["stroki"], ""]
    md += ["## Предложение размера (решает владелец)", f"Исследовательский пример, не бюджет: ${NOTIONAL} на ногу × {W[-1]['nogi']} ног ({W[-1]['long_count']}L/{W[-1]['short_count']}S) ≈ ${NOTIONAL * W[-1]['nogi']} брутто; фактические лоты округляются вниз и могут дать иной gross;",
           "плечо не выше 1× на ногу; R5 (две операционные FAIL подряд) — автоматический стоп новых входов на стороне исполнения.", "",
           "## Чего не хватает", *([f"- {x}" for x in ne_hvataet] or ["- ничего: можно готовить orders-OFF пакет Codex → GO владельца"]),
           "", "## Вне исследования (проверить ДО 23.10, иначе это последовательный блокер)",
           "- счёт владельца на Bybit: доступны ли USDT-перпы (шорт-ноги!) для его юрисдикции/сущности (Bybit EU — деривативы ограничены);",
           "- исполнитель KITY у Codex: вход закрытием d, выход закрытием d+7, фактические 2×(n//10) ног (6–10), R5 — собран и прогнан на сохранённых payload-ах."]
    out = LAB / f"DOSIE_KITY_BYBIT_{a.d2}.md"; out.write_text("\n".join(md) + "\n"); print(status); print("\n".join(ne_hvataet)); print(out)
    return 0 if status == "DOSIE_READY" else 2


if __name__ == "__main__":
    sys.exit(main())
