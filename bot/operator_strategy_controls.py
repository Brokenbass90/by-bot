"""Persistent, human-owned per-strategy entry controls.

This control plane is deliberately separate from automated health/breaker
logic.  Only an explicit operator command writes it.  A paused sleeve stops
creating new entries; existing positions and their protective management are
left untouched.

Missing or malformed state is fail-open and reported in ``snapshot()``.  That
matches the operating rule that monitoring/control-file damage must not
silently switch trading off.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "runtime" / "operator_strategy_controls.json"
SCHEMA_ID = "operator_strategy_controls_v1"

ALIASES = {
    "att1": "att1",
    "att1_trendline_touch": "att1",
    "range": "range",
    "inplay": "inplay",
    "breakout": "breakout",
    "retest": "retest",
    "midterm": "midterm",
    "sloped": "sloped",
    "asm1": "asm1",
    "asb1": "asb1",
    "hzbo1": "hzbo1",
    "bounce1": "bounce1",
    "flat": "flat",
    "breakdown": "breakdown",
    "micro_scalper": "micro_scalper",
    "support_reclaim": "support_reclaim",
    "ivb1": "ivb1",
    "elder": "elder",
    "brc1": "brc1",
    "sob1": "sob1",
    "ts132": "ts132",
    "xsec": "xsec",
}
KNOWN_SLEEVES = tuple(sorted(set(ALIASES.values())))


class OperatorControlError(ValueError):
    """Invalid explicit operator control request."""


def _path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    configured = str(os.getenv("OPERATOR_STRATEGY_CONTROL_PATH", "") or "").strip()
    candidate = Path(configured) if configured else DEFAULT_PATH
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    return candidate


def normalize_sleeve(value: str) -> str:
    key = str(value or "").strip().lower().replace("-", "_")
    sleeve = ALIASES.get(key)
    if not sleeve:
        raise OperatorControlError(
            f"unknown strategy '{value}'; allowed: {','.join(KNOWN_SLEEVES)}"
        )
    return sleeve


def _empty() -> dict[str, Any]:
    return {
        "schema_id": SCHEMA_ID,
        "updated_at_utc": None,
        "paused": {},
    }


def _read(path: Path | str | None = None) -> tuple[dict[str, Any], str | None]:
    target = _path(path)
    if not target.exists():
        return _empty(), None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema_id") != SCHEMA_ID:
            raise ValueError("schema mismatch")
        paused = payload.get("paused")
        if not isinstance(paused, dict):
            raise ValueError("paused must be an object")
        clean: dict[str, dict[str, Any]] = {}
        for raw, metadata in paused.items():
            sleeve = normalize_sleeve(str(raw))
            if not isinstance(metadata, dict):
                raise ValueError(f"metadata for {sleeve} must be an object")
            clean[sleeve] = dict(metadata)
        payload["paused"] = clean
        return payload, None
    except Exception as exc:
        # Explicitly fail-open: a broken monitoring/control file is not an
        # instruction from the human owner to stop trading.
        return _empty(), f"{type(exc).__name__}: {exc}"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def pause(
    sleeve: str,
    *,
    source: str = "operator",
    reason: str = "",
    path: Path | str | None = None,
) -> dict[str, Any]:
    normalized = normalize_sleeve(sleeve)
    target = _path(path)
    payload, error = _read(target)
    if error:
        raise OperatorControlError(
            f"refusing to overwrite malformed operator control state: {error}"
        )
    now = datetime.now(timezone.utc).isoformat()
    payload["updated_at_utc"] = now
    payload["paused"][normalized] = {
        "paused_at_utc": now,
        "source": str(source or "operator")[:80],
        "reason": str(reason or "")[:240],
        "scope": "new_entries_only",
    }
    _atomic_write(target, payload)
    return snapshot(target)


def resume(
    sleeve: str,
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    normalized = normalize_sleeve(sleeve)
    target = _path(path)
    payload, error = _read(target)
    if error:
        raise OperatorControlError(
            f"refusing to overwrite malformed operator control state: {error}"
        )
    payload["paused"].pop(normalized, None)
    payload["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_write(target, payload)
    return snapshot(target)


def is_paused(sleeve: str, *, path: Path | str | None = None) -> bool:
    try:
        normalized = normalize_sleeve(sleeve)
    except OperatorControlError:
        return False
    payload, error = _read(path)
    if error:
        return False
    return normalized in payload["paused"]


def snapshot(path: Path | str | None = None) -> dict[str, Any]:
    target = _path(path)
    payload, error = _read(target)
    return {
        "schema_id": SCHEMA_ID,
        "path": str(target),
        "exists": target.exists(),
        "read_error": error,
        "fail_open_on_error": True,
        "scope": "new_entries_only",
        "paused": dict(payload.get("paused") or {}),
        "paused_sleeves": sorted((payload.get("paused") or {}).keys()),
        "updated_at_utc": payload.get("updated_at_utc"),
    }


def format_status(path: Path | str | None = None) -> str:
    state = snapshot(path)
    if state["read_error"]:
        return (
            "Operator strategy controls: ERROR, fail-open\n"
            f"{state['read_error']}"
        )
    paused = state["paused_sleeves"]
    if not paused:
        return "Operator strategy controls: all sleeves allowed"
    return (
        "Operator strategy controls: paused new entries for "
        + ", ".join(paused)
    )
