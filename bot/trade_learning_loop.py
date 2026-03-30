"""
bot/trade_learning_loop.py — bounded per-trade learning loop
============================================================

Purpose:
  - persist a lightweight record for each closed trade review
  - classify recurring failure/success patterns
  - emit bounded proposal candidates when the same pattern repeats often enough

This module is intentionally conservative:
  - it does not mutate live config
  - it does not launch research
  - it only accumulates evidence and suggests proposals for approval
"""
from __future__ import annotations

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LOG_PATH = DATA_DIR / "trade_learning_log.jsonl"
STATE_PATH = ROOT / "configs" / "trade_learning_state.json"

LEARNING_ENABLE = str(os.getenv("TRADE_LEARNING_ENABLE", "1")).strip().lower() not in {"0", "false", "no", "off"}
WINDOW_DAYS = int(float(os.getenv("TRADE_LEARNING_WINDOW_DAYS", "14") or 14))
PATTERN_THRESHOLD = int(float(os.getenv("TRADE_LEARNING_PATTERN_THRESHOLD", "3") or 3))
COOLDOWN_HOURS = int(float(os.getenv("TRADE_LEARNING_PROPOSAL_COOLDOWN_HOURS", "24") or 24))
MAX_RECENT_SCAN = int(float(os.getenv("TRADE_LEARNING_MAX_RECENT_SCAN", "300") or 300))


def _now() -> int:
    return int(time.time())


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _iter_recent_entries() -> list[dict[str, Any]]:
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-MAX_RECENT_SCAN:]:
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def _classify(payload: dict[str, Any]) -> list[str]:
    tags: list[str] = []
    pnl = _safe_float(payload.get("pnl_closed"))
    fees = abs(_safe_float(payload.get("fees")))
    r_mult = payload.get("r_mult")
    r_val = _safe_float(r_mult) if r_mult is not None else None
    hold_sec = int(payload.get("hold_sec") or 0)
    close_reason = str(payload.get("close_reason") or "").upper()
    verdict = str(payload.get("verdict") or "")

    if fees > 0 and pnl > 0 and fees >= max(0.02, pnl * 0.20):
        tags.append("fee_drag")
    if "SL" in close_reason and hold_sec <= 45 * 60:
        tags.append("fast_stop")
    if "TIME_STOP" in close_reason and pnl <= 0:
        tags.append("timeout_stall")
    if verdict == "loss_review" and pnl < 0:
        tags.append("unstructured_loss")
    if r_val is not None and pnl > 0 and r_val < 0.50:
        tags.append("underrealized_win")
    if r_val is not None and pnl > 0 and r_val >= 1.00 and "TP" in close_reason:
        tags.append("clean_tp")
    if pnl < 0 and fees > abs(pnl) * 0.10:
        tags.append("loss_plus_fee_drag")
    return tags


def _build_proposal(strategy: str, tag: str, count: int, samples: list[dict[str, Any]]) -> dict[str, Any]:
    symbol_counts = Counter(str(x.get("symbol") or "") for x in samples if x.get("symbol"))
    reason_counts = Counter(str(x.get("close_reason") or "") for x in samples if x.get("close_reason"))
    top_symbols = [sym for sym, _ in symbol_counts.most_common(3)]
    top_reasons = [reason for reason, _ in reason_counts.most_common(3)]
    summary = f"{strategy}: repeated pattern `{tag}` seen {count}x over last {WINDOW_DAYS}d"
    payload = {
        "kind": "trade_learning",
        "strategy": strategy,
        "pattern": tag,
        "count": count,
        "window_days": WINDOW_DAYS,
        "top_symbols": top_symbols,
        "top_close_reasons": top_reasons,
        "suggested_action": _suggest_action(strategy, tag),
    }
    return {"summary": summary, "payload": payload}


def _suggest_action(strategy: str, tag: str) -> str:
    if tag == "fast_stop":
        return f"Review entry quality / confirmation logic for {strategy}; avoid immediate stop-outs."
    if tag == "timeout_stall":
        return f"Review time stop or take-profit density for {strategy}; trades are not resolving productively."
    if tag == "underrealized_win":
        return f"Review partial take-profit / trail settings for {strategy}; winners are being cut too early."
    if tag == "fee_drag":
        return f"Review minimum expected move / cooldown / symbol pocket for {strategy}; fees are eating edge."
    if tag == "loss_plus_fee_drag":
        return f"Review weak-market suitability for {strategy}; losses and fees are compounding."
    return f"Review bounded research path for recurring pattern `{tag}` in {strategy}."


class TradeLearningLoop:
    def record(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not LEARNING_ENABLE:
            return None
        strategy = str(payload.get("strategy") or "").strip()
        if not strategy:
            return None
        entry = dict(payload)
        entry["logged_ts"] = _now()
        entry["tags"] = _classify(payload)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        proposal = self._maybe_raise_proposal(entry)
        return {"entry": entry, "proposal": proposal}

    def _maybe_raise_proposal(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        tags = list(entry.get("tags") or [])
        if not tags:
            return None
        now_ts = _now()
        cutoff = now_ts - WINDOW_DAYS * 86400
        recent = [x for x in _iter_recent_entries() if int(x.get("logged_ts") or 0) >= cutoff]
        state = _load_state()
        proposals_state = state.setdefault("last_proposals", {})
        strategy = str(entry.get("strategy") or "")

        for tag in tags:
            samples = [x for x in recent if str(x.get("strategy") or "") == strategy and tag in list(x.get("tags") or [])]
            count = len(samples)
            if count < PATTERN_THRESHOLD:
                continue
            key = f"{strategy}:{tag}"
            last_ts = int(proposals_state.get(key) or 0)
            if now_ts - last_ts < COOLDOWN_HOURS * 3600:
                continue
            proposals_state[key] = now_ts
            _save_state(state)
            return _build_proposal(strategy, tag, count, samples)
        return None

    def status_text(self) -> str:
        recent = _iter_recent_entries()
        if not recent:
            return "Trade learning: пока нет закрытых сделок после включения модуля."
        recent = recent[-MAX_RECENT_SCAN:]
        tag_counts = Counter()
        strat_counts = Counter()
        for item in recent:
            strat = str(item.get("strategy") or "")
            if strat:
                strat_counts[strat] += 1
            for tag in list(item.get("tags") or []):
                tag_counts[str(tag)] += 1
        lines = [
            "Trade learning status:",
            f"- logged trades: {len(recent)}",
        ]
        if strat_counts:
            lines.append("- strategies: " + ", ".join(f"{k}={v}" for k, v in strat_counts.most_common(5)))
        if tag_counts:
            lines.append("- top tags: " + ", ".join(f"{k}={v}" for k, v in tag_counts.most_common(6)))
        state = _load_state().get("last_proposals", {})
        if state:
            lines.append(f"- proposal cooldown entries: {len(state)}")
        return "\n".join(lines)


trade_learning = TradeLearningLoop()
