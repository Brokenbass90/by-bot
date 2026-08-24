#!/usr/bin/env python3
"""Run actual direct-strategy versus live-wrapper parity on pre-sealed bytes.

Authority is research-only.  The runner verifies the immutable manifest before
decoding data, never reads the reserved 2025-10..2026-06 holdout, never imports
a broker client, and writes separate ATT1/SBR1 base/stress ledgers and reports.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterator, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.att1_runtime_contract import build_att1_runtime_contract
from bot.live_native_decision_contract import (
    apply_exchange_stop_filter,
    ContractViolation,
    FillRebasePolicy,
    H1_MS,
    LiveNativeDecisionPlan,
    rebase_targets_once,
    time_stop_deadline_ms,
)
from bot.live_native_fill_adapter import adapt_next_open_replay_fill
from bot.live_native_manifest import VerifiedParityManifest, load_and_verify_manifest
from bot.live_native_regime_gate import (
    ClosedH1EMA200RegimeGate,
    ClosedH1RegimeEvidence,
)
from bot.live_native_signal_adapters import (
    adapt_att1_live_signal_to_plan,
    adapt_att1_research_signal_to_plan,
    adapt_sbr1_live_signal_to_plan,
    adapt_sbr1_research_signal_to_plan,
    closed_h1_evidence_from_row,
)
from research_lab.adapter_parity import compare_ledgers, read_jsonl
from research_lab.live_native_adapter_emitters import (
    AdapterParityContext,
    emit_live_adapter_row,
    emit_research_adapter_row,
    normalized_row_jsonl_bytes,
)
from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Strategy
from strategies.att1_live import ATT1LiveEngine
from strategies.sbr1_live import SBR1LiveEngine
from strategies.signals import TradeSignal
from strategies.sloped_break_retest_v1 import SlopedBreakRetestV1Strategy


DEFAULT_MANIFEST = Path("configs/research/att1_sbr1_live_native_parity_v1.json")
DEFAULT_OUT = Path(
    "research_lab/results/att1_sbr1_actual_adapter_parity_presealed_v1_20260823"
)
M5_MS = 5 * 60 * 1000


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _decimal_text(value: Decimal) -> str:
    return "0" if value == 0 else format(value.normalize(), "f")


def _row_bytes(row: Sequence[object]) -> bytes:
    return json.dumps(
        list(row), separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


@dataclass(frozen=True)
class MarketData:
    symbol: str
    m5: tuple[tuple[object, ...], ...]
    h1: tuple[tuple[object, ...], ...]
    m5_index: Mapping[int, int]
    h1_index: Mapping[int, int]


def _aggregate_h1(m5: Sequence[Sequence[object]]) -> tuple[tuple[object, ...], ...]:
    result: list[tuple[object, ...]] = []
    bucket: list[Sequence[object]] = []
    bucket_start: int | None = None

    def flush() -> None:
        nonlocal bucket, bucket_start
        if bucket_start is None:
            return
        expected = [bucket_start + index * M5_MS for index in range(12)]
        actual = [int(row[0]) for row in bucket]
        if actual != expected:
            raise RuntimeError(f"incomplete_h1_bucket:{bucket_start}")
        result.append(
            (
                bucket_start,
                bucket[0][1],
                max(float(row[2]) for row in bucket),
                min(float(row[3]) for row in bucket),
                bucket[-1][4],
                sum(float(row[5]) for row in bucket),
            )
        )
        bucket = []
        bucket_start = None

    for row in m5:
        start = int(row[0])
        current_bucket = start // H1_MS * H1_MS
        if bucket_start is None:
            bucket_start = current_bucket
        if current_bucket != bucket_start:
            flush()
            bucket_start = current_bucket
        bucket.append(row)
    flush()
    return tuple(result)


def _load_market_data(root: Path, manifest: VerifiedParityManifest) -> dict[str, MarketData]:
    result: dict[str, MarketData] = {}
    end_exclusive = int(
        __import__("datetime").datetime.fromisoformat(
            str(manifest.payload["window"]["end_utc_exclusive"]).replace("Z", "+00:00")
        ).timestamp()
        * 1000
    )
    for item in manifest.payload["data_files"]:
        path = root / str(item["path"])
        payload = json.loads(path.read_text(encoding="utf-8"))
        symbol = str(item["symbol"]).upper()
        if payload.get("schema_id") != "bybit_public_m5_preholdout_v1":
            raise RuntimeError(f"wrong_data_schema:{symbol}")
        if str(payload.get("symbol") or "").upper() != symbol:
            raise RuntimeError(f"data_symbol_mismatch:{symbol}")
        if int(payload.get("end_exclusive_ms") or 0) > end_exclusive:
            raise RuntimeError(f"sealed_data_boundary_crossed:{symbol}")
        records = payload.get("records")
        if not isinstance(records, list) or not records:
            raise RuntimeError(f"empty_data:{symbol}")
        rows: list[tuple[object, ...]] = []
        previous = None
        for record in records:
            ts = int(record["ts_ms"])
            if ts >= end_exclusive:
                raise RuntimeError(f"sealed_row_decoded:{symbol}:{ts}")
            if previous is not None and ts != previous + M5_MS:
                raise RuntimeError(f"noncontiguous_m5:{symbol}:{ts}")
            previous = ts
            rows.append(
                (
                    ts,
                    record["open"],
                    record["high"],
                    record["low"],
                    record["close"],
                    record["volume"],
                )
            )
        h1 = _aggregate_h1(rows)
        result[symbol] = MarketData(
            symbol=symbol,
            m5=tuple(rows),
            h1=h1,
            m5_index={int(row[0]): index for index, row in enumerate(rows)},
            h1_index={int(row[0]): index for index, row in enumerate(h1)},
        )
    return result


def _build_regime_map(
    rows: Sequence[Sequence[object]],
) -> dict[int, ClosedH1RegimeEvidence]:
    """Build each causal EMA state once, exactly as a live stream would."""

    gate = ClosedH1EMA200RegimeGate()
    result: dict[int, ClosedH1RegimeEvidence] = {}
    for row in rows:
        close_ts = int(row[0]) + H1_MS
        evidence = gate.update(
            row,
            observed_at_ms=close_ts + 1,
            max_age_ms=300_000,
        )
        if evidence is not None:
            result[close_ts] = evidence
    return result


class _ReplayStore:
    def __init__(self, symbol: str, rows: Sequence[Sequence[object]]):
        self.symbol = symbol
        self.rows = rows
        self.cursor = 0
        self.last_rows: list[Sequence[object]] = []

    def fetch_klines(self, _symbol: str, _interval: str, limit: int) -> list:
        self.last_rows = list(self.rows[: self.cursor + 1][-int(limit) :])
        return self.last_rows


class _ReplayFetcher:
    def __init__(self, rows: Sequence[Sequence[object]]):
        self.rows = rows
        self.cursor = 0

    def __call__(self, _symbol: str, _interval: str, limit: int) -> list:
        return list(self.rows[: self.cursor + 1][-int(limit) :])


@contextlib.contextmanager
def _frozen_env(universe: Sequence[str]) -> Iterator[None]:
    values = {
        "ATT1_SYMBOL_ALLOWLIST": ",".join(universe),
        "ATT1_SIGNAL_TF": "60",
        "ATT1_SL_ATR_MULT": "6.60",
        "ATT1_MAX_STOP_PCT": "0.25",
        "ATT1_TP1_RR": "1.20",
        "ATT1_TP2_RR": "2.50",
        "ATT1_TP1_FRAC": "0.55",
        "ATT1_BE_TRIGGER_RR": "0",
        "ATT1_TRAIL_ATR_MULT": "0",
        "ATT1_TIME_STOP_BARS_5M": "4032",
        "ATT1_COOLDOWN_BARS_5M": "96",
        "ATT1_ALLOW_LONGS": "0",
        "ATT1_ALLOW_SHORTS": "1",
        "SBR1_SYMBOL_ALLOWLIST": ",".join(universe),
        "SBR1_SIGNAL_TF": "60",
        "SBR1_SL_ATR_MULT": "4.60",
        "SBR1_TP1_RR": "1.10",
        "SBR1_TP2_RR": "2.60",
        "SBR1_TP1_FRAC": "0.50",
        "SBR1_TP2_FRAC": "0.30",
        "SBR1_BE_TRIGGER_RR": "0",
        "SBR1_TRAIL_ATR_MULT": "0",
        "SBR1_TIME_STOP_BARS_5M": "2016",
        "SBR1_COOLDOWN_TF_BARS": "6",
        "SBR1_ALLOW_LONGS": "1",
        "SBR1_ALLOW_SHORTS": "0",
    }
    keys = {
        key
        for key in os.environ
        if key.startswith("ATT1_") or key.startswith("SBR1_")
    } | set(values)
    previous = {key: os.environ.get(key) for key in keys}
    for key in keys:
        os.environ.pop(key, None)
    os.environ.update(values)
    try:
        yield
    finally:
        for key in keys:
            os.environ.pop(key, None)
        for key, value in previous.items():
            if value is not None:
                os.environ[key] = value


def _signal_payload(signal: TradeSignal | None) -> object:
    if signal is None:
        return None
    return {
        "strategy": signal.strategy,
        "symbol": signal.symbol,
        "side": signal.side,
        "entry": str(signal.entry),
        "sl": str(signal.sl),
        "tp": str(signal.tp),
        "tps": [str(value) for value in list(signal.tps or [])],
        "tp_fracs": [str(value) for value in list(signal.tp_fracs or [])],
        "time_stop_bars": signal.time_stop_bars,
        "reason": signal.reason,
    }


def _cost_hash(cost: Mapping[str, object]) -> str:
    return _sha({"cost": dict(cost), "schema_id": "parity_cost_contract_v1"})


def _simulate_outcome(
    plan: LiveNativeDecisionPlan,
    fill,
    policy: FillRebasePolicy,
    data: MarketData,
    cost: Mapping[str, object],
) -> tuple[str, Decimal, int]:
    execution = rebase_targets_once(plan, fill, policy)
    deadline = time_stop_deadline_ms(execution)
    end_ts = deadline - M5_MS
    start_index = data.m5_index.get(fill.fill_ts_ms)
    end_index = data.m5_index.get(end_ts)
    if start_index is None or end_index is None or end_index < start_index:
        raise ContractViolation("incomplete_outcome_window")

    entry = fill.fill_price
    stop = execution.frozen_sl
    risk = abs(entry - stop)
    if risk <= 0:
        raise ContractViolation("nonpositive_outcome_risk")
    fee_bps = Decimal(str(cost["fee_bps_per_side"]))
    exit_slip_bps = Decimal(str(cost["slippage_bps_per_side"]))
    funding_bps = Decimal(str(cost.get("adverse_funding_bps_per_8h", "0")))
    if fee_bps < 0 or exit_slip_bps < 0 or funding_bps < 0:
        raise ContractViolation("negative_cost_contract")
    direction = Decimal("1") if plan.side == "long" else Decimal("-1")
    net_r = -(fee_bps / Decimal("10000")) * entry / risk
    remaining = Decimal("1")
    target_index = 0
    labels: list[str] = []
    exit_ts_ms = fill.fill_ts_ms

    def realize(price: Decimal, fraction: Decimal, label: str) -> None:
        nonlocal net_r, remaining
        exit_direction = Decimal("-1") if plan.side == "long" else Decimal("1")
        executed = price * (
            Decimal("1") + exit_direction * exit_slip_bps / Decimal("10000")
        )
        net_r += fraction * direction * (executed - entry) / risk
        net_r -= fraction * (fee_bps / Decimal("10000")) * executed / risk
        remaining -= fraction
        labels.append(label)

    for raw in data.m5[start_index : end_index + 1]:
        raw_ts = int(raw[0])
        raw_open = Decimal(str(raw[1]))
        high = Decimal(str(raw[2]))
        low = Decimal(str(raw[3]))
        # Bybit perpetual funding settles on the 8-hour UTC grid.  Stress is
        # deliberately adverse for either side and applies only after entry.
        if raw_ts > fill.fill_ts_ms and raw_ts % (8 * H1_MS) == 0 and remaining > 0:
            net_r -= (
                remaining
                * (funding_bps / Decimal("10000"))
                * raw_open
                / risk
            )
        stop_hit = low <= stop if plan.side == "long" else high >= stop
        if stop_hit:
            gap_through = (
                raw_open < stop if plan.side == "long" else raw_open > stop
            )
            realize(raw_open if gap_through else stop, remaining, "gap_stop" if gap_through else "stop")
            exit_ts_ms = raw_ts + M5_MS
            break
        while target_index < len(execution.rebased_tps):
            target = execution.rebased_tps[target_index]
            hit = high >= target if plan.side == "long" else low <= target
            if not hit:
                break
            fraction = plan.tp_fractions[target_index]
            realize(target, fraction, f"tp{target_index + 1}")
            target_index += 1
        if remaining <= 0:
            exit_ts_ms = raw_ts + M5_MS
            break
    if remaining > 0:
        realize(Decimal(str(data.m5[end_index][4])), remaining, "time_stop")
        exit_ts_ms = int(data.m5[end_index][0]) + M5_MS
    return "+".join(labels), net_r, exit_ts_ms


def _source_bundle(
    root: Path, manifest: VerifiedParityManifest, paths: set[str]
) -> tuple[dict[str, bytes], dict[str, str]]:
    rows = {
        str(item["path"]): item for item in manifest.payload["source_files"]
    }
    if not paths.issubset(rows):
        raise RuntimeError(f"missing_source_manifest:{sorted(paths - set(rows))}")
    return (
        {path: (root / path).read_bytes() for path in paths},
        {path: str(rows[path]["sha256"]) for path in paths},
    )


def _policy(plan: LiveNativeDecisionPlan, tick_size: object) -> FillRebasePolicy:
    return FillRebasePolicy(
        spec_id=plan.spec_id,
        profile_hash=plan.profile_hash,
        tick_size=Decimal(str(tick_size)),
        max_adverse_risk_expansion=Decimal("0.20"),
        max_fill_age_ms=300_000,
        max_finalize_delay_ms=60_000,
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_sleeve(
    sleeve: str,
    root: Path,
    out: Path,
    manifest: VerifiedParityManifest,
    market: Mapping[str, MarketData],
    regime_by_close: Mapping[int, ClosedH1RegimeEvidence],
) -> dict[str, object]:
    if sleeve == "ATT1":
        source_paths = {
            "strategies/alt_trendline_touch_v1.py",
            "strategies/att1_live.py",
            "strategies/live_kline_utils.py",
            "strategies/signals.py",
        }
        expected_side = "short"
        runtime_contract = build_att1_runtime_contract(risk_mult=0.0)
    else:
        source_paths = {
            "strategies/sloped_break_retest_v1.py",
            "strategies/sbr1_live.py",
            "strategies/live_kline_utils.py",
            "strategies/signals.py",
        }
        expected_side = "long"
        runtime_contract = None
    source_files, source_hashes = _source_bundle(root, manifest, source_paths)

    evaluation_research: list[dict[str, object]] = []
    evaluation_live: list[dict[str, object]] = []
    rows_by_mode: dict[str, dict[str, list[dict[str, object]]]] = {
        mode: {"research": [], "live": []} for mode in ("base", "stress")
    }
    counters = {
        "evaluations": 0,
        "raw_signals": 0,
        "regime_eligible_signals": 0,
        "normalized_signals": {"base": 0, "stress": 0},
        "drops": {},
    }

    for symbol in manifest.universe:
        data = market[symbol]
        direct_store = _ReplayStore(symbol, data.h1)
        live_fetcher = _ReplayFetcher(data.h1)
        if sleeve == "ATT1":
            direct_strategy = AltTrendlineTouchV1Strategy()
            live_engine = ATT1LiveEngine(live_fetcher)
        else:
            direct_strategy = SlopedBreakRetestV1Strategy()
            live_engine = SBR1LiveEngine(live_fetcher)

        for index in range(200, len(data.h1)):
            bar = data.h1[index]
            bar_start = int(bar[0])
            close_ts = bar_start + H1_MS
            regime = regime_by_close.get(close_ts)
            if regime is None:
                continue
            direct_store.cursor = index
            live_fetcher.cursor = index
            error_research = error_live = None
            direct_signal = live_signal = None
            try:
                direct_signal = direct_strategy.maybe_signal(
                    direct_store,
                    close_ts,
                    float(bar[1]),
                    float(bar[2]),
                    float(bar[3]),
                    float(bar[4]),
                    float(bar[5]),
                )
            except Exception as exc:  # recorded, then parity fails closed below
                error_research = f"{type(exc).__name__}:{exc}"
            try:
                live_signal = live_engine.signal(
                    symbol,
                    close_ts,
                    float(bar[1]),
                    float(bar[2]),
                    float(bar[3]),
                    float(bar[4]),
                    float(bar[5]),
                )
            except Exception as exc:
                error_live = f"{type(exc).__name__}:{exc}"

            eligible = regime.allows(sleeve)
            base_evaluation = {
                "bar_ts": close_ts,
                "eligible_regime": eligible,
                "regime_bar_ts": regime.closed_h1_ts_ms,
                "regime_value": regime.value,
                "side_contract": expected_side,
                "sleeve_id": sleeve,
                "symbol": symbol,
            }
            research_eval = {
                **base_evaluation,
                "exception": error_research,
                "signal": _signal_payload(direct_signal),
            }
            live_eval = {
                **base_evaluation,
                "exception": error_live,
                "signal": _signal_payload(live_signal),
            }
            evaluation_research.append(research_eval)
            evaluation_live.append(live_eval)
            counters["evaluations"] += 1
            if research_eval != live_eval:
                raise RuntimeError(f"evaluation_boundary_mismatch:{sleeve}:{symbol}:{close_ts}")
            if error_research or error_live:
                raise RuntimeError(f"boundary_exception:{sleeve}:{symbol}:{close_ts}")
            if direct_signal is None:
                continue
            counters["raw_signals"] += 1
            if not eligible:
                counters["drops"]["regime"] = counters["drops"].get("regime", 0) + 1
                continue
            counters["regime_eligible_signals"] += 1

            consumed_research = list(direct_store.last_rows)
            consumed_live = list(live_engine.last_closed_rows(symbol, "60"))
            if not consumed_research or consumed_research[-1] != bar:
                raise RuntimeError(f"research_consumed_row_mismatch:{sleeve}:{symbol}:{close_ts}")
            if not consumed_live or consumed_live[-1] != bar:
                raise RuntimeError(f"live_consumed_row_mismatch:{sleeve}:{symbol}:{close_ts}")
            evidence_research = closed_h1_evidence_from_row(
                consumed_research[-1],
                row_bytes=_row_bytes(consumed_research[-1]),
                observed_at_ms=close_ts + 1,
                max_decision_age_ms=300_000,
            )
            evidence_live = closed_h1_evidence_from_row(
                consumed_live[-1],
                row_bytes=_row_bytes(consumed_live[-1]),
                observed_at_ms=close_ts + 1,
                max_decision_age_ms=300_000,
            )
            if sleeve == "ATT1":
                research_plan = adapt_att1_research_signal_to_plan(
                    direct_signal,
                    evidence_research,
                    runtime_contract,
                    source_files=source_files,
                    expected_source_hashes=source_hashes,
                )
                live_plan = adapt_att1_live_signal_to_plan(
                    live_signal,
                    evidence_live,
                    runtime_contract,
                    source_files=source_files,
                    expected_source_hashes=source_hashes,
                )
            else:
                research_plan = adapt_sbr1_research_signal_to_plan(
                    direct_signal,
                    evidence_research,
                    direct_strategy.cfg,
                    source_files=source_files,
                    expected_source_hashes=source_hashes,
                )
                live_plan = adapt_sbr1_live_signal_to_plan(
                    live_signal,
                    evidence_live,
                    live_engine.effective_config(symbol),
                    source_files=source_files,
                    expected_source_hashes=source_hashes,
                )
            if research_plan != live_plan:
                raise RuntimeError(f"decision_plan_mismatch:{sleeve}:{symbol}:{close_ts}")

            m5_index = data.m5_index.get(close_ts)
            if m5_index is None:
                counters["drops"]["missing_next_open"] = counters["drops"].get("missing_next_open", 0) + 1
                continue
            next_open = data.m5[m5_index]
            next_open_bytes = _row_bytes(next_open)
            tick = manifest.payload["exchange_filters"][symbol]["tick_size"]
            research_plan = apply_exchange_stop_filter(research_plan, tick)
            live_plan = apply_exchange_stop_filter(live_plan, tick)
            if research_plan != live_plan:
                raise RuntimeError(
                    f"exchange_filtered_plan_mismatch:{sleeve}:{symbol}:{close_ts}"
                )
            policy = _policy(research_plan, tick)
            for mode in ("base", "stress"):
                cost = manifest.payload["cost_contracts"][mode]
                research_fill = live_fill = None
                research_result = live_result = None
                research_error = live_error = None
                try:
                    research_fill = adapt_next_open_replay_fill(
                        research_plan,
                        policy,
                        next_open,
                        row_bytes=next_open_bytes,
                        adverse_slippage_bps=cost["slippage_bps_per_side"],
                    )
                    research_result = _simulate_outcome(
                        research_plan, research_fill, policy, data, cost
                    )
                except ContractViolation as exc:
                    research_error = exc.code
                try:
                    live_fill = adapt_next_open_replay_fill(
                        live_plan,
                        policy,
                        next_open,
                        row_bytes=next_open_bytes,
                        adverse_slippage_bps=cost["slippage_bps_per_side"],
                    )
                    live_result = _simulate_outcome(
                        live_plan, live_fill, policy, data, cost
                    )
                except ContractViolation as exc:
                    live_error = exc.code
                if research_error or live_error:
                    if research_error != live_error:
                        raise RuntimeError(
                            f"independent_outcome_error_mismatch:{sleeve}:{symbol}:"
                            f"{close_ts}:{mode}:{research_error}:{live_error}"
                        )
                    code = f"{mode}:{research_error}"
                    counters["drops"][code] = counters["drops"].get(code, 0) + 1
                    continue
                if (
                    research_fill is None
                    or live_fill is None
                    or research_result is None
                    or live_result is None
                ):
                    raise RuntimeError("missing_independent_outcome")
                research_outcome, research_net_r, research_exit_ts = research_result
                live_outcome, live_net_r, live_exit_ts = live_result
                research_context = AdapterParityContext(
                    cooldown_state="ready",
                    cooldown_until_ts_ms=None,
                    regime_value=regime.value,
                    regime_bar_ts_ms=regime.closed_h1_ts_ms,
                    outcome=research_outcome,
                    net_r=research_net_r,
                    exit_ts_ms=research_exit_ts,
                    cost_contract_hash=_cost_hash(cost),
                )
                live_context = AdapterParityContext(
                    cooldown_state="ready",
                    cooldown_until_ts_ms=None,
                    regime_value=regime.value,
                    regime_bar_ts_ms=regime.closed_h1_ts_ms,
                    outcome=live_outcome,
                    net_r=live_net_r,
                    exit_ts_ms=live_exit_ts,
                    cost_contract_hash=_cost_hash(cost),
                )
                research_row = emit_research_adapter_row(
                    research_plan, research_fill, policy, research_context
                )
                live_row = emit_live_adapter_row(
                    live_plan,
                    live_fill,
                    policy,
                    live_context,
                )
                rows_by_mode[mode]["research"].append(research_row)
                rows_by_mode[mode]["live"].append(live_row)
                counters["normalized_signals"][mode] += 1

    eval_research_bytes = b"".join(
        _canonical_bytes(row) + b"\n" for row in evaluation_research
    )
    eval_live_bytes = b"".join(_canonical_bytes(row) + b"\n" for row in evaluation_live)
    if eval_research_bytes != eval_live_bytes:
        raise RuntimeError(f"evaluation_ledger_byte_mismatch:{sleeve}")
    (out / f"{sleeve.lower()}_evaluation_research.jsonl").write_bytes(eval_research_bytes)
    (out / f"{sleeve.lower()}_evaluation_live.jsonl").write_bytes(eval_live_bytes)

    reports: dict[str, object] = {}
    for mode in ("base", "stress"):
        research_path = out / f"{sleeve.lower()}_{mode}_research.jsonl"
        live_path = out / f"{sleeve.lower()}_{mode}_live.jsonl"
        research_path.write_bytes(
            b"".join(normalized_row_jsonl_bytes(row) for row in rows_by_mode[mode]["research"])
        )
        live_path.write_bytes(
            b"".join(normalized_row_jsonl_bytes(row) for row in rows_by_mode[mode]["live"])
        )
        if not rows_by_mode[mode]["research"]:
            raise RuntimeError(f"empty_normalized_ledger:{sleeve}:{mode}")
        report = compare_ledgers(read_jsonl(research_path), read_jsonl(live_path))
        report["research_ledger_sha256"] = hashlib.sha256(
            research_path.read_bytes()
        ).hexdigest()
        report["live_ledger_sha256"] = hashlib.sha256(
            live_path.read_bytes()
        ).hexdigest()
        _write_json(out / f"{sleeve.lower()}_{mode}_parity_report.json", report)
        if report.get("decision") != "PASS":
            raise RuntimeError(f"comparator_failed:{sleeve}:{mode}")
        reports[mode] = report
    return {
        "counters": counters,
        "evaluation_ledger_sha256": hashlib.sha256(eval_research_bytes).hexdigest(),
        "reports": reports,
    }


def run(root: Path, manifest_path: Path, out: Path) -> dict[str, object]:
    root = root.resolve()
    out = out if out.is_absolute() else root / out
    out.mkdir(parents=True, exist_ok=True)
    manifest = load_and_verify_manifest(root, manifest_path)
    market = _load_market_data(root, manifest)
    if set(market) != set(manifest.universe):
        raise RuntimeError("loaded_market_universe_mismatch")
    regime_by_close = _build_regime_map(market["BTCUSDT"].h1)
    with _frozen_env(manifest.universe):
        sleeves = {
            sleeve: _run_sleeve(
                sleeve, root, out, manifest, market, regime_by_close
            )
            for sleeve in ("ATT1", "SBR1")
        }
    receipt = {
        "schema_id": "att1_sbr1_actual_adapter_parity_receipt_v1",
        "created_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "decision": "COMPONENT_PARITY_PASS",
        "live_caller_parity": "BLOCKED",
        "authority": "research_only_no_live_no_broker_no_promotion",
        "release_or_promotion_authority": False,
        "money_authority": False,
        "live_or_broker_calls": False,
        "orders_created_or_changed": 0,
        "sealed_holdout_rows_decoded": 0,
        "manifest_path": str(manifest.path.relative_to(root)),
        "manifest_sha256": manifest.manifest_sha256,
        "data_bundle_sha256": manifest.data_bundle_sha256,
        "source_bundle_sha256": manifest.source_bundle_sha256,
        "window": manifest.payload["window"],
        "sealed_holdout_guard": manifest.payload["sealed_holdout_guard"],
        "sleeves": sleeves,
        "what_pass_means": "Direct strategy and default-off wrapper components independently produced byte-equal evaluation ledgers and field-equal normalized signal/fill/outcome rows on the declared pre-sealed bytes.",
        "what_pass_does_not_mean": "No sealed OOS, prospective shadow, live broker fill, profitability, promotion, risk, or money authority is granted.",
        "next_gate": "default_off_production_caller_parity_then_zero_order_prospective_shadow; broker fills require a separate owner-approved minimum-notional canary",
    }
    receipt["receipt_sha256"] = _sha(receipt)
    _write_json(out / "receipt.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    try:
        receipt = run(args.root, args.manifest, args.out)
    except Exception as exc:
        print(json.dumps({"decision": "FAIL_CLOSED", "error": f"{type(exc).__name__}:{exc}"}))
        return 2
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
