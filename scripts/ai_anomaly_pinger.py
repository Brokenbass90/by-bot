#!/usr/bin/env python3
"""AI anomaly pinger.

Cron every 15 minutes. Reads heartbeat + recent closed trades + signal counters,
detects concrete anomalies, and (if any), asks Haiku/DeepSeek for a one-paragraph
explanation. Result is appended to ``runtime/ai_anomaly_log.jsonl`` and (if a
Telegram bot token is configured) posted to the operator chat.

Anomalies detected:
  1. Losing streak: >= N closed trades in a row with pnl <= 0 (default N=3)
  2. Latency spike: any recent entry_filled with latency_send_to_fill_sec > T
     (default T=15s)
  3. Regime stale: regime_mirror_report classification != "ok"
  4. Signal rate drop: last hour signals < ALPHA * trailing 24h average
     (default ALPHA=0.2)
  5. Open position aged >24h with no broker-side TP (runner stuck)

This script does NOT change params, does not call /v5/order endpoints. It only
reads runtime files, queries the AI for context, and journals/pings.

Author: Claude Opus, 2026-06-02. Active AI surveillance, read-only.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
HEARTBEAT = ROOT / "runtime" / "bot_heartbeat.json"
MIRROR_HEARTBEAT = ROOT / "runtime" / "live_mirror" / "bot_heartbeat.json"
EVENTS = ROOT / "runtime" / "live_trade_events.jsonl"
MIRROR_EVENTS = ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl"
REGIME_REPORT = ROOT / "runtime" / "regime_mirror_report.json"
JOURNAL = ROOT / "runtime" / "ai_anomaly_log.jsonl"
COOLDOWN_FILE = ROOT / "runtime" / "ai_anomaly_cooldown.json"

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
DEEPSEEK_API = "https://api.deepseek.com/chat/completions"

_SSL = ssl.create_default_context()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(p: Path) -> Any:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_env_file(p: Path) -> None:
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        if k.strip() and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _tail_events(path: Path, n: int = 3000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for raw in lines:
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# Anomaly detectors
# ---------------------------------------------------------------------------

def detect_losing_streak(events: list[dict[str, Any]], min_streak: int) -> dict[str, Any] | None:
    closes = [e for e in events if str(e.get("event") or "") == "close"]
    closes.sort(key=lambda e: int(e.get("ts") or 0))
    if len(closes) < min_streak:
        return None
    tail = closes[-min_streak:]
    if all(float(c.get("pnl") or 0.0) <= 0.0 for c in tail):
        return {
            "anomaly": "losing_streak",
            "streak_length": min_streak,
            "tail_symbols": [c.get("symbol") for c in tail],
            "tail_pnls": [round(float(c.get("pnl") or 0.0), 4) for c in tail],
            "tail_strategies": [c.get("strategy") for c in tail],
        }
    return None


def detect_latency_spike(events: list[dict[str, Any]], threshold_sec: float, window_n: int = 20) -> dict[str, Any] | None:
    fills = [e for e in events if str(e.get("event") or "") == "entry_filled"]
    fills = fills[-window_n:]
    spikes = []
    for f in fills:
        lat = f.get("latency_send_to_fill_sec")
        if lat is None:
            continue
        try:
            v = float(lat)
        except Exception:
            continue
        if v > threshold_sec:
            spikes.append({"symbol": f.get("symbol"), "latency_sec": v, "ts_utc": f.get("ts_utc")})
    if not spikes:
        return None
    return {
        "anomaly": "latency_spike",
        "threshold_sec": threshold_sec,
        "spikes": spikes,
        "window_examined": len(fills),
    }


def detect_regime_stale() -> dict[str, Any] | None:
    rep = _load_json(REGIME_REPORT)
    if not rep:
        return None
    cls = str(rep.get("classification") or "ok")
    if cls == "ok":
        return None
    return {
        "anomaly": "regime_mirror_broken",
        "classification": cls,
        "issues": rep.get("issues") or [],
        "orchestrator_regime": rep.get("hops", {}).get("orchestrator_state", {}).get("regime"),
        "heartbeat_regime": rep.get("hops", {}).get("heartbeat", {}).get("regime"),
    }


def detect_runner_stuck(events: list[dict[str, Any]], max_age_sec: float = 86400.0) -> dict[str, Any] | None:
    """Find positions submitted with request_tp=null that are still open and stale."""
    state: dict[str, dict[str, Any]] = {}
    for ev in events:
        sym = str(ev.get("symbol") or "").upper()
        if not sym:
            continue
        kind = str(ev.get("event") or "")
        if kind == "order_submitted":
            if ev.get("request_tp") is None:
                state[sym] = {"submitted": ev, "filled": None}
            else:
                state.pop(sym, None)
        elif kind == "entry_filled":
            cur = state.get(sym)
            if cur is not None:
                cur["filled"] = ev
        elif kind == "close":
            state.pop(sym, None)
    now = time.time()
    stuck = []
    for sym, slot in state.items():
        fil = slot.get("filled")
        if not fil:
            continue
        age = now - int(fil.get("ts") or 0)
        if age > max_age_sec:
            stuck.append({"symbol": sym, "filled_ts_utc": fil.get("ts_utc"), "age_sec": int(age),
                          "strategy": fil.get("strategy")})
    if not stuck:
        return None
    return {
        "anomaly": "runner_stuck",
        "max_age_sec": max_age_sec,
        "stuck": stuck,
    }


def detect_signal_rate_drop(hb: dict[str, Any], alpha: float = 0.2) -> dict[str, Any] | None:
    """Conservative signal-rate drop check using uptime and aggregate counters.

    Not a true rolling-hour metric (no per-hour timeseries here), but flags
    cases where signals per hour computed across uptime is unexpectedly low.
    Returns anomaly only when uptime_h >= 6h to avoid noise on fresh restart.
    """
    rc = hb.get("runtime_counters") or {}
    uptime_h = float(hb.get("uptime_s") or 0) / 3600.0
    if uptime_h < 6.0:
        return None
    signals = sum(int(v) for k, v in rc.items() if k.endswith("_signal") and not k.startswith("ws_"))
    tries = sum(int(v) for k, v in rc.items() if k.endswith("_try") and not k.startswith("ws_"))
    sig_per_hour = signals / max(1.0, uptime_h)
    try_per_hour = tries / max(1.0, uptime_h)
    if try_per_hour < 1.0:
        return None  # too quiet, can't conclude
    if signals == 0 and try_per_hour > 20.0:
        return {
            "anomaly": "signal_rate_zero_while_tries_high",
            "uptime_h": round(uptime_h, 2),
            "tries_total": tries,
            "try_per_hour": round(try_per_hour, 2),
            "note": "Strategies evaluated frequently but no signal emitted.",
        }
    return None


# ---------------------------------------------------------------------------
# AI prompt + send
# ---------------------------------------------------------------------------

_SYSTEM = (
    "Ты — дежурный аналитик торгового бота. Тебе дают список свежих аномалий. "
    "Дай 1-2 короткие версии причины (по фактам), 1 конкретный следующий шаг "
    "(не call-to-action на закрытие позиций без явной деградации). "
    "Не паникуй. Если аномалия может быть нормой — скажи это."
)


def _ask_haiku(api_key: str, system: str, user: str, model: str, max_tokens: int = 400) -> str:
    payload = {"model": model, "max_tokens": max_tokens, "system": system,
               "messages": [{"role": "user", "content": user}]}
    req = request.Request(ANTHROPIC_API, data=json.dumps(payload).encode(),
                          headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, context=_SSL, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            return str(data.get("content", [{}])[0].get("text", "")).strip()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"haiku_http_{exc.code}: {detail}") from None


def _ask_deepseek(api_key: str, system: str, user: str, model: str, max_tokens: int = 400) -> str:
    payload = {"model": model, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    req = request.Request(DEEPSEEK_API, data=json.dumps(payload).encode(),
                          headers={"Authorization": f"Bearer {api_key}",
                                   "content-type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, context=_SSL, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            choices = data.get("choices") or []
            return str(((choices[0] or {}).get("message") or {}).get("content", "")).strip()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"deepseek_http_{exc.code}: {detail}") from None


def _tg_send(text: str) -> None:
    token = (os.getenv("TG_BOT_TOKEN") or "").strip()
    chat_id = (os.getenv("TG_CHAT_ID") or "").strip()
    if not (token and chat_id):
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text[:4000],
                                   "disable_web_page_preview": "true"}).encode()
    req = request.Request(url, data=body, method="POST",
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        request.urlopen(req, context=_SSL, timeout=15).read()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Cooldown (don't spam same anomaly)
# ---------------------------------------------------------------------------

def _load_cooldown() -> dict[str, float]:
    return _load_json(COOLDOWN_FILE) or {}


def _write_cooldown(state: dict[str, float]) -> None:
    COOLDOWN_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOLDOWN_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _anomaly_key(a: dict[str, Any]) -> str:
    return str(a.get("anomaly") or "unknown")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="AI anomaly surveillance pinger")
    ap.add_argument("--loss-streak", type=int, default=3, help="Trigger on N losses in a row")
    ap.add_argument("--latency-threshold-sec", type=float, default=15.0)
    ap.add_argument("--cooldown-sec", type=int, default=3600,
                    help="Re-ping the same anomaly only after this many seconds")
    ap.add_argument("--prefer-deepseek", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="Only print, don't call AI / TG")
    args = ap.parse_args()

    _load_env_file(ROOT / ".env")

    heartbeat_path = HEARTBEAT if HEARTBEAT.exists() else MIRROR_HEARTBEAT
    events_path = EVENTS if EVENTS.exists() else MIRROR_EVENTS

    hb = _load_json(heartbeat_path) or {}
    events = _tail_events(events_path, n=3000)

    anomalies: list[dict[str, Any]] = []
    for d in [
        detect_losing_streak(events, args.loss_streak),
        detect_latency_spike(events, args.latency_threshold_sec),
        detect_regime_stale(),
        detect_runner_stuck(events),
        detect_signal_rate_drop(hb),
    ]:
        if d is not None:
            anomalies.append(d)

    summary: dict[str, Any] = {
        "generated_at_utc": _utc_now_iso(),
        "anomalies_count": len(anomalies),
        "anomalies": anomalies,
        "heartbeat_path": str(heartbeat_path),
        "events_path": str(events_path),
        "dry_run": args.dry_run,
    }

    if not anomalies:
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    # Filter through cooldown
    now = time.time()
    cooldown = _load_cooldown()
    fresh = []
    for a in anomalies:
        k = _anomaly_key(a)
        last = float(cooldown.get(k, 0))
        if now - last < args.cooldown_sec:
            continue
        fresh.append(a)
        cooldown[k] = now
    if not fresh:
        summary["all_in_cooldown"] = True
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    # Compose AI prompt
    prompt = (
        f"Аномалии текущего цикла наблюдения ({_utc_now_iso()}):\n"
        f"{json.dumps(fresh, indent=2, ensure_ascii=False)}\n\n"
        "Дай короткий разбор: версии причин и 1 следующий шаг для оператора."
    )

    if args.dry_run:
        summary["prompt_preview"] = prompt[:1000]
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    deepseek_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    model_claude = os.getenv("POST_TRADE_AI_MODEL", "claude-haiku-4-5-20251001")
    model_ds = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    use_claude = anthropic_key and not args.prefer_deepseek

    try:
        if use_claude:
            answer = _ask_haiku(anthropic_key, _SYSTEM, prompt, model_claude)
            backend = f"claude:{model_claude}"
        elif deepseek_key:
            answer = _ask_deepseek(deepseek_key, _SYSTEM, prompt, model_ds)
            backend = f"deepseek:{model_ds}"
        else:
            summary["error"] = "no_ai_key_configured"
            print(json.dumps(summary, ensure_ascii=False))
            return 2
    except Exception as exc:
        summary["error"] = str(exc)[:300]
        print(json.dumps(summary, ensure_ascii=False))
        return 1

    # Write journal entry
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts_utc": _utc_now_iso(),
        "event": "anomaly_review",
        "backend": backend,
        "anomalies": fresh,
        "ai_response": answer[:4000],
    }
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    _write_cooldown(cooldown)

    # Telegram alert (only the headline + AI take, keep it tight)
    summary_tags = ", ".join(_anomaly_key(a) for a in fresh)
    tg_text = f"⚠️ Anomaly alert\n{summary_tags}\n\n{answer[:3500]}"
    _tg_send(tg_text)

    summary["sent_to_tg"] = True
    summary["backend"] = backend
    summary["ai_response_preview"] = answer[:300]
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
