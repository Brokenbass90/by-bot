#!/usr/bin/env python3
"""Automatic L1 strategy-to-shadow parity for frozen ATT1 and ETS2S.

This runner is public-data/research-only.  It imports no broker client, places
no orders, and grants no money authority.  Every decision bar is recorded,
including no-signal and exception rows.
"""
from __future__ import annotations

import argparse
import contextlib
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Callable, Iterator, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from research_lab.research_ohlcv_store import ResearchKlineStore, timeframe_minutes
from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Strategy
from strategies.att1_live import ATT1LiveEngine
from strategies.elder_live import (
    ETS2S_ENTRY_OFFSET,
    ETS2S_ENTRY_TYPE,
    ETS2S_ENTRY_WAIT_BARS,
    ETS2S_FROZEN_ENV,
    ETS2S_STOP_DISTANCE_MULTIPLIER,
    ETS2S_STOP_TRANSFORM_ID,
    ETS2S_TIME_STOP_BARS_5M,
    ElderShadowEngine,
)
from strategies.elder_triple_screen_v2 import ElderTripleScreenV2Strategy
from strategies.signals import TradeSignal


SCHEMA_ID = "att1_ets2s_signal_shadow_parity_v1"
STORE_CONTRACT_ID = "canonical_closed_utc_buckets_v1"
H1_MS = 60 * 60 * 1000
DEFAULT_FIXTURE_ROOT = ROOT / "research_lab/fixtures/paritet_l1"
DEFAULT_OUT = ROOT / "research_lab/results/att1_ets2s_signal_shadow_parity_20260904"


@dataclass(frozen=True)
class SignalProfile:
    sleeve_id: str
    entry_type: str
    entry_offset: float
    entry_wait_bars: int
    time_stop_hours: int
    stop_transform_id: str
    env: Mapping[str, str]
    source_paths: tuple[str, ...]


ATT1_PROFILE = SignalProfile(
    sleeve_id="ATT1",
    entry_type="market",
    entry_offset=0.0,
    entry_wait_bars=0,
    time_stop_hours=336,
    stop_transform_id="native_strategy_geometry_v1",
    env={
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
    },
    source_paths=(
        "strategies/alt_trendline_touch_v1.py",
        "strategies/att1_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
        "research_lab/research_ohlcv_store.py",
        "research_lab/att1_ets2s_signal_shadow_parity.py",
    ),
)

ETS2S_PROFILE = SignalProfile(
    sleeve_id="ETS2S",
    entry_type=ETS2S_ENTRY_TYPE,
    entry_offset=ETS2S_ENTRY_OFFSET,
    entry_wait_bars=ETS2S_ENTRY_WAIT_BARS,
    time_stop_hours=336,
    stop_transform_id=ETS2S_STOP_TRANSFORM_ID,
    env=ETS2S_FROZEN_ENV,
    source_paths=(
        "strategies/elder_triple_screen_v2.py",
        "strategies/elder_live.py",
        "strategies/live_kline_utils.py",
        "strategies/signals.py",
        "research_lab/research_ohlcv_store.py",
        "research_lab/att1_ets2s_signal_shadow_parity.py",
    ),
)

PROFILES = {profile.sleeve_id: profile for profile in (ATT1_PROFILE, ETS2S_PROFILE)}


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha_object(value: object) -> str:
    return _sha_bytes(_canonical_bytes(value))


def _artifact_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def _source_hash(profile: SignalProfile) -> str:
    digest = hashlib.sha256()
    for relative in profile.source_paths:
        path = ROOT / relative
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


@contextlib.contextmanager
def frozen_profile_env(profile: SignalProfile, universe: Sequence[str]) -> Iterator[None]:
    prefix = "ATT1_" if profile.sleeve_id == "ATT1" else "ETS2_"
    allowlist_key = f"{prefix}SYMBOL_ALLOWLIST"
    values = dict(profile.env)
    values[allowlist_key] = ",".join(str(symbol).upper() for symbol in universe)
    keys = {key for key in os.environ if key.startswith(prefix)} | set(values)
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


def _strategy(profile: SignalProfile):
    if profile.sleeve_id == "ATT1":
        return AltTrendlineTouchV1Strategy()
    return ElderTripleScreenV2Strategy()


def _resolved_config_hash(
    profile: SignalProfile, strategy: object, universe: Sequence[str]
) -> str:
    return _sha_object(
        {
            "entry_offset": profile.entry_offset,
            "entry_type": profile.entry_type,
            "entry_wait_bars": profile.entry_wait_bars,
            "resolved_strategy_config": asdict(strategy.cfg),
            "sleeve_id": profile.sleeve_id,
            "stop_transform_id": profile.stop_transform_id,
            "store_contract_id": STORE_CONTRACT_ID,
            "time_stop_hours": profile.time_stop_hours,
            "universe": sorted(str(symbol).upper() for symbol in universe),
        }
    )


class CausalRawReplayFeed:
    """Emulate raw multi-timeframe exchange bars at one historical as-of."""

    def __init__(self, symbol: str, rows: Sequence[Sequence[object]]):
        self.symbol = symbol
        self.rows = [list(row) for row in rows]
        self.cursor = -1
        self.base_minutes = 60

    @property
    def observed_at_ms(self) -> int:
        if self.cursor < 0:
            raise RuntimeError("replay cursor is not set")
        return int(self.rows[self.cursor][0]) + self.base_minutes * 60_000

    def set_cursor(self, cursor: int) -> None:
        if cursor < 0 or cursor >= len(self.rows):
            raise IndexError("replay cursor outside fixture")
        self.cursor = int(cursor)

    def __call__(self, symbol: str, timeframe: object, limit: int) -> list:
        if symbol != self.symbol:
            raise ValueError("replay feed is per-symbol")
        if self.cursor < 0:
            raise RuntimeError("replay cursor is not set")
        target_minutes = timeframe_minutes(timeframe)
        if target_minutes < self.base_minutes or target_minutes % self.base_minutes:
            raise ValueError("unsupported replay target timeframe")
        source = self.rows[: self.cursor + 1]
        requested = max(0, int(limit))
        if target_minutes == self.base_minutes:
            return list(source[-requested:]) if requested else []

        base_ms = self.base_minutes * 60_000
        target_ms = target_minutes * 60_000
        children = target_minutes // self.base_minutes
        buckets: list[list[list[object]]] = []
        starts: list[int] = []
        for row in source:
            timestamp = int(row[0])
            bucket_start = timestamp // target_ms * target_ms
            if not starts or starts[-1] != bucket_start:
                starts.append(bucket_start)
                buckets.append([])
            buckets[-1].append(row)

        output: list[list[object]] = []
        for index, (bucket_start, bucket) in enumerate(zip(starts, buckets)):
            timestamps = [int(row[0]) for row in bucket]
            if index == 0 and timestamps[0] != bucket_start:
                continue
            expected_prefix = [bucket_start + child * base_ms for child in range(len(bucket))]
            if timestamps != expected_prefix:
                raise ValueError(f"noncausal_or_gapped_replay_bucket:{bucket_start}")
            if index < len(buckets) - 1 and len(bucket) != children:
                raise ValueError(f"incomplete_historical_replay_bucket:{bucket_start}")
            output.append(
                [
                    bucket_start,
                    float(bucket[0][1]),
                    max(float(row[2]) for row in bucket),
                    min(float(row[3]) for row in bucket),
                    float(bucket[-1][4]),
                    sum(float(row[5]) for row in bucket),
                ]
            )
        return output[-requested:] if requested else []


def _load_fixture(fixture_root: Path) -> tuple[dict[str, list[list[object]]], dict[str, str]]:
    source_manifest_path = fixture_root / "manifest.source.json"
    manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    result: dict[str, list[list[object]]] = {}
    hashes: dict[str, str] = {}
    for symbol, expected in sorted(manifest["bary"].items()):
        path = fixture_root / "bars" / f"{symbol}.json"
        raw = path.read_bytes()
        actual_hash = _sha_bytes(raw)
        if actual_hash != expected["sha256"]:
            raise RuntimeError(f"fixture_hash_mismatch:{symbol}")
        payload = json.loads(raw)
        if payload.get("symbol") != symbol or payload.get("interval_minutes") != 60:
            raise RuntimeError(f"fixture_contract_mismatch:{symbol}")
        rows = payload.get("rows")
        if not isinstance(rows, list) or len(rows) != int(expected["barov"]):
            raise RuntimeError(f"fixture_row_count_mismatch:{symbol}")
        result[symbol] = rows
        hashes[symbol] = actual_hash
    return result, hashes


def _oracle_effective_signal(profile: SignalProfile, signal: TradeSignal | None):
    if signal is None or profile.sleeve_id == "ATT1":
        return signal
    if signal.side != "short":
        raise ValueError("ETS2S oracle received a non-short signal")
    entry = float(signal.entry)
    raw_stop = float(signal.sl)
    effective_stop = entry + (raw_stop - entry) * ETS2S_STOP_DISTANCE_MULTIPLIER
    result = replace(
        signal,
        sl=effective_stop,
        time_stop_bars=ETS2S_TIME_STOP_BARS_5M,
        tps=list(signal.tps or []),
        tp_fracs=list(signal.tp_fracs or []),
    )
    if not result.validate():
        raise ValueError("ETS2S oracle effective geometry is invalid")
    return result


def _record(
    *,
    profile: SignalProfile,
    symbol: str,
    bar_ts: int,
    signal: TradeSignal | None,
    config_hash: str,
    source_hash: str,
    data_hash: str,
    exception: str | None,
    no_signal_reason: str,
) -> dict[str, object]:
    values: dict[str, object] = {
        "schema_id": SCHEMA_ID,
        "sleeve_id": profile.sleeve_id,
        "symbol": symbol,
        "bar_ts": int(bar_ts),
        "side": None,
        "entry": None,
        "sl": None,
        "tps": None,
        "tp_fracs": None,
        "reason": None,
        "no_signal_reason": no_signal_reason if signal is None else "",
        "time_stop_bars_5m": profile.time_stop_hours * 12,
        "time_stop_hours": profile.time_stop_hours,
        "entry_type": profile.entry_type,
        "entry_offset": profile.entry_offset,
        "entry_wait_bars": profile.entry_wait_bars,
        "stop_transform_id": profile.stop_transform_id,
        "store_contract_id": STORE_CONTRACT_ID,
        "config_hash": config_hash,
        "source_hash": source_hash,
        "data_hash": data_hash,
        "exception": exception,
    }
    if signal is not None and exception is None:
        values.update(
            {
                "side": signal.side,
                "entry": float(signal.entry),
                "sl": float(signal.sl),
                "tps": [float(value) for value in list(signal.tps or [])],
                "tp_fracs": [float(value) for value in list(signal.tp_fracs or [])],
                "reason": str(signal.reason or ""),
                "time_stop_bars_5m": int(signal.time_stop_bars),
                "time_stop_hours": int(signal.time_stop_bars) * 5 / 60,
            }
        )
    return values


COMPARE_FIELDS = (
    "schema_id",
    "side",
    "entry",
    "sl",
    "tps",
    "tp_fracs",
    "reason",
    "no_signal_reason",
    "time_stop_bars_5m",
    "time_stop_hours",
    "entry_type",
    "entry_offset",
    "entry_wait_bars",
    "stop_transform_id",
    "store_contract_id",
    "config_hash",
    "source_hash",
    "data_hash",
    "exception",
)


def _close(left: object, right: object) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1e-9 * max(
            abs(float(left)), abs(float(right)), 1.0
        )
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        return all(_close(a, b) for a, b in zip(left, right))
    return left == right


def compare_records(
    research: Sequence[Mapping[str, object]],
    shadow: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    def keyed(rows: Sequence[Mapping[str, object]]) -> dict[tuple[object, ...], Mapping[str, object]]:
        result = {}
        for row in rows:
            key = (row.get("sleeve_id"), row.get("symbol"), row.get("bar_ts"))
            if key in result:
                raise RuntimeError(f"duplicate_parity_key:{key}")
            result[key] = row
        return result

    left, right = keyed(research), keyed(shadow)
    only_research = sorted(set(left) - set(right))
    only_shadow = sorted(set(right) - set(left))
    mismatches: list[dict[str, object]] = []
    by_field: dict[str, int] = {}
    for key in sorted(set(left) & set(right)):
        for field in COMPARE_FIELDS:
            if not _close(left[key].get(field), right[key].get(field)):
                by_field[field] = by_field.get(field, 0) + 1
                if len(mismatches) < 25:
                    mismatches.append(
                        {
                            "key": list(key),
                            "field": field,
                            "research": left[key].get(field),
                            "shadow": right[key].get(field),
                        }
                    )
    exception_rows = sum(
        1 for row in list(research) + list(shadow) if row.get("exception")
    )
    passed = not only_research and not only_shadow and not by_field and exception_rows == 0 and bool(left)
    return {
        "verdict": "PASS" if passed else "FAIL",
        "research_rows": len(left),
        "shadow_rows": len(right),
        "only_research": [list(key) for key in only_research[:25]],
        "only_shadow": [list(key) for key in only_shadow[:25]],
        "mismatches_by_field": by_field,
        "mismatch_examples": mismatches,
        "exception_rows": exception_rows,
    }


def _capture(call: Callable[[], TradeSignal | None]) -> tuple[TradeSignal | None, str | None]:
    try:
        return call(), None
    except Exception as exc:  # an exception is evidence and forces FAIL
        return None, f"{type(exc).__name__}: {str(exc)[:240]}"


def _run_sleeve(
    profile: SignalProfile,
    market: Mapping[str, list[list[object]]],
    data_hashes: Mapping[str, str],
    decision_bars: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    symbols = sorted(market)
    research_rows: list[dict[str, object]] = []
    shadow_rows: list[dict[str, object]] = []
    with frozen_profile_env(profile, symbols):
        source_hash = _source_hash(profile)
        config_hashes: set[str] = set()
        for symbol in symbols:
            rows = market[symbol]
            if len(rows) <= decision_bars:
                raise RuntimeError(f"fixture_too_short:{symbol}")
            start = len(rows) - decision_bars - 1
            direct_store = ResearchKlineStore(symbol, base_interval_minutes=60)
            direct_strategy = _strategy(profile)
            feed = CausalRawReplayFeed(symbol, rows)
            shadow_engine = (
                ATT1LiveEngine(feed)
                if profile.sleeve_id == "ATT1"
                else ElderShadowEngine(feed)
            )
            shadow_strategy = shadow_engine._get_strategy(symbol)
            direct_config_hash = _resolved_config_hash(
                profile, direct_strategy, symbols
            )
            shadow_config_hash = _resolved_config_hash(
                profile, shadow_strategy, symbols
            )
            config_hashes.update((direct_config_hash, shadow_config_hash))
            for index in range(start, len(rows) - 1):
                bar = rows[index]
                direct_store.rows = rows[: index + 1]
                feed.set_cursor(index)
                direct_signal, direct_exception = _capture(
                    lambda b=bar: direct_strategy.maybe_signal(direct_store, *b)
                )
                if direct_exception is None:
                    direct_signal, direct_exception = _capture(
                        lambda s=direct_signal: _oracle_effective_signal(profile, s)
                    )
                shadow_signal, shadow_exception = _capture(
                    lambda b=bar: shadow_engine.signal(
                        symbol,
                        *b,
                        observed_at_ms=feed.observed_at_ms,
                    )
                )
                common = {
                    "profile": profile,
                    "symbol": symbol,
                    "bar_ts": int(bar[0]),
                    "source_hash": source_hash,
                    "data_hash": data_hashes[symbol],
                }
                direct_no_signal_reason = (
                    str(
                        getattr(
                            direct_strategy,
                            "_last_no_signal_reason",
                            getattr(direct_strategy, "last_no_signal_reason", ""),
                        )
                        or ""
                    )
                    if direct_signal is None and direct_exception is None
                    else ""
                )
                shadow_no_signal_reason = (
                    shadow_engine.last_no_signal_reason(symbol)
                    if shadow_signal is None and shadow_exception is None
                    else ""
                )
                research_rows.append(
                    _record(
                        signal=direct_signal,
                        exception=direct_exception,
                        no_signal_reason=direct_no_signal_reason,
                        config_hash=direct_config_hash,
                        **common,
                    )
                )
                shadow_rows.append(
                    _record(
                        signal=shadow_signal,
                        exception=shadow_exception,
                        no_signal_reason=shadow_no_signal_reason,
                        config_hash=shadow_config_hash,
                        **common,
                    )
                )
        if len(config_hashes) != 1:
            raise RuntimeError(
                f"resolved_strategy_config_diverged:{profile.sleeve_id}:{sorted(config_hashes)}"
            )
        config_hash = next(iter(config_hashes))
    comparison = compare_records(research_rows, shadow_rows)
    comparison.update(
        {
            "decision_rows": len(research_rows),
            "signals": sum(1 for row in research_rows if row["side"] is not None),
            "config_hash": config_hash,
            "source_hash": source_hash,
        }
    )
    return research_rows, shadow_rows, comparison


def run_fixture_parity(fixture_root: Path, *, decision_bars: int = 300) -> dict[str, object]:
    market, data_hashes = _load_fixture(fixture_root)
    sleeves: dict[str, object] = {}
    for sleeve_id in ("ATT1", "ETS2S"):
        _research, _shadow, comparison = _run_sleeve(
            PROFILES[sleeve_id], market, data_hashes, decision_bars
        )
        sleeves[sleeve_id] = comparison
    return {
        "schema_id": "att1_ets2s_signal_shadow_parity_receipt_v1",
        "authority": "research_only_no_orders_no_broker_no_money_authority",
        "store_contract_id": STORE_CONTRACT_ID,
        "fixture_root": _artifact_path(fixture_root),
        "decision_bars_per_symbol": decision_bars,
        "symbols": sorted(market),
        "sleeves": sleeves,
        "overall_verdict": (
            "PASS" if all(item["verdict"] == "PASS" for item in sleeves.values()) else "FAIL"
        ),
    }


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    path.write_text(
        "".join(_canonical_bytes(dict(row)).decode("ascii") + "\n" for row in rows),
        encoding="ascii",
    )


def run_and_write(fixture_root: Path, out: Path, *, decision_bars: int) -> dict[str, object]:
    market, data_hashes = _load_fixture(fixture_root)
    out.mkdir(parents=True, exist_ok=True)
    sleeves: dict[str, object] = {}
    for sleeve_id in ("ATT1", "ETS2S"):
        research, shadow, comparison = _run_sleeve(
            PROFILES[sleeve_id], market, data_hashes, decision_bars
        )
        _write_jsonl(out / f"{sleeve_id.lower()}_research.jsonl", research)
        _write_jsonl(out / f"{sleeve_id.lower()}_shadow.jsonl", shadow)
        sleeves[sleeve_id] = comparison
    receipt = {
        "schema_id": "att1_ets2s_signal_shadow_parity_receipt_v1",
        "authority": "research_only_no_orders_no_broker_no_money_authority",
        "store_contract_id": STORE_CONTRACT_ID,
        "fixture_root": _artifact_path(fixture_root),
        "decision_bars_per_symbol": decision_bars,
        "symbols": sorted(market),
        "sleeves": sleeves,
        "overall_verdict": (
            "PASS" if all(item["verdict"] == "PASS" for item in sleeves.values()) else "FAIL"
        ),
    }
    (out / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--decision-bars", type=int, default=300)
    args = parser.parse_args()
    receipt = run_and_write(
        args.fixture_root.resolve(), args.out.resolve(), decision_bars=args.decision_bars
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if receipt["overall_verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
