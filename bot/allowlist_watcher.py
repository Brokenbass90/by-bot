"""
bot/allowlist_watcher.py — Dynamic Runtime Env Hot-Reload
=========================================================
Watches generated env overlays and applies changes to os.environ
WITHOUT restarting the bot process.

How it works:
  1. Background thread polls the overlay files every POLL_INTERVAL seconds
  2. When file changes (mtime check) → re-parses and updates os.environ
  3. Strategies / bot components that re-read os.environ on each cycle pick up
     new symbols directly.
  4. For symbol lists that still require a restart or engine rebuild, the watcher
     writes configs/allowlist_restart_needed.flag
  5. Sends Telegram digest of changes

Usage — add to smart_pump_reversal_bot.py startup:
    from bot.allowlist_watcher import AllowlistWatcher
    watcher = AllowlistWatcher()
    watcher.start()              # starts background thread
    # ... rest of bot startup

Integration points:
    - Already works for ASC1/ARF1 because they call os.getenv() each cycle
    - For BREAKOUT: check restart flag file before opening new positions:
        if Path("configs/allowlist_restart_needed.flag").exists():
            logger.warning("Allowlist updated — restart when safe")

Config:
    ALLOWLIST_WATCHER_INTERVAL=300               # poll every 5 min (default)
    ALLOWLIST_WATCHER_ENABLED=1                  # set 0 to disable
    ALLOWLIST_WATCHER_FILE=configs/dynamic_allowlist_latest.env
    AUTO_APPLY_WATCHER_FILE=configs/auto_apply_params.env
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Set
from urllib import request

logger = logging.getLogger(__name__)

ROOT            = Path(__file__).resolve().parent.parent
RESTART_FLAG    = ROOT / "configs" / "allowlist_restart_needed.flag"
CHANGE_LOG      = ROOT / "configs" / "allowlist_change_log.json"


def _resolve_allowlist_file() -> Path:
    return Path(
        os.getenv(
            "ALLOWLIST_WATCHER_FILE",
            str(ROOT / "configs" / "dynamic_allowlist_latest.env"),
        )
    ).expanduser()


def _resolve_auto_apply_file() -> Path:
    return Path(
        os.getenv(
            "AUTO_APPLY_WATCHER_FILE",
            str(ROOT / "configs" / "auto_apply_params.env"),
        )
    ).expanduser()

# Which env vars can be hot-reloaded (strategies/bot re-read them at runtime)
HOT_RELOAD_VARS: Set[str] = {
    "ASC1_SYMBOL_ALLOWLIST",
    "ARF1_SYMBOL_ALLOWLIST",
    "BREAKDOWN_SYMBOL_ALLOWLIST",
    "BREAKOUT_SYMBOL_ALLOWLIST",
    "BREAKOUT_SYMBOL_DENYLIST",
    "MIDTERM_SYMBOLS",
}

HOT_RELOAD_PREFIXES: tuple[str, ...] = (
    "ARF1_",
    "IVB1_",
    "ETS2_",
    "ARS1_",
    "ASB1_",
    "ASC1_",
    "BREAKDOWN_",
)

# Which vars still need a restart or explicit operator intervention
RESTART_REQUIRED_VARS: Set[str] = {
    "MICRO_SCALPER_SYMBOL_ALLOWLIST",
    "SUPPORT_RECLAIM_SYMBOL_ALLOWLIST",
}


def _is_symbol_like_var(var: str) -> bool:
    return (
        var.endswith("_SYMBOL_ALLOWLIST")
        or var.endswith("_SYMBOL_DENYLIST")
        or var.endswith("_SYMBOLS")
    )


def _is_hot_reload_var(var: str) -> bool:
    return var in HOT_RELOAD_VARS or var.startswith(HOT_RELOAD_PREFIXES)


def _tg(token: str, chat_id: str, msg: str) -> None:
    if not token or not chat_id:
        return
    payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode()
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload, headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, context=ssl.create_default_context(), timeout=8):
            pass
    except Exception:
        pass


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse key=value .env file → dict."""
    result: Dict[str, str] = {}
    if not path.exists():
        return result
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.split("#")[0].strip().strip('"').strip("'")
            if key:
                result[key] = val
    return result


def _symbols_changed(old: str, new: str) -> tuple[Set[str], Set[str]]:
    """Returns (added, removed) symbol sets."""
    def parse(s: str) -> Set[str]:
        return {x.strip().upper() for x in s.replace(";", ",").split(",") if x.strip()}
    old_set = parse(old)
    new_set = parse(new)
    return new_set - old_set, old_set - new_set


class AllowlistWatcher:
    """
    Background thread that watches the dynamic allowlist env file
    and applies changes to os.environ without bot restart.
    """

    def __init__(self, poll_interval: Optional[int] = None) -> None:
        self._interval  = poll_interval or int(os.getenv("ALLOWLIST_WATCHER_INTERVAL", "300"))
        self._enabled   = os.getenv("ALLOWLIST_WATCHER_ENABLED", "1").strip() == "1"
        self._files     = [_resolve_allowlist_file(), _resolve_auto_apply_file()]
        self._tg_token  = os.getenv("TG_TOKEN", "")
        self._tg_chat   = os.getenv("TG_CHAT_ID", "") or os.getenv("TG_CHAT", "")
        self._last_mtimes: Dict[Path, float] = {}
        self._last_values_by_file: Dict[Path, Dict[str, str]] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if not self._enabled:
            logger.info("[AllowlistWatcher] Disabled via ALLOWLIST_WATCHER_ENABLED=0")
            return
        for path in self._files:
            if not path.exists():
                logger.info(f"[AllowlistWatcher] File not found: {path} — waiting")
        self._thread = threading.Thread(
            target=self._run, name="allowlist-watcher", daemon=True
        )
        self._thread.start()
        logger.info(
            f"[AllowlistWatcher] Started (poll={self._interval}s, files={[str(p) for p in self._files]})"
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        # Load initial state without sending alerts
        for path in self._files:
            if path.exists():
                self._last_mtimes[path] = path.stat().st_mtime
                values = _parse_env_file(path)
                self._last_values_by_file[path] = values
                self._apply(values, silent=True, source=path.name)

        while not self._stop_event.wait(self._interval):
            for path in self._files:
                self._check(path)

    def _check(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return
        if mtime <= float(self._last_mtimes.get(path, 0.0)):
            return  # file unchanged

        new_values = _parse_env_file(path)
        self._apply(new_values, silent=False, source=path.name)
        self._last_mtimes[path] = mtime
        self._last_values_by_file[path] = new_values

    def _apply(self, new_values: Dict[str, str], silent: bool = False, source: str = "runtime_env") -> None:
        """Apply new env values → os.environ. Track changes."""
        hot_changes: Dict[str, tuple[str, str]] = {}     # var → (old, new)
        restart_changes: Dict[str, tuple[str, str]] = {}

        for var, new_val in new_values.items():
            old_val = os.environ.get(var, "")
            if old_val == new_val:
                continue

            os.environ[var] = new_val

            if _is_hot_reload_var(var):
                hot_changes[var] = (old_val, new_val)
            elif var in RESTART_REQUIRED_VARS:
                restart_changes[var] = (old_val, new_val)

        if not hot_changes and not restart_changes:
            return

        # Write restart flag if needed
        if restart_changes:
            RESTART_FLAG.write_text(
                f"Allowlist updated at {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}.\n"
                f"Changed vars (require restart): {', '.join(restart_changes)}\n"
                f"Restart when no open positions to apply BREAKOUT allowlist changes."
            )
            logger.warning(f"[AllowlistWatcher] Restart required for: {list(restart_changes)}")

        # Log changes
        self._log_changes(hot_changes, restart_changes, source=source)

        if not silent:
            self._send_tg_digest(hot_changes, restart_changes, source=source)

        # Log to console
        for var, (old, new) in hot_changes.items():
            if _is_symbol_like_var(var):
                added, removed = _symbols_changed(old, new)
                logger.info(
                    f"[AllowlistWatcher] {source} {var} hot-reloaded: "
                    f"+{sorted(added)} -{sorted(removed)}"
                )
            else:
                logger.info(f"[AllowlistWatcher] {source} {var} hot-reloaded: {old or '-'} -> {new or '-'}")

    def _log_changes(
        self,
        hot: Dict[str, tuple[str, str]],
        restart: Dict[str, tuple[str, str]],
        *,
        source: str,
    ) -> None:
        log: list = []
        if CHANGE_LOG.exists():
            try:
                log = json.loads(CHANGE_LOG.read_text())
            except Exception:
                log = []
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": source,
            "hot_reload": {v: {"old": o, "new": n} for v, (o, n) in hot.items()},
            "restart_needed": {v: {"old": o, "new": n} for v, (o, n) in restart.items()},
        }
        log.append(entry)
        log = log[-50:]   # keep last 50 changes
        try:
            CHANGE_LOG.parent.mkdir(parents=True, exist_ok=True)
            CHANGE_LOG.write_text(json.dumps(log, indent=2))
        except Exception:
            pass

    def _send_tg_digest(
        self,
        hot: Dict[str, tuple[str, str]],
        restart: Dict[str, tuple[str, str]],
        *,
        source: str,
    ) -> None:
        lines = [f"🔄 <b>Runtime Params Updated</b>\nsource={source}"]

        for var, (old, new) in hot.items():
            strat = var.replace("_SYMBOL_ALLOWLIST", "")
            lines.append(f"\n<b>{strat}</b> (hot-reloaded ✅):")
            if _is_symbol_like_var(var):
                added, removed = _symbols_changed(old, new)
                if added:
                    lines.append(f"  ➕ Added: {', '.join(sorted(added))}")
                if removed:
                    lines.append(f"  ➖ Removed: {', '.join(sorted(removed))}")
            else:
                lines.append(f"  {old or '-'} → {new or '-'}")

        for var, (old, new) in restart.items():
            strat = var.replace("_SYMBOL_ALLOWLIST", "")
            lines.append(f"\n<b>{strat}</b> (⚠️ needs restart):")
            if _is_symbol_like_var(var):
                added, removed = _symbols_changed(old, new)
                if added:
                    lines.append(f"  ➕ Added: {', '.join(sorted(added))}")
                if removed:
                    lines.append(f"  ➖ Removed: {', '.join(sorted(removed))}")
            else:
                lines.append(f"  {old or '-'} → {new or '-'}")
            lines.append("  → Restart bot when no open positions.")

        _tg(self._tg_token, self._tg_chat, "\n".join(lines))


# ── Standalone apply script (run without starting the bot) ──────────────────────
def apply_now(dry_run: bool = False) -> None:
    """
    Apply current runtime env overlays to os.environ immediately.
    Useful for testing. Prints diff without starting background thread.
    """
    for path in (_resolve_allowlist_file(), _resolve_auto_apply_file()):
        values = _parse_env_file(path)
        if not values:
            print(f"No values found in {path}")
            continue
        print(f"Loaded {len(values)} vars from {path.name}")
        for var, new_val in sorted(values.items()):
            old_val = os.environ.get(var, "(not set)")
            if old_val == new_val:
                print(f"  {var}: unchanged")
            else:
                print(f"  {var}:")
                if _is_symbol_like_var(var):
                    added, removed = _symbols_changed(old_val, new_val)
                    if added:
                        print(f"    ➕ {sorted(added)}")
                    if removed:
                        print(f"    ➖ {sorted(removed)}")
                else:
                    print(f"    {old_val} -> {new_val}")
                if _is_hot_reload_var(var):
                    print(f"    → Hot-reloadable ✅")
                elif var in RESTART_REQUIRED_VARS:
                    print(f"    → Requires bot restart ⚠️")
                if not dry_run:
                    os.environ[var] = new_val


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    print(f"apply_now({'dry-run' if dry else 'live'})")
    apply_now(dry_run=dry)
    if not dry:
        print("\n✅ os.environ updated.")
        print("   Hot-reload vars (ASC1/ARF1) active immediately.")
        print("   Restart-required vars: check configs/allowlist_restart_needed.flag")
