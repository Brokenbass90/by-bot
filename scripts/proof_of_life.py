#!/usr/bin/env python3
"""Proof-of-life digest — a clear, honest one-screen status of the live bot.

Reads reports/SERVER_SNAPSHOT_latest.json (committed by export_server_snapshot.py)
and prints a human/AI/Telegram-friendly "is the bot alive and what is it doing"
summary. The point: make the system's REAL state visible at a glance — alive,
protected, what's live vs shadow, per-arm P&L, distance to risk limits — so
progress is tangible even before profits appear.

Additive / read-only. Run:  python scripts/proof_of_life.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from urllib import error, parse, request

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "reports" / "SERVER_SNAPSHOT_latest.json"
TG_URL_TMPL = "https://api.telegram.org/bot{token}/sendMessage"


def _age(ts_iso: str) -> str:
    try:
        t = dt.datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00"))
        secs = (dt.datetime.now(dt.timezone.utc) - t).total_seconds()
        if secs < 3600:
            return f"{int(secs//60)}m ago"
        if secs < 86400:
            return f"{secs/3600:.1f}h ago"
        return f"{secs/86400:.1f}d ago"
    except Exception:
        return "?"


def build_digest(snap: dict) -> str:
    hb = snap.get("heartbeat") or {}
    cat = snap.get("strategy_catalog") or {}
    pnl = snap.get("pnl_by_sleeve") or {}
    events = snap.get("recent_trade_events") or []
    rtc = hb.get("strategy_runtime_config") or {}

    alive = bool(hb.get("trade_on")) and (hb.get("open_trades") is not None)
    msgs = hb.get("bybit_msgs")
    feed_ok = isinstance(msgs, (int, float)) and msgs > 0

    L = []
    L.append("================ BOT PROOF-OF-LIFE ================")
    L.append(f"snapshot: {snap.get('generated_at_utc')} ({_age(snap.get('generated_at_utc'))})  git {snap.get('git_head')}")
    status = "ALIVE" if alive else "NOT TRADING"
    L.append(f"STATUS: {status} | regime={hb.get('regime')} | dry_run={hb.get('dry_run')} | open_trades={hb.get('open_trades')}")
    L.append(f"market feed: {'OK' if feed_ok else 'STALE'} (bybit_msgs={msgs}) | uptime={hb.get('uptime_s')}s")

    # risk posture
    L.append("")
    L.append("-- RISK POSTURE --")
    L.append(f"risk_per_trade={hb.get('risk_per_trade_pct')}% | max_positions={hb.get('max_positions')} "
             f"| orch_mult={hb.get('orch_global_risk_mult')} | alloc_mult={hb.get('allocator_global_risk_mult')}")
    L.append(f"allocator: hard_block={hb.get('allocator_hard_block')} safe_mode={hb.get('allocator_safe_mode')} "
             f"| max_open_portfolio_risk={hb.get('max_open_portfolio_risk_pct')}%")

    # live vs shadow
    L.append("")
    L.append("-- SLEEVES (live vs shadow) --")
    enabled = rtc.get("enabled") or {}
    rmult = rtc.get("risk_mult") or {}
    if enabled or rmult:
        live = [s for s in rmult if (rmult.get(s) or 0) > 0 and enabled.get(s)]
        shadow = [s for s in enabled if enabled.get(s) and (rmult.get(s) or 0) == 0]
        off = [s for s in enabled if not enabled.get(s)]
        live_str = ", ".join(f"{s}={rmult.get(s)}" for s in live) if live else "NONE — все в shadow"
        L.append(f"LIVE (risk>0): {live_str}")
        L.append(f"shadow (enabled, risk=0): {', '.join(shadow) if shadow else '-'}")
        L.append(f"off: {', '.join(off) if off else '-'}")
    else:
        L.append(f"active (catalog): {', '.join(cat.get('active_keys') or []) or '-'}")

    # pnl by sleeve
    L.append("")
    L.append("-- RECENT P&L BY SLEEVE (journal) --")
    if pnl:
        for s, a in pnl.items():
            if isinstance(a, dict):
                L.append(f"  {s}: pnl={a.get('pnl'):+.4f} trades={a.get('n')} W/L={a.get('w')}/{a.get('l')}")
        tot = sum(a.get("pnl", 0.0) for a in pnl.values() if isinstance(a, dict))
        L.append(f"  TOTAL recent: {tot:+.4f}")
    else:
        L.append("  (no closed trades in recent journal)")

    # last trade
    last = None
    for e in reversed(events):
        if (e.get("event") or e.get("type")) in ("close", "entry_filled", "order_submitted"):
            last = e
            break
    L.append("")
    if last:
        L.append(f"last trade event: {last.get('event') or last.get('type')} {last.get('strategy')} {last.get('symbol')}")
    L.append(f"recent events in snapshot: {len(events)}")

    # honest verdict
    L.append("")
    L.append("-- HONEST VERDICT --")
    if alive and feed_ok:
        any_live = any((rmult.get(s) or 0) > 0 and enabled.get(s) for s in rmult)
        if any_live:
            L.append("ALIVE & PROTECTED, торгует с малым риском — фаза доказательства эджа.")
        else:
            L.append("ALIVE & PROTECTED, но почти всё в SHADOW — фаза доказательства, реального риска ~нет.")
    else:
        L.append("Бот не в активной торговле — проверить trade_on / feed.")
    L.append("===================================================")
    return "\n".join(L)


def build_telegram_digest(snap: dict) -> str:
    """Compact, scannable status for a Telegram message (plain text, no emoji)."""
    hb = snap.get("heartbeat") or {}
    pnl = snap.get("pnl_by_sleeve") or {}
    rtc = hb.get("strategy_runtime_config") or {}
    enabled = rtc.get("enabled") or {}
    rmult = rtc.get("risk_mult") or {}
    live = [f"{s}={rmult.get(s)}" for s in rmult if (rmult.get(s) or 0) > 0 and enabled.get(s)]
    msgs = hb.get("bybit_msgs")
    feed = "OK" if isinstance(msgs, (int, float)) and msgs > 0 else "STALE"
    alive = "ALIVE" if hb.get("trade_on") else "NOT TRADING"
    tot = sum(a.get("pnl", 0.0) for a in pnl.values() if isinstance(a, dict)) if pnl else 0.0
    n = sum(a.get("n", 0) for a in pnl.values() if isinstance(a, dict)) if pnl else 0

    lines = [
        f"BOT PULSE — {_age(snap.get('generated_at_utc'))}",
        f"{alive} | regime={hb.get('regime')} | feed {feed} | open={hb.get('open_trades')}",
        f"risk/trade={hb.get('risk_per_trade_pct')}% | maxpos={hb.get('max_positions')} "
        f"| block={hb.get('allocator_hard_block')}",
        f"LIVE sleeves: {', '.join(live) if live else 'NONE (all shadow)'}",
        f"recent P&L: {tot:+.3f} over {n} trades",
    ]
    return "\n".join(lines)


def _send_tg(text: str) -> bool:
    """Send the compact pulse to Telegram when explicitly requested."""
    token = os.getenv("TG_TOKEN", "").strip()
    chat = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not token or not chat:
        print("TG send skipped: TG_TOKEN and TG_CHAT_ID/TG_CHAT are required")
        return False
    body = parse.urlencode({"chat_id": chat, "text": text}).encode("utf-8")
    req = request.Request(TG_URL_TMPL.format(token=token), data=body, method="POST")
    try:
        with request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("TG send ok")
        return True
    except error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="ignore")[:200]
        except Exception:
            detail = ""
        print(f"TG send failed: HTTP {exc.code} {detail}")
        return False
    except Exception as exc:
        print(f"TG send failed: {exc}")
        return False


def main():
    import sys
    if not SNAP.exists():
        print(f"no snapshot at {SNAP} — run scripts/export_server_snapshot.py first")
        return
    snap = json.loads(SNAP.read_text(encoding="utf-8", errors="ignore"))
    if "--tg" in sys.argv or "--telegram" in sys.argv:
        tg = build_telegram_digest(snap)
        print(tg)
        (ROOT / "reports" / "PROOF_OF_LIFE_telegram.txt").write_text(tg, encoding="utf-8")
        if "--send" in sys.argv or "--telegram-send" in sys.argv:
            _send_tg(tg)
        return
    digest = build_digest(snap)
    print(digest)
    (ROOT / "reports" / "PROOF_OF_LIFE_latest.txt").write_text(digest, encoding="utf-8")


if __name__ == "__main__":
    main()
