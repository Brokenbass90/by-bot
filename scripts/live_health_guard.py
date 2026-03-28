#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


STATE_PATH = Path(
    os.getenv("LIVE_GUARD_STATE_JSON", str(ROOT / "runtime" / "live_health_guard" / "state.json"))
)
DEFAULT_SINCE = os.getenv("LIVE_GUARD_SINCE", "2 hours ago")
DEFAULT_LOCAL = str(os.getenv("LIVE_GUARD_LOCAL", "1")).strip().lower() in {"1", "true", "yes", "on"}
ALERT_REPEAT = max(1, int(os.getenv("LIVE_GUARD_ALERT_REPEAT", "2") or "2"))
ALERT_ON_WARN = str(os.getenv("LIVE_GUARD_ALERT_ON_WARN", "0")).strip().lower() in {"1", "true", "yes", "on"}
SEND_RECOVERY = str(os.getenv("LIVE_GUARD_SEND_RECOVERY", "1")).strip().lower() in {"1", "true", "yes", "on"}
TEST_INPUT = (os.getenv("LIVE_GUARD_TEST_INPUT", "") or "").strip()
MIN_CONNECT_DELTA = max(1, int(os.getenv("LIVE_GUARD_MIN_CONNECT_DELTA", "3") or "3"))
AUTO_RESTART = _bool_env("LIVE_GUARD_AUTO_RESTART", False)
AUTO_RESTART_REPEAT = max(1, int(os.getenv("LIVE_GUARD_AUTO_RESTART_REPEAT", str(ALERT_REPEAT)) or str(ALERT_REPEAT)))
AUTO_RESTART_COOLDOWN_SEC = max(60, int(os.getenv("LIVE_GUARD_AUTO_RESTART_COOLDOWN_SEC", "1800") or "1800"))
AUTO_RESTART_REQUIRE_NO_OPEN_TRADES = _bool_env("LIVE_GUARD_AUTO_RESTART_REQUIRE_NO_OPEN_TRADES", True)
AUTO_RESTART_ON = {
    x.strip().upper()
    for x in (os.getenv("LIVE_GUARD_AUTO_RESTART_ON", "CRITICAL_NO_CONNECT,NO_DATA") or "").split(",")
    if x.strip()
}
AUTO_RESTART_CMD = (os.getenv("LIVE_GUARD_AUTO_RESTART_CMD", "bash scripts/restart_live_bot.sh") or "").strip()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "last_status": "INIT",
            "critical_streak": 0,
            "warn_streak": 0,
            "incident_open": False,
            "incident_status": "",
            "last_checked_at": "",
            "last_restart_ts": 0,
            "last_restart_action": "never",
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "last_status": "BROKEN_STATE",
            "critical_streak": 0,
            "warn_streak": 0,
            "incident_open": False,
            "incident_status": "",
            "last_checked_at": "",
            "last_restart_ts": 0,
            "last_restart_action": "broken_state",
        }


def _save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_diag() -> str:
    if TEST_INPUT:
        return Path(TEST_INPUT).read_text(encoding="utf-8")
    env = os.environ.copy()
    env["SINCE"] = DEFAULT_SINCE
    if DEFAULT_LOCAL:
        env["BYBOT_DIAG_LOCAL"] = "1"
    proc = subprocess.run(
        ["bash", "scripts/run_live_diagnostics.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    return (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")


def _extract_int(text: str, pattern: str, default: int = 0) -> int:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else default


def _extract_last_int(text: str, pattern: str, default: int = 0) -> int:
    matches = re.findall(pattern, text)
    return int(matches[-1]) if matches else default


def _extract_str(text: str, pattern: str, default: str = "") -> str:
    m = re.search(pattern, text)
    return m.group(1) if m else default


def _parse_diag(text: str) -> dict:
    status = _extract_str(text, r"status=([A-Z_]+)", "NO_DATA")
    breakout_try = _extract_int(text, r"breakout: try=(\d+)")
    breakout_entry = _extract_int(text, r"breakout: try=\d+ entry=(\d+)")
    breakout_no_signal = _extract_int(text, r"breakout: try=\d+ entry=\d+ no_signal=(\d+)")
    midterm_try = _extract_int(text, r"midterm:\s+try=(\d+)")
    midterm_entry = _extract_int(text, r"midterm:\s+try=\d+ entry=(\d+)")
    ws_connect = _extract_int(text, r"ws: connect=(\d+)")
    ws_disconnect = _extract_int(text, r"ws: connect=\d+ disconnect=(\d+)")
    ws_handshake_timeout = _extract_int(text, r"ws: connect=\d+ disconnect=\d+ handshake_timeout=(\d+)")
    no_break = _extract_int(text, r"no_break=(\d+)")
    impulse_weak = _extract_int(text, r"impulse_weak=(\d+)")
    impulse_body = _extract_int(text, r"impulse_body=(\d+)")
    dist = _extract_int(text, r"dist=(\d+)")
    open_trades = _extract_last_int(text, r"open_trades=(\d+)", 0)
    return {
        "status": status,
        "breakout_try": breakout_try,
        "breakout_entry": breakout_entry,
        "breakout_no_signal": breakout_no_signal,
        "midterm_try": midterm_try,
        "midterm_entry": midterm_entry,
        "ws_connect": ws_connect,
        "ws_disconnect": ws_disconnect,
        "ws_handshake_timeout": ws_handshake_timeout,
        "no_break": no_break,
        "impulse_weak": impulse_weak,
        "impulse_body": impulse_body,
        "dist": dist,
        "open_trades": open_trades,
    }


def _send_tg(text: str) -> None:
    token = (os.getenv("TG_TOKEN", "") or "").strip()
    chat = (os.getenv("TG_CHAT_ID", "") or os.getenv("TG_CHAT", "") or "").strip()
    if not token or not chat:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urlencode({"chat_id": chat, "text": text}).encode()
    req = Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(req, timeout=15) as resp:
        resp.read()


def _summary_line(diag: dict) -> str:
    return (
        f"status={diag['status']} | ws={diag['ws_connect']}/{diag['ws_disconnect']}"
        f" hs={diag['ws_handshake_timeout']} | breakout try={diag['breakout_try']} entry={diag['breakout_entry']}"
        f" no_signal={diag['breakout_no_signal']} | impulse_weak={diag['impulse_weak']}"
        f" impulse_body={diag['impulse_body']} no_break={diag['no_break']} dist={diag['dist']}"
        f" | midterm try={diag['midterm_try']} entry={diag['midterm_entry']} | open_trades={diag['open_trades']}"
    )


def _maybe_auto_restart(diag: dict, state: dict) -> str:
    status = str(diag.get("status") or "").upper()
    if not AUTO_RESTART or status not in AUTO_RESTART_ON or not AUTO_RESTART_CMD:
        return "disabled"

    streak = int(state.get("critical_streak", 0) or 0)
    if status == "WARN":
        streak = int(state.get("warn_streak", 0) or 0)
    if streak < AUTO_RESTART_REPEAT:
        return "waiting"

    if AUTO_RESTART_REQUIRE_NO_OPEN_TRADES and int(diag.get("open_trades", 0) or 0) > 0:
        return "blocked_open_trades"

    now_ts = int(datetime.now(timezone.utc).timestamp())
    last_restart_ts = int(state.get("last_restart_ts", 0) or 0)
    if last_restart_ts > 0 and (now_ts - last_restart_ts) < AUTO_RESTART_COOLDOWN_SEC:
        return "cooldown"

    proc = subprocess.run(
        ["bash", "-lc", AUTO_RESTART_CMD],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    state["last_restart_ts"] = now_ts
    state["last_restart_cmd"] = AUTO_RESTART_CMD
    state["last_restart_rc"] = int(proc.returncode)
    state["last_restart_at"] = _now_iso()
    output = ((proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")).strip()
    state["last_restart_output"] = output[-2000:]

    if proc.returncode == 0:
        _send_tg(
            "♻️ LIVE auto-restart executed\n"
            f"time={_now_iso()}\n"
            f"reason={status}\n"
            f"since={DEFAULT_SINCE}\n"
            f"{_summary_line(diag)}"
        )
        return "restarted"

    _send_tg(
        "❌ LIVE auto-restart failed\n"
        f"time={_now_iso()}\n"
        f"reason={status}\n"
        f"cmd={AUTO_RESTART_CMD}\n"
        f"rc={proc.returncode}"
    )
    return "restart_failed"


def main() -> int:
    raw = _run_diag()
    diag = _parse_diag(raw)
    state = _load_state()

    status = diag["status"]
    # Keep the standalone health guard aligned with the in-bot WS alerting logic:
    # tiny connect samples can produce absurd ratios and page as CRITICAL even when
    # the transport noise is not yet operationally actionable.
    if status in {"WARN", "CRITICAL"} and int(diag.get("ws_connect", 0) or 0) < MIN_CONNECT_DELTA:
        status = "LOW_SAMPLE"
        diag["status"] = status
    critical_like = status in {"CRITICAL", "CRITICAL_NO_CONNECT", "NO_DATA"}
    warn_like = status == "WARN"

    if critical_like:
        state["critical_streak"] = int(state.get("critical_streak", 0)) + 1
        state["warn_streak"] = 0
    elif warn_like:
        state["warn_streak"] = int(state.get("warn_streak", 0)) + 1
        state["critical_streak"] = 0
    else:
        state["critical_streak"] = 0
        state["warn_streak"] = 0

    should_alert = False
    if status == "CRITICAL_NO_CONNECT":
        should_alert = True
    elif status in {"CRITICAL", "NO_DATA"} and state["critical_streak"] >= ALERT_REPEAT:
        should_alert = True
    elif status == "WARN" and ALERT_ON_WARN and state["warn_streak"] >= ALERT_REPEAT:
        should_alert = True

    incident_open = bool(state.get("incident_open", False))
    incident_status = str(state.get("incident_status", "") or "")

    restart_action = _maybe_auto_restart(diag, state)
    state["last_restart_action"] = restart_action

    if should_alert and (not incident_open or incident_status != status):
        msg = (
            "LIVE health alert\n"
            f"time={_now_iso()}\n"
            f"since={DEFAULT_SINCE}\n"
            f"restart_action={restart_action}\n"
            f"{_summary_line(diag)}"
        )
        _send_tg(msg)
        state["incident_open"] = True
        state["incident_status"] = status
    elif incident_open and status == "OK" and SEND_RECOVERY:
        msg = (
            "LIVE health recovery\n"
            f"time={_now_iso()}\n"
            f"since={DEFAULT_SINCE}\n"
            f"restart_action={restart_action}\n"
            f"{_summary_line(diag)}"
        )
        _send_tg(msg)
        state["incident_open"] = False
        state["incident_status"] = ""
    elif not critical_like and not warn_like:
        state["incident_open"] = False
        state["incident_status"] = ""

    state["last_status"] = status
    state["last_checked_at"] = _now_iso()
    state["last_diag"] = diag
    _save_state(state)

    print(_summary_line(diag))
    print(
        f"alert_repeat={ALERT_REPEAT} critical_streak={state['critical_streak']} "
        f"warn_streak={state['warn_streak']} incident_open={state['incident_open']} "
        f"restart_action={state.get('last_restart_action', 'n/a')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
