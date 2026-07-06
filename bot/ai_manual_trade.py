"""ai_manual_v1 guardrails.

This module intentionally does not place orders. It owns the small, testable
parts that must be correct before any execution path is wired:
one-shot owner token, mandatory stop-loss validation, liquid allowlist,
max-one-position guard, and hard risk_mult=0.05.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import time
from pathlib import Path
from typing import Any

STRATEGY = "ai_manual_v1"
HARD_RISK_MULT = 0.05
DEFAULT_TTL_SEC = 3600
DEFAULT_TOKEN_PATH = Path("runtime/ai_manual_token.json")
DEFAULT_ALLOWLIST = {
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "SUIUSDT",
    "HYPEUSDT",
    "1000PEPEUSDT",
}


def _sha256(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _token_path(root: Path | str, path: Path | str = DEFAULT_TOKEN_PATH) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return Path(root) / p


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def issue_token(
    root: Path | str = ".",
    *,
    ttl_sec: int = DEFAULT_TTL_SEC,
    now_ts: int | None = None,
    token_path: Path | str = DEFAULT_TOKEN_PATH,
) -> tuple[str, dict[str, Any]]:
    now = int(now_ts if now_ts is not None else time.time())
    token = secrets.token_urlsafe(24)
    payload = {
        "strategy": STRATEGY,
        "token_sha256": _sha256(token),
        "created_ts": now,
        "expires_ts": now + max(60, int(ttl_sec)),
        "used_ts": 0,
        "status": "active",
    }
    path = _token_path(root, token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return token, payload


def validate_and_burn_token(
    token: str,
    root: Path | str = ".",
    *,
    now_ts: int | None = None,
    token_path: Path | str = DEFAULT_TOKEN_PATH,
) -> tuple[bool, str]:
    now = int(now_ts if now_ts is not None else time.time())
    path = _token_path(root, token_path)
    payload = _read_json(path)
    if not payload:
        return False, "token_missing"
    if str(payload.get("status") or "") != "active":
        return False, f"token_not_active:{payload.get('status')}"
    if int(payload.get("used_ts") or 0) > 0:
        return False, "token_already_used"
    if now > int(payload.get("expires_ts") or 0):
        payload["status"] = "expired"
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return False, "token_expired"
    if _sha256(token) != str(payload.get("token_sha256") or ""):
        return False, "token_hash_mismatch"
    payload["used_ts"] = now
    payload["status"] = "used"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True, "ok"


def validate_trade_card(
    card: dict[str, Any],
    *,
    liquid_allowlist: set[str] | None = None,
    open_ai_positions: int = 0,
) -> tuple[bool, list[str], dict[str, Any]]:
    allowlist = {str(x).upper() for x in (liquid_allowlist or DEFAULT_ALLOWLIST)}
    reasons: list[str] = []
    symbol = str(card.get("symbol") or "").upper().strip()
    side = str(card.get("side") or "").strip().title()
    entry_type = str(card.get("entry_type") or "market").strip().lower()

    try:
        sl = float(card.get("sl"))
    except Exception:
        sl = 0.0
    try:
        tp_raw = card.get("tp")
        tp = float(tp_raw) if tp_raw not in (None, "") else None
    except Exception:
        tp = None

    if symbol not in allowlist:
        reasons.append("symbol_not_in_liquid_allowlist")
    if side not in {"Buy", "Sell"}:
        reasons.append("side_must_be_Buy_or_Sell")
    if entry_type not in {"market", "limit"}:
        reasons.append("entry_type_must_be_market_or_limit")
    if sl <= 0:
        reasons.append("sl_required")
    if open_ai_positions >= 1:
        reasons.append("max_one_ai_manual_position")

    normalized = {
        "strategy": STRATEGY,
        "symbol": symbol,
        "side": side,
        "entry_type": entry_type,
        "sl": sl if sl > 0 else None,
        "tp": tp,
        "risk_mult": HARD_RISK_MULT,
        "reason": str(card.get("reason") or "").strip()[:600],
    }
    return not reasons, reasons, normalized


def main() -> int:
    ap = argparse.ArgumentParser(description="ai_manual_v1 token and trade-card guardrails")
    ap.add_argument("--root", default=".")
    ap.add_argument("--issue-token", action="store_true")
    ap.add_argument("--ttl-sec", type=int, default=DEFAULT_TTL_SEC)
    args = ap.parse_args()
    if args.issue_token:
        token, payload = issue_token(args.root, ttl_sec=args.ttl_sec)
        print(token)
        print(json.dumps({k: v for k, v in payload.items() if k != "token_sha256"}, ensure_ascii=False))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
