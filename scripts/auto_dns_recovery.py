#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_dns_recovery.py — Phase B4: DNS health check + automatic fallback.

The 10 April 2026 incident: local DNS resolver hiccup made
`build_symbol_router.py` and `regime_orchestrator.py` unable to reach
api.bybit.com. Orchestrator silently died; nobody noticed for 53 days.

This script:
  1. Tests DNS resolution for critical hosts (api.bybit.com, paper-api.alpaca.markets,
     api.telegram.org, api.anthropic.com)
  2. If 2+ critical hosts fail to resolve → DNS is broken
  3. Writes runtime/dns_health.json with the test results
  4. If broken → optionally rewrites resolv.conf (only when run as root + --apply)
     using a backup set of resolvers (Cloudflare 1.1.1.1, Google 8.8.8.8)
  5. Sends a TG alert

Defaults to safe / read-only mode. Operator must pass --apply to actually rewrite
/etc/resolv.conf. The bot itself can read runtime/dns_health.json and gate
external calls on DNS health.

Usage:
  python3 scripts/auto_dns_recovery.py             # check only, no fix
  python3 scripts/auto_dns_recovery.py --apply     # apply fallback if broken (root)
  python3 scripts/auto_dns_recovery.py --json      # machine-readable output
  python3 scripts/auto_dns_recovery.py --tg        # TG alert on failure

Cron (every 5 min):
  */5 * * * * cd /root/by-bot && python3 scripts/auto_dns_recovery.py --tg >> logs/dns_health.log 2>&1

Notes:
  - Does NOT use any third-party libraries — pure socket + stdlib
  - Backup resolvers are conservative public ones (Cloudflare, Google, Quad9)
  - Rewriting /etc/resolv.conf requires running as root and managing
    systemd-resolved if active. Safer to use NetworkManager dispatcher,
    but this script handles the simple resolv.conf-mutation case.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
HEALTH_PATH = ROOT / "runtime" / "dns_health.json"
RESOLV_CONF = Path("/etc/resolv.conf")
RESOLV_BACKUP = Path("/etc/resolv.conf.opus_backup")

CRITICAL_HOSTS = [
    "api.bybit.com",
    "paper-api.alpaca.markets",
    "api.telegram.org",
    "api.anthropic.com",
]
NON_CRITICAL_HOSTS = [
    "fapi.binance.com",   # for funding rates cross-check
    "raw.githubusercontent.com",
]

FALLBACK_RESOLVERS = ["1.1.1.1", "8.8.8.8", "9.9.9.9"]  # Cloudflare, Google, Quad9
RESOLVE_TIMEOUT_SEC = 5.0

# How many critical hosts must fail before we call DNS "broken"
BREAK_THRESHOLD = 2


def _resolve(host: str, timeout: float = RESOLVE_TIMEOUT_SEC) -> Tuple[bool, str]:
    """Try to resolve host; return (ok, ip_or_error)."""
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        info = socket.getaddrinfo(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
        if info:
            return True, info[0][4][0]
        return False, "no address records"
    except socket.gaierror as exc:
        return False, f"gaierror: {exc}"
    except socket.timeout:
        return False, "timeout"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        socket.setdefaulttimeout(old_timeout)


def _read_resolv_conf() -> List[str]:
    """Return list of nameserver IPs currently configured."""
    try:
        text = RESOLV_CONF.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("nameserver"):
            parts = line.split()
            if len(parts) >= 2:
                out.append(parts[1])
    return out


def _write_fallback_resolv_conf(resolvers: List[str]) -> bool:
    """Replace /etc/resolv.conf with fallback nameservers. Returns True on success."""
    if os.geteuid() != 0:
        print("[dns] not root — cannot rewrite /etc/resolv.conf", file=sys.stderr)
        return False
    try:
        if RESOLV_CONF.exists() and not RESOLV_BACKUP.exists():
            shutil.copy2(RESOLV_CONF, RESOLV_BACKUP)
        ts = datetime.now(timezone.utc).isoformat()
        lines = [
            f"# Auto-rewritten by auto_dns_recovery.py at {ts}",
            f"# Original at {RESOLV_BACKUP}",
        ]
        for r in resolvers:
            lines.append(f"nameserver {r}")
        lines.append("options timeout:2 attempts:2 single-request-reopen")
        tmp = RESOLV_CONF.with_suffix(".tmp")
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(RESOLV_CONF)
        return True
    except PermissionError:
        print("[dns] permission denied (run as root or with sudo)", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[dns] resolv.conf write failed: {exc}", file=sys.stderr)
        return False


def _check_all_hosts() -> Dict[str, Any]:
    """Test all critical + non-critical hosts. Return summary dict."""
    results = {}
    failed_critical = 0
    failed_total = 0
    started = time.time()

    for host in CRITICAL_HOSTS:
        ok, info = _resolve(host)
        results[host] = {"ok": ok, "info": info, "critical": True}
        if not ok:
            failed_critical += 1
            failed_total += 1

    for host in NON_CRITICAL_HOSTS:
        ok, info = _resolve(host)
        results[host] = {"ok": ok, "info": info, "critical": False}
        if not ok:
            failed_total += 1

    elapsed = time.time() - started

    healthy = failed_critical < BREAK_THRESHOLD
    return {
        "checked_at":         datetime.now(timezone.utc).isoformat(),
        "elapsed_sec":        round(elapsed, 2),
        "healthy":            healthy,
        "failed_critical":    failed_critical,
        "failed_total":       failed_total,
        "break_threshold":    BREAK_THRESHOLD,
        "current_resolvers":  _read_resolv_conf(),
        "results":            results,
    }


def _write_health(report: Dict[str, Any]) -> None:
    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = HEALTH_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(HEALTH_PATH)


def _tg_send(text: str) -> None:
    token = os.getenv("TG_TOKEN", "").strip()
    chat = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not token or not chat:
        return
    try:
        payload = json.dumps({"chat_id": chat, "text": text[:3500], "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        print(f"[dns] TG send failed: {exc}", file=sys.stderr)


def _format_text(report: Dict[str, Any]) -> str:
    lines = []
    status = "✅ HEALTHY" if report["healthy"] else "🔴 BROKEN"
    lines.append(f"DNS health check — {status}")
    lines.append(f"  elapsed:        {report['elapsed_sec']}s")
    lines.append(f"  failed_critical: {report['failed_critical']}/{len(CRITICAL_HOSTS)}")
    lines.append(f"  current_resolvers: {', '.join(report['current_resolvers']) or '(none in resolv.conf)'}")
    lines.append("")
    for host, res in report["results"].items():
        flag = "✓" if res["ok"] else "✗"
        crit = "*" if res["critical"] else " "
        lines.append(f"  {flag} {crit} {host:<40} {res['info']}")
    return "\n".join(lines)


def _main() -> int:
    ap = argparse.ArgumentParser(description="DNS health check + automatic fallback.")
    ap.add_argument("--apply", action="store_true",
                    help="If DNS broken, rewrite /etc/resolv.conf with fallback (root only).")
    ap.add_argument("--json", action="store_true", help="Machine-readable JSON only.")
    ap.add_argument("--tg", action="store_true", help="TG alert on failure.")
    ap.add_argument("--no-write", action="store_true", help="Don't write runtime/dns_health.json")
    args = ap.parse_args()

    report = _check_all_hosts()

    if not args.no_write:
        _write_health(report)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(_format_text(report))

    if not report["healthy"]:
        # DNS is broken — try fallback
        if args.apply:
            applied = _write_fallback_resolv_conf(FALLBACK_RESOLVERS)
            if applied:
                print("[dns] rewrote /etc/resolv.conf to fallback resolvers — retest...")
                # Brief settle then retest
                time.sleep(2)
                retest = _check_all_hosts()
                if not args.no_write:
                    _write_health(retest)
                ok_after = retest["healthy"]
                print(f"[dns] post-rewrite healthy={ok_after}")
                if args.tg:
                    msg = (
                        f"🔧 <b>DNS recovery applied</b>\n"
                        f"  before: {report['failed_critical']}/{len(CRITICAL_HOSTS)} critical hosts down\n"
                        f"  after:  {retest['failed_critical']}/{len(CRITICAL_HOSTS)} critical hosts down\n"
                        f"  resolvers: {', '.join(FALLBACK_RESOLVERS)}"
                    )
                    _tg_send(msg)
            else:
                print("[dns] could not rewrite resolv.conf — operator must intervene")
                if args.tg:
                    _tg_send(
                        f"🚨 <b>DNS broken, cannot auto-recover</b>\n"
                        f"  {report['failed_critical']}/{len(CRITICAL_HOSTS)} critical hosts down\n"
                        f"  Run as root: <code>sudo python3 scripts/auto_dns_recovery.py --apply</code>"
                    )
                return 1
        else:
            print(
                "[dns] DNS broken but --apply not given. "
                "Re-run with sudo --apply or fix resolvers manually."
            )
            if args.tg:
                # Only alert on critical break
                _tg_send(
                    f"🚨 <b>DNS health: BROKEN</b>\n"
                    f"  {report['failed_critical']}/{len(CRITICAL_HOSTS)} critical hosts unresolved\n"
                    f"  Suggest: <code>sudo python3 scripts/auto_dns_recovery.py --apply</code>"
                )
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
