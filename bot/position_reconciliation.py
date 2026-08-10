"""Pure broker/runner/owner/accounting reconciliation contract.

The module has no broker credentials and performs no mutations.  Its output is
designed for a live entry gate: a conflict blocks additions on that symbol,
while an unusable or stale source blocks all new entries.  Existing position
management is deliberately outside this contract and must remain active.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


SOURCES = ("broker", "runner", "owner", "accounting")
TERMINAL_STATUSES = {"closed", "failed", "cancelled", "canceled", "error"}


def _symbol(value: Any) -> str:
    return str(value or "").upper().strip()


def _side(value: Any) -> str:
    raw = str(value or "").lower().strip()
    if raw in {"buy", "long"}:
        return "Buy"
    if raw in {"sell", "short"}:
        return "Sell"
    return ""


def _qty(row: Mapping[str, Any]) -> float | None:
    for key in ("qty", "size", "position_qty", "remaining_qty"):
        if key not in row:
            continue
        try:
            value = abs(float(row.get(key) or 0.0))
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) else None
    return None


def _strategy(row: Mapping[str, Any]) -> str:
    return str(
        row.get("strategy")
        or row.get("strategy_owner")
        or row.get("owner")
        or ""
    ).lower().strip()


def _active(row: Mapping[str, Any], source: str) -> bool:
    status = str(row.get("status") or "").lower().strip()
    if status in TERMINAL_STATUSES:
        return False
    qty = _qty(row)
    if source == "owner" and qty is None:
        return True
    return qty is None or qty > 0.0


def _canonical_rows(
    rows: Sequence[Mapping[str, Any]] | None,
    source: str,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    conflicts: list[dict[str, Any]] = []
    if rows is None or isinstance(rows, (str, bytes)) or not isinstance(rows, Sequence):
        return indexed, [
            {
                "symbol": "*",
                "code": "invalid_source_container",
                "source": source,
                "detail": "expected_sequence",
            }
        ]
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            conflicts.append(
                {
                    "symbol": "*",
                    "code": "invalid_source_row",
                    "source": source,
                    "detail": f"row_{index}_not_mapping",
                }
            )
            continue
        if not _active(row, source):
            continue
        symbol = _symbol(row.get("symbol"))
        if not symbol:
            conflicts.append(
                {
                    "symbol": "*",
                    "code": "invalid_source_row",
                    "source": source,
                    "detail": f"row_{index}_missing_symbol",
                }
            )
            continue
        indexed.setdefault(symbol, []).append(
            {
                "symbol": symbol,
                "side": _side(row.get("side")),
                "qty": _qty(row),
                "strategy": _strategy(row),
                "stop_present": row.get("stop") not in (None, "", "0", 0, 0.0)
                or row.get("stopLoss") not in (None, "", "0", 0, 0.0),
            }
        )
    return indexed, conflicts


def _qty_equal(left: float | None, right: float | None, *, rel_tol: float, abs_tol: float) -> bool:
    if left is None or right is None:
        return False
    return math.isclose(left, right, rel_tol=rel_tol, abs_tol=abs_tol)


def reconcile_positions(
    *,
    broker_rows: Sequence[Mapping[str, Any]] | None,
    runner_rows: Sequence[Mapping[str, Any]] | None,
    owner_rows: Sequence[Mapping[str, Any]] | None,
    accounting_rows: Sequence[Mapping[str, Any]] | None,
    source_as_of_ts: Mapping[str, float],
    now_ts: float,
    max_age_sec: float = 180.0,
    qty_rel_tol: float = 1e-6,
    qty_abs_tol: float = 1e-9,
    require_broker_stop: bool = True,
) -> dict[str, Any]:
    """Reconcile four independent position views into an entry-gate receipt."""

    conflicts: list[dict[str, Any]] = []
    global_block = False
    freshness: dict[str, dict[str, Any]] = {}
    now = float(now_ts)

    for source in SOURCES:
        raw = source_as_of_ts.get(source)
        try:
            as_of = float(raw) if raw is not None else math.nan
        except (TypeError, ValueError):
            as_of = math.nan
        age = now - as_of if math.isfinite(as_of) else math.inf
        fresh = math.isfinite(age) and -1.0 <= age <= float(max_age_sec)
        freshness[source] = {
            "as_of_ts": as_of if math.isfinite(as_of) else None,
            "age_sec": age if math.isfinite(age) else None,
            "fresh": fresh,
        }
        if not fresh:
            global_block = True
            conflicts.append(
                {
                    "symbol": "*",
                    "code": "source_stale_or_missing",
                    "source": source,
                    "detail": f"age_sec={age if math.isfinite(age) else 'unknown'}",
                }
            )

    indexed: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for source, rows in (
        ("broker", broker_rows),
        ("runner", runner_rows),
        ("owner", owner_rows),
        ("accounting", accounting_rows),
    ):
        source_index, source_conflicts = _canonical_rows(rows, source)
        indexed[source] = source_index
        conflicts.extend(source_conflicts)
        if any(item["symbol"] == "*" for item in source_conflicts):
            global_block = True

    symbols = sorted(
        set().union(*(set(source_index) for source_index in indexed.values()))
    )
    records: list[dict[str, Any]] = []

    def add(symbol: str, code: str, source: str, detail: str = "") -> None:
        conflicts.append(
            {"symbol": symbol, "code": code, "source": source, "detail": detail}
        )

    for symbol in symbols:
        rows_by_source = {source: indexed[source].get(symbol, []) for source in SOURCES}
        for source, rows in rows_by_source.items():
            if len(rows) > 1:
                add(symbol, "duplicate_or_hedged_rows", source, f"count={len(rows)}")

        one = {
            source: (rows[0] if len(rows) == 1 else None)
            for source, rows in rows_by_source.items()
        }
        broker = one["broker"]
        for source in ("runner", "owner", "accounting"):
            other = one[source]
            if broker is not None and other is None:
                add(symbol, f"{source}_missing_for_broker_position", source)
            elif broker is None and other is not None:
                add(symbol, f"{source}_position_missing_at_broker", source)

        if broker is not None and require_broker_stop and not broker["stop_present"]:
            add(symbol, "broker_stop_missing", "broker")

        if broker is not None:
            for source in ("runner", "owner", "accounting"):
                other = one[source]
                if other is None:
                    continue
                if not broker["side"] or not other["side"]:
                    add(symbol, "side_identity_missing", source)
                elif broker["side"] != other["side"]:
                    add(
                        symbol,
                        "side_mismatch",
                        source,
                        f"broker={broker['side']},other={other['side']}",
                    )
                if source != "owner" or other["qty"] is not None:
                    if not _qty_equal(
                        broker["qty"],
                        other["qty"],
                        rel_tol=qty_rel_tol,
                        abs_tol=qty_abs_tol,
                    ):
                        add(
                            symbol,
                            "qty_mismatch",
                            source,
                            f"broker={broker['qty']},other={other['qty']}",
                        )

        strategies = {
            source: row["strategy"]
            for source, row in one.items()
            if source in {"runner", "owner", "accounting"} and row is not None
        }
        if broker is not None:
            if not strategies or any(not value for value in strategies.values()):
                add(symbol, "strategy_identity_missing", "owner")
            elif len(set(strategies.values())) > 1:
                add(symbol, "strategy_owner_mismatch", "owner", str(strategies))

        symbol_conflicts = [row for row in conflicts if row["symbol"] == symbol]
        records.append(
            {
                "symbol": symbol,
                "status": "CONFLICT" if symbol_conflicts else "RECONCILED",
                "sources_present": sorted(
                    source for source, row in one.items() if row is not None
                ),
                "conflict_codes": sorted({row["code"] for row in symbol_conflicts}),
            }
        )

    blocked_symbols = sorted(
        {row["symbol"] for row in conflicts if row["symbol"] != "*"}
    )
    return {
        "schema_id": "position_reconciliation_v1",
        "as_of_ts": now,
        "max_age_sec": float(max_age_sec),
        "scope": "block_new_entries_only_existing_management_continues",
        "ok": not conflicts,
        "global_block_new_entries": bool(global_block),
        "blocked_symbols": blocked_symbols,
        "freshness": freshness,
        "records": records,
        "conflicts": conflicts,
    }


def entry_allowed(receipt: Mapping[str, Any], symbol: str) -> bool:
    """Fail closed for a global source problem or a conflicted symbol."""

    if receipt.get("schema_id") != "position_reconciliation_v1":
        return False
    if bool(receipt.get("global_block_new_entries")):
        return False
    blocked = {_symbol(item) for item in (receipt.get("blocked_symbols") or [])}
    normalized = _symbol(symbol)
    return bool(normalized) and normalized not in blocked
