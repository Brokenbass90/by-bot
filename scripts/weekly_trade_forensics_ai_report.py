#!/usr/bin/env python3
"""Weekly trade-forensics digest with optional AI interpretation.

This is read-only for trading. It runs the local forensic analyzer on:
- the latest relevant portfolio backtest trades.csv
- recent live close events

Then it sends a concise Telegram digest. If DeepSeek is configured, it also
adds an AI interpretation based on the generated forensic report.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default).strip()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _send_tg(text: str) -> None:
    token = _env("TG_TOKEN")
    chat = _env("TG_CHAT_ID") or _env("TG_CHAT")
    if not token or not chat:
        return
    chunks = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > 3400:
            chunks.append(current.rstrip())
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.rstrip())
    for chunk in chunks or [text[:3400]]:
        payload = urllib.parse.urlencode({"chat_id": chat, "text": chunk}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload)
        with urllib.request.urlopen(req, timeout=20):
            pass


def _latest_backtest_trades(explicit: str = "") -> Path | None:
    if explicit:
        path = Path(explicit)
        if not path.is_absolute():
            path = ROOT / path
        return path if path.exists() else None

    patterns = [
        "backtest_runs/portfolio_*canary*/trades.csv",
        "backtest_runs/portfolio_*live*/trades.csv",
        "backtest_runs/portfolio_*/trades.csv",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates = [p for p in ROOT.glob(pattern) if p.is_file()]
        if candidates:
            break
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def _run_forensics(args: list[str]) -> Path | None:
    cmd = [sys.executable, "scripts/trade_forensics_report.py", *args]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=True)
    md_path: Path | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("wrote_md="):
            raw = line.split("=", 1)[1].strip()
            md_path = Path(raw)
            if not md_path.is_absolute():
                md_path = ROOT / md_path
    return md_path


def _extract_digest(markdown: str) -> str:
    lines = markdown.splitlines()
    keep: list[str] = []
    copy = False
    for line in lines:
        if line.startswith("# "):
            keep.append(line.replace("# ", ""))
            continue
        if line.startswith("Trades analyzed:") or line.startswith("Net PnL:"):
            keep.append(line)
            continue
        if line.startswith("## Strategy Summary"):
            copy = True
            keep.append(line)
            continue
        if line.startswith("## Worst Trades"):
            break
        if copy:
            keep.append(line)
    return "\n".join(keep).strip()


def _ai_interpret(markdown: str, live_md: str) -> str:
    if not _env_bool("FORENSICS_AI_ENABLE", True):
        return ""
    try:
        sys.path.insert(0, str(ROOT))
        from bot.deepseek_overlay import DeepSeekOverlay  # type: ignore
    except Exception as exc:
        return f"AI forensic interpretation skipped: import failed ({exc})."

    overlay = DeepSeekOverlay()
    if not overlay.is_ready():
        return "AI forensic interpretation skipped: DeepSeek is not configured/enabled."

    prompt = (
        "Проанализируй weekly trade-forensics отчёт. "
        "Дай коротко: 1) что реально работает, 2) что ломает портфель, "
        "3) какие 3 исследовательских теста запустить дальше. "
        "Не предлагай включать live без 180/360d additivity gate.\n\n"
        "BACKTEST FORENSICS:\n"
        f"{markdown[:9000]}\n\n"
        "LIVE FORENSICS:\n"
        f"{live_md[:4000]}"
    )
    snapshot = {
        "kind": "weekly_trade_forensics",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        return overlay.ask(prompt, snapshot).strip()
    except Exception as exc:
        return f"AI forensic interpretation failed: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest-trades", default=_env("FORENSICS_TRADES_CSV", ""))
    ap.add_argument("--live-days", type=int, default=int(_env("FORENSICS_LIVE_DAYS", "120") or 120))
    ap.add_argument("--limit", type=int, default=int(_env("FORENSICS_TRADE_LIMIT", "120") or 120))
    ap.add_argument("--telegram", action="store_true")
    ap.add_argument("--ai", action="store_true")
    ap.add_argument("--no-ai", action="store_true")
    args = ap.parse_args()

    _load_env_file(ROOT / ".env")
    _load_env_file(ROOT / "configs" / "server.env")

    backtest_trades = _latest_backtest_trades(args.backtest_trades)
    parts: list[str] = []
    backtest_md = ""
    live_md = ""

    if backtest_trades:
        md_path = _run_forensics(
            [
                "--trades-csv",
                str(backtest_trades.relative_to(ROOT) if backtest_trades.is_relative_to(ROOT) else backtest_trades),
                "--cache-dir",
                ".cache/klines",
                "--tag",
                f"weekly_backtest_{backtest_trades.parent.name}",
                "--limit",
                str(args.limit),
            ]
        )
        if md_path and md_path.exists():
            backtest_md = md_path.read_text(encoding="utf-8", errors="ignore")
            parts.append("🧪 Weekly trade forensics — backtest\n" + _extract_digest(backtest_md))
            parts.append(f"Backtest source: {backtest_trades}")
            parts.append(f"Report: {md_path}")
    else:
        parts.append("🧪 Weekly trade forensics — no backtest trades.csv found.")

    live_events = ROOT / "runtime" / "live_trade_events.jsonl"
    if live_events.exists():
        md_path = _run_forensics(
            [
                "--live-events",
                "runtime/live_trade_events.jsonl",
                "--live-days",
                str(args.live_days),
                "--cache-dir",
                ".cache/klines",
                "--tag",
                f"weekly_live_{args.live_days}d",
                "--limit",
                str(args.limit),
            ]
        )
        if md_path and md_path.exists():
            live_md = md_path.read_text(encoding="utf-8", errors="ignore")
            parts.append("\n📡 Weekly trade forensics — live\n" + _extract_digest(live_md))
            parts.append(f"Live report: {md_path}")
    else:
        parts.append("\n📡 Weekly trade forensics — no live events file.")

    if args.ai and not args.no_ai:
        ai_text = _ai_interpret(backtest_md, live_md)
        if ai_text:
            parts.append("\n🧠 AI forensic interpretation\n" + ai_text)

    text = "\n\n".join(p for p in parts if p.strip())
    print(text)
    if args.telegram:
        _send_tg(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
