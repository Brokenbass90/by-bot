#!/usr/bin/env python3
"""Read-only state-transition funnel for frozen Sloped Break/Retest V2."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.engine import KlineStore
from research_lab.strategy_adapter import load_candles
from strategies.sloped_break_retest_v2 import SlopedBreakRetestV2Strategy


SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "LINKUSDT", "DOTUSDT", "AVAXUSDT", "SUIUSDT")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(raw_tmp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def diagnose_symbol(symbol: str, input_path: Path) -> dict:
    candles = load_candles(symbol, limit=10**9, input_path=input_path)
    store = KlineStore(symbol, candles, base_interval_min=5)
    strategy = SlopedBreakRetestV2Strategy()
    counts: Counter[str] = Counter()
    for index, bar in enumerate(candles):
        store.set_index(index)
        before_line = strategy._last_line_ts
        before_pending = dict(strategy._pending) if strategy._pending else None
        signal = strategy.maybe_signal(store, bar.ts, bar.o, bar.h, bar.l, bar.c, bar.v)
        after_pending = dict(strategy._pending) if strategy._pending else None
        if strategy._last_line_ts != before_line:
            counts["completed_4h_evaluations"] += 1
        if before_pending is None and after_pending is not None:
            counts["break_events"] += 1
            counts[f"break_{after_pending['side']}"] += 1
        if (
            before_pending is not None
            and not before_pending.get("touched")
            and after_pending is not None
            and after_pending.get("touched")
        ):
            counts["first_retests_held"] += 1
            counts[f"retest_{after_pending['side']}"] += 1
        if before_pending is not None and after_pending is None and signal is None:
            counts[str(strategy.last_no_signal_reason)] += 1
        if signal is not None:
            counts["signals"] += 1
            counts[f"signal_{signal.side}"] += 1
    return {
        "symbol": symbol,
        "input": str(input_path.relative_to(ROOT)),
        "input_sha256": _sha256(input_path),
        "bars": len(candles),
        "counts": dict(sorted(counts.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        default="research_lab/data/bybit_major8_m5_preholdout_20240301_20250930",
    )
    parser.add_argument(
        "--out",
        default="reports/evidence/SLOPED_BREAK_RETEST_V2_FUNNEL_20260814.json",
    )
    parser.add_argument("--passport", required=True)
    args = parser.parse_args()
    passport = json.loads((ROOT / args.passport).read_text(encoding="utf-8"))
    if passport.get("sealed_holdout_rows_decoded") != 0:
        raise RuntimeError("passport does not prove sealed holdout remained unread")
    rows = [
        diagnose_symbol(symbol, ROOT / args.data_root / symbol / f"{symbol}.json")
        for symbol in SYMBOLS
    ]
    total: Counter[str] = Counter()
    for row in rows:
        total.update(row["counts"])
    payload = {
        "schema_id": "sloped_break_retest_v2_funnel_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authority": "research_only_no_live_or_promotion_authority",
        "experiment_id": "sloped_break_retest_v2_funnel_preholdout_v1_20260814",
        "passport_sha256": passport.get("passport_sha256"),
        "sealed_holdout_rows_read": 0,
        "symbols": rows,
        "total": dict(sorted(total.items())),
    }
    _atomic_json(ROOT / args.out, payload)
    print(json.dumps(payload["total"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
