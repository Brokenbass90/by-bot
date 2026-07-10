#!/usr/bin/env python3
"""Pre-registered ATT1 exit/regime A/B runner.

Research-only. It does not touch live configs, keys, orders, or server state.

Why this exists:
  * ADA exposed a runner execution incident that was fixed separately.
  * LTC/DOT then showed a different failure: entries did not reach 1R, so
    breakeven/trailing never armed.
  * This runner tests whether the ATT1 money sleeve needs a different exit
    model and/or a trend-only regime gate before any risk increase.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOLS = "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT"

FALLBACK_ATT1_ENV = {
    "ATT1_SYMBOL_ALLOWLIST": DEFAULT_SYMBOLS,
    "ATT1_ALLOW_LONGS": "0",
    "ATT1_ALLOW_SHORTS": "1",
    "ATT1_RSI_SHORT_MIN": "45",
}

VARIANTS: dict[str, dict[str, str]] = {
    "base": {
        "ATT1_TP1_RR": "1.20",
        "ATT1_TP2_RR": "2.50",
        "ATT1_TP1_FRAC": "0.55",
        "ATT1_BE_TRIGGER_RR": "1.00",
        "ATT1_TRAIL_ACTIVATE_RR": "1.00",
        "ATT1_TRAIL_ATR_MULT": "1.50",
    },
    "small_tp1": {
        "ATT1_TP1_RR": "1.20",
        "ATT1_TP2_RR": "2.50",
        "ATT1_TP1_FRAC": "0.33",
        "ATT1_BE_TRIGGER_RR": "1.00",
        "ATT1_TRAIL_ACTIVATE_RR": "1.00",
        "ATT1_TRAIL_ATR_MULT": "1.50",
    },
    "early_be_05": {
        "ATT1_TP1_RR": "1.20",
        "ATT1_TP2_RR": "2.50",
        "ATT1_TP1_FRAC": "0.55",
        "ATT1_BE_TRIGGER_RR": "0.50",
        "ATT1_TRAIL_ACTIVATE_RR": "0.50",
        "ATT1_TRAIL_ATR_MULT": "1.50",
    },
    "early_be_03": {
        "ATT1_TP1_RR": "1.20",
        "ATT1_TP2_RR": "2.50",
        "ATT1_TP1_FRAC": "0.55",
        "ATT1_BE_TRIGGER_RR": "0.30",
        "ATT1_TRAIL_ACTIVATE_RR": "0.30",
        "ATT1_TRAIL_ATR_MULT": "1.50",
    },
    # Approximation of "no fixed TP": targets are intentionally unreachable in
    # normal trades, so exits come from SL/trailing/time-stop. Kept as research
    # only because live runner currently expects a ladder.
    "pure_trail": {
        "ATT1_TP1_RR": "50.00",
        "ATT1_TP2_RR": "100.00",
        "ATT1_TP1_FRAC": "0.10",
        "ATT1_BE_TRIGGER_RR": "1.00",
        "ATT1_TRAIL_ACTIVATE_RR": "1.00",
        "ATT1_TRAIL_ATR_MULT": "1.50",
    },
}

REGIME_MODES: dict[str, dict[str, str]] = {
    "all_regimes": {
        "REGIME_ROUTER_ENABLE": "0",
    },
    "trend_only": {
        "REGIME_ROUTER_ENABLE": "1",
        "REGIME_TREND_STRATEGIES": "alt_trendline_touch_v1",
        "REGIME_FLAT_STRATEGIES": "",
    },
}


def _load_env_file(path: Path) -> dict[str, str]:
    """Load simple KEY=VALUE env files without shell evaluation."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


@dataclass
class FoldRun:
    variant: str
    regime_mode: str
    fold: int
    end_date: str
    out_dir: Path
    trades: int
    net_pnl: float
    profit_factor: float
    winrate: float
    max_drawdown: float
    reasons: dict[str, int]
    returncode: int


def _parse_date(s: str) -> datetime:
    if not s:
        return datetime.now(timezone.utc)
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _read_summary(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return rows[0] if rows else {}


def _read_trades(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
    except Exception:
        return default
    return v if math.isfinite(v) else default


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _profit_factor_from_trades(trades: list[dict[str, str]]) -> float:
    wins = sum(max(0.0, _safe_float(t.get("pnl"))) for t in trades)
    losses = -sum(min(0.0, _safe_float(t.get("pnl"))) for t in trades)
    if losses <= 0:
        return float("inf") if wins > 0 else 0.0
    return wins / losses


def _reasons_from_trades(trades: list[dict[str, str]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in trades:
        reason = str(row.get("reason") or "?")
        out[reason] = out.get(reason, 0) + 1
    return out


def run_case(
    *,
    variant: str,
    regime_mode: str,
    fold: int,
    end_date: str,
    days: int,
    symbols: str,
    fee_bps: float,
    slippage_bps: float,
    entry_on_next_open: bool,
    cache_only: bool,
    cache_dir: str,
    base_env: dict[str, str],
) -> FoldRun:
    env = os.environ.copy()
    env.update(FALLBACK_ATT1_ENV)
    env.update(base_env)
    env.update(VARIANTS[variant])
    env.update(REGIME_MODES[regime_mode])
    if cache_only:
        env["BACKTEST_CACHE_ONLY"] = "1"
        env["BACKTEST_CACHE_FALLBACK_ENABLE"] = "1"

    tag = f"att1_exit_ab_20260710_{variant}_{regime_mode}_f{fold}"
    cmd = [
        sys.executable,
        "backtest/run_portfolio.py",
        "--symbols",
        symbols,
        "--strategies",
        "alt_trendline_touch_v1",
        "--days",
        str(days),
        "--end",
        end_date,
        "--tag",
        tag,
        "--starting_equity",
        "1000",
        "--risk_pct",
        "0.0044",
        "--leverage",
        "3",
        "--max_positions",
        "3",
        "--fee_bps",
        str(fee_bps),
        "--slippage_bps",
        str(slippage_bps),
        "--cache",
        cache_dir,
    ]
    if entry_on_next_open:
        cmd.append("--entry-on-next-open")

    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    out_dir: Path | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("Saved portfolio run to:"):
            out_dir = ROOT / line.split(":", 1)[1].strip()
            break
    if out_dir is None:
        raise RuntimeError(
            f"run_portfolio did not report output dir for {tag}; rc={proc.returncode}\n{proc.stdout[-4000:]}"
        )

    summary = _read_summary(out_dir / "summary.csv")
    trades = _read_trades(out_dir / "trades.csv")
    return FoldRun(
        variant=variant,
        regime_mode=regime_mode,
        fold=fold,
        end_date=end_date,
        out_dir=out_dir,
        trades=_safe_int(summary.get("trades")),
        net_pnl=_safe_float(summary.get("net_pnl")),
        profit_factor=_profit_factor_from_trades(trades),
        winrate=_safe_float(summary.get("winrate")),
        max_drawdown=_safe_float(summary.get("max_drawdown")),
        reasons=_reasons_from_trades(trades),
        returncode=int(proc.returncode),
    )


def _aggregate(rows: list[FoldRun]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[FoldRun]] = {}
    for row in rows:
        grouped.setdefault((row.variant, row.regime_mode), []).append(row)

    out: list[dict[str, Any]] = []
    for (variant, regime_mode), group in sorted(grouped.items()):
        trades = sum(r.trades for r in group)
        net = sum(r.net_pnl for r in group)
        pos_folds = sum(1 for r in group if r.net_pnl > 0)
        pf = _profit_factor_from_trades(
            [
                {"pnl": str(pnl)}
                for r in group
                for pnl in _fold_trade_pnls(r.out_dir / "trades.csv")
            ]
        )
        reasons: dict[str, int] = {}
        for r in group:
            for k, v in r.reasons.items():
                reasons[k] = reasons.get(k, 0) + v
        out.append(
            {
                "variant": variant,
                "regime_mode": regime_mode,
                "folds": len(group),
                "positive_folds": pos_folds,
                "trades": trades,
                "net_pnl": net,
                "profit_factor": pf,
                "avg_winrate": sum(r.winrate for r in group) / max(1, len(group)),
                "max_drawdown_worst": max((r.max_drawdown for r in group), default=0.0),
                "reasons": reasons,
            }
        )
    return sorted(out, key=lambda x: (_safe_float(x["profit_factor"]), x["net_pnl"]), reverse=True)


def _fold_trade_pnls(path: Path) -> list[float]:
    return [_safe_float(row.get("pnl")) for row in _read_trades(path)]


def write_outputs(out_dir: Path, rows: list[FoldRun], agg: list[dict[str, Any]], args: argparse.Namespace) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    folds_csv = out_dir / "folds.csv"
    with folds_csv.open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(
            [
                "variant",
                "regime_mode",
                "fold",
                "end_date",
                "trades",
                "net_pnl",
                "profit_factor",
                "winrate",
                "max_drawdown",
                "reasons_json",
                "out_dir",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r.variant,
                    r.regime_mode,
                    r.fold,
                    r.end_date,
                    r.trades,
                    f"{r.net_pnl:.6f}",
                    "inf" if math.isinf(r.profit_factor) else f"{r.profit_factor:.6f}",
                    f"{r.winrate:.6f}",
                    f"{r.max_drawdown:.6f}",
                    json.dumps(r.reasons, sort_keys=True),
                    str(r.out_dir),
                ]
            )

    summary_csv = out_dir / "summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(
            [
                "variant",
                "regime_mode",
                "folds",
                "positive_folds",
                "trades",
                "net_pnl",
                "profit_factor",
                "avg_winrate",
                "max_drawdown_worst",
                "reasons_json",
            ]
        )
        for r in agg:
            w.writerow(
                [
                    r["variant"],
                    r["regime_mode"],
                    r["folds"],
                    r["positive_folds"],
                    r["trades"],
                    f"{r['net_pnl']:.6f}",
                    "inf" if math.isinf(float(r["profit_factor"])) else f"{r['profit_factor']:.6f}",
                    f"{r['avg_winrate']:.6f}",
                    f"{r['max_drawdown_worst']:.6f}",
                    json.dumps(r["reasons"], sort_keys=True),
                ]
            )

    verdict = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "promotion": False,
        "reason": "diagnostic_ab_only_no_live_change",
        "args": vars(args),
        "best": agg[0] if agg else None,
        "rows": agg,
    }
    (out_dir / "verdict.json").write_text(json.dumps(verdict, indent=2, sort_keys=True), encoding="utf-8")

    lines = [
        "# ATT1 Exit/Regime A/B 2026-07-10",
        "",
        "Research-only. No live config/order/risk change.",
        "",
        f"- symbols: `{args.symbols}`",
        f"- folds: `{args.folds}` x `{args.fold_days}` days, end `{args.end}`",
        f"- costs: fee `{args.fee_bps}` bps, slippage `{args.slippage_bps}` bps, next-open `{args.entry_on_next_open}`",
        "",
        "| variant | regime | folds+ | trades | net pnl | PF | winrate | top exits |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in agg:
        reasons = ", ".join(f"{k}:{v}" for k, v in sorted(r["reasons"].items(), key=lambda kv: kv[1], reverse=True)[:4])
        pf = r["profit_factor"]
        pf_s = "inf" if math.isinf(float(pf)) else f"{float(pf):.3f}"
        lines.append(
            f"| {r['variant']} | {r['regime_mode']} | {r['positive_folds']}/{r['folds']} | "
            f"{r['trades']} | {r['net_pnl']:.2f} | {pf_s} | {r['avg_winrate']:.3f} | {reasons} |"
        )
    lines.extend(
        [
            "",
            "Promotion rule for later review: no live change unless a variant beats base on PF/net, has enough trades, and holds across folds.",
            "This runner intentionally does not decide promotion by itself.",
        ]
    )
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", default=DEFAULT_SYMBOLS)
    ap.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--fold-days", type=int, default=180)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--fee-bps", type=float, default=6.0)
    ap.add_argument("--slippage-bps", type=float, default=2.0)
    ap.add_argument("--entry-on-next-open", action="store_true", default=True)
    ap.add_argument("--cache-only", action="store_true", default=True)
    ap.add_argument("--cache-dir", default="data_cache")
    ap.add_argument("--env-file", default="configs/att1_short_r001_canary_20260702.env")
    ap.add_argument("--variants", default=",".join(VARIANTS))
    ap.add_argument("--regime-modes", default=",".join(REGIME_MODES))
    ap.add_argument("--out-dir", default="")
    ap.add_argument("--max-runs", type=int, default=0, help="For smoke tests only.")
    args = ap.parse_args()

    variants = [x.strip() for x in args.variants.split(",") if x.strip()]
    regimes = [x.strip() for x in args.regime_modes.split(",") if x.strip()]
    for v in variants:
        if v not in VARIANTS:
            raise SystemExit(f"unknown variant: {v}")
    for r in regimes:
        if r not in REGIME_MODES:
            raise SystemExit(f"unknown regime mode: {r}")

    end_dt = _parse_date(args.end)
    folds: list[tuple[int, str]] = []
    for idx in range(args.folds):
        # Chronological folds from old -> recent.
        offset = args.folds - idx - 1
        fold_end = end_dt - timedelta(days=offset * int(args.fold_days))
        folds.append((idx + 1, fold_end.strftime("%Y-%m-%d")))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "reports" / "research" / f"att1_exit_regime_ab_20260710_{stamp}"
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    base_env = _load_env_file(env_file)

    rows: list[FoldRun] = []
    run_count = 0
    for variant in variants:
        for regime in regimes:
            for fold, fold_end in folds:
                run_count += 1
                if args.max_runs and run_count > args.max_runs:
                    break
                print(
                    json.dumps(
                        {
                            "event": "run_start",
                            "variant": variant,
                            "regime": regime,
                            "fold": fold,
                            "end": fold_end,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                row = run_case(
                    variant=variant,
                    regime_mode=regime,
                    fold=fold,
                    end_date=fold_end,
                    days=int(args.fold_days),
                    symbols=args.symbols,
                    fee_bps=float(args.fee_bps),
                    slippage_bps=float(args.slippage_bps),
                    entry_on_next_open=bool(args.entry_on_next_open),
                    cache_only=bool(args.cache_only),
                    cache_dir=str(args.cache_dir),
                    base_env=base_env,
                )
                rows.append(row)
                print(
                    json.dumps(
                        {
                            "event": "run_done",
                            "variant": row.variant,
                            "regime": row.regime_mode,
                            "fold": row.fold,
                            "trades": row.trades,
                            "net": round(row.net_pnl, 6),
                            "pf": "inf" if math.isinf(row.profit_factor) else round(row.profit_factor, 6),
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            if args.max_runs and run_count > args.max_runs:
                break
        if args.max_runs and run_count > args.max_runs:
            break

    agg = _aggregate(rows)
    write_outputs(out_dir, rows, agg, args)
    print(json.dumps({"event": "done", "out_dir": str(out_dir), "rows": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
