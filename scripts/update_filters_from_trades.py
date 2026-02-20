#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def load_trades(csv_path: Path):
    rows = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        for r in rd:
            sym = str(r.get("symbol", "")).upper().strip()
            st = str(r.get("strategy", "")).strip()
            if not sym or not st:
                continue
            try:
                pnl = float(r.get("pnl", "0") or 0.0)
            except Exception:
                pnl = 0.0
            rows.append((st, sym, pnl))
    return rows


def ensure_strategy_node(data: dict, strategy: str) -> dict:
    per = data.setdefault("per_strategy", {})
    node = per.setdefault(strategy, {})
    node.setdefault("allowlist", [])
    node.setdefault("denylist", [])
    return node


def main() -> int:
    ap = argparse.ArgumentParser(description="Update symbol filters denylist from trades CSV stats.")
    ap.add_argument("--filters", required=True, help="Path to symbol filters json.")
    ap.add_argument("--trades", required=True, help="Path to trades.csv.")
    ap.add_argument("--strategy", default="inplay_breakout")
    ap.add_argument("--filters-strategy-key", default="breakout", help="per_strategy key to update in filters json")
    ap.add_argument("--min-trades", type=int, default=2)
    ap.add_argument("--max-net", type=float, default=0.0, help="Deny if net_pnl <= max-net")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    filters_path = Path(args.filters)
    trades_path = Path(args.trades)
    if not filters_path.exists():
        raise SystemExit(f"filters not found: {filters_path}")
    if not trades_path.exists():
        raise SystemExit(f"trades not found: {trades_path}")

    data = json.loads(filters_path.read_text(encoding="utf-8"))
    rows = load_trades(trades_path)

    by_sym = defaultdict(lambda: {"trades": 0, "net": 0.0})
    for st, sym, pnl in rows:
        if st != args.strategy:
            continue
        by_sym[sym]["trades"] += 1
        by_sym[sym]["net"] += pnl

    deny_add = []
    for sym, s in sorted(by_sym.items()):
        if int(s["trades"]) >= int(args.min_trades) and float(s["net"]) <= float(args.max_net):
            deny_add.append(sym)

    node = ensure_strategy_node(data, str(args.filters_strategy_key).strip().lower())
    deny = set(str(x).upper() for x in (node.get("denylist") or []))
    deny.update(deny_add)
    node["denylist"] = sorted(deny)

    print(f"strategy={args.strategy} candidates={len(by_sym)} deny_add={len(deny_add)}")
    for sym in deny_add:
        s = by_sym[sym]
        print(f"  {sym}: trades={s['trades']} net={s['net']:+.4f}")

    if args.dry_run:
        print("dry-run: filters not written")
        return 0

    filters_path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")
    print(f"updated: {filters_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
