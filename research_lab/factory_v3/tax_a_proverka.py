#!/usr/bin/env python3
"""tax_a_proverka.py — TAX-A: проверка, что журнал реального исполнения несёт бухгалтерский след с первой сделки (15.10.2026).
Только чтение. Работает на ЭКСПОРТЕ журнала (JSONL, контракт KONTRAKTY_DLYA_CODEX §1), не на рабочих файлах Codex.
    python3 research_lab/factory_v3/tax_a_proverka.py <export.jsonl>      → TAX_A_PASS / TAX_A_FAIL + список пропусков по строкам
Виды строк: fill (исполнение), funding (фандинг перпа), fee (отдельная комиссия), transfer (ввод/вывод/перевод), realized (закрытие).
"""
import json, sys
from pathlib import Path

OBSHCHIE = ("kind", "venue", "account_type", "t_ms", "ccy", "source_ref", "source_sha256")
PO_VIDU = {
    "fill": ("order_id", "trade_id", "instrument", "instrument_type", "side", "qty", "px", "fee", "fee_ccy", "liquidity"),
    "funding": ("instrument", "qty", "rate", "amount"),
    "fee": ("amount", "fee_ccy", "reference_id"),
    "transfer": ("transfer_id", "amount", "direction", "counterparty_account"),
    "realized": ("instrument", "position_id", "realized_pnl", "opening_trade_ids", "closing_trade_ids"),
}


def proverit_stroku(z):
    vid = z.get("kind")
    nuzhno = OBSHCHIE + PO_VIDU.get(vid, ())
    net = [k for k in nuzhno if z.get(k) in (None, "")]
    if vid not in PO_VIDU: net.append(f"kind∉{sorted(PO_VIDU)}")
    if isinstance(z.get("t_ms"), (int, float)) and z["t_ms"] < 1e12: net.append("t_ms не в миллисекундах UTC")
    if z.get("source_sha256") not in (None, "") and len(str(z["source_sha256"])) != 64: net.append("source_sha256 не 64 hex")
    for k in ("api_key", "secret", "password", "token"):
        if k in json.dumps(z).lower(): net.append(f"в строке похоже на секрет: {k}")
    return net


def proverit(put):
    stroki = [json.loads(l) for l in open(put, encoding="utf-8") if l.strip()]
    plohie = {i + 1: n for i, z in enumerate(stroki) for n in [proverit_stroku(z)] if n}
    vidy = sorted({z.get("kind") for z in stroki})
    rez = dict(strok=len(stroki), vidy=vidy, plohih=len(plohie), primery=dict(list(plohie.items())[:10]),
               verdikt="TAX_A_PASS" if stroki and not plohie else "TAX_A_FAIL")
    if stroki and "fill" in vidy and not ({"funding"} & set(vidy)) and any(z.get("instrument_type") == "perp" for z in stroki):
        rez["preduprezhdenie"] = "есть перпы, но нет строк funding — фандинг не учтён"
    return rez


if __name__ == "__main__":
    print(json.dumps(proverit(sys.argv[1]), ensure_ascii=False, indent=1))
