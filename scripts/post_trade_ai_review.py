#!/usr/bin/env python3
"""Post-trade AI review.

After each closed trade, send a compact lifecycle summary to a cheap LLM
(Haiku by default, DeepSeek fallback) and ask:

    1. What is present in the recorded lifecycle and review-time snapshots?
    2. What signal would have been obvious in hindsight?
    3. Pattern code (1-3 short tags) for future grouping.
    4. Win/loss honest verdict on the strategy, not just the outcome.

The model answer is appended to ``runtime/ai_trade_journal.jsonl``. Nothing
changes in trading — this is a learning journal.

A small offset file ``runtime/ai_trade_journal_offset.json`` tracks the last
processed close event so the script is idempotent under cron.

Cost: ~50-200 tokens per review on Haiku. Budget cap via
``POST_TRADE_AI_DAILY_REVIEWS`` (default 50).

Usage::

    python3 scripts/post_trade_ai_review.py             # process new closes
    python3 scripts/post_trade_ai_review.py --dry-run   # show what would be sent
    python3 scripts/post_trade_ai_review.py --limit 5   # cap one run

Author: Claude Opus, 2026-06-02. Read-only AI learning loop.
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
EVENTS = ROOT / "runtime" / "live_trade_events.jsonl"
MIRROR_EVENTS = ROOT / "runtime" / "live_mirror" / "live_trade_events.jsonl"
JOURNAL = ROOT / "runtime" / "ai_trade_journal.jsonl"
OFFSET = ROOT / "runtime" / "ai_trade_journal_offset.json"
FULL_CTX = ROOT / "runtime" / "ai_context" / "full_context.json"
OHLC_CTX = ROOT / "runtime" / "ai_context" / "ohlc_and_logs.json"

DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
DEEPSEEK_API = "https://api.deepseek.com/chat/completions"

_SSL = ssl.create_default_context()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_env_file(p: Path) -> None:
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def _load_json(p: Path) -> Any:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AI clients
# ---------------------------------------------------------------------------

def _haiku_ask(api_key: str, system: str, user: str, model: str, max_tokens: int = 600) -> str:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = request.Request(
        ANTHROPIC_API,
        data=json.dumps(payload).encode(),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, context=_SSL, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            return str(data.get("content", [{}])[0].get("text", "")).strip()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"haiku_http_{exc.code}: {detail}") from None


def _deepseek_ask(api_key: str, system: str, user: str, model: str, max_tokens: int = 600) -> str:
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = request.Request(
        DEEPSEEK_API,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, context=_SSL, timeout=45) as resp:
            data = json.loads(resp.read().decode())
            choices = data.get("choices") or []
            return str(((choices[0] or {}).get("message") or {}).get("content", "")).strip()
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"deepseek_http_{exc.code}: {detail}") from None


# ---------------------------------------------------------------------------
# Trade lifecycle rebuild
# ---------------------------------------------------------------------------

def _read_offset() -> dict[str, Any]:
    return _load_json(OFFSET) or {"last_close_ts": 0, "today_count": 0, "today_utc": ""}


def _write_offset(state: dict[str, Any]) -> None:
    OFFSET.parent.mkdir(parents=True, exist_ok=True)
    OFFSET.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _tail_events(path: Path, n: int = 5000) -> list[dict[str, Any]]:
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


def _build_lifecycles(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pair order_submitted + entry_filled + close into one record per closed trade."""
    by_oid: dict[str, dict[str, Any]] = {}
    closes: list[dict[str, Any]] = []
    for ev in events:
        oid = str(ev.get("entry_order_id") or "")
        kind = str(ev.get("event") or "")
        if kind == "order_submitted" and oid:
            by_oid[oid] = {"submitted": ev, "filled": None}
        elif kind == "entry_filled" and oid:
            slot = by_oid.setdefault(oid, {"submitted": None, "filled": None})
            slot["filled"] = ev
        elif kind == "close":
            cur = dict(by_oid.get(oid, {}))
            cur["close"] = ev
            closes.append(cur)
    return closes


def _scanner_setup_for(symbol: str) -> dict[str, Any] | None:
    ctx = _load_json(FULL_CTX) or {}
    setup = ctx.get("setups_scanner") if isinstance(ctx.get("setups_scanner"), dict) else {}
    for card in (setup.get("cards_top") or []):
        if not isinstance(card, dict):
            continue
        if str(card.get("symbol") or "").upper() == symbol.upper():
            return {
                "score": card.get("score"),
                "side": card.get("side"),
                "setup_type": card.get("setup_type"),
                "reasons": list(card.get("reasons") or [])[:4],
            }
    return None


def _ohlc_for(symbol: str) -> dict[str, Any] | None:
    ctx = _load_json(OHLC_CTX) or {}
    ohlc = ctx.get("ohlc") if isinstance(ctx.get("ohlc"), dict) else {}
    return ohlc.get(symbol) or ohlc.get(symbol.upper())


def _compact_trade_for_ai(lc: dict[str, Any]) -> dict[str, Any]:
    sub = lc.get("submitted") or {}
    fil = lc.get("filled") or {}
    cls = lc.get("close") or {}
    symbol = str(cls.get("symbol") or fil.get("symbol") or sub.get("symbol") or "").upper()
    return {
        "symbol": symbol,
        "strategy": cls.get("strategy") or fil.get("strategy") or sub.get("strategy"),
        "signal_reason": cls.get("signal_reason") or sub.get("signal_reason"),
        "side": cls.get("side") or fil.get("side") or sub.get("side"),
        "entry_price": fil.get("fill_price") or fil.get("entry_price") or sub.get("entry_price"),
        "exit_price": cls.get("exit_price"),
        "sl_price": cls.get("sl_price") or fil.get("sl_price"),
        "tp_price": cls.get("tp_price"),
        "close_reason": cls.get("close_reason"),
        "pnl_usd": cls.get("pnl"),
        "fees_usd": cls.get("fees"),
        "entry_notional_usd": cls.get("entry_notional_usd") or sub.get("entry_notional_usd"),
        "entry_ts_utc": fil.get("ts_utc") or sub.get("ts_utc"),
        "exit_ts_utc": cls.get("ts_utc"),
        "latency_sig_to_send_sec": fil.get("latency_sig_to_send_sec"),
        "latency_send_to_fill_sec": fil.get("latency_send_to_fill_sec"),
        "duration_sec": int(cls.get("ts", 0)) - int(fil.get("ts", 0)) if cls.get("ts") and fil.get("ts") else None,
        "context_timing": "review_time_not_entry_time",
        "scanner_setup_at_review_time": _scanner_setup_for(symbol),
        "ohlc_top_at_review_time": _ohlc_for(symbol),
    }


# ---------------------------------------------------------------------------
# Review prompt
# ---------------------------------------------------------------------------

_SYSTEM = (
    "Ты — senior квант-аналитик. Тебе дают закрытую сделку алго-бота на Bybit perpetuals. "
    "Твоя задача — холодный разбор:\n"
    "1. Что подтверждено жизненным циклом сделки и снимками на момент разбора?\n"
    "2. Какие факторы из ПЕРЕДАННЫХ данных могли повлиять на исход?\n"
    "3. Это качественная победа/проигрыш стратегии или удача/неудача?\n"
    "4. Pattern code: 1-3 коротких тега (например `bear_chop_short_runner_win` или `low_atr_chop_stopped`).\n"
    "Отвечай строго в JSON: "
    '{"setup_visibility":"...","hidden_factors":"...","quality_verdict":"win_quality|loss_quality|lucky_win|unlucky_loss","pattern_tags":["..."],"one_line_lesson":"..."}\n'
    "Не выдумывай новости, листинги, макро-события, ликвидность или время-сезонность, если их нет во входных данных. "
    "Поля scanner_setup_at_review_time и ohlc_top_at_review_time сняты ПОСЛЕ сделки: "
    "не используй их как доказательство того, что было видно на входе. "
    "Для неизвестных факторов пиши `unknown_from_snapshot`. "
    "Будь краток. Не пиши markdown, не объясняй что такое JSON."
)


def _format_user(trade: dict[str, Any]) -> str:
    return "Сделка:\n" + json.dumps(trade, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Post-trade AI review (one entry per closed trade)")
    ap.add_argument("--limit", type=int, default=20, help="Max reviews per run")
    ap.add_argument("--dry-run", action="store_true", help="Print prompts, do not call AI")
    ap.add_argument("--max-token-budget", type=int, default=600, help="max_tokens per review")
    ap.add_argument("--prefer-deepseek", action="store_true",
                    help="Use DeepSeek even if Anthropic key present")
    args = ap.parse_args()

    _load_env_file(ROOT / ".env")
    daily_cap = int(os.getenv("POST_TRADE_AI_DAILY_REVIEWS", "50"))

    offset = _read_offset()
    if offset.get("today_utc") != _today_utc():
        offset = {"last_close_ts": offset.get("last_close_ts", 0), "today_count": 0, "today_utc": _today_utc()}

    events_path = EVENTS if EVENTS.exists() else MIRROR_EVENTS
    events = _tail_events(events_path, n=5000)
    closes = [lc for lc in _build_lifecycles(events)
              if int(((lc.get("close") or {}).get("ts") or 0)) > int(offset.get("last_close_ts", 0))]
    closes.sort(key=lambda lc: int(((lc.get("close") or {}).get("ts") or 0)))

    summary: dict[str, Any] = {
        "generated_at_utc": _utc_now_iso(),
        "events_path": str(events_path),
        "candidates_total": len(closes),
        "processed": 0,
        "skipped_budget": 0,
        "errors": 0,
        "dry_run": bool(args.dry_run),
    }

    if not closes:
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    deepseek_key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    claude_model = os.getenv("POST_TRADE_AI_MODEL", DEFAULT_CLAUDE_MODEL)
    ds_model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)

    use_claude = anthropic_key and not args.prefer_deepseek
    use_deepseek = deepseek_key and (args.prefer_deepseek or not anthropic_key)
    if not args.dry_run and not (use_claude or use_deepseek):
        summary["error"] = "no_ai_key_configured"
        print(json.dumps(summary, ensure_ascii=False))
        return 2

    JOURNAL.parent.mkdir(parents=True, exist_ok=True)

    for lc in closes[: args.limit]:
        if offset["today_count"] >= daily_cap:
            summary["skipped_budget"] += 1
            continue
        compact = _compact_trade_for_ai(lc)
        prompt = _format_user(compact)

        if args.dry_run:
            print("--- DRY RUN ---")
            print(json.dumps(compact, indent=2, ensure_ascii=False))
            summary["processed"] += 1
            offset["last_close_ts"] = int(((lc.get("close") or {}).get("ts") or 0))
            continue

        try:
            if use_claude:
                answer = _haiku_ask(anthropic_key, _SYSTEM, prompt, claude_model, args.max_token_budget)
                backend = f"claude:{claude_model}"
            else:
                answer = _deepseek_ask(deepseek_key, _SYSTEM, prompt, ds_model, args.max_token_budget)
                backend = f"deepseek:{ds_model}"
        except Exception as exc:
            summary["errors"] += 1
            entry = {
                "ts_utc": _utc_now_iso(),
                "event": "review_failed",
                "symbol": compact["symbol"],
                "error": str(exc)[:200],
                "trade": compact,
            }
            with JOURNAL.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            continue

        # Try to parse model JSON answer; tolerate plain text.
        parsed: Any
        try:
            parsed = json.loads(answer)
        except Exception:
            parsed = {"_raw": answer}

        entry = {
            "ts_utc": _utc_now_iso(),
            "event": "review",
            "backend": backend,
            "trade": compact,
            "review": parsed,
        }
        with JOURNAL.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

        summary["processed"] += 1
        offset["today_count"] += 1
        offset["last_close_ts"] = int(((lc.get("close") or {}).get("ts") or 0))
        # tiny politeness pause
        time.sleep(0.5)

    _write_offset(offset)
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
