#!/usr/bin/env python3
"""Run the bounded public-only cash-carry research station.

The default command is a no-network/no-write preflight.  The long-running
station requires four explicit acknowledgements and still has no key, account,
private API, order, transfer, withdrawal, live, or demo execution path.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.bybit_cashcarry_shadow_v1 import CashCarryShadowError  # noqa: E402
from bot.public_cashcarry_station_v1 import (  # noqa: E402
    BYBIT_ADAPTER_ID,
    BYBIT_EXCHANGE_ID,
    BYBIT_SOURCE_ID,
    FunctionPublicAdapter,
    PublicCashCarryStationV1,
    load_station_config,
    read_station_status,
)
from scripts.run_bybit_cashcarry_shadow_v2 import (  # noqa: E402
    PUBLIC_HOSTS,
    PUBLIC_PATHS,
    fetch_public_snapshot,
)


DEFAULT_SPEC = ROOT / "configs/preregistered/public_cashcarry_station_v1_20260716.json"
DEFAULT_RUN_ROOT = ROOT / "runtime/research/public_cashcarry_station_v1_20260716"


def _preflight(spec_path: Path) -> dict[str, Any]:
    payload, config, shadow, collector = load_station_config(spec_path, root=ROOT)
    return {
        "schema_id": "public_cashcarry_station_preflight_v1",
        "ok": True,
        "status": "RESEARCH_ONLY_DEFAULT_DISABLED",
        "spec": str(spec_path),
        "spec_status": payload.get("status"),
        "station_config_sha256": config.config_sha256,
        "v2_spec_sha256": config.v2_spec_sha256,
        "default_enabled": False,
        "network_calls": False,
        "filesystem_writes": False,
        "daemon_started": False,
        "api_keys_or_environment_reads": False,
        "private_api_calls": False,
        "broker_calls": False,
        "orders_transfers_withdrawals": False,
        "executable": False,
        "performance_claims": False,
        "adapter": {
            "adapter_id": config.adapter_id,
            "exchange_id": config.exchange_id,
            "source_id": config.source_id,
            "public_only": True,
            "method": "GET_ONLY",
            "hosts": sorted(PUBLIC_HOSTS),
            "paths": list(PUBLIC_PATHS),
        },
        "symbols": list(config.symbols),
        "bounds": {
            "max_runtime_seconds": config.max_runtime_seconds,
            "max_observations": config.max_observations,
            "max_journal_bytes_per_symbol": config.max_journal_bytes_per_symbol,
            "max_total_bytes": config.max_total_bytes,
            "max_append_reserve_bytes": config.max_append_reserve_bytes,
            "min_free_bytes": config.min_free_bytes,
            "max_consecutive_all_symbol_failure_cycles": (
                config.max_consecutive_all_symbol_failure_cycles
            ),
            "retention_action": "STOP_NO_DELETE_NO_ROTATE",
        },
        "frozen_shadow_config_sha256": shadow.config_sha256,
        "frozen_collector_basis_stress_bps": collector.basis_stress_bps,
        "frozen_collector_minimum_edge_bps": collector.minimum_expected_edge_bps,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("preflight", help="No-network/no-write safety receipt (default).")

    status = sub.add_parser("status", help="No-network status and deterministic journal replay.")
    status.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)

    run = sub.add_parser("run", help="Run the bounded public research station.")
    run.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    run.add_argument("--allow-public-network", action="store_true")
    run.add_argument("--enable-durable-collector", action="store_true")
    run.add_argument("--enable-research-shadow", action="store_true")
    run.add_argument("--acknowledge-research-only", action="store_true")
    run.add_argument("--resume-existing", action="store_true")
    run.add_argument(
        "--max-cycles-this-process",
        type=int,
        help="Optional bounded operator/test pause; does not alter the frozen total run limits.",
    )
    return parser


def _require_run_opt_ins(args: argparse.Namespace) -> None:
    required = {
        "--allow-public-network": args.allow_public_network,
        "--enable-durable-collector": args.enable_durable_collector,
        "--enable-research-shadow": args.enable_research_shadow,
        "--acknowledge-research-only": args.acknowledge_research_only,
    }
    missing = [name for name, enabled in required.items() if not enabled]
    if missing:
        raise CashCarryShadowError(
            "run requires explicit opt-ins: " + ", ".join(missing)
        )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "preflight"
    try:
        if command == "preflight":
            print(json.dumps(_preflight(args.spec), indent=2, sort_keys=True))
            return 0
        payload, config, shadow, collector = load_station_config(args.spec, root=ROOT)
        del payload
        if command == "status":
            print(
                json.dumps(
                    read_station_status(
                        root=args.run_root,
                        config=config,
                        shadow_config=shadow,
                        collector_config=collector,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        _require_run_opt_ins(args)
        active_collector = dataclasses.replace(
            collector,
            enabled=True,
            shadow_enabled=True,
        )
        adapter = FunctionPublicAdapter(
            adapter_id=BYBIT_ADAPTER_ID,
            exchange_id=BYBIT_EXCHANGE_ID,
            source_id=BYBIT_SOURCE_ID,
            base_url="https://api.bybit.com",
            fetcher=fetch_public_snapshot,
        )
        intent = {
            "schema_id": "public_cashcarry_station_run_intent_v1",
            "research_only": True,
            "executable": False,
            "broker_calls": False,
            "private_api_calls": False,
            "api_keys_or_environment_reads": False,
            "orders_transfers_withdrawals": False,
            "adapter_id": adapter.adapter_id,
            "symbols": list(config.symbols),
            "run_root": str(args.run_root),
            "bounded_by_frozen_spec": True,
        }
        print(json.dumps(intent, sort_keys=True), flush=True)
        station = PublicCashCarryStationV1(
            config=config,
            shadow_config=shadow,
            collector_config=active_collector,
            adapter=adapter,
            root=args.run_root,
        )
        result = station.run(
            resume_existing=args.resume_existing,
            max_cycles_this_process=args.max_cycles_this_process,
        )
        print(json.dumps(dataclasses.asdict(result), indent=2, sort_keys=True), flush=True)
        return 0
    except (CashCarryShadowError, KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(
            json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True),
            file=sys.stderr,
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
