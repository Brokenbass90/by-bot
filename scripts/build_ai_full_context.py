#!/usr/bin/env python3
"""Build single AI full-context JSON for DeepSeek/Claude prompt.

Это read-only сборщик, который кладёт всё что нужно ИИ в один файл
`runtime/ai_context/full_context.json`. Скрипт ничего не торгует, не
правит .env, не делает сетевых вызовов.

После того как Codex включит этот JSON в DeepSeek prompt build
(см. bot/deepseek_signal_gate.py и bot/deepseek_advisor.py),
ИИ будет видеть:
    - текущий регим + macro
    - heartbeat counters + grouped no_signal
    - router/allocator state (dynamic universe + portfolio decisions)
    - compact crypto blocker summary (setup -> live filter)
    - setups scanner cards последние N
    - live trade events последние M
    - weekly live-vs-backtest summary
    - project doctor snapshot
    - operator snapshot

Запуск (на сервере раз в 5 минут cron):
    cd /root/by-bot && python3 scripts/build_ai_full_context.py
или с настройками:
    python3 scripts/build_ai_full_context.py \
        --out runtime/ai_context/full_context.json \
        --tail-trades 100 --tail-decisions 200 --max-setups 50

Безопасность: скрипт пишет только в runtime/ai_context/ — путь
зафиксирован, нельзя случайно перезаписать конфиг или env.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "runtime" / "ai_context" / "full_context.json"

# Все источники собраны в одну таблицу для удобства аудита.
# Каждый источник опционален: если файла нет, в JSON будет null.
SOURCES = {
    "heartbeat": "runtime/bot_heartbeat.json",
    "regime": "runtime/regime/orchestrator_state.json",
    "intraday_state": "configs/intraday_state.json",
    "trade_events": "runtime/live_trade_events.jsonl",
    "router_state": "runtime/router/symbol_router_state.json",
    "allocator_state": "runtime/control_plane/portfolio_allocator_state.json",
    "allocator_history": "runtime/control_plane/portfolio_allocator_history.jsonl",
    "allocator_decisions": "runtime/allocator_decisions.jsonl",  # пока может не существовать
    "project_doctor": "runtime/project_doctor/latest.json",
    "operator_snapshot": "runtime/operator/operator_snapshot.json",
    "self_audit": "runtime/self_audit/latest.json",
    "research_status": "runtime/research_nightly/status.json",
    "funding_carry_latest_plan": "runtime/funding_carry/latest_plan.json",
    "cross_exchange_funding": "runtime/arb/cross_exchange_funding_latest.json",
    "cross_exchange_funding_validated": "runtime/arb/cross_exchange_funding_validated.json",
    "cross_exchange_funding_shadow": "runtime/arb/cross_exchange_funding_shadow.json",
    "router_quality": "runtime/control_plane/router_quality_audit.json",
    "crypto_blocker": "runtime/crypto_blocker/latest.json",
}

SOURCE_FALLBACKS = {
    "heartbeat": ["runtime/live_mirror/bot_heartbeat.json"],
    "regime": ["runtime/live_mirror/regime/orchestrator_state.json"],
    "intraday_state": ["runtime/live_mirror/intraday_state.json"],
    "trade_events": ["runtime/live_mirror/live_trade_events.jsonl"],
}

# Куда смотрит scanner — несколько кандидатов имени файла, берём первый
# существующий.
SETUPS_PATH_CANDIDATES = [
    "runtime/setup_scanner/state.json",
    "runtime/setup_scanner_state.json",
    "runtime/live_mirror/setup_scanner_state.json",
    "runtime/setups/latest.json",
    "runtime/operator/setups_latest.json",
]

WEEKLY_REPORT_GLOB = "reports/weekly_live_vs_backtest/weekly_live_vs_backtest_*.md"


def load_json(path: Path, *, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return {"_error": f"json load: {type(exc).__name__}: {exc}"}


def source_path(key: str) -> Path:
    candidates = [SOURCES[key], *SOURCE_FALLBACKS.get(key, [])]
    for rel in candidates:
        path = REPO_ROOT / rel
        if path.exists():
            return path
    return REPO_ROOT / SOURCES[key]


def tail_jsonl(path: Path, n: int) -> list[Any]:
    if not path.exists() or n <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        return [{"_error": f"jsonl read: {type(exc).__name__}: {exc}"}]
    out: list[Any] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"_raw": line})
    return out


def find_setups_path() -> Path | None:
    for candidate in SETUPS_PATH_CANDIDATES:
        p = REPO_ROOT / candidate
        if p.exists():
            return p
    return None


def find_latest_weekly_report() -> Path | None:
    pattern = str(REPO_ROOT / WEEKLY_REPORT_GLOB)
    matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not matches:
        return None
    return Path(matches[0])


def build_setup_cards_from_runtime(max_cards: int) -> tuple[dict[str, Any], str | None]:
    """Build the same setup scanner cards as the web dashboard when no cache file exists."""
    try:
        from web.routes.data_routes import _build_setup_cards  # type: ignore
    except Exception as exc:
        return {"_warn": f"setup scanner builder import failed: {type(exc).__name__}: {exc}"}, None

    geometry_path = REPO_ROOT / "runtime" / "geometry" / "geometry_state.json"
    router_path = REPO_ROOT / "runtime" / "router" / "symbol_router_state.json"
    allocator_path = REPO_ROOT / "runtime" / "control_plane" / "portfolio_allocator_state.json"
    geometry_state = load_json(geometry_path, fallback={}) or {}
    router_state = load_json(router_path, fallback={}) or {}
    allocator_state = load_json(allocator_path, fallback={}) or {}
    if not geometry_state:
        return {
            "_warn": "geometry_state missing; cannot build setup scanner cards",
            "geometry_path": str(geometry_path.relative_to(REPO_ROOT)),
        }, None

    cards = _build_setup_cards(geometry_state, router_state, allocator_state)
    return {
        "card_count": len(cards),
        "cards_top": cards[:max_cards],
        "raw_meta": {
            "generated_at_utc": geometry_state.get("generated_at_utc"),
            "symbols_analyzed": geometry_state.get("symbols_analyzed") or len(geometry_state.get("symbols") or {}),
            "regime": router_state.get("regime") or allocator_state.get("regime"),
            "source": "runtime_geometry_router_allocator",
            "geometry_path": str(geometry_path.relative_to(REPO_ROOT)),
            "router_path": str(router_path.relative_to(REPO_ROOT)),
            "allocator_path": str(allocator_path.relative_to(REPO_ROOT)),
        },
    }, "runtime_geometry_router_allocator"


def parse_weekly_report(path: Path) -> dict[str, Any]:
    """Best-effort: вытащить headline-цифры из markdown."""
    if not path.exists():
        return {"_warn": "weekly report not found"}
    text = path.read_text(encoding="utf-8", errors="ignore")

    def find_num(pat: str) -> float | None:
        m = re.search(pat, text, re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def find_int(pat: str) -> int | None:
        v = find_num(pat)
        return int(v) if v is not None else None

    return {
        "report_path": str(path.relative_to(REPO_ROOT)),
        "live_closed_events": find_int(r"live closed events[:\s]+(\-?\d+)"),
        "backtest_entries": find_int(r"backtest entries[:\s]+(\-?\d+)"),
        "backtest_exits": find_int(r"backtest exits[:\s]+(\-?\d+)"),
        "backtest_net_pnl": find_num(r"backtest net pnl[:\s]+(\-?\d+\.?\d*)"),
        "backtest_pf": find_num(r"backtest pf[:\s]+(\-?\d+\.?\d*)"),
        "backtest_winrate_pct": find_num(r"backtest winrate[:\s]+(\-?\d+\.?\d*)\s*%"),
        "max_dd_pct": find_num(r"max drawdown[^:]*:\s*(\-?\d+\.?\d*)\s*%"),
    }


def split_counters(counters: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Группируем runtime_counters по prefix перед первым '_'."""
    groups: dict[str, dict[str, int]] = {}
    for key, val in counters.items():
        if not isinstance(key, str):
            continue
        try:
            ival = int(val or 0)
        except Exception:
            continue
        prefix = key.split("_", 1)[0]
        groups.setdefault(prefix, {})[key] = ival
    return groups


def grouped_no_signal_summary(counters: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Для каждой sleeve: топ-N grouped ns_* counters."""
    out: dict[str, dict[str, int]] = {}
    for sleeve in ("att1", "asm1", "midterm", "flat", "breakdown", "sloped",
                   "ivb1", "elder"):
        ns_keys = {
            k: int(v or 0) for k, v in counters.items()
            if isinstance(k, str) and k.startswith(f"{sleeve}_ns_")
            and isinstance(v, (int, float))
        }
        if ns_keys:
            top = dict(sorted(ns_keys.items(), key=lambda kv: -kv[1]))
            out[sleeve] = top
    return out


def compact_crypto_blocker(blocker: Any, max_cards: int = 12) -> dict[str, Any] | None:
    if not isinstance(blocker, dict) or not blocker:
        return None
    return {
        "generated_at_utc": blocker.get("generated_at_utc"),
        "cards_analyzed": blocker.get("cards_analyzed"),
        "classification_counts": blocker.get("classification_counts") or {},
        "strategy_counts": blocker.get("strategy_counts") or {},
        "sleeves": blocker.get("sleeves") or {},
        "cards_top": list(blocker.get("cards") or [])[:max_cards],
    }


def collect_strategies_inventory() -> dict[str, Any]:
    """Список файлов в strategies/, classes найти не пытаемся (быстро)."""
    strat_dir = REPO_ROOT / "strategies"
    if not strat_dir.exists():
        return {"_warn": "strategies/ not found"}
    files: list[str] = []
    for p in sorted(strat_dir.glob("*.py")):
        files.append(p.name)
    return {
        "count": len(files),
        "files": files,
    }


def collect_active_configs() -> dict[str, Any]:
    """Best-effort: какие env-файлы скорее всего активны (по последней правке)."""
    cfg_dir = REPO_ROOT / "configs"
    if not cfg_dir.exists():
        return {"_warn": "configs/ not found"}
    canary = sorted(cfg_dir.glob("crypto_income_live_canary_*.env"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    approved = cfg_dir / "approved_strategy_params.env"
    overlays = sorted(cfg_dir.glob("regime_overlay_*.env"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
    policy = sorted(cfg_dir.glob("portfolio_allocator_policy*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True)
    return {
        "latest_canary_env": canary[0].name if canary else None,
        "approved_strategy_params_env": approved.name if approved.exists() else None,
        "approved_strategy_params_age_sec": round(time.time() - approved.stat().st_mtime, 1) if approved.exists() else None,
        "regime_overlays": [p.name for p in overlays],
        "latest_policy_json": policy[0].name if policy else None,
    }


def build_context(args: argparse.Namespace) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.0",
        "repo_root": str(REPO_ROOT),
        "sources_used": {},
    }

    # ---- Heartbeat (key live source) ----
    hb_path = source_path("heartbeat")
    hb = load_json(hb_path)
    ctx["sources_used"]["heartbeat"] = str(hb_path.relative_to(REPO_ROOT)) if hb_path.exists() else None
    ctx["heartbeat"] = hb
    if isinstance(hb, dict):
        counters = hb.get("runtime_counters") or {}
        ctx["counters_by_sleeve"] = split_counters(counters)
        ctx["grouped_no_signal"] = grouped_no_signal_summary(counters)
    else:
        ctx["counters_by_sleeve"] = {}
        ctx["grouped_no_signal"] = {}

    # ---- Regime ----
    regime_path = source_path("regime")
    ctx["sources_used"]["regime"] = str(regime_path.relative_to(REPO_ROOT)) if regime_path.exists() else None
    ctx["regime"] = load_json(regime_path)

    # ---- Intraday Alpaca state ----
    intra_path = source_path("intraday_state")
    ctx["sources_used"]["intraday_state"] = str(intra_path.relative_to(REPO_ROOT)) if intra_path.exists() else None
    ctx["alpaca_intraday_state"] = load_json(intra_path)

    # ---- Trade events (tail) ----
    trades_path = source_path("trade_events")
    ctx["sources_used"]["trade_events"] = str(trades_path.relative_to(REPO_ROOT)) if trades_path.exists() else None
    ctx["live_trade_events_tail"] = tail_jsonl(trades_path, args.tail_trades)

    # ---- Router/allocator state + decisions ----
    router_state_path = source_path("router_state")
    ctx["sources_used"]["router_state"] = (
        str(router_state_path.relative_to(REPO_ROOT)) if router_state_path.exists() else None
    )
    ctx["router_state"] = load_json(router_state_path)

    alloc_state_path = source_path("allocator_state")
    ctx["sources_used"]["allocator_state"] = str(alloc_state_path.relative_to(REPO_ROOT)) if alloc_state_path.exists() else None
    ctx["allocator_state"] = load_json(alloc_state_path)
    alloc_hist_path = REPO_ROOT / SOURCES["allocator_history"]
    ctx["allocator_history_tail"] = tail_jsonl(alloc_hist_path, min(args.tail_decisions, 50))
    alloc_dec_path = REPO_ROOT / SOURCES["allocator_decisions"]
    ctx["allocator_decisions_tail"] = tail_jsonl(alloc_dec_path, args.tail_decisions)

    blocker_path = source_path("crypto_blocker")
    ctx["sources_used"]["crypto_blocker"] = (
        str(blocker_path.relative_to(REPO_ROOT)) if blocker_path.exists() else None
    )
    ctx["crypto_blocker_summary"] = compact_crypto_blocker(load_json(blocker_path))

    # ---- Project doctor + operator snapshot ----
    pd_path = source_path("project_doctor")
    ctx["sources_used"]["project_doctor"] = str(pd_path.relative_to(REPO_ROOT)) if pd_path.exists() else None
    ctx["project_doctor"] = load_json(pd_path)

    op_path = source_path("operator_snapshot")
    ctx["sources_used"]["operator_snapshot"] = str(op_path.relative_to(REPO_ROOT)) if op_path.exists() else None
    ctx["operator_snapshot"] = load_json(op_path)

    sa_path = source_path("self_audit")
    ctx["sources_used"]["self_audit"] = str(sa_path.relative_to(REPO_ROOT)) if sa_path.exists() else None
    ctx["self_audit"] = load_json(sa_path)

    # ---- Setups scanner ----
    setups_path = find_setups_path()
    if setups_path:
        ctx["sources_used"]["setups_scanner"] = str(setups_path.relative_to(REPO_ROOT))
        scanner = load_json(setups_path) or {}
        if isinstance(scanner, dict):
            cards = scanner.get("cards") or scanner.get("setups") or []
        elif isinstance(scanner, list):
            cards = scanner
        else:
            cards = []
        ctx["setups_scanner"] = {
            "card_count": len(cards) if isinstance(cards, list) else None,
            "cards_top": cards[: args.max_setups] if isinstance(cards, list) else cards,
            "raw_meta": {k: v for k, v in (scanner.items() if isinstance(scanner, dict) else [])
                         if k not in ("cards", "setups")},
        }
    else:
        built_scanner, built_source = build_setup_cards_from_runtime(args.max_setups)
        if built_source:
            ctx["sources_used"]["setups_scanner"] = built_source
            ctx["setups_scanner"] = built_scanner
        else:
            operator_snapshot = ctx.get("operator_snapshot") or {}
            op_scanner = operator_snapshot.get("setup_scanner") if isinstance(operator_snapshot, dict) else None
            if isinstance(op_scanner, dict) and op_scanner:
                top_cards = list(op_scanner.get("top_cards") or [])
                ctx["sources_used"]["setups_scanner"] = "runtime/operator/operator_snapshot.json:setup_scanner"
                ctx["setups_scanner"] = {
                    "card_count": op_scanner.get("card_count"),
                    "cards_top": top_cards[: args.max_setups],
                    "raw_meta": {k: v for k, v in op_scanner.items() if k != "top_cards"},
                    "_warn": "using operator_snapshot fallback; full scanner cache file not found",
                }
            else:
                ctx["sources_used"]["setups_scanner"] = None
                ctx["setups_scanner"] = {
                    "_warn": "setup scanner state file not found and runtime builder failed",
                    "builder_error": built_scanner,
                    "candidates": SETUPS_PATH_CANDIDATES,
                }

    # ---- Weekly live-vs-backtest ----
    weekly_path = find_latest_weekly_report()
    if weekly_path:
        ctx["sources_used"]["weekly_live_vs_backtest"] = str(weekly_path.relative_to(REPO_ROOT))
        ctx["weekly_live_vs_backtest"] = parse_weekly_report(weekly_path)
    else:
        ctx["weekly_live_vs_backtest"] = {"_warn": "no weekly report found"}

    # ---- Research status + funding ----
    rs_path = source_path("research_status")
    ctx["sources_used"]["research_status"] = str(rs_path.relative_to(REPO_ROOT)) if rs_path.exists() else None
    ctx["research_status"] = load_json(rs_path)

    fc_path = source_path("funding_carry_latest_plan")
    ctx["sources_used"]["funding_carry_latest_plan"] = str(fc_path.relative_to(REPO_ROOT)) if fc_path.exists() else None
    ctx["funding_carry_latest_plan"] = load_json(fc_path)

    xfund_path = source_path("cross_exchange_funding")
    ctx["sources_used"]["cross_exchange_funding"] = (
        str(xfund_path.relative_to(REPO_ROOT)) if xfund_path.exists() else None
    )
    xfund = load_json(xfund_path)
    if isinstance(xfund, dict) and isinstance(xfund.get("opportunities"), list):
        ctx["cross_exchange_funding"] = {
            **{k: v for k, v in xfund.items() if k != "opportunities"},
            "opportunities": xfund["opportunities"][:10],
        }
    else:
        ctx["cross_exchange_funding"] = xfund

    xfund_valid_path = source_path("cross_exchange_funding_validated")
    ctx["sources_used"]["cross_exchange_funding_validated"] = (
        str(xfund_valid_path.relative_to(REPO_ROOT)) if xfund_valid_path.exists() else None
    )
    xfund_valid = load_json(xfund_valid_path)
    if isinstance(xfund_valid, dict) and isinstance(xfund_valid.get("items"), list):
        ctx["cross_exchange_funding_validated"] = {
            **{k: v for k, v in xfund_valid.items() if k != "items"},
            "items": xfund_valid["items"][:10],
        }
    else:
        ctx["cross_exchange_funding_validated"] = xfund_valid

    xfund_shadow_path = source_path("cross_exchange_funding_shadow")
    ctx["sources_used"]["cross_exchange_funding_shadow"] = (
        str(xfund_shadow_path.relative_to(REPO_ROOT)) if xfund_shadow_path.exists() else None
    )
    xfund_shadow = load_json(xfund_shadow_path)
    if isinstance(xfund_shadow, dict):
        ctx["cross_exchange_funding_shadow"] = {
            **{k: v for k, v in xfund_shadow.items() if k not in {"open", "closed"}},
            "open": (xfund_shadow.get("open") or [])[:10],
            "closed": (xfund_shadow.get("closed") or [])[-10:],
        }
    else:
        ctx["cross_exchange_funding_shadow"] = xfund_shadow

    # ---- Static inventory ----
    ctx["strategies_inventory"] = collect_strategies_inventory()
    ctx["active_configs_hint"] = collect_active_configs()

    return ctx


def trim_for_size(ctx: dict[str, Any], max_kb: int) -> dict[str, Any]:
    """Если JSON слишком большой — обрезаем длинные секции."""
    if max_kb <= 0:
        return ctx
    blob = json.dumps(ctx, default=str)
    if len(blob) <= max_kb * 1024:
        return ctx

    # порядок trim'а: trade_events_tail, allocator_decisions_tail, allocator_history_tail, setups_top
    trim_targets = [
        ("live_trade_events_tail", 50),
        ("allocator_decisions_tail", 50),
        ("allocator_history_tail", 25),
        ("setups_scanner", "cards_top", 20),
    ]
    for spec in trim_targets:
        if isinstance(ctx.get(spec[0]), list):
            ctx[spec[0]] = ctx[spec[0]][: spec[1]]
        elif len(spec) == 3 and isinstance(ctx.get(spec[0]), dict):
            inner = ctx[spec[0]].get(spec[1])
            if isinstance(inner, list):
                ctx[spec[0]][spec[1]] = inner[: spec[2]]
        blob = json.dumps(ctx, default=str)
        if len(blob) <= max_kb * 1024:
            return ctx
    ctx["_trimmed"] = True
    return ctx


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="Output JSON path")
    ap.add_argument("--tail-trades", type=int, default=100,
                    help="How many last live_trade_events to include")
    ap.add_argument("--tail-decisions", type=int, default=200,
                    help="How many last allocator_decisions to include")
    ap.add_argument("--max-setups", type=int, default=50,
                    help="How many setup cards to include")
    ap.add_argument("--max-kb", type=int, default=500,
                    help="Soft cap on JSON size in KB (0=unlimited)")
    ap.add_argument("--quiet", action="store_true",
                    help="Don't print summary to stdout")
    args = ap.parse_args()

    out_path = Path(args.out).resolve()
    # Защита: разрешаем писать только в runtime/ai_context/ или подпапку
    allowed_root = REPO_ROOT / "runtime" / "ai_context"
    try:
        out_path.relative_to(allowed_root)
    except ValueError:
        print(f"ERROR: --out must be under {allowed_root}, got {out_path}", file=sys.stderr)
        return 2

    ctx = build_context(args)
    ctx = trim_for_size(ctx, args.max_kb)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ctx, indent=2, default=str, sort_keys=False),
                        encoding="utf-8")

    if not args.quiet:
        size_kb = out_path.stat().st_size / 1024
        hb = ctx.get("heartbeat") or {}
        regime = ctx.get("regime") or {}
        used = ctx.get("sources_used") or {}
        present = sum(1 for v in used.values() if v)
        total = len(used)
        print(f"# build_ai_full_context")
        print(f"output:        {out_path.relative_to(REPO_ROOT) if out_path.is_relative_to(REPO_ROOT) else out_path}")
        print(f"size:          {size_kb:.1f} KB")
        print(f"sources used:  {present}/{total}")
        if isinstance(hb, dict):
            print(f"regime:        {regime.get('regime') if isinstance(regime, dict) else None} "
                  f"(heartbeat={hb.get('regime')})")
            print(f"open_trades:   {hb.get('open_trades')}")
            print(f"global_risk:   {hb.get('allocator_global_risk_mult')}")
        trades = ctx.get("live_trade_events_tail") or []
        print(f"trade events:  {len(trades)} (tail)")
        setups = ctx.get("setups_scanner") or {}
        print(f"setup cards:   {setups.get('card_count')} "
              f"(top {len(setups.get('cards_top') or []) if isinstance(setups.get('cards_top'), list) else 0})")
        ns = ctx.get("grouped_no_signal") or {}
        if ns:
            print("grouped no_signal coverage:")
            for sleeve, top in ns.items():
                top3 = list(top.items())[:3]
                fmt = ", ".join(f"{k}={v}" for k, v in top3)
                print(f"  {sleeve}: {fmt}")
        missing = [k for k, v in used.items() if not v]
        if missing:
            print(f"missing sources: {', '.join(missing)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
