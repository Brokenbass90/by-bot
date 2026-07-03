#!/usr/bin/env python3
"""Analyze research trades by tag, symbol and calendar period.

This is deliberately post-hoc and read-only. It helps separate a real plateau from
one-symbol / one-period pockets before we consider another gate.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


def _float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if x == x else default
    except Exception:
        return default


def _ts_to_dt(v: Any) -> datetime:
    ts = _float(v)
    if ts > 10_000_000_000:  # ms
        ts /= 1000.0
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _pf(rs: Sequence[float]) -> float:
    gains = sum(x for x in rs if x > 0)
    losses = -sum(x for x in rs if x < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _summ(rs: Sequence[float]) -> Dict[str, Any]:
    n = len(rs)
    return {
        "trades": n,
        "net_r": round(sum(rs), 4),
        "pf": _pf(rs),
        "win_rate": round(sum(1 for x in rs if x > 0) / n, 4) if n else 0.0,
        "avg_r": round(sum(rs) / n, 4) if n else 0.0,
    }


def _tag(row: Dict[str, Any]) -> str:
    if row.get("tag"):
        return str(row["tag"])
    if row.get("variant"):
        side = str(row.get("side") or "").strip()
        return str(row["variant"]) + (f"_{side}" if side else "")
    parts = [
        str(row.get("setup") or row.get("strategy") or "unknown"),
        str(row.get("side") or "side"),
        f"rr{row.get('tp_rr', '')}",
        f"sl{row.get('sl_atr', '')}",
        f"h{row.get('max_hold', '')}",
    ]
    return "_".join(p for p in parts if p)


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trades_csv")
    ap.add_argument("--outdir", default="")
    ap.add_argument("--top", type=int, default=30)
    args = ap.parse_args()

    src = Path(args.trades_csv)
    rows = list(csv.DictReader(src.open(encoding="utf-8")))
    outdir = Path(args.outdir or src.parent / "analysis")
    outdir.mkdir(parents=True, exist_ok=True)

    enriched: List[Dict[str, Any]] = []
    for r in rows:
        ts = r.get("ts") or r.get("entry_ts")
        if ts is None:
            continue
        dt = _ts_to_dt(ts)
        nr = dict(r)
        nr["tag"] = _tag(r)
        nr["symbol"] = str(r.get("symbol") or "?").upper()
        nr["year"] = dt.strftime("%Y")
        nr["month"] = dt.strftime("%Y-%m")
        nr["r"] = _float(r.get("r"))
        enriched.append(nr)

    by_tag: Dict[str, List[float]] = defaultdict(list)
    by_tag_symbol: Dict[tuple, List[float]] = defaultdict(list)
    by_tag_year: Dict[tuple, List[float]] = defaultdict(list)
    by_tag_month: Dict[tuple, List[float]] = defaultdict(list)
    for r in enriched:
        key = str(r["tag"])
        val = float(r["r"])
        by_tag[key].append(val)
        by_tag_symbol[(key, str(r["symbol"]))].append(val)
        by_tag_year[(key, str(r["year"]))].append(val)
        by_tag_month[(key, str(r["month"]))].append(val)

    tag_rows: List[Dict[str, Any]] = []
    for tag, rs in by_tag.items():
        months = [m for (t, m), xs in by_tag_month.items() if t == tag and xs]
        month_net = [sum(by_tag_month[(tag, m)]) for m in sorted(months)]
        years = [y for (t, y), xs in by_tag_year.items() if t == tag and xs]
        year_net = [sum(by_tag_year[(tag, y)]) for y in sorted(years)]
        symbols = [s for (t, s), xs in by_tag_symbol.items() if t == tag and xs]
        positive_symbols = sum(1 for s in symbols if sum(by_tag_symbol[(tag, s)]) > 0)
        positive_years = sum(1 for x in year_net if x > 0)
        positive_months = sum(1 for x in month_net if x > 0)
        worst_month = min(month_net) if month_net else 0.0
        top_symbol_trades = max((len(by_tag_symbol[(tag, s)]) for s in symbols), default=0)
        base = _summ(rs)
        base.update({
            "tag": tag,
            "symbols": len(symbols),
            "positive_symbols": positive_symbols,
            "years": len(years),
            "positive_years": positive_years,
            "months": len(month_net),
            "positive_months": positive_months,
            "worst_month_r": round(worst_month, 4),
            "top_symbol_frac": round(top_symbol_trades / len(rs), 4) if rs else 0.0,
        })
        tag_rows.append(base)
    tag_rows.sort(key=lambda r: (float(r["net_r"]), float(r["pf"])), reverse=True)

    symbol_rows = []
    for (tag, sym), rs in by_tag_symbol.items():
        base = _summ(rs)
        base.update({"tag": tag, "symbol": sym})
        symbol_rows.append(base)
    symbol_rows.sort(key=lambda r: (r["tag"], -float(r["net_r"])))

    year_rows = []
    for (tag, year), rs in by_tag_year.items():
        base = _summ(rs)
        base.update({"tag": tag, "year": year})
        year_rows.append(base)
    year_rows.sort(key=lambda r: (r["tag"], r["year"]))

    month_rows = []
    for (tag, month), rs in by_tag_month.items():
        base = _summ(rs)
        base.update({"tag": tag, "month": month})
        month_rows.append(base)
    month_rows.sort(key=lambda r: (r["tag"], r["month"]))

    _write_csv(outdir / "by_tag.csv", tag_rows)
    _write_csv(outdir / "by_symbol.csv", symbol_rows)
    _write_csv(outdir / "by_year.csv", year_rows)
    _write_csv(outdir / "by_month.csv", month_rows)

    lines = [
        "# Research trade analysis",
        "",
        f"- source: `{src}`",
        f"- trades: {len(enriched)}",
        "",
        "| tag | trades | netR | PF | WR | symbols+ | years+ | months+ | worst_month | concentration |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in tag_rows[: max(1, int(args.top))]:
        pf = float(r["pf"])
        pf_s = "inf" if pf == float("inf") else f"{pf:.3f}"
        lines.append(
            f"| {r['tag']} | {r['trades']} | {r['net_r']:.3f} | {pf_s} | {r['win_rate']:.3f} | "
            f"{r['positive_symbols']}/{r['symbols']} | {r['positive_years']}/{r['years']} | "
            f"{r['positive_months']}/{r['months']} | {r['worst_month_r']:.3f} | {r['top_symbol_frac']:.2%} |"
        )
    lines += [
        "",
        "## Outputs",
        "",
        f"- `{outdir / 'by_tag.csv'}`",
        f"- `{outdir / 'by_symbol.csv'}`",
        f"- `{outdir / 'by_year.csv'}`",
        f"- `{outdir / 'by_month.csv'}`",
    ]
    (outdir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(outdir / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
