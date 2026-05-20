#!/usr/bin/env python3
"""Build a read-only scanner -> strategy blocker report.

The report answers the practical live question:

    setup scanner sees a candidate -> is the mapped live sleeve enabled ->
    did that sleeve evaluate recently -> what no-signal bucket dominates?

It writes only to runtime/crypto_blocker/ and never changes trading state.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"_error": f"{type(exc).__name__}: {exc}"}


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except Exception:
        return default


def _setup_cards() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    geometry_path = ROOT / "runtime" / "geometry" / "geometry_state.json"
    router_path = ROOT / "runtime" / "router" / "symbol_router_state.json"
    allocator_path = ROOT / "runtime" / "control_plane" / "portfolio_allocator_state.json"
    geometry_state = _load_json(geometry_path, {}) or {}
    router_state = _load_json(router_path, {}) or {}
    allocator_state = _load_json(allocator_path, {}) or {}
    meta = {
        "geometry_path": str(geometry_path.relative_to(ROOT)),
        "router_path": str(router_path.relative_to(ROOT)),
        "allocator_path": str(allocator_path.relative_to(ROOT)),
        "geometry_present": bool(geometry_state),
        "router_present": bool(router_state),
        "allocator_present": bool(allocator_state),
    }
    if not geometry_state:
        op = _load_json(ROOT / "runtime" / "operator" / "operator_snapshot.json", {}) or {}
        scanner = op.get("setup_scanner") if isinstance(op, dict) else {}
        cards = list((scanner or {}).get("top_cards") or [])
        meta["source"] = "operator_snapshot_fallback"
        meta["fallback_card_count"] = (scanner or {}).get("card_count")
        return cards, meta

    try:
        from web.routes.data_routes import _build_setup_cards  # type: ignore
    except Exception as exc:
        meta["source"] = "import_failed"
        meta["error"] = f"{type(exc).__name__}: {exc}"
        return [], meta

    cards = _build_setup_cards(geometry_state, router_state, allocator_state)
    meta["source"] = "geometry_router_allocator"
    meta["card_count"] = len(cards)
    return cards, meta


def _runtime_counters() -> dict[str, int]:
    hb_path = ROOT / "runtime" / "bot_heartbeat.json"
    if not hb_path.exists():
        hb_path = ROOT / "runtime" / "live_mirror" / "bot_heartbeat.json"
    hb = _load_json(hb_path, {}) or {}
    counters = hb.get("runtime_counters") if isinstance(hb, dict) else {}
    if not isinstance(counters, dict):
        return {}
    return {str(k): _as_int(v) for k, v in counters.items()}


def _allocator_sleeves() -> dict[str, dict[str, Any]]:
    path = ROOT / "runtime" / "control_plane" / "portfolio_allocator_state.json"
    state = _load_json(path, {}) or {}
    sleeves = state.get("sleeves") if isinstance(state, dict) else {}
    if isinstance(sleeves, dict):
        return {str(k): v for k, v in sleeves.items() if isinstance(v, dict)}
    return {}


STRATEGY_PREFIX = {
    "flat": "flat",
    "asb1": "asb1",
    "att1": "att1",
    "asm1": "asm1",
    "breakout": "breakdown",
    "breakdown": "breakdown",
    "sloped": "sloped",
    "midterm": "midterm",
    "brc1": "brc1",
    "ivb1": "ivb1",
}


def _prefix_for(card: dict[str, Any]) -> str:
    strategy = str(card.get("strategy") or "").strip().lower()
    return STRATEGY_PREFIX.get(strategy, strategy)


def _top_ns(counters: dict[str, int], prefix: str, limit: int = 6) -> list[dict[str, Any]]:
    rows = []
    for key, value in counters.items():
        if key.startswith(f"{prefix}_ns_") and value > 0:
            rows.append({"reason": key.removeprefix(f"{prefix}_ns_"), "count": value})
    rows.sort(key=lambda x: -int(x["count"]))
    return rows[:limit]


def _sleeve_snapshot(counters: dict[str, int], prefix: str) -> dict[str, Any]:
    tries = counters.get(f"{prefix}_try", 0)
    entries = counters.get(f"{prefix}_entry", 0)
    no_signal = counters.get(f"{prefix}_no_signal", 0)
    ns = _top_ns(counters, prefix)
    top_reason = ns[0]["reason"] if ns else ""
    same_bar = sum(r["count"] for r in ns if r["reason"] in {"same_bar", "cooldown", "first_bar"})
    evaluated_ns = max(0, no_signal - same_bar)
    status = "no_recent_eval"
    if entries > 0:
        status = "entries_seen"
    elif tries > 0 and no_signal > 0:
        status = "seen_but_no_signal"
    elif tries > 0:
        status = "seen_no_entry_counter"
    return {
        "prefix": prefix,
        "try": tries,
        "entry": entries,
        "no_signal": no_signal,
        "evaluated_no_signal_est": evaluated_ns,
        "top_no_signal": ns,
        "dominant_reason": top_reason,
        "status": status,
    }


def _classify_card(
    card: dict[str, Any],
    sleeve: dict[str, Any],
    allocator_sleeve: dict[str, Any] | None = None,
) -> str:
    runtime = card.get("runtime") if isinstance(card.get("runtime"), dict) else {}
    alloc = allocator_sleeve if isinstance(allocator_sleeve, dict) else {}
    enabled = bool(alloc.get("enabled")) if alloc else bool(runtime.get("enabled"))
    risk = _as_float(alloc.get("final_risk_mult"), 0.0) if alloc else _as_float(runtime.get("risk_mult"), 0.0)
    if not enabled or risk <= 0:
        return "blocked_runtime_disabled_or_zero_risk"
    symbols = {str(x).strip().upper() for x in (alloc.get("symbols") or []) if str(x).strip()}
    symbol = str(card.get("symbol") or "").strip().upper()
    if symbols and symbol and symbol not in symbols:
        return "blocked_by_symbol_allowlist"
    if sleeve["status"] == "no_recent_eval":
        return "scanner_not_confirmed_by_live_counter"
    if sleeve["status"] == "entries_seen":
        return "live_entries_seen_for_sleeve"
    top = str(sleeve.get("dominant_reason") or "")
    if top in {"same_bar", "cooldown", "first_bar"}:
        return "diagnostic_noise_same_bar_or_cooldown"
    if top:
        return f"blocked_by_{top}"
    return "seen_but_reason_missing"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    cards, scanner_meta = _setup_cards()
    counters = _runtime_counters()
    allocator_sleeves = _allocator_sleeves()
    by_prefix = {prefix: _sleeve_snapshot(counters, prefix) for prefix in sorted(set(STRATEGY_PREFIX.values()))}

    card_rows = []
    class_counts: Counter[str] = Counter()
    strategy_counts: Counter[str] = Counter()
    for card in cards[: args.max_cards]:
        prefix = _prefix_for(card)
        sleeve = by_prefix.get(prefix) or _sleeve_snapshot(counters, prefix)
        allocator_sleeve = allocator_sleeves.get(prefix) or {}
        allocator_symbols = [str(x).strip().upper() for x in (allocator_sleeve.get("symbols") or []) if str(x).strip()]
        card_symbol = str(card.get("symbol") or "").strip().upper()
        symbol_in_allocator = bool(card_symbol and card_symbol in set(allocator_symbols))
        classification = _classify_card(card, sleeve, allocator_sleeve)
        class_counts[classification] += 1
        strategy_counts[str(card.get("strategy") or "unknown")] += 1
        card_rows.append({
            "symbol": card.get("symbol"),
            "interval": card.get("interval"),
            "setup_type": card.get("setup_type"),
            "side": card.get("side"),
            "strategy": card.get("strategy"),
            "score": card.get("score"),
            "runtime": card.get("runtime"),
            "classification": classification,
            "sleeve": sleeve,
            "allocator_enabled": allocator_sleeve.get("enabled"),
            "allocator_risk_mult": allocator_sleeve.get("final_risk_mult"),
            "allocator_symbols": allocator_symbols,
            "symbol_in_allocator": symbol_in_allocator,
            "reasons": card.get("reasons") or [],
        })

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.0",
        "scanner": scanner_meta,
        "cards_analyzed": len(card_rows),
        "classification_counts": dict(class_counts),
        "strategy_counts": dict(strategy_counts),
        "sleeves": by_prefix,
        "cards": card_rows,
        "notes": [
            "This report is read-only and does not approve trades.",
            "If classification is diagnostic_noise_same_bar_or_cooldown, add per-symbol evaluated counters before changing strategy filters.",
            "If classification is blocked_runtime_disabled_or_zero_risk, check allocator/policy before strategy code.",
        ],
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Crypto Setup Blocker Report",
        "",
        f"generated_at_utc: `{report['generated_at_utc']}`",
        f"cards_analyzed: `{report['cards_analyzed']}`",
        "",
        "## Classification Counts",
        "",
    ]
    for key, value in sorted((report.get("classification_counts") or {}).items(), key=lambda kv: -kv[1]):
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Top Cards", ""])
    for card in list(report.get("cards") or [])[:30]:
        sleeve = card.get("sleeve") or {}
        top = list(sleeve.get("top_no_signal") or [])[:3]
        top_txt = ", ".join(f"{x['reason']}={x['count']}" for x in top) or "-"
        runtime = card.get("runtime") or {}
        allocator_symbols = list(card.get("allocator_symbols") or [])
        symbol_status = "in" if card.get("symbol_in_allocator") else "out"
        lines.append(
            f"- `{card.get('symbol')}` `{card.get('interval')}` `{card.get('setup_type')}` "
            f"`{card.get('side')}` strategy=`{card.get('strategy')}` score=`{card.get('score')}` "
            f"class=`{card.get('classification')}` enabled=`{runtime.get('enabled')}` "
            f"risk=`{runtime.get('risk_mult')}` allocator_symbol=`{symbol_status}` "
            f"allocator_symbols=`{','.join(allocator_symbols[:10])}` sleeve_try=`{sleeve.get('try')}` "
            f"sleeve_no_signal=`{sleeve.get('no_signal')}` top_ns=`{top_txt}`"
        )
    lines.extend(["", "## Notes", ""])
    for note in report.get("notes") or []:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", default=str(ROOT / "runtime" / "crypto_blocker"))
    ap.add_argument("--max-cards", type=int, default=80)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).resolve()
    allowed = ROOT / "runtime" / "crypto_blocker"
    try:
        out_dir.relative_to(allowed)
    except ValueError:
        print(f"ERROR: --out-dir must be under {allowed}", file=sys.stderr)
        return 2

    report = build_report(args)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "latest.json"
    md_path = out_dir / "latest.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(report, md_path)

    if not args.quiet:
        print(f"json={json_path.relative_to(ROOT)}")
        print(f"md={md_path.relative_to(ROOT)}")
        print(f"cards={report['cards_analyzed']}")
        print(f"classifications={report.get('classification_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
