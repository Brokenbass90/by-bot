"""Persistent quarantine for instruments rejected by the exchange."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


DEFAULT_TTL_SEC = 30 * 24 * 60 * 60


def is_unsupported_symbol_error(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return "symbol is not supported" in text or "unsupported symbol" in text


def _read_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"version": 1, "symbols": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), dict):
        return {"version": 1, "symbols": {}}
    return payload


def load_quarantined_symbols(
    path: str | Path,
    *,
    now_ts: float | None = None,
    ttl_sec: int = DEFAULT_TTL_SEC,
) -> set[str]:
    payload = _read_payload(Path(path))
    now = float(time.time() if now_ts is None else now_ts)
    cutoff = now - max(1, int(ttl_sec))
    active: set[str] = set()
    for raw_symbol, raw_meta in payload.get("symbols", {}).items():
        symbol = str(raw_symbol or "").strip().upper()
        meta = raw_meta if isinstance(raw_meta, dict) else {}
        try:
            quarantined_at = float(meta.get("quarantined_at") or 0.0)
        except (TypeError, ValueError):
            quarantined_at = 0.0
        if symbol and quarantined_at >= cutoff:
            active.add(symbol)
    return active


def quarantine_symbol(
    path: str | Path,
    symbol: str,
    *,
    now_ts: float | None = None,
) -> set[str]:
    target = Path(path)
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return load_quarantined_symbols(target, now_ts=now_ts)

    payload = _read_payload(target)
    symbols = payload.setdefault("symbols", {})
    now = float(time.time() if now_ts is None else now_ts)
    symbols[normalized] = {
        "quarantined_at": now,
        "reason": "exchange_unsupported",
    }
    payload["version"] = 1
    payload["updated_at"] = now

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, target)
    return load_quarantined_symbols(target, now_ts=now)
