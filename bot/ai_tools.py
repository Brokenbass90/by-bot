"""Unified on-board-AI toolbox — the AI's eyes, ears and analysis in one place.

Consolidates the scattered read/analysis capabilities behind ONE interface so
Codex can wire the on-board AI (Telegram + web) coherently, and the AI knows
exactly what it can do. This is what turns the AI from a chat toy into an
analyst: full awareness (state + config + code) + structured analysis hooks.

What it does NOT do: act/trade/write. Influence on the system goes through the
existing human-in-the-loop proposal pipeline (bot.deepseek_action_executor:
propose -> human /ai_deploy -> patch env -> deploy, with backups & rollback).
This module is strictly READ/ANALYSE; the write path stays gated by a human.

Pure stdlib + project modules. Safe (code reads go through bot.code_access,
live state is the already-redacted snapshot).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


# ---- awareness: live state -------------------------------------------------
def get_live_snapshot() -> Dict[str, Any]:
    """Latest redacted server snapshot (heartbeat, regime, pnl, config, events)."""
    p = REPORTS / "SERVER_SNAPSHOT_latest.json"
    if not p.exists():
        return {"_error": "no snapshot; run scripts/export_server_snapshot.py on server"}
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:
        return {"_error": str(e)}


def get_pulse() -> str:
    """One-screen honest status digest (alive/protected/live-vs-shadow/pnl)."""
    try:
        from scripts.proof_of_life import build_digest  # type: ignore
        snap = get_live_snapshot()
        return build_digest(snap) if "_error" not in snap else snap["_error"]
    except Exception as e:
        return f"pulse unavailable: {e}"


# ---- awareness: strategy config + TP/SL model ------------------------------
def get_strategy_catalog() -> Dict[str, Any]:
    from bot.strategy_catalog import build_strategy_catalog
    return build_strategy_catalog()


# ---- awareness: code (map + on-demand read) --------------------------------
def get_codemap() -> Dict[str, Any]:
    p = REPORTS / "AI_CODEMAP.json"
    if not p.exists():
        return {"_error": "no codemap; run scripts/build_ai_codemap.py"}
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:
        return {"_error": str(e)}


def read_code(relpath: str) -> str:
    from bot.code_access import read_source, CodeAccessError
    try:
        return read_source(relpath)
    except CodeAccessError as e:
        return f"refused: {e}"


def search_code(pattern: str, subdir: str = "strategies") -> List[str]:
    from bot.code_access import grep_sources, CodeAccessError
    try:
        return grep_sources(pattern, subdir)
    except CodeAccessError as e:
        return [f"refused: {e}"]


def list_modules(subdir: str = "strategies") -> List[str]:
    from bot.code_access import list_sources, CodeAccessError
    try:
        return list_sources(subdir)
    except CodeAccessError as e:
        return [f"refused: {e}"]


# ---- manifest: what the AI can do ------------------------------------------
def available_tools() -> List[Dict[str, str]]:
    """Self-describing tool list so the AI knows its own capabilities."""
    return [
        {"name": "get_pulse", "kind": "read", "desc": "honest live status digest"},
        {"name": "get_live_snapshot", "kind": "read", "desc": "full redacted server snapshot"},
        {"name": "get_strategy_catalog", "kind": "read", "desc": "strategy config + TP/SL model"},
        {"name": "get_codemap", "kind": "read", "desc": "map of all code modules + purpose"},
        {"name": "read_code", "kind": "read", "desc": "read one source file (secret-safe)"},
        {"name": "search_code", "kind": "read", "desc": "grep code for a pattern"},
        {"name": "list_modules", "kind": "read", "desc": "list source files in a dir"},
        {"name": "propose_change", "kind": "write(gated)",
         "desc": "via bot.deepseek_action_executor: proposal -> HUMAN /ai_deploy -> patch+deploy"},
    ]
