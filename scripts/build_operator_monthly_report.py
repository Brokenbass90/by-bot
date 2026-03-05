#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        return [dict(r) for r in rd]


def _read_list(path: Path) -> List[str]:
    if not path.exists():
        return []
    out: List[str] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if not s or s in {"-", "none", "None"}:
            continue
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if not parts:
            continue
        out.extend(parts)
    return out


def _calc_tax_block(tax_rows: List[Dict[str, str]]) -> Dict[str, Any]:
    if not tax_rows:
        return {
            "months": 0,
            "trades_total": 0,
            "net_total": 0.0,
            "fees_total": 0.0,
            "est_tax_total": 0.0,
            "latest_month": "",
            "latest_net": 0.0,
            "latest_est_tax": 0.0,
        }
    months = sorted(r.get("month", "") for r in tax_rows if r.get("month"))
    latest_m = months[-1] if months else ""
    trades_total = int(sum(_safe_float(r.get("trades"), 0.0) for r in tax_rows))
    net_total = sum(_safe_float(r.get("net_pnl"), 0.0) for r in tax_rows)
    fees_total = sum(_safe_float(r.get("fees_total"), 0.0) for r in tax_rows)
    est_tax_total = sum(_safe_float(r.get("est_tax"), 0.0) for r in tax_rows)
    latest_rows = [r for r in tax_rows if r.get("month", "") == latest_m]
    latest_net = sum(_safe_float(r.get("net_pnl"), 0.0) for r in latest_rows)
    latest_est_tax = sum(_safe_float(r.get("est_tax"), 0.0) for r in latest_rows)
    return {
        "months": len(months),
        "trades_total": trades_total,
        "net_total": net_total,
        "fees_total": fees_total,
        "est_tax_total": est_tax_total,
        "latest_month": latest_m,
        "latest_net": latest_net,
        "latest_est_tax": latest_est_tax,
    }


def _calc_data_status(rows: List[Dict[str, str]]) -> Dict[str, Any]:
    total = len(rows)
    ready = 0
    for r in rows:
        exists = str(r.get("exists", "")).strip()
        if exists == "1":
            ready += 1
    return {"total": total, "ready": ready}


def main() -> int:
    ap = argparse.ArgumentParser(description="Build consolidated monthly operator report.")
    ap.add_argument("--tax-csv", default="docs/tax_monthly_latest.csv")
    ap.add_argument("--forex-active", default="docs/forex_combo_active_latest.txt")
    ap.add_argument("--equities-active", default="docs/equities_combo_active_latest.txt")
    ap.add_argument("--forex-data-status", default="docs/forex_data_status.csv")
    ap.add_argument("--equities-data-status", default="docs/equities_data_status.csv")
    ap.add_argument("--out-txt", default="docs/operator_monthly_latest.txt")
    ap.add_argument("--out-json", default="docs/operator_monthly_latest.json")
    args = ap.parse_args()

    tax_rows = _read_csv_rows(Path(args.tax_csv).resolve())
    fx_active = _read_list(Path(args.forex_active).resolve())
    eq_active = _read_list(Path(args.equities_active).resolve())
    fx_data_rows = _read_csv_rows(Path(args.forex_data_status).resolve())
    eq_data_rows = _read_csv_rows(Path(args.equities_data_status).resolve())

    tax_block = _calc_tax_block(tax_rows)
    fx_data = _calc_data_status(fx_data_rows)
    eq_data = _calc_data_status(eq_data_rows)

    generated = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    payload: Dict[str, Any] = {
        "generated_utc": generated,
        "tax": tax_block,
        "forex": {
            "active_count": len(fx_active),
            "active": fx_active,
            "data_ready": fx_data,
        },
        "equities": {
            "active_count": len(eq_active),
            "active": eq_active,
            "data_ready": eq_data,
        },
        "notes": [
            "Estimated tax is informational; payment is manual.",
            "Use this report as a monthly operator checklist, not legal advice.",
        ],
    }

    out_json = Path(args.out_json).resolve()
    out_txt = Path(args.out_txt).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_txt.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    txt_lines = [
        "operator monthly report",
        f"generated_utc={generated}",
        "",
        "[tax]",
        f"months={tax_block['months']}",
        f"trades_total={tax_block['trades_total']}",
        f"net_total={tax_block['net_total']:+.6f}",
        f"fees_total={tax_block['fees_total']:.6f}",
        f"est_tax_total={tax_block['est_tax_total']:.6f}",
        f"latest_month={tax_block['latest_month'] or 'n/a'}",
        f"latest_net={tax_block['latest_net']:+.6f}",
        f"latest_est_tax={tax_block['latest_est_tax']:.6f}",
        "",
        "[forex]",
        f"active_count={len(fx_active)}",
        f"active={','.join(fx_active) if fx_active else '-'}",
        f"data_ready={fx_data['ready']}/{fx_data['total']}",
        "",
        "[equities]",
        f"active_count={len(eq_active)}",
        f"active={','.join(eq_active) if eq_active else '-'}",
        f"data_ready={eq_data['ready']}/{eq_data['total']}",
        "",
        "notes:",
        "- Estimated tax is informational; payment is manual.",
        "- Use this report as a monthly operator checklist, not legal advice.",
    ]
    out_txt.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")

    print(f"saved_txt={out_txt}")
    print(f"saved_json={out_json}")
    print(
        f"summary tax_months={tax_block['months']} "
        f"fx_active={len(fx_active)} eq_active={len(eq_active)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
