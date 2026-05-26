#!/usr/bin/env python3
"""
scripts/monitor.py — Operator health dashboard for the live crypto bot.

Complements server_status.sh with:
  • Per-sleeve health gate status (OK / WATCH / PAUSE / KILL)
  • Log error scanner — unique error patterns from the last hour
  • Exit code 0 = healthy, 1 = degraded, 2 = critical (for cron alerting)

Usage:
  # On the server directly:
  python3 scripts/monitor.py

  # From local machine via SSH (reads ~/.ssh/by-bot key by default):
  SERVER_IP=64.226.73.119 python3 scripts/monitor.py --ssh

  # Pipe-friendly compact output:
  python3 scripts/monitor.py --compact

  # JSON output for programmatic use:
  python3 scripts/monitor.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Colour helpers ─────────────────────────────────────────────────────────
NO_COLOR = not sys.stdout.isatty() or os.getenv("NO_COLOR")

def _c(code: str, text: str) -> str:
    if NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"

RED    = lambda t: _c("31", t)
GREEN  = lambda t: _c("32", t)
YELLOW = lambda t: _c("33", t)
BLUE   = lambda t: _c("34", t)
CYAN   = lambda t: _c("36", t)
BOLD   = lambda t: _c("1",  t)
DIM    = lambda t: _c("2",  t)

def ok(msg: str) -> str:    return f"  {GREEN('✅')} {msg}"
def warn(msg: str) -> str:  return f"  {YELLOW('⚠️')} {msg}"
def err(msg: str) -> str:   return f"  {RED('❌')} {msg}"
def info(msg: str) -> str:  return f"     {DIM(msg)}"


# ── Constants ──────────────────────────────────────────────────────────────
BOT_DIR     = Path(os.getenv("BOT_DIR", "/root/by-bot"))
SERVICE     = os.getenv("SERVICE_NAME", "bybot")
LOG_HOURS   = 1          # scan last N hours of logs for errors
MAX_ERRORS  = 6          # max unique error patterns to display
HB_STALE    = 90         # heartbeat age (sec) to flag as stale
HB_WARN     = 30         # heartbeat warn threshold
HEALTH_STALE = 48 * 3600 # health snapshot older than 48h is informational only


# ── File readers ──────────────────────────────────────────────────────────
def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _file_age(path: Path) -> int | None:
    try:
        return int(time.time() - path.stat().st_mtime)
    except Exception:
        return None


# ── Section collectors ────────────────────────────────────────────────────
def section_bot() -> tuple[list[str], int]:
    """Service + heartbeat. Returns (lines, severity 0=ok 1=warn 2=crit)."""
    lines: list[str] = []
    severity = 0

    # systemd / screen
    try:
        r = subprocess.run(
            ["systemctl", "is-active", SERVICE],
            capture_output=True, text=True, timeout=5
        )
        active = r.stdout.strip() == "active"
    except Exception:
        active = False

    if active:
        lines.append(ok(f"systemd service '{SERVICE}': RUNNING"))
    else:
        # Fallback: check screen session
        try:
            r2 = subprocess.run(
                ["screen", "-list"], capture_output=True, text=True, timeout=5
            )
            if "bot" in r2.stdout.lower():
                lines.append(warn(f"service '{SERVICE}': NOT systemd — running in screen"))
                severity = max(severity, 1)
            else:
                lines.append(err(f"service '{SERVICE}': NOT RUNNING"))
                severity = max(severity, 2)
        except Exception:
            lines.append(err(f"service '{SERVICE}': NOT RUNNING (systemctl failed)"))
            severity = max(severity, 2)

    # Heartbeat
    hb_path = BOT_DIR / "runtime" / "bot_heartbeat.json"
    hb = _read_json(hb_path)
    if hb is None:
        lines.append(err("heartbeat: file missing"))
        severity = max(severity, 2)
    else:
        ts  = int(hb.get("ts", 0) or 0)
        age = int(time.time()) - ts if ts else 9999
        uptime_s = int(hb.get("uptime_s", 0) or 0)
        uptime   = f"{uptime_s//3600}h{(uptime_s%3600)//60:02d}m"
        open_t   = hb.get("open_trades", "?")
        ws       = hb.get("ws_guard_active", "?")
        regime   = hb.get("regime", "?")
        tag = f"age={age}s  uptime={uptime}  open_trades={open_t}  ws={ws}  regime={regime}"
        if age < HB_WARN:
            lines.append(ok(f"heartbeat: FRESH  {tag}"))
        elif age < HB_STALE:
            lines.append(warn(f"heartbeat: SLOW   {tag}"))
            severity = max(severity, 1)
        else:
            lines.append(err(f"heartbeat: STALE  {tag}"))
            severity = max(severity, 2)

    return lines, severity


def section_regime() -> tuple[list[str], int]:
    lines: list[str] = []
    severity = 0

    path = BOT_DIR / "runtime" / "regime" / "orchestrator_state.json"
    age  = _file_age(path)
    d    = _read_json(path)

    if d is None:
        lines.append(err("regime state: file missing"))
        return lines, 2

    regime     = d.get("regime", "?")
    conf       = d.get("confidence", 0.0)
    pending    = d.get("pending_regime", "?")
    pcount     = d.get("pending_count", "?")
    ts_str     = d.get("timestamp_utc", "?")
    age_str    = f"{age}s" if age is not None else "?"

    tag = f"regime={BOLD(regime)}  conf={conf:.2f}  pending={pending}({pcount}/3)  age={age_str}"

    if age is not None and age > 7200:
        lines.append(err(f"regime: STALE  {tag}"))
        severity = 2
    elif age is not None and age > 3600:
        lines.append(warn(f"regime: OLD    {tag}"))
        severity = 1
    else:
        lines.append(ok(f"regime: OK     {tag}"))

    return lines, severity


def section_sleeves() -> tuple[list[str], int]:
    """Per-strategy health gate status."""
    lines: list[str] = []
    severity = 0

    health_path = BOT_DIR / "configs" / "strategy_health.json"
    d = _read_json(health_path)
    if d is None:
        lines.append(warn("strategy_health.json: not found (gate running on defaults)"))
        return lines, 1

    overall = d.get("overall_health", "?")
    ts      = d.get("timestamp", "?")
    strats  = d.get("strategies") or {}
    age     = _file_age(health_path)
    stale   = age is None or age > HEALTH_STALE

    if stale:
        age_str = f"{age}s" if age is not None else "unknown"
        lines.append(warn(
            f"strategy_health.json: STALE age={age_str}; sleeve statuses below are historical only"
        ))
        severity = max(severity, 1)

    STATUS_COLOR = {
        "OK":    GREEN,
        "WATCH": YELLOW,
        "PAUSE": RED,
        "KILL":  RED,
    }

    for name, info_d in strats.items():
        status = str(info_d.get("status", "?")).upper()
        col    = STATUS_COLOR.get(status, DIM)
        short  = name.replace("alt_", "").replace("_v1", "").replace("btc_eth_", "")
        tag    = f"{col(status):30s}  {DIM(short)}"
        if stale:
            lines.append(info(f"sleeve {status:30s}  {short}  (historical snapshot)"))
        elif status in ("PAUSE", "KILL"):
            lines.append(err(f"sleeve {tag}"))
            severity = max(severity, 2)
        elif status == "WATCH":
            lines.append(warn(f"sleeve {tag}"))
            severity = max(severity, 1)
        else:
            lines.append(ok(f"sleeve {tag}"))

    lines.append(info(f"overall_health={overall}  updated={ts}  stale={int(stale)}"))
    return lines, severity


def section_control_plane() -> tuple[list[str], int]:
    """Check key control plane files are fresh."""
    lines: list[str] = []
    severity = 0

    FILES = [
        ("Regime state",    BOT_DIR / "runtime" / "regime" / "orchestrator_state.json",          7200),
        ("Regime env",      BOT_DIR / "configs"  / "regime_orchestrator_latest.env",             7200),
        ("Router state",    BOT_DIR / "runtime" / "router" / "symbol_router_state.json",        28800),
        ("Allocator state", BOT_DIR / "runtime" / "control_plane" / "portfolio_allocator_state.json", 10800),
        ("Allocator env",   BOT_DIR / "configs"  / "portfolio_allocator_latest.env",            10800),
        ("Geometry state",  BOT_DIR / "runtime" / "geometry" / "geometry_state.json",            21600),
    ]

    for label, path, max_age in FILES:
        age = _file_age(path)
        if age is None:
            lines.append(err(f"{label}: MISSING"))
            severity = max(severity, 2)
        elif age > max_age:
            lines.append(err(f"{label}: STALE  age={age}s  max={max_age}s"))
            severity = max(severity, 2)
        elif age > max_age * 0.75:
            lines.append(warn(f"{label}: OLD    age={age}s  max={max_age}s"))
            severity = max(severity, 1)
        else:
            lines.append(ok(f"{label}: OK     age={age}s"))

    # Allocator degraded / safe_mode check
    alloc_path = BOT_DIR / "runtime" / "control_plane" / "portfolio_allocator_state.json"
    alloc = _read_json(alloc_path)
    if alloc:
        degraded  = bool(alloc.get("degraded", False))
        safe_mode = bool(alloc.get("safe_mode", False))
        risk_mult = alloc.get("allocator_global_risk_mult", alloc.get("global_risk_mult", "?"))
        tag = f"degraded={int(degraded)}  safe_mode={int(safe_mode)}  risk_mult={risk_mult}"
        if safe_mode or degraded:
            lines.append(warn(f"allocator: DEGRADED  {tag}"))
            severity = max(severity, 1)
        else:
            lines.append(info(f"allocator: {tag}"))

    return lines, severity


def section_log_errors() -> tuple[list[str], int]:
    """Grep recent bot log for ERROR / CRITICAL / Traceback patterns."""
    lines: list[str] = []
    severity = 0

    log_path = BOT_DIR / "runtime" / "live.out"
    since_sec = LOG_HOURS * 3600
    require_timestamp = False

    if not log_path.exists():
        # Try journalctl
        try:
            r = subprocess.run(
                ["journalctl", "-u", SERVICE, f"--since={LOG_HOURS}h ago",
                 "--no-pager", "-q"],
                capture_output=True, text=True, timeout=10
            )
            raw_lines = r.stdout.splitlines()
        except Exception:
            lines.append(warn("log: live.out missing; journalctl unavailable"))
            return lines, 0
    else:
        require_timestamp = True
        # Read last N bytes to avoid reading whole file
        try:
            stat = log_path.stat()
            offset = max(0, stat.st_size - 2 * 1024 * 1024)  # last 2MB
            with open(log_path, "rb") as f:
                f.seek(offset)
                content = f.read().decode("utf-8", errors="replace")
            raw_lines = content.splitlines()
        except Exception as exc:
            lines.append(warn(f"log: read error ({exc})"))
            return lines, 0

    # Filter to last LOG_HOURS by line timestamp
    now_ts = time.time()
    cutoff_ts = now_ts - since_sec

    def _line_ts(line: str) -> float | None:
        # Match ISO timestamps like 2026-05-25T14:23:01 or 2026-05-25 14:23:01
        m = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", line)
        if not m:
            return None
        try:
            dt = datetime.fromisoformat(m.group(1).replace(" ", "T"))
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            return None

    ERROR_PATTERNS = re.compile(
        r"(ERROR|CRITICAL|Traceback \(most recent|Exception:|raise |EXCEPTION|NoneType|ConnectionError|TimeoutError)",
        re.IGNORECASE
    )
    IGNORE_PATTERNS = re.compile(
        r"(heartbeat|DEBUG|routine|retry succeeded)",
        re.IGNORECASE
    )

    error_lines: list[str] = []
    recent_total = 0
    undated_skipped = 0
    for line in raw_lines:
        ts = _line_ts(line)
        if require_timestamp and ts is None:
            undated_skipped += 1
            continue
        if ts is not None and ts < cutoff_ts:
            continue
        recent_total += 1
        if ERROR_PATTERNS.search(line) and not IGNORE_PATTERNS.search(line):
            error_lines.append(line.strip())

    # Deduplicate by fingerprint (remove timestamps + addresses for grouping)
    def _fingerprint(line: str) -> str:
        line = re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[.,]\d*", "", line)
        line = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", line)
        line = re.sub(r"\d{10,}", "TS", line)
        line = re.sub(r"\s+", " ", line)
        return line[:120]

    seen: dict[str, str] = {}
    for line in error_lines:
        fp = _fingerprint(line)
        if fp not in seen:
            seen[fp] = line

    unique = list(seen.values())
    count  = len(error_lines)

    if count == 0:
        lines.append(ok(f"log errors (last {LOG_HOURS}h): 0 — clean"))
    elif count < 5:
        lines.append(warn(f"log errors (last {LOG_HOURS}h): {count} occurrences, {len(unique)} unique"))
        severity = max(severity, 1)
    else:
        lines.append(err(f"log errors (last {LOG_HOURS}h): {count} occurrences, {len(unique)} unique"))
        severity = max(severity, 2)

    for i, line in enumerate(unique[:MAX_ERRORS]):
        truncated = (line[:140] + "…") if len(line) > 140 else line
        lines.append(info(f"  [{i+1}] {RED(truncated) if count >= 5 else YELLOW(truncated)}"))

    suffix = f"; skipped {undated_skipped} undated file lines" if undated_skipped else ""
    lines.append(info(f"(scanned {recent_total} log lines from last {LOG_HOURS}h{suffix})"))
    return lines, severity


# ── Main render ───────────────────────────────────────────────────────────
SECTIONS = [
    ("BOT PROCESS",    section_bot),
    ("REGIME",         section_regime),
    ("SLEEVES",        section_sleeves),
    ("CONTROL PLANE",  section_control_plane),
    ("LOG ERRORS",     section_log_errors),
]


def run_all() -> tuple[list[str], int]:
    """Run all sections, return (output_lines, max_severity)."""
    out: list[str] = []
    max_sev = 0
    results: dict[str, Any] = {}

    width = 55
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out.append("")
    out.append(BOLD("═" * width))
    out.append(BOLD(f"  BOT MONITOR   {now_str}"))
    out.append(BOLD("═" * width))

    for label, fn in SECTIONS:
        out.append("")
        out.append(BOLD(f"▶ {label}"))
        try:
            section_lines, sev = fn()
        except Exception as exc:
            section_lines = [err(f"section crash: {exc}")]
            sev = 2
        for line in section_lines:
            out.append(line)
        max_sev = max(max_sev, sev)
        results[label] = {"severity": sev}

    out.append("")
    SEV_LABEL = {0: GREEN("HEALTHY"), 1: YELLOW("DEGRADED"), 2: RED("CRITICAL")}
    out.append(BOLD("═" * width))
    out.append(BOLD(f"  OVERALL: {SEV_LABEL.get(max_sev, '?')}"))
    out.append(BOLD("═" * width))
    out.append("")
    return out, max_sev


def run_ssh(server_ip: str, server_user: str, ssh_key: str | None,
            remote_flags: list[str] | None = None) -> int:
    """Execute monitor.py on remote server via SSH, stream output."""
    bot_dir_remote = os.getenv("REMOTE_BOT_DIR", "/root/by-bot")
    cmd_parts = []
    if ssh_key:
        cmd_parts += ["-i", ssh_key, "-o", "StrictHostKeyChecking=no"]
    cmd_parts += [f"{server_user}@{server_ip}"]
    remote_cmd = (
        f"cd {bot_dir_remote} && "
        f"BOT_DIR={bot_dir_remote} python3 scripts/monitor.py {' '.join(remote_flags or [])}"
    )
    cmd = ["ssh"] + cmd_parts + [remote_cmd]
    try:
        r = subprocess.run(cmd, timeout=30)
        return r.returncode
    except subprocess.TimeoutExpired:
        print(err("SSH connection timed out"), file=sys.stderr)
        return 2
    except Exception as exc:
        print(err(f"SSH failed: {exc}"), file=sys.stderr)
        return 2


# ── Entry point ───────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="Bot health monitor")
    ap.add_argument("--ssh",     action="store_true",  help="Run via SSH on remote server")
    ap.add_argument("--server",  default=os.getenv("SERVER_IP", "64.226.73.119"))
    ap.add_argument("--user",    default=os.getenv("SERVER_USER", "root"))
    ap.add_argument("--key",     default=os.getenv("SSH_KEY", None), help="SSH key path")
    ap.add_argument("--compact", action="store_true",  help="No decorative borders")
    ap.add_argument("--json",    action="store_true",  help="Machine-readable JSON output")
    args = ap.parse_args()

    # Auto-detect SSH key
    if args.ssh and args.key is None:
        default_key = Path.home() / ".ssh" / "by-bot"
        if default_key.exists():
            args.key = str(default_key)

    if args.ssh:
        remote_flags = []
        if args.compact:
            remote_flags.append("--compact")
        if args.json:
            remote_flags.append("--json")
        return run_ssh(args.server, args.user, args.key, remote_flags)

    lines, severity = run_all()

    if args.json:
        # Minimal machine-readable output
        result: dict[str, Any] = {
            "severity": severity,
            "healthy":  severity == 0,
            "ts":       int(time.time()),
        }
        print(json.dumps(result))
        return severity

    if args.compact:
        for line in lines:
            stripped = re.sub(r"\033\[[0-9;]*m", "", line)  # strip ANSI
            print(stripped)
    else:
        for line in lines:
            print(line)

    return severity


if __name__ == "__main__":
    sys.exit(main())
