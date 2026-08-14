#!/usr/bin/env python3
"""Build a truthful strategy inventory without assigning performance verdicts.

The liveness census answers only whether a strategy can emit a signal through
the research adapter.  The system manifest answers only whether a file is
referenced.  Neither proves edge, shadow readiness, or live authority.  This
script keeps those facts separate in one reviewable artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _strategy_files() -> dict[str, str]:
    return {
        path.stem: str(path.relative_to(ROOT))
        for path in sorted((ROOT / "strategies").glob("*.py"))
        if path.stem not in {"__init__", "live_kline_utils", "signals"}
    }


def build_inventory(census_path: Path, manifest_path: Path) -> dict[str, Any]:
    census = _load_json(census_path)
    manifest = _load_json(manifest_path)
    paths = _strategy_files()
    reference_counts = manifest.get("reference_counts", {})
    names = sorted(set(paths) | set(census) | set(reference_counts))

    rows: list[dict[str, Any]] = []
    for name in names:
        probe = census.get(name, {}) if isinstance(census, dict) else {}
        rows.append(
            {
                "name": name,
                "path": paths.get(name),
                "research_liveness_status": probe.get("status", "NOT_PROBED"),
                "probe_signal_count": probe.get("signals"),
                "probe_exception_count": probe.get("exc"),
                "probe_symbol": probe.get("symbol"),
                "probe_adapter": probe.get("conv"),
                "probe_detail": probe.get("detail", ""),
                "reference_count": int(reference_counts.get(name, 0) or 0),
                "performance_status": "NOT_ESTABLISHED_BY_THIS_INVENTORY",
                "live_authority": "NOT_ESTABLISHED_BY_THIS_INVENTORY",
            }
        )

    counts: dict[str, int] = {}
    for row in rows:
        status = row["research_liveness_status"]
        counts[status] = counts.get(status, 0) + 1

    return {
        "schema_id": "strategy_inventory_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authority": "read_only_inventory_no_performance_or_live_promotion_authority",
        "definitions": {
            "research_liveness_status": "Adapter smoke result only; not profitability evidence.",
            "reference_count": "Static source/config references only; not proof of runtime wiring.",
            "performance_status": "Requires a separate passported causal experiment.",
            "live_authority": "Requires direct runtime and broker evidence plus owner-approved gates.",
        },
        "inputs": [
            {"path": _display_path(census_path), "sha256": _sha256(census_path)},
            {"path": _display_path(manifest_path), "sha256": _sha256(manifest_path)},
        ],
        "summary": {
            "inventory_rows": len(rows),
            "strategy_files": len(paths),
            "research_liveness_counts": dict(sorted(counts.items())),
            "referenced_files": sum(1 for row in rows if row["reference_count"] > 0),
            "unreferenced_files": sum(1 for row in rows if row["path"] and row["reference_count"] == 0),
            "wired_entry_handler_count": len(manifest.get("monolith", {}).get("wired_entry_handlers", [])),
            "enable_flag_count": len(manifest.get("monolith", {}).get("enable_flags", [])),
        },
        "wired_entry_handlers": manifest.get("monolith", {}).get("wired_entry_handlers", []),
        "enable_flags": manifest.get("monolith", {}).get("enable_flags", []),
        "strategies": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", type=Path, default=Path("research_lab/results/strategy_census.json"))
    parser.add_argument("--manifest", type=Path, default=Path("runtime/research/system_manifest_inventory.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/evidence/STRATEGY_INVENTORY_20260814.json"))
    args = parser.parse_args()
    census = args.census if args.census.is_absolute() else ROOT / args.census
    manifest = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_inventory(census, manifest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
