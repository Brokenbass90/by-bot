"""AI Chat — Anthropic Claude with full bot context injection and safe control commands.

The AI sees:
  - Current regime, confidence, risk mult
  - All allocator sleeves and their status
  - Last 50 trades + strategy performance summary
  - Strategy health
  - Bot heartbeat / liveness
  - Alpaca monthly picks and metrics

Safe control commands the AI can request (user must confirm, then they execute):
  - enable_sleeve   / disable_sleeve
  - set_safe_mode   / clear_safe_mode
  - reload_config

All executed commands are written to runtime/web_audit_log.jsonl.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..deps import require_admin

router = APIRouter(prefix="/api/ai", tags=["ai"])

_ROOT = Path(__file__).parent.parent.parent
_AUDIT_LOG = _ROOT / "runtime" / "web_audit_log.jsonl"
_OVERLAY_ENV = _ROOT / "configs" / "web_control_overlay.env"
_CHAT_RATE: Dict[str, List[float]] = {}  # email → list of timestamps
_MAX_RPM = 20  # requests per minute per user


def _rt(*p: str) -> Path:
    return _ROOT / "runtime" / Path(*p)


def _cfg(*p: str) -> Path:
    return _ROOT / "configs" / Path(*p)


def _json(p: Path) -> Optional[dict]:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _read_env(p: Path) -> Dict[str, str]:
    result = {}
    if not p.exists():
        return result
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


# ── Rate limiter ──────────────────────────────────────────────────────────────

def _check_rate(email: str) -> None:
    now = time.time()
    times = [t for t in _CHAT_RATE.get(email, []) if now - t < 60]
    if len(times) >= _MAX_RPM:
        raise HTTPException(status_code=429, detail="Rate limit: max 20 messages/minute")
    times.append(now)
    _CHAT_RATE[email] = times


# ── Context builder ───────────────────────────────────────────────────────────

def _build_context() -> str:
    """Build a compact context string injected into every AI request."""
    parts: List[str] = []
    now = datetime.now(timezone.utc).isoformat()
    parts.append(f"=== BOT CONTEXT [{now}] ===\n")

    # Bot liveness
    hb = _json(_rt("bot_heartbeat.json"))
    hb_path = _rt("bot_heartbeat.json")
    alive = hb_path.exists() and (time.time() - hb_path.stat().st_mtime) < 120
    parts.append(f"BOT: {'ALIVE' if alive else 'OFFLINE'} | open_trades={hb.get('open_trades',0) if hb else 0}\n")

    # Regime
    reg = _json(_rt("regime", "orchestrator_state.json")) or _json(_rt("regime.json"))
    if reg:
        parts.append(
            f"REGIME: {reg.get('regime','?')} conf={reg.get('confidence','?')} "
            f"risk_mult={reg.get('global_risk_mult','?')} "
            f"longs={'Y' if reg.get('allow_longs') else 'N'} shorts={'Y' if reg.get('allow_shorts') else 'N'}\n"
        )

    # Allocator sleeves: always prefer runtime control-plane truth over static policy.
    allocator = _json(_rt("control_plane", "portfolio_allocator_state.json")) or {}
    sleeve_states = dict(allocator.get("sleeves") or {})
    if sleeve_states:
        active = sorted(
            [
                str(name)
                for name, state in sleeve_states.items()
                if bool((state or {}).get("enabled"))
                and float((state or {}).get("final_risk_mult") or 0.0) > 0.0
            ]
        )
        inactive = sorted(
            [
                str(name)
                for name, state in sleeve_states.items()
                if not (
                    bool((state or {}).get("enabled"))
                    and float((state or {}).get("final_risk_mult") or 0.0) > 0.0
                )
            ]
        )
        parts.append(
            f"ALLOCATOR: status={allocator.get('status','?')} "
            f"global_risk={allocator.get('allocator_global_risk_mult', allocator.get('global_risk_mult','?'))}\n"
        )
        parts.append(f"SLEEVES ACTIVE: {', '.join(active) or 'none'}\n")
        parts.append(f"SLEEVES OFF: {', '.join(inactive[:8]) or 'none'}\n")

    # Control overlay (web-applied commands)
    overlay = _read_env(_OVERLAY_ENV)
    if overlay:
        parts.append(f"WEB OVERLAY: {json.dumps(overlay)}\n")

    # Recent trades summary
    trades_path = None
    for p in sorted(_ROOT.glob("runtime/**/trades.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        trades_path = p
        break
    if trades_path:
        import csv
        rows = []
        try:
            with open(trades_path) as f:
                rows = list(csv.DictReader(f))
        except Exception:
            pass
        rows = rows[-50:]  # last 50
        if rows:
            wins = sum(1 for r in rows if float(r.get("pnl", 0) or 0) > 0)
            losses = sum(1 for r in rows if float(r.get("pnl", 0) or 0) < 0)
            net = sum(float(r.get("pnl", 0) or 0) for r in rows)
            strats = list({r.get("strategy", "?") for r in rows})[:6]
            parts.append(f"LAST 50 TRADES: wins={wins} losses={losses} net={net:.4f}\n")
            parts.append(f"ACTIVE STRATEGIES: {', '.join(strats)}\n")

    # Alpaca
    import csv as _csv
    alpaca_picks = []
    picks_path = _rt("equities_monthly_v36", "current_cycle_picks.csv")
    if picks_path.exists():
        try:
            with open(picks_path) as f:
                alpaca_picks = [r["ticker"] for r in _csv.DictReader(f) if r.get("ticker")]
        except Exception:
            pass
    if alpaca_picks:
        parts.append(f"ALPACA PICKS: {', '.join(alpaca_picks)}\n")

    # Health
    health = _json(_rt("strategy_health.json"))
    if health:
        statuses = {k: v.get("status", "?") for k, v in health.items() if isinstance(v, dict)}
        bad = [f"{k}={v}" for k, v in statuses.items() if v not in ("OK", "ok")]
        if bad:
            parts.append(f"HEALTH ALERTS: {', '.join(bad[:5])}\n")

    parts.append(
        "\n=== AVAILABLE CONTROL COMMANDS ===\n"
        "You can suggest control actions. The user will confirm before execution.\n"
        "To suggest a command, include a JSON block: ```command\n{\"action\": \"...\", \"params\": {...}}\n```\n"
        "Available actions:\n"
        "  enable_sleeve   {\"sleeve\": \"asb1\"}          — set sleeve multipliers active\n"
        "  disable_sleeve  {\"sleeve\": \"ivb1\"}          — zero out sleeve risk mults\n"
        "  set_safe_mode   {}                             — set global risk mult to 0.25\n"
        "  clear_safe_mode {}                             — restore normal risk mult\n"
        "  reload_config   {}                             — trigger bot hot-reload\n"
        "  add_user        {\"email\": \"x@y.com\"}         — pre-create user slot (no TOTP yet)\n"
        "  remove_user     {\"email\": \"x@y.com\"}         — revoke web access\n"
    )

    return "".join(parts)


# ── Control command executor ──────────────────────────────────────────────────

_VALID_SLEEVE_NAMES = {
    "breakout", "breakdown", "flat", "sloped", "att1", "asm1",
    "midterm", "midterm_short", "midterm_short_v2", "range_scalp",
    "asb1", "hzbo1", "bounce1", "impulse", "pump_fade",
    "elder_ts", "elder_ts_v3", "vwap_mr",
}

_ENABLE_ENV_MAP = {
    "breakout": "ENABLE_BREAKOUT_TRADING", "breakdown": "ENABLE_BREAKDOWN_TRADING",
    "flat": "ENABLE_FLAT_TRADING", "sloped": "ENABLE_SLOPED_TRADING",
    "att1": "ENABLE_ATT1_TRADING", "asm1": "ENABLE_ASM1_TRADING",
    "midterm": "ENABLE_MIDTERM_TRADING", "midterm_short": "ENABLE_MTSV1_TRADING",
    "midterm_short_v2": "ENABLE_MTSV2_TRADING", "range_scalp": "ENABLE_RANGE_TRADING",
    "asb1": "ENABLE_ASB1_TRADING", "hzbo1": "ENABLE_HZBO1_TRADING",
    "bounce1": "ENABLE_BOUNCE1_TRADING", "impulse": "ENABLE_IVB1_TRADING",
    "pump_fade": "ENABLE_PUMP_FADE_TRADING", "elder_ts": "ENABLE_ELDER_TRADING",
    "elder_ts_v3": "ENABLE_ETS3_TRADING", "vwap_mr": "ENABLE_VWAP_TRADING",
}


def _write_overlay(updates: Dict[str, str]) -> None:
    """Merge updates into the web control overlay env file."""
    existing = _read_env(_OVERLAY_ENV)
    existing.update(updates)
    _OVERLAY_ENV.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in sorted(existing.items())]
    _OVERLAY_ENV.write_text("\n".join(lines) + "\n")


def _audit(email: str, action: str, params: dict, result: str) -> None:
    _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "user": email,
        "action": action,
        "params": params,
        "result": result,
    }
    with open(_AUDIT_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def execute_command(action: str, params: dict, email: str) -> str:
    """Execute a confirmed control command. Returns result message."""
    if action == "enable_sleeve":
        sleeve = params.get("sleeve", "").lower()
        if sleeve not in _VALID_SLEEVE_NAMES:
            return f"Unknown sleeve: {sleeve}"
        env_key = _ENABLE_ENV_MAP.get(sleeve)
        if env_key:
            _write_overlay({env_key: "1"})
        _audit(email, action, params, f"enabled {sleeve}")
        return f"✓ Sleeve '{sleeve}' enabled in overlay. Bot will pick up on next reload."

    elif action == "disable_sleeve":
        sleeve = params.get("sleeve", "").lower()
        if sleeve not in _VALID_SLEEVE_NAMES:
            return f"Unknown sleeve: {sleeve}"
        env_key = _ENABLE_ENV_MAP.get(sleeve)
        if env_key:
            _write_overlay({env_key: "0"})
        _audit(email, action, params, f"disabled {sleeve}")
        return f"✓ Sleeve '{sleeve}' disabled in overlay."

    elif action == "set_safe_mode":
        _write_overlay({"WEB_SAFE_MODE": "1", "PORTFOLIO_GLOBAL_RISK_MULT": "0.25"})
        _audit(email, action, params, "safe_mode=ON risk=0.25")
        return "⚠️ Safe mode ON — global risk mult set to 0.25×."

    elif action == "clear_safe_mode":
        _write_overlay({"WEB_SAFE_MODE": "0", "PORTFOLIO_GLOBAL_RISK_MULT": "1.0"})
        _audit(email, action, params, "safe_mode=OFF")
        return "✓ Safe mode cleared — risk back to normal."

    elif action == "reload_config":
        # Send SIGHUP to bot process if PID file exists
        pid_path = _rt("bot.pid")
        if pid_path.exists():
            try:
                import signal
                pid = int(pid_path.read_text().strip())
                os.kill(pid, signal.SIGHUP)
                _audit(email, action, params, f"SIGHUP sent to pid {pid}")
                return f"✓ SIGHUP sent to bot (PID {pid}) — config will reload."
            except Exception as e:
                return f"Could not send SIGHUP: {e}"
        _audit(email, action, params, "no pid file")
        return "PID file not found — restart bot manually to apply overlay."

    elif action == "add_user":
        # Pre-create user slot without TOTP (they run setup_totp.py separately)
        from ..auth import _load_config, _save_config
        target_email = params.get("email", "").strip().lower()
        if not target_email or "@" not in target_email:
            return "Invalid email."
        cfg = _load_config()
        cfg.setdefault("users", {})[target_email] = {"enabled": False, "note": "pending_totp_setup"}
        _save_config(cfg)
        _audit(email, action, params, f"added slot for {target_email}")
        return f"✓ User slot created for {target_email}. They must run setup_totp.py to activate."

    elif action == "remove_user":
        from ..auth import _load_config, _save_config
        target_email = params.get("email", "").strip().lower()
        if target_email == email:
            return "Cannot remove yourself."
        cfg = _load_config()
        if target_email in cfg.get("users", {}):
            del cfg["users"][target_email]
            _save_config(cfg)
            _audit(email, action, params, f"removed {target_email}")
            return f"✓ User {target_email} removed."
        return f"User {target_email} not found."

    else:
        return f"Unknown action: {action}"


# ── Models ────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    execute_command: Optional[Dict[str, Any]] = None  # confirmed command to run


class ChatResponse(BaseModel):
    reply: str
    suggested_command: Optional[Dict[str, Any]] = None
    command_result: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, email: str = Depends(require_admin)):
    """Send a message to the AI with full bot context.

    If body.execute_command is set, execute that command first, then send chat.
    """
    _check_rate(email)

    # Execute a confirmed command first if provided
    cmd_result = None
    if body.execute_command:
        action = body.execute_command.get("action", "")
        params = body.execute_command.get("params", {})
        cmd_result = execute_command(action, params, email)

    # ── pick AI provider: DeepSeek > Anthropic ───────────────────────────────
    deepseek_key  = os.getenv("DEEPSEEK_API_KEY", "").strip()
    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("AI_API_KEY", "")).strip()

    if not deepseek_key and not anthropic_key:
        return ChatResponse(
            reply=(
                "⚠️ AI не настроен. Добавь в .env файл:\n"
                "  DEEPSEEK_API_KEY=sk-...    (дешевле, рекомендуется)\n"
                "  или ANTHROPIC_API_KEY=sk-ant-...\n"
                "Затем перезапусти сервер."
            ),
            command_result=cmd_result,
        )

    system_prompt = (
        "You are an AI assistant embedded in a cryptocurrency + equities trading bot dashboard. "
        "You help the operator understand performance, diagnose issues, and manage the system. "
        "You have access to live bot data (injected below). "
        "Be concise and precise. When you spot issues, say so directly. "
        "When suggesting control commands, emit a ```command JSON block. "
        "Never suggest actions that could cause significant losses without clear justification. "
        "Always explain the reason for any control command you suggest.\n\n"
        + _build_context()
    )
    messages_payload = [{"role": m.role, "content": m.content} for m in body.messages[-20:]]

    try:
        if deepseek_key:
            # ── DeepSeek (OpenAI-compatible API) ─────────────────────────────
            import urllib.request as _urllib_req
            import ssl as _ssl

            model = os.getenv("WEB_AI_MODEL", "deepseek-chat")
            payload = json.dumps({
                "model": model,
                "max_tokens": 1500,
                "temperature": 0.4,
                "messages": [{"role": "system", "content": system_prompt}] + messages_payload,
            }).encode()
            req = _urllib_req.Request(
                "https://api.deepseek.com/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {deepseek_key}",
                },
            )
            ctx = _ssl.create_default_context()
            with _urllib_req.urlopen(req, context=ctx, timeout=60) as resp:
                js = json.loads(resp.read().decode())
            reply_text = js["choices"][0]["message"]["content"].strip()

        else:
            # ── Anthropic Claude ──────────────────────────────────────────────
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            model = os.getenv("WEB_AI_MODEL", "claude-sonnet-4-6")
            response = client.messages.create(
                model=model,
                max_tokens=1500,
                system=system_prompt,
                messages=messages_payload,
            )
            reply_text = response.content[0].text

        # Parse suggested command from reply if any
        suggested_cmd = None
        import re
        cmd_match = re.search(r"```command\s*\n(\{.*?\})\s*\n```", reply_text, re.DOTALL)
        if cmd_match:
            try:
                suggested_cmd = json.loads(cmd_match.group(1))
            except Exception:
                pass

        return ChatResponse(
            reply=reply_text,
            suggested_command=suggested_cmd,
            command_result=cmd_result,
        )

    except Exception as e:
        return ChatResponse(
            reply=f"AI error: {str(e)[:200]}",
            command_result=cmd_result,
        )


@router.get("/audit")
async def get_audit(email: str = Depends(require_admin)):
    """Recent command audit log."""
    if not _AUDIT_LOG.exists():
        return {"entries": []}
    entries = []
    for line in _AUDIT_LOG.read_text().splitlines()[-50:]:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return {"entries": list(reversed(entries))}


@router.get("/context")
async def get_context(email: str = Depends(require_admin)):
    """Return the current context that gets injected into AI. Useful for debugging."""
    return {"context": _build_context()}
