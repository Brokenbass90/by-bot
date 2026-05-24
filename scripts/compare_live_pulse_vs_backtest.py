#!/usr/bin/env python3
"""Compare live pulse counters vs weekly live-vs-backtest report.

Покажет, что именно блокирует каждую sleeve в текущей live‑сессии,
сопоставляя heartbeat counters со свежим weekly backtest report.

Запуск (read‑only, без побочных эффектов):

    cd /root/by-bot
    python3 scripts/compare_live_pulse_vs_backtest.py

Опционально:

    python3 scripts/compare_live_pulse_vs_backtest.py \
        --heartbeat runtime/live_mirror/bot_heartbeat.json \
        --weekly-report reports/weekly_live_vs_backtest/weekly_live_vs_backtest_20260518_184145.md \
        --json-out runtime/compare_live_vs_bt_latest.json

Источники:
    - runtime/live_mirror/bot_heartbeat.json  (runtime_counters, regime, allocator status)
    - reports/weekly_live_vs_backtest/weekly_live_vs_backtest_<TS>.md (последний по mtime если не указан)
    - runtime/live_mirror/regime/orchestrator_state.json
    - configs/<active>.env через grep ENABLE_*_TRADING (best‑effort)

Вывод:
    Печатает таблицу
        sleeve | live_try | live_entries | bt_entries_7d | dominant_block_reason | classification
    и JSON, если задан --json-out.

Никаких .env правок, никаких рестартов, никаких сетевых вызовов.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


SLEEVE_KEY_MAP = {
    "att1": {"try_key": "att1_try", "no_signal_key": "att1_no_signal", "ns_prefix": "att1_ns_"},
    "asm1": {"try_key": "asm1_try", "no_signal_key": "asm1_no_signal", "ns_prefix": "asm1_ns_"},
    "midterm": {"try_key": "midterm_try", "no_signal_key": "midterm_no_signal", "ns_prefix": "midterm_ns_"},
    "flat": {"try_key": "flat_try", "no_signal_key": "flat_no_signal", "ns_prefix": "flat_ns_"},
    "breakdown": {"try_key": "breakdown_try", "no_signal_key": "breakdown_no_signal", "ns_prefix": "breakdown_ns_"},
    "sloped": {"try_key": "sloped_try", "no_signal_key": "sloped_no_signal", "ns_prefix": "sloped_ns_"},
}


@dataclass
class SleeveReport:
    sleeve: str
    enabled_env: str  # "yes" | "no" | "unknown"
    sched_count: int
    try_count: int
    no_signal: int
    entries_est: int
    skip_portfolio: int
    skip_global_risk: int
    skip_max_positions: int
    skip_overlap: int
    skip_portfolio_other: int
    skip_details: dict[str, int]
    skip_cooldown: int
    ns_breakdown: dict[str, int]
    dominant_block_reason: str
    classification: str
    bt_entries_7d: int | None
    bt_pf_7d: float | None
    notes: list[str]


def load_heartbeat(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_existing_path(path: Path, fallbacks: list[Path]) -> Path | None:
    if path.exists():
        return path
    for fallback in fallbacks:
        if fallback.exists():
            return fallback
    return None


def load_regime(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def find_latest_weekly_report() -> Path | None:
    pattern = str(REPO_ROOT / "reports" / "weekly_live_vs_backtest" / "weekly_live_vs_backtest_*.md")
    matches = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not matches:
        return None
    return Path(matches[0])


def parse_weekly_report(path: Path) -> dict[str, Any]:
    """Очень best-effort парсер: вытаскиваем основные цифры из markdown."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")

    def find_num(pattern: str) -> float | None:
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def find_int(pattern: str) -> int | None:
        v = find_num(pattern)
        return int(v) if v is not None else None

    summary = {
        "report_path": str(path),
        "live_closed_events": find_int(r"live closed events[:\s]+(\-?\d+)"),
        "backtest_entries": find_int(r"backtest entries[:\s]+(\-?\d+)"),
        "backtest_exits": find_int(r"backtest exits[:\s]+(\-?\d+)"),
        "backtest_net_pnl": find_num(r"backtest net pnl[:\s]+(\-?\d+\.?\d*)"),
        "backtest_pf": find_num(r"backtest pf[:\s]+(\-?\d+\.?\d*)"),
        "backtest_winrate_pct": find_num(r"backtest winrate[:\s]+(\-?\d+\.?\d*)\s*%"),
        "max_dd_pct": find_num(r"max drawdown[^:]*:\s*(\-?\d+\.?\d*)\s*%"),
    }

    # Sleeve‑level per‑strategy bt_entries — если есть таблица «strategy | entries» в отчёте
    sleeve_entries: dict[str, int] = {}
    # ищем строки вида | alt_inplay_breakdown_v1 | 2 |  (или похожие)
    for line in text.splitlines():
        m = re.match(r"\|\s*(alt_[\w_]+|btc_eth_midterm[\w_]*)\s*\|\s*(\d+)\s*\|", line)
        if m:
            strat = m.group(1).strip().lower()
            count = int(m.group(2))
            # map strategy name → sleeve guess
            if "inplay_breakdown" in strat or "breakdown" in strat:
                sleeve = "breakdown"
            elif "resistance_fade" in strat or "flat" in strat:
                sleeve = "flat"
            elif "trendline_touch" in strat or "att1" in strat:
                sleeve = "att1"
            elif "spike" in strat or "asm1" in strat or "volume_spike" in strat:
                sleeve = "asm1"
            elif "midterm" in strat:
                sleeve = "midterm"
            elif "sloped" in strat or "channel" in strat:
                sleeve = "sloped"
            else:
                continue
            sleeve_entries[sleeve] = sleeve_entries.get(sleeve, 0) + count
    summary["per_sleeve_bt_entries"] = sleeve_entries
    return summary


def detect_enabled_env_for_sleeve(sleeve: str, env_files: list[Path]) -> str:
    """Best-effort: ищем ENABLE_<SLEEVE>_TRADING=0|1 в активных env."""
    pattern_map = {
        "att1": r"ENABLE_ATT1_TRADING",
        "asm1": r"ENABLE_ASM1_TRADING",
        "midterm": r"ENABLE_MIDTERM_TRADING",
        "flat": r"ENABLE_FLAT_TRADING",
        "breakdown": r"ENABLE_BREAKDOWN_TRADING",
        "sloped": r"ENABLE_SLOPED_TRADING",
    }
    pat = pattern_map.get(sleeve)
    if not pat:
        return "unknown"
    for env_file in env_files:
        if not env_file.exists():
            continue
        try:
            text = env_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        m = re.search(rf"^\s*{pat}\s*=\s*([01])\s*(?:#.*)?$", text, re.MULTILINE)
        if m:
            return "yes" if m.group(1) == "1" else "no"
    return "unknown"


def classify(sr: SleeveReport, regime: str | None) -> tuple[str, str]:
    """Вернуть (dominant_block_reason, classification)."""
    if sr.enabled_env == "no":
        return ("env_disabled", "disabled_in_env")

    if sr.try_count == 0:
        if sr.sched_count > 0:
            return ("scheduled_no_try_yet", "scheduled_waiting_engine_counters")
        return ("no_attempts", "no_attempts_check_scheduler")

    no_entry_hour = int(sr.skip_details.get("no_entry_hour", 0) or 0)
    effective_portfolio_skip = max(0, sr.skip_portfolio - no_entry_hour)
    if effective_portfolio_skip > sr.try_count * 1.5:
        buckets = {
            "global_risk": max(0, sr.skip_global_risk - no_entry_hour),
            "max_positions": sr.skip_max_positions,
            "overlap": sr.skip_overlap,
            "portfolio_other": sr.skip_portfolio_other,
        }
        top_bucket, top_count = max(buckets.items(), key=lambda kv: kv[1])
        if top_count > 0:
            return (f"skip_{top_bucket}_dominant", f"portfolio_{top_bucket}")
        return ("skip_portfolio_dominant", "portfolio_unknown")

    # если no_signal ≈ try_count → конверсия 0
    if sr.no_signal and sr.try_count and sr.no_signal >= sr.try_count * 0.95:
        # смотрим какой ns_* доминирует
        if sr.ns_breakdown:
            top = max(sr.ns_breakdown.items(), key=lambda kv: kv[1])
            reason_key, reason_count = top
            if "same_bar" in reason_key:
                return (reason_key, "same_bar_artifact")
            if "first_bar" in reason_key:
                return (reason_key, "first_bar_init_window")
            if "history" in reason_key:
                return (reason_key, "needs_more_history")
            if "macro" in reason_key:
                return (reason_key, "macro_filter_block")
            if "trend" in reason_key:
                return (reason_key, "trend_filter_block")
            if "rsi" in reason_key:
                return (reason_key, "rsi_filter_block")
            if "zone" in reason_key or "trigger" in reason_key:
                return (reason_key, "true_no_signal_market")
            if "atr" in reason_key:
                return (reason_key, "atr_out_of_range")
            if "volume" in reason_key:
                return (reason_key, "volume_filter_block")
            if "blank" in reason_key or "unknown" in reason_key:
                return (reason_key, "reason_attribution_missing")
            return (reason_key, "true_no_signal_market")
        return ("no_grouped_counters", "needs_grouped_counters_first")

    if sr.skip_cooldown > sr.try_count * 0.8:
        return ("skip_cooldown_dominant", "cooldown_bound")

    return ("mixed", "mixed_review_per_pulse")


def build_sleeve_report(
    sleeve: str,
    counters: dict[str, Any],
    bt_summary: dict[str, Any],
    enabled_env: str,
    regime: str | None,
) -> SleeveReport:
    cfg = SLEEVE_KEY_MAP[sleeve]
    sched_count = int(counters.get(f"{sleeve}_sched", 0) or 0)
    try_count = int(counters.get(cfg["try_key"], 0) or 0)
    no_signal = int(counters.get(cfg["no_signal_key"], 0) or 0)
    skip_portfolio = int(counters.get(f"{sleeve}_skip_portfolio", 0) or 0)
    skip_global_risk = int(counters.get(f"{sleeve}_skip_global_risk", 0) or 0)
    skip_max_positions = int(counters.get(f"{sleeve}_skip_max_positions", 0) or 0)
    skip_overlap = int(counters.get(f"{sleeve}_skip_overlap", 0) or 0)
    skip_portfolio_other = int(counters.get(f"{sleeve}_skip_portfolio_other", 0) or 0)
    skip_cooldown = int(counters.get(f"{sleeve}_skip_cooldown", 0) or 0)
    known_skip_keys = {
        f"{sleeve}_skip_portfolio",
        f"{sleeve}_skip_global_risk",
        f"{sleeve}_skip_max_positions",
        f"{sleeve}_skip_overlap",
        f"{sleeve}_skip_portfolio_other",
        f"{sleeve}_skip_cooldown",
    }
    skip_details = {}
    for k, v in counters.items():
        if not isinstance(k, str) or not k.startswith(f"{sleeve}_skip_") or k in known_skip_keys:
            continue
        try:
            iv = int(v or 0)
        except Exception:
            continue
        if iv > 0:
            skip_details[k.removeprefix(f"{sleeve}_skip_")] = iv
    entries_est = max(0, try_count - no_signal - skip_portfolio - skip_cooldown)

    ns_break = {}
    for k, v in counters.items():
        if isinstance(k, str) and k.startswith(cfg["ns_prefix"]):
            try:
                ns_break[k] = int(v or 0)
            except Exception:
                continue

    bt_entries_7d = None
    bt_pf_7d = None
    per_sleeve = bt_summary.get("per_sleeve_bt_entries") or {}
    if sleeve in per_sleeve:
        bt_entries_7d = per_sleeve[sleeve]
    bt_pf_7d = bt_summary.get("backtest_pf")

    sr = SleeveReport(
        sleeve=sleeve,
        enabled_env=enabled_env,
        sched_count=sched_count,
        try_count=try_count,
        no_signal=no_signal,
        entries_est=entries_est,
        skip_portfolio=skip_portfolio,
        skip_global_risk=skip_global_risk,
        skip_max_positions=skip_max_positions,
        skip_overlap=skip_overlap,
        skip_portfolio_other=skip_portfolio_other,
        skip_details=skip_details,
        skip_cooldown=skip_cooldown,
        ns_breakdown=ns_break,
        dominant_block_reason="",
        classification="",
        bt_entries_7d=bt_entries_7d,
        bt_pf_7d=bt_pf_7d,
        notes=[],
    )
    sr.dominant_block_reason, sr.classification = classify(sr, regime)

    if sr.ns_breakdown:
        total_ns = sum(sr.ns_breakdown.values())
        if no_signal and abs(total_ns - no_signal) > max(5, no_signal * 0.05):
            sr.notes.append(
                f"ns_breakdown sum {total_ns} != no_signal {no_signal} "
                "(grouped counters не покрывают все return-точки)"
            )
    elif no_signal > 50:
        sr.notes.append("нет grouped no-signal counters — добавить ns_* split")
    if sr.skip_details:
        top_details = sorted(sr.skip_details.items(), key=lambda kv: -kv[1])[:5]
        sr.notes.append(
            "portfolio skip detail: "
            + ", ".join(f"{k}={v}" for k, v in top_details)
        )

    return sr


def format_table(reports: list[SleeveReport]) -> str:
    headers = [
        "sleeve", "env", "sched", "try", "no_sig", "entry_est",
        "skip_port", "skip_glob", "skip_max", "skip_ovr",
        "skip_cd", "bt_e7d", "bt_pf", "dominant", "class",
    ]
    rows = []
    for r in reports:
        rows.append([
            r.sleeve,
            r.enabled_env,
            str(r.sched_count),
            str(r.try_count),
            str(r.no_signal),
            str(r.entries_est),
            str(r.skip_portfolio),
            str(r.skip_global_risk),
            str(r.skip_max_positions),
            str(r.skip_overlap),
            str(r.skip_cooldown),
            "-" if r.bt_entries_7d is None else str(r.bt_entries_7d),
            "-" if r.bt_pf_7d is None else f"{r.bt_pf_7d:.3f}",
            r.dominant_block_reason,
            r.classification,
        ])
    widths = [max(len(h), *(len(row[i]) for row in rows)) for i, h in enumerate(headers)]
    line = " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers))
    sep = "-+-".join("-" * w for w in widths)
    out = [line, sep]
    for row in rows:
        out.append(" | ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--heartbeat",
        default=str(REPO_ROOT / "runtime" / "live_mirror" / "bot_heartbeat.json"),
        help="path to bot_heartbeat.json",
    )
    ap.add_argument(
        "--weekly-report",
        default=None,
        help="path to weekly_live_vs_backtest_*.md (default: latest by mtime)",
    )
    ap.add_argument(
        "--regime",
        default=str(REPO_ROOT / "runtime" / "live_mirror" / "regime" / "orchestrator_state.json"),
        help="path to orchestrator_state.json",
    )
    ap.add_argument(
        "--env-files",
        nargs="*",
        default=[
            str(REPO_ROOT / "configs" / "portfolio_allocator_latest.env"),
            str(REPO_ROOT / ".env"),
            str(REPO_ROOT / "configs" / "crypto_income_live_canary_v2_2_rescue.env"),
            str(REPO_ROOT / "configs" / "regime_overlay_bear_chop.env"),
            str(REPO_ROOT / "configs" / "regime_overlay_bull_chop.env"),
        ],
        help="env files where ENABLE_*_TRADING is searched",
    )
    ap.add_argument("--json-out", default=None, help="write structured JSON to this path")
    args = ap.parse_args()

    requested_hb_path = Path(args.heartbeat)
    hb_path = resolve_existing_path(
        requested_hb_path,
        [
            REPO_ROOT / "runtime" / "bot_heartbeat.json",
            REPO_ROOT / "runtime" / "live_mirror" / "bot_heartbeat.json",
        ],
    )
    if hb_path is None:
        print(f"ERROR: heartbeat not found: {requested_hb_path}", file=sys.stderr)
        return 2

    hb = load_heartbeat(hb_path)
    counters = hb.get("runtime_counters") or {}
    requested_regime_path = Path(args.regime)
    regime_path = resolve_existing_path(
        requested_regime_path,
        [
            REPO_ROOT / "runtime" / "regime" / "orchestrator_state.json",
            REPO_ROOT / "runtime" / "live_mirror" / "regime" / "orchestrator_state.json",
        ],
    )
    regime_data = load_regime(regime_path) if regime_path else {}
    regime = (
        regime_data.get("regime")
        or hb.get("regime")
        or "unknown"
    )

    weekly_path = Path(args.weekly_report) if args.weekly_report else find_latest_weekly_report()
    bt_summary = parse_weekly_report(weekly_path) if weekly_path else {}

    env_files = [Path(p) for p in args.env_files]

    reports: list[SleeveReport] = []
    for sleeve in SLEEVE_KEY_MAP.keys():
        enabled = detect_enabled_env_for_sleeve(sleeve, env_files)
        sr = build_sleeve_report(sleeve, counters, bt_summary, enabled, regime)
        reports.append(sr)

    print(f"# compare_live_pulse_vs_backtest")
    print(f"heartbeat:    {hb_path}")
    print(f"weekly_rep:   {weekly_path or '(not found)'}")
    print(f"regime:       {regime}")
    print(f"allocator:    global_risk={hb.get('allocator_global_risk_mult')} "
          f"hard_block={hb.get('allocator_hard_block')} safe_mode={hb.get('allocator_safe_mode')}")
    print(f"open_trades:  {hb.get('open_trades')}")
    print(f"dry_run:      {hb.get('dry_run')}")
    if bt_summary:
        print(f"bt_summary:   live_events={bt_summary.get('live_closed_events')} "
              f"bt_entries={bt_summary.get('backtest_entries')} "
              f"bt_pf={bt_summary.get('backtest_pf')} "
              f"bt_winrate%={bt_summary.get('backtest_winrate_pct')} "
              f"maxDD%={bt_summary.get('max_dd_pct')}")
    print()
    print(format_table(reports))
    print()

    for r in reports:
        if r.notes:
            print(f"[note:{r.sleeve}]")
            for note in r.notes:
                print(f"  - {note}")

    print()
    print("# Recommendations (auto):")
    for r in reports:
        cls = r.classification
        if cls == "disabled_in_env":
            print(f"  {r.sleeve}: disabled in env — это намеренно? Если да, исключить из metric ожиданий.")
        elif cls == "no_attempts_check_scheduler":
            print(f"  {r.sleeve}: 0 attempts — проверить scheduler, universe, или sleeve scheduling.")
        elif cls == "scheduled_waiting_engine_counters":
            print(f"  {r.sleeve}: scheduler active ({r.sched_count}), но try/skip counters ещё не накопились — ждать следующую свечу/entry gate.")
        elif cls.startswith("portfolio_"):
            print(
                f"  {r.sleeve}: portfolio blocker — total={r.skip_portfolio}, "
                f"global={r.skip_global_risk}, max={r.skip_max_positions}, "
                f"overlap={r.skip_overlap}, other={r.skip_portfolio_other}."
            )
        elif cls == "same_bar_artifact":
            print(f"  {r.sleeve}: same_bar dominant — verify candle alignment (closed vs open).")
        elif cls == "first_bar_init_window":
            print(f"  {r.sleeve}: first_bar — sample ещё мал, подождать ≥1 час.")
        elif cls == "needs_grouped_counters_first":
            print(f"  {r.sleeve}: добавить grouped *_ns_* counters прежде чем тюнить фильтры.")
        elif cls == "macro_filter_block":
            print(f"  {r.sleeve}: macro filter режет — корректно для текущего регима {regime}? "
                  "Если да, не трогать; если нет — отдельный backtest.")
        elif cls == "trend_filter_block":
            print(f"  {r.sleeve}: trend filter — пересчитать threshold с backtest на 60+ дней.")
        elif cls == "true_no_signal_market":
            print(f"  {r.sleeve}: рыночная реальность — нет setups сейчас. Не трогаем фильтры.")
        elif cls == "reason_attribution_missing":
            print(f"  {r.sleeve}: причина '{r.dominant_block_reason}' — добавить более детальный mapping.")
        else:
            print(f"  {r.sleeve}: {cls}")

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "heartbeat_path": str(hb_path),
            "weekly_report_path": str(weekly_path) if weekly_path else None,
            "regime": regime,
            "allocator": {
                "global_risk_mult": hb.get("allocator_global_risk_mult"),
                "hard_block": hb.get("allocator_hard_block"),
                "safe_mode": hb.get("allocator_safe_mode"),
            },
            "open_trades": hb.get("open_trades"),
            "dry_run": hb.get("dry_run"),
            "backtest_summary": bt_summary,
            "sleeves": [asdict(r) for r in reports],
        }
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        print(f"\nWrote JSON: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
