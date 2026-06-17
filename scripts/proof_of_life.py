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
SNAP_MD = ROOT / "reports" / "SERVER_SNAPSHOT_latest.md"
TG_URL_TMPL = "https://api.telegram.org/bot{token}/sendMessage"

SLEEVE_LABELS = {
    "flat": "short from resistance",
    "range": "range scalp",
    "att1": "trendline touch",
    "breakdown": "support breakdown",
    "ivb1": "old impulse breakout",
    "midterm": "BTC/ETH swing",
    "bounce1": "support bounce",
    "asb1_slope_break": "slope break",
    "elder": "Elder triple screen",
    "hzbo1": "horizontal breakout",
}

STRATEGY_TO_SLEEVE = {
    "flat_resistance_fade": "flat",
    "range": "range",
    "alt_range_scalp_v1": "range",
    "att1_trendline_touch": "att1",
    "alt_inplay_breakdown_v1": "breakdown",
    "impulse_volume_breakout_v1": "ivb1",
    "bounce1": "bounce1",
    "btc_eth_midterm": "midterm",
}


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


def _event_ts_iso(event: dict) -> str:
    raw = event.get("ts_utc")
    if raw:
        text = str(raw).strip()
        if text.endswith(" UTC"):
            return text[:-4].replace(" ", "T") + "Z"
        return text
    ts = event.get("ts")
    try:
        return dt.datetime.fromtimestamp(float(ts), tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def _latest_trade_event(events: list[dict]) -> dict | None:
    for e in reversed(events or []):
        if (e.get("event") or e.get("type")) in ("close", "entry_filled", "order_submitted"):
            return e
    return None


def _sleeve_label(name: str, risk_mult=None) -> str:
    label = SLEEVE_LABELS.get(str(name), str(name))
    suffix = f" ({name})"
    if risk_mult is None:
        return label + suffix
    return f"{label}{suffix} x{risk_mult}"


def _runtime_sets(hb: dict) -> tuple[dict, dict, list[str], list[str], list[str]]:
    rtc = hb.get("strategy_runtime_config") or {}
    enabled = rtc.get("enabled") or {}
    rmult = rtc.get("risk_mult") or {}
    live = [s for s in rmult if (rmult.get(s) or 0) > 0 and enabled.get(s)]
    shadow = [s for s in enabled if enabled.get(s) and (rmult.get(s) or 0) == 0]
    off = [s for s in enabled if not enabled.get(s)]
    return enabled, rmult, live, shadow, off


def _sleeve_for_strategy(strategy: str) -> str:
    key = str(strategy or "")
    return STRATEGY_TO_SLEEVE.get(key, key)


def _split_pnl_by_runtime(pnl: dict, live_sleeves: set[str], shadow_sleeves: set[str]) -> tuple[list[tuple[str, dict]], list[tuple[str, dict]], float, int, float, int]:
    live_rows = []
    shadow_rows = []
    live_pnl = 0.0
    live_n = 0
    all_pnl = 0.0
    all_n = 0
    for strategy, agg in (pnl or {}).items():
        if not isinstance(agg, dict):
            continue
        sleeve = _sleeve_for_strategy(strategy)
        p = float(agg.get("pnl") or 0.0)
        n = int(agg.get("n") or 0)
        all_pnl += p
        all_n += n
        row = (strategy, agg)
        if sleeve in live_sleeves:
            live_rows.append(row)
            live_pnl += p
            live_n += n
        elif sleeve in shadow_sleeves:
            shadow_rows.append(row)
    return live_rows, shadow_rows, live_pnl, live_n, all_pnl, all_n


def _maybe_refresh_snapshot() -> dict | None:
    """Use fresh runtime files when they are newer than the exported snapshot."""
    hb_path = ROOT / "runtime" / "bot_heartbeat.json"
    try:
        snap_mtime = SNAP.stat().st_mtime if SNAP.exists() else 0.0
        hb_mtime = hb_path.stat().st_mtime if hb_path.exists() else 0.0
        current_hb = json.loads(hb_path.read_text(encoding="utf-8", errors="ignore")) if hb_path.exists() else {}
        current_ts = float(current_hb.get("ts") or 0.0)
        snap_ts = 0.0
        if SNAP.exists():
            try:
                previous = json.loads(SNAP.read_text(encoding="utf-8", errors="ignore"))
                snap_ts = float((previous.get("heartbeat") or {}).get("ts") or 0.0)
            except Exception:
                snap_ts = 0.0
    except Exception:
        return None
    if hb_mtime <= snap_mtime and current_ts <= snap_ts:
        return None
    try:
        import sys
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        from scripts.export_server_snapshot import build_snapshot, to_markdown

        snap = build_snapshot()
        SNAP.parent.mkdir(exist_ok=True)
        SNAP.write_text(json.dumps(snap, indent=2, default=str), encoding="utf-8")
        SNAP_MD.write_text(to_markdown(snap), encoding="utf-8")
        return snap
    except Exception:
        return None


def _load_snapshot() -> dict:
    fresh = _maybe_refresh_snapshot()
    if fresh is not None:
        return fresh
    return json.loads(SNAP.read_text(encoding="utf-8", errors="ignore"))


def build_digest(snap: dict) -> str:
    hb = snap.get("heartbeat") or {}
    cat = snap.get("strategy_catalog") or {}
    pnl = snap.get("pnl_by_sleeve") or {}
    events = snap.get("recent_trade_events") or []
    enabled, rmult, live, shadow, off = _runtime_sets(hb)
    live_sleeves = set(live)
    shadow_sleeves = set(shadow)
    live_rows, shadow_rows, live_pnl, live_n, all_pnl, all_n = _split_pnl_by_runtime(pnl, live_sleeves, shadow_sleeves)

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
    if enabled or rmult:
        live_str = ", ".join(_sleeve_label(s, rmult.get(s)) for s in live) if live else "NONE — all shadow"
        L.append(f"LIVE (risk>0): {live_str}")
        L.append(f"shadow (enabled, risk=0): {', '.join(_sleeve_label(s) for s in shadow) if shadow else '-'}")
        L.append(f"off: {', '.join(_sleeve_label(s) for s in off) if off else '-'}")
    else:
        L.append(f"active (catalog): {', '.join(cat.get('active_keys') or []) or '-'}")

    # pnl by sleeve
    L.append("")
    L.append("-- JOURNAL P&L (tail, includes older/shadow attribution) --")
    if pnl:
        if live_rows:
            L.append("  current live-risk sleeves:")
            for s, a in live_rows:
                L.append(f"    {s}: pnl={a.get('pnl'):+.4f} trades={a.get('n')} W/L={a.get('w')}/{a.get('l')}")
        if shadow_rows:
            L.append("  enabled now but zero-risk/shadow:")
            for s, a in shadow_rows:
                L.append(f"    {s}: pnl={a.get('pnl'):+.4f} trades={a.get('n')} W/L={a.get('w')}/{a.get('l')}")
        L.append("  full journal tail:")
        for s, a in pnl.items():
            if isinstance(a, dict):
                L.append(f"    {s}: pnl={a.get('pnl'):+.4f} trades={a.get('n')} W/L={a.get('w')}/{a.get('l')}")
        L.append(f"  LIVE-risk subtotal: {live_pnl:+.4f} over {live_n} trades")
        L.append(f"  TOTAL journal tail: {all_pnl:+.4f} over {all_n} trades")
    else:
        L.append("  (no closed trades in recent journal)")

    # last trade
    last = _latest_trade_event(events)
    L.append("")
    if last:
        last_iso = _event_ts_iso(last)
        age = _age(last_iso) if last_iso else "?"
        L.append(f"last trade event: {age}: {last.get('event') or last.get('type')} {last.get('strategy')} {last.get('symbol')}")
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
    _enabled, rmult, live, shadow, _off = _runtime_sets(hb)
    msgs = hb.get("bybit_msgs")
    feed = "OK" if isinstance(msgs, (int, float)) and msgs > 0 else "STALE"
    alive = "ALIVE" if hb.get("trade_on") else "NOT TRADING"
    live_rows, _shadow_rows, live_pnl, live_n, all_pnl, all_n = _split_pnl_by_runtime(pnl, set(live), set(shadow))
    last = _latest_trade_event(snap.get("recent_trade_events") or [])
    last_line = "last trade: none in journal tail"
    if last:
        last_iso = _event_ts_iso(last)
        last_line = f"last trade: {_age(last_iso) if last_iso else '?'} {last.get('event') or last.get('type')} {last.get('strategy')} {last.get('symbol')}"
    live_line = ", ".join(_sleeve_label(s, rmult.get(s)) for s in live) if live else "NONE (all shadow)"
    shadow_line = ", ".join(shadow[:5]) + ("..." if len(shadow) > 5 else "")

    lines = [
        f"BOT PULSE — {_age(snap.get('generated_at_utc'))}",
        f"{alive} | regime={hb.get('regime')} | feed {feed} | open={hb.get('open_trades')}",
        f"risk/trade={hb.get('risk_per_trade_pct')}% | maxpos={hb.get('max_positions')} "
        f"| block={hb.get('allocator_hard_block')}",
        f"LIVE risk: {live_line}",
        f"shadow: {shadow_line or '-'}",
        last_line,
        f"P&L journal: live-risk {live_pnl:+.3f}/{live_n} trades | all tail {all_pnl:+.3f}/{all_n}",
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
    snap = _load_snapshot()
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
