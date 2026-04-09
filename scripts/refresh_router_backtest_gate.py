#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GLOB = "portfolio_*validated_baseline_regression*/trades.csv"
DEFAULT_OUT = ROOT / "runtime" / "control_plane" / "router_trades_baseline.csv"
DEFAULT_META = ROOT / "runtime" / "control_plane" / "router_trades_baseline_meta.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Refresh curated router backtest gate CSV from latest validated baseline trades.")
    ap.add_argument("--glob", default=DEFAULT_GLOB, help="Glob under backtest_runs/ used to discover source trades.csv.")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output trades.csv path.")
    ap.add_argument("--meta-out", default=str(DEFAULT_META), help="Metadata json path.")
    args = ap.parse_args()

    source_matches = sorted((ROOT / "backtest_runs").glob(args.glob))
    if not source_matches:
        print("ERROR: no validated baseline trades.csv found", flush=True)
        return 1

    source = source_matches[-1].resolve()
    out_path = Path(args.out).expanduser()
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    meta_path = Path(args.meta_out).expanduser()
    if not meta_path.is_absolute():
        meta_path = ROOT / meta_path

    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, out_path)

    meta = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_trades_csv": str(source),
        "output_trades_csv": str(out_path),
        "source_glob": args.glob,
        "bytes": out_path.stat().st_size if out_path.exists() else 0,
    }
    _write_json(meta_path, meta)

    print(f"source={source}")
    print(f"output={out_path}")
    print(f"meta={meta_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
