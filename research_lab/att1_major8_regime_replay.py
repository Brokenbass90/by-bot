#!/usr/bin/env python3
"""Frozen major-8 ATT1 causal regime-gate ON/OFF replay.

This is a research-only scorer.  It will not decode the declared pre-holdout
bytes until a separately supplied production-caller parity PASS receipt has
been validated.  A missing or non-PASS receipt produces a deterministic
preflight blocker manifest rather than performance numbers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.att1_runtime_contract import build_att1_runtime_contract
from bot.live_native_decision_contract import (
    ContractViolation,
    apply_exchange_stop_filter,
)
from bot.live_native_fill_adapter import adapt_next_open_replay_fill
from bot.live_native_manifest import ManifestViolation, load_and_verify_manifest
from bot.live_native_regime_gate import ClosedH1RegimeEvidence
from bot.live_native_signal_adapters import (
    adapt_att1_live_signal_to_plan,
    closed_h1_evidence_from_row,
)
from strategies.att1_live import ATT1LiveEngine

from research_lab.run_att1_sbr1_actual_adapter_parity import (
    MarketData,
    _ReplayFetcher,
    _build_regime_map,
    _frozen_env,
    _load_market_data,
    _policy,
    _row_bytes,
    _simulate_outcome,
    _source_bundle,
)


FIXED_MAJOR8 = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "DOTUSDT",
    "SUIUSDT",
)
PRESEALED_MANIFEST = Path("configs/research/att1_sbr1_live_native_parity_v1.json")
DEFAULT_OUTPUT = Path(
    "research_lab/results/att1_major8_regime_replay_presealed_v1_20260826/receipt.json"
)
GATE_ON_REGIME = "flat_down"
CALLER_PASS_SCHEMA_ID = "live_caller_parity_release_gate_v1"


class ReplayBlocker(RuntimeError):
    """Input/evidence is not eligible for a performance replay."""


def _jsonable(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ReplayBlocker("noncanonical_replay_payload")
        return "0" if value == 0 else format(value.normalize(), "f")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key in normalized:
                raise ReplayBlocker("noncanonical_replay_payload")
            normalized[key] = _jsonable(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_jsonable(item) for item in value]
    raise ReplayBlocker("noncanonical_replay_payload")


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise ReplayBlocker("noncanonical_replay_payload") from exc


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ReplayBlocker(f"invalid_decimal:{field}")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ReplayBlocker(f"invalid_decimal:{field}") from exc
    if not result.is_finite():
        raise ReplayBlocker(f"invalid_decimal:{field}")
    return result


def _int(value: object, field: str) -> int:
    if isinstance(value, bool):
        raise ReplayBlocker(f"invalid_integer:{field}")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReplayBlocker(f"invalid_integer:{field}") from exc
    if str(value).strip() not in {str(result), str(result) + ".0"}:
        raise ReplayBlocker(f"invalid_integer:{field}")
    return result


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def _metric_rows(events: Sequence[Mapping[str, object]]) -> dict[str, object]:
    if not events:
        raise ReplayBlocker("no_eligible_outcome_events")
    ordered = sorted(events, key=lambda row: (_int(row["bar_ts"], "bar_ts"), str(row["symbol"])))
    values = [_decimal(row["net_r"], "net_r") for row in ordered]
    gains = sum((value for value in values if value > 0), Decimal("0"))
    losses = -sum((value for value in values if value < 0), Decimal("0"))
    cumulative = Decimal("0")
    peak = Decimal("0")
    max_dd = Decimal("0")
    by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    by_month: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for row, value in zip(ordered, values):
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
        by_symbol[str(row["symbol"])] += value
        month = str(row.get("month") or datetime.fromtimestamp(
            _int(row["bar_ts"], "bar_ts") / 1000, timezone.utc
        ).strftime("%Y-%m"))
        by_month[month] += value
    positive_symbols = [value for value in by_symbol.values() if value > 0]
    positive_total = sum(positive_symbols, Decimal("0"))
    concentration = (
        max(positive_symbols) / positive_total if positive_total > 0 else Decimal("1")
    )
    positive_months = sum(value > 0 for value in by_month.values())
    return {
        "n": len(values),
        "sum_r": _decimal_text(sum(values, Decimal("0"))),
        "profit_factor": _decimal_text(gains / losses) if losses > 0 else None,
        "max_drawdown_r": _decimal_text(max_dd),
        "positive_months": positive_months,
        "months": len(by_month),
        "positive_month_fraction": _decimal_text(
            Decimal(positive_months) / Decimal(len(by_month))
        ),
        "positive_symbol_concentration": _decimal_text(concentration),
        "by_symbol_r": {
            symbol: _decimal_text(value) for symbol, value in sorted(by_symbol.items())
        },
        "admitted_regimes": {
            regime: sum(str(row.get("regime_value")) == regime for row in ordered)
            for regime in sorted({str(row.get("regime_value")) for row in ordered})
        },
        "event_ledger_sha256": _sha(
            [dict(sorted((str(k), str(v)) for k, v in row.items())) for row in ordered]
        ),
    }


def score_gate_variants(events: Sequence[Mapping[str, object]]) -> dict[str, dict[str, object]]:
    """Score the same event ledger with only regime admission changed."""

    seen: set[tuple[str, int]] = set()
    normalized: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, Mapping):
            raise ReplayBlocker("event_not_object")
        symbol = str(event.get("symbol") or "").strip().upper()
        if symbol not in FIXED_MAJOR8:
            raise ReplayBlocker("unknown_major8_symbol")
        bar_ts = _int(event.get("bar_ts"), "bar_ts")
        key = (symbol, bar_ts)
        if key in seen:
            raise ReplayBlocker("duplicate_event_key")
        seen.add(key)
        regime = str(event.get("regime_value") or "").strip()
        if regime not in {"below_band", "flat_down", "flat_up", "above_band"}:
            raise ReplayBlocker("unknown_regime_value")
        net_r = _decimal(event.get("net_r"), "net_r")
        normalized.append({**event, "symbol": symbol, "bar_ts": bar_ts, "regime_value": regime, "net_r": net_r})

    off = _metric_rows(normalized)
    on_rows = [row for row in normalized if row["regime_value"] == GATE_ON_REGIME]
    on = _metric_rows(on_rows)
    return {"gate_off": off, "gate_on": on}


def build_blocker_manifest(
    *, root: Path, reasons: Sequence[str], context: Mapping[str, object] | None = None
) -> dict[str, object]:
    """Create a stable no-metrics receipt for an ineligible replay."""

    blockers = sorted({str(reason).strip() for reason in reasons if str(reason).strip()})
    if not blockers:
        raise ReplayBlocker("empty_blocker_manifest")
    payload: dict[str, object] = {
        "schema_id": "att1_major8_regime_replay_preflight_v1",
        "decision": "PREFLIGHT_BLOCKED",
        "authority": "research_only_no_live_no_broker_no_promotion",
        "money_authority": False,
        "live_or_broker_calls": False,
        "orders_created_or_changed": 0,
        "sealed_holdout_rows_decoded": 0,
        "universe": list(FIXED_MAJOR8),
        "gate_contract": {
            "gate_off": "admit every validated ATT1 outcome",
            "gate_on": "admit only regime_value=flat_down",
            "changed_input": "causal BTC EMA200 regime admission only",
        },
        "blockers": blockers,
        "what_metrics_mean": "No N/PF/DD are emitted until caller parity and outcome eligibility pass.",
    }
    if context:
        payload["binding"] = {
            str(key): context[key] for key in sorted(context, key=str)
        }
    payload["manifest_sha256"] = _sha(payload)
    return payload


def _load_caller_pass(
    path: Path, *, root: Path, expected_manifest_sha256: str
) -> dict[str, object]:
    if not path.is_file():
        raise ReplayBlocker("caller_receipt_missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayBlocker("caller_receipt_unreadable") from exc
    if not isinstance(payload, dict):
        raise ReplayBlocker("caller_receipt_not_object")
    if payload.get("schema_id") != CALLER_PASS_SCHEMA_ID:
        raise ReplayBlocker("caller_receipt_schema_mismatch")
    if payload.get("decision") != "LIVE_CALLER_PARITY_PASS":
        raise ReplayBlocker("live_caller_parity_blocked")
    if payload.get("money_authority") is not False or payload.get("live_or_broker_calls") is not False:
        raise ReplayBlocker("caller_receipt_claims_authority")
    if int(payload.get("sealed_holdout_rows_decoded", -1)) != 0:
        raise ReplayBlocker("caller_receipt_reads_sealed_rows")
    if payload.get("parity_manifest_sha256") != expected_manifest_sha256:
        raise ReplayBlocker("caller_receipt_manifest_mismatch")
    raw = dict(payload)
    expected_self = str(raw.pop("receipt_sha256", ""))
    if len(expected_self) != 64 or _sha(raw) != expected_self:
        raise ReplayBlocker("caller_receipt_hash_mismatch")
    p1 = payload.get("P1")
    if (
        not isinstance(p1, Mapping)
        or p1.get("decision") != "PASS"
        or p1.get("money_authority") is not False
        or p1.get("orders_allowed") is not False
        or len(str(p1.get("state_sha256") or "")) != 64
        or len(str(p1.get("receipt_sha256") or "")) != 64
    ):
        raise ReplayBlocker("caller_receipt_p1_invalid")
    p1_rel = str(p1.get("path") or "").strip().replace("\\", "/")
    p1_expected_sha = str(p1.get("sha256") or "").strip()
    if (
        not p1_rel
        or p1_rel.startswith("/")
        or p1_rel.startswith("../")
        or "/../" in p1_rel
        or len(p1_expected_sha) != 64
    ):
        raise ReplayBlocker("caller_receipt_p1_binding_invalid")
    p1_artifact = (root / p1_rel).resolve()
    if root.resolve() not in p1_artifact.parents:
        raise ReplayBlocker("caller_receipt_p1_binding_invalid")
    try:
        p1_actual_sha = hashlib.sha256(p1_artifact.read_bytes()).hexdigest()
        p1_payload = json.loads(p1_artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayBlocker("caller_receipt_p1_artifact_unreadable") from exc
    if p1_actual_sha != p1_expected_sha or p1_payload.get("decision") != "PASS":
        raise ReplayBlocker("caller_receipt_p1_artifact_mismatch")
    gates = payload.get("gates")
    expected_decisions = {
        "P2": "P2_ENGINEERING_PASS_P5_STILL_REQUIRED",
        "P4": "PASS",
        "P5": "PASS",
    }
    if not isinstance(gates, Mapping) or set(gates) != set(expected_decisions):
        raise ReplayBlocker("caller_receipt_gate_bindings_missing")
    for gate, decision in expected_decisions.items():
        binding = gates.get(gate)
        if not isinstance(binding, Mapping) or binding.get("decision") != decision:
            raise ReplayBlocker(f"caller_receipt_{gate.lower()}_invalid")
        rel = str(binding.get("path") or "").strip().replace("\\", "/")
        expected_sha = str(binding.get("sha256") or "").strip()
        if (
            not rel
            or rel.startswith("/")
            or rel.startswith("../")
            or "/../" in rel
            or len(expected_sha) != 64
        ):
            raise ReplayBlocker(f"caller_receipt_{gate.lower()}_binding_invalid")
        artifact = (root / rel).resolve()
        if root.resolve() not in artifact.parents:
            raise ReplayBlocker(f"caller_receipt_{gate.lower()}_binding_invalid")
        try:
            actual_sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
            actual_payload = json.loads(artifact.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReplayBlocker(
                f"caller_receipt_{gate.lower()}_artifact_unreadable"
            ) from exc
        if actual_sha != expected_sha or actual_payload.get("decision") != decision:
            raise ReplayBlocker(f"caller_receipt_{gate.lower()}_artifact_mismatch")
    return payload


def _events_for_att1(
    root: Path,
    manifest: Any,
    market: Mapping[str, MarketData],
    regime_by_close: Mapping[int, ClosedH1RegimeEvidence],
) -> dict[str, list[dict[str, object]]]:
    source_paths = {
        "strategies/alt_trendline_touch_v1.py",
        "strategies/att1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
    }
    source_files, source_hashes = _source_bundle(root, manifest, source_paths)
    runtime_contract = build_att1_runtime_contract(risk_mult=0.0)
    output = {"base": [], "stress": []}
    for symbol in FIXED_MAJOR8:
        data = market[symbol]
        fetcher = _ReplayFetcher(data.h1)
        engine = ATT1LiveEngine(fetcher)
        for index in range(200, len(data.h1)):
            bar = data.h1[index]
            close_ts = int(bar[0]) + 60 * 60 * 1000
            regime = regime_by_close.get(close_ts)
            if regime is None:
                continue
            fetcher.cursor = index
            signal = engine.signal(symbol, close_ts, float(bar[1]), float(bar[2]), float(bar[3]), float(bar[4]), float(bar[5]))
            if signal is None:
                continue
            consumed = engine.last_closed_rows(symbol, "60")
            if not consumed or consumed[-1] != bar:
                raise ReplayBlocker("caller_consumed_row_mismatch")
            evidence = closed_h1_evidence_from_row(
                consumed[-1], row_bytes=_row_bytes(consumed[-1]),
                observed_at_ms=close_ts + 1, max_decision_age_ms=300_000,
            )
            plan = adapt_att1_live_signal_to_plan(
                signal, evidence, runtime_contract,
                source_files=source_files, expected_source_hashes=source_hashes,
            )
            next_index = data.m5_index.get(close_ts)
            if next_index is None:
                continue
            tick = manifest.payload["exchange_filters"][symbol]["tick_size"]
            plan = apply_exchange_stop_filter(plan, tick)
            policy = _policy(plan, tick)
            for mode in ("base", "stress"):
                cost = manifest.payload["cost_contracts"][mode]
                try:
                    fill = adapt_next_open_replay_fill(
                        plan, policy, data.m5[next_index], row_bytes=_row_bytes(data.m5[next_index]),
                        adverse_slippage_bps=cost["slippage_bps_per_side"],
                    )
                    outcome, net_r, exit_ts = _simulate_outcome(plan, fill, policy, data, cost)
                except ContractViolation:
                    continue
                output[mode].append({
                    "symbol": symbol,
                    "bar_ts": close_ts,
                    "regime_value": regime.value,
                    "net_r": net_r,
                    "outcome": outcome,
                    "exit_ts_ms": exit_ts,
                    "decision_id": plan.decision_id,
                    "execution_contract_hash": _sha({"plan": plan.decision_payload(), "cost": dict(cost)}),
                })
    return output


def run(
    root: Path,
    *,
    manifest_path: Path = PRESEALED_MANIFEST,
    caller_receipt: Path | None = None,
    output: Path = DEFAULT_OUTPUT,
) -> dict[str, object]:
    root = root.resolve()
    reasons: list[str] = []
    binding: dict[str, object] = {}
    try:
        manifest = load_and_verify_manifest(root, manifest_path)
        binding = {
            "manifest_sha256": manifest.manifest_sha256,
            "data_bundle_sha256": manifest.data_bundle_sha256,
            "source_bundle_sha256": manifest.source_bundle_sha256,
            "presealed_window": manifest.payload["window"],
            "sealed_holdout_guard": manifest.payload["sealed_holdout_guard"],
        }
        if manifest.universe != FIXED_MAJOR8:
            raise ReplayBlocker("manifest_universe_not_fixed_major8")
        if caller_receipt is None:
            raise ReplayBlocker("caller_receipt_missing")
        caller_path = caller_receipt if caller_receipt.is_absolute() else root / caller_receipt
        _load_caller_pass(
            caller_path,
            root=root,
            expected_manifest_sha256=manifest.manifest_sha256,
        )
        binding["caller_receipt_sha256"] = hashlib.sha256(caller_path.read_bytes()).hexdigest()
    except (ManifestViolation, ReplayBlocker) as exc:
        reasons.append(str(exc))
    if reasons:
        receipt = build_blocker_manifest(root=root, reasons=reasons, context=binding)
        target = output if output.is_absolute() else root / output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_canonical_bytes(receipt) + b"\n")
        return receipt

    market = _load_market_data(root, manifest)
    regime_map = _build_regime_map(market["BTCUSDT"].h1)
    with _frozen_env(FIXED_MAJOR8):
        events_by_mode = _events_for_att1(root, manifest, market, regime_map)
    if any(not rows for rows in events_by_mode.values()):
        receipt = build_blocker_manifest(
            root=root,
            reasons=["no_eligible_outcome_events"],
            context=binding,
        )
    else:
        receipt = {
            "schema_id": "att1_major8_regime_replay_receipt_v1",
            "decision": "REPLAY_COMPLETE_RESEARCH_ONLY",
            "authority": "research_only_no_live_no_broker_no_promotion",
            "money_authority": False,
            "live_or_broker_calls": False,
            "orders_created_or_changed": 0,
            "sealed_holdout_rows_decoded": 0,
            "universe": list(FIXED_MAJOR8),
            "binding": binding,
            "gate_contract": {"off": "all events", "on": "flat_down only"},
            "metrics": {
                mode: score_gate_variants(rows) for mode, rows in events_by_mode.items()
            },
            "event_ledger_sha256": {
                mode: _sha(rows) for mode, rows in events_by_mode.items()
            },
        }
        receipt["receipt_sha256"] = _sha(receipt)
    target = output if output.is_absolute() else root / output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_canonical_bytes(receipt) + b"\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=PRESEALED_MANIFEST)
    parser.add_argument("--caller-receipt", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        receipt = run(args.root, manifest_path=args.manifest, caller_receipt=args.caller_receipt, output=args.output)
    except Exception as exc:
        print(json.dumps({"decision": "FAIL_CLOSED", "error": f"{type(exc).__name__}:{exc}"}, sort_keys=True))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["decision"] == "REPLAY_COMPLETE_RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
