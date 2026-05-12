#!/usr/bin/env python3
"""universe_change_notifier.py — TG-нотификация о смене универсума монет per стратегия.

Idea: после каждого запуска build_symbol_router.py читает свежие списки символов
из runtime/router/*, сравнивает с прошлым snapshot, шлёт TG если изменилось.

Запуск (cron сразу после router rebuild):
    5 */4 * * * cd /root/by-bot && /root/by-bot/.venv/bin/python3 scripts/universe_change_notifier.py >> logs/universe_notifier.log 2>&1

Настройки через env:
    TG_TOKEN, TG_CHAT_ID
    UNIVERSE_NOTIFY_MIN_CHANGE_PCT       (15.0)  — минимальный % изменения для TG
    UNIVERSE_NOTIFY_PER_STRATEGY_LIMIT   (12)    — топ N стратегий показывать в одном TG
    UNIVERSE_NOTIFY_STATE_PATH           (runtime/universe_notifier_last.json)
    UNIVERSE_NOTIFY_ROUTER_DIR           (runtime/router)

State хранится локально, не зависит от .env истории.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str = "") -> str:
    v = os.getenv(name)
    return str(v).strip() if v else default


def _env_float(name: str, default: float) -> float:
    try: return float(os.getenv(name, "") or default)
    except: return default


def _env_int(name: str, default: int) -> int:
    try: return int(os.getenv(name, "") or default)
    except: return default


def _tg_send(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        print(f"[NO TG CREDS] {msg[:200]}")
        return
    try:
        payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
        req = request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as e:
        print(f"[TG ERROR] {e}")


def _load_router_snapshots(router_dir: Path) -> Dict[str, List[str]]:
    """Reads runtime/router/*.json, returns {strategy: [symbol1, symbol2, ...]}."""
    out: Dict[str, List[str]] = {}
    if not router_dir.exists():
        return out
    for fp in sorted(router_dir.glob("*.json")):
        if fp.name.startswith("_"): continue
        try:
            data = json.loads(fp.read_text())
        except Exception:
            continue
        # Heuristics for router file shapes — handle several common ones
        symbols: List[str] = []
        if isinstance(data, dict):
            for key in ("symbols", "allowlist", "active", "selected"):
                v = data.get(key)
                if isinstance(v, list):
                    symbols = [str(x).upper() for x in v if x]
                    break
            if not symbols and isinstance(data.get("by_strategy"), dict):
                # Aggregated file: dispatch into multiple strategy entries
                for strat, sub in data["by_strategy"].items():
                    if isinstance(sub, list):
                        out[str(strat).lower()] = [str(x).upper() for x in sub if x]
                    elif isinstance(sub, dict) and isinstance(sub.get("symbols"), list):
                        out[str(strat).lower()] = [str(x).upper() for x in sub["symbols"] if x]
                continue
        elif isinstance(data, list):
            symbols = [str(x).upper() for x in data if x]
        if symbols:
            # strategy name = filename stem без _allowlist суффикса
            strat = fp.stem.replace("_allowlist", "").replace("_universe", "").lower()
            out[strat] = symbols
    return out


def _compare(old: Set[str], new: Set[str]) -> Tuple[Set[str], Set[str], float]:
    """Returns (added, removed, change_pct)."""
    if not old and not new:
        return set(), set(), 0.0
    added = new - old
    removed = old - new
    union = max(1, len(old | new))
    change = (len(added) + len(removed)) / union * 100.0
    return added, removed, change


def _format_msg(changes: List[Dict[str, Any]]) -> str:
    """Build TG-сообщение."""
    lines = ["🧩 <b>Universe changed</b>"]
    lines.append(f"<i>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</i>")
    lines.append("")
    for ch in changes:
        added = sorted(ch["added"])
        removed = sorted(ch["removed"])
        bits = [f"<b>{ch['strategy']}</b> ({ch['change_pct']:.0f}% diff)"]
        if added:
            preview = ",".join(added[:5]) + (f" (+{len(added)-5})" if len(added) > 5 else "")
            bits.append(f"  ➕ {preview}")
        if removed:
            preview = ",".join(removed[:5]) + (f" (+{len(removed)-5})" if len(removed) > 5 else "")
            bits.append(f"  ➖ {preview}")
        bits.append(f"  📋 now: {len(ch['new_set'])} symbols")
        lines.append("\n".join(bits))
        lines.append("")
    return "\n".join(lines).strip()


def main() -> int:
    router_dir = Path(_env("UNIVERSE_NOTIFY_ROUTER_DIR", str(ROOT / "runtime" / "router")))
    state_path = Path(_env("UNIVERSE_NOTIFY_STATE_PATH", str(ROOT / "runtime" / "universe_notifier_last.json")))
    min_change_pct = _env_float("UNIVERSE_NOTIFY_MIN_CHANGE_PCT", 15.0)
    per_strategy_limit = _env_int("UNIVERSE_NOTIFY_PER_STRATEGY_LIMIT", 12)
    tg_token = _env("TG_TOKEN")
    tg_chat = _env("TG_CHAT_ID") or _env("TG_CHAT")  # support both names

    current = _load_router_snapshots(router_dir)
    if not current:
        print(f"[INFO] No router files in {router_dir}, exit")
        return 0

    # Load previous state
    previous: Dict[str, List[str]] = {}
    if state_path.exists():
        try:
            previous = json.loads(state_path.read_text())
        except Exception:
            previous = {}

    changes = []
    for strategy, syms in current.items():
        old = set(previous.get(strategy, []))
        new = set(syms)
        added, removed, change_pct = _compare(old, new)

        if not previous:
            # First run — silent (initial snapshot)
            print(f"[INIT] {strategy}: {len(new)} symbols (no notify, first run)")
            continue

        if change_pct >= min_change_pct or (added and len(added) >= 2) or (removed and len(removed) >= 2):
            changes.append({
                "strategy": strategy,
                "added": added,
                "removed": removed,
                "change_pct": change_pct,
                "new_set": new,
            })
            print(f"[CHANGE] {strategy}: +{len(added)} -{len(removed)} ({change_pct:.1f}%)")
        else:
            print(f"[STABLE] {strategy}: +{len(added)} -{len(removed)} ({change_pct:.1f}% < {min_change_pct}%)")

    # Save current as new state
    try:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({k: sorted(v) for k, v in current.items()}, indent=2))
    except Exception as e:
        print(f"[STATE WRITE ERR] {e}")

    if not changes:
        print("[INFO] No notifiable changes")
        return 0

    # Limit per-strategy messages so we don't blast TG
    changes = changes[:per_strategy_limit]
    msg = _format_msg(changes)
    print(f"[TG] sending {len(changes)} changes")
    _tg_send(tg_token, tg_chat, msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
