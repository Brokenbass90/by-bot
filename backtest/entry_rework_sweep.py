#!/usr/bin/env python3
"""Plateau sweep for ASB1/ATT1 entry rework.

The recent auto-pick WF produced zero canary candidates mostly because the
strategies barely enter. This runner tests the specific relaxed-entry plateaus
from reports/CLAUDE_TO_CODEX_2026_06_15_entry_rework.md and writes an audit
matrix. It does not promote anything by itself.

Run on the server after refreshing coin picks:
    PYTHONPATH=. python scripts/strategy_coin_picks.py --top-n 12
    PYTHONPATH=. python backtest/entry_rework_sweep.py --top-k 8 --windows 4
"""
from __future__ import annotations

import argparse
import datetime as dt
import itertools
import json
import os
from contextlib import contextmanager
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

from backtest.crypto_multiwindow_wf import run as mw_run

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


ASB1_GRID = {
    "ASB1_REGIME_MAX_SLOPE_PCT": ["1.8", "2.6", "3.5"],
    "ASB1_REGIME_MAX_ATR_PCT": ["6.5", "9", "12"],
    "ASB1_MIN_RANGE_PCT": ["3.5", "5.0"],
    "ASB1_COOLDOWN_BARS_5M": ["36", "72"],
}

ATT1_GRID = {
    "ATT1_MIN_R2": ["0.62", "0.68", "0.74", "0.80"],
    "ATT1_TOUCH_ATR": ["0.35", "0.5", "0.7"],
    "ATT1_COOLDOWN_BARS_5M": ["48", "72", "96"],
}

DEFAULT_ATT1_SYMBOLS = "ADAUSDT,ENAUSDT,NEARUSDT,SOLUSDT,TRUMPUSDT"


@contextmanager
def temporary_env(overrides: Dict[str, str]):
    old = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            os.environ[str(k)] = str(v)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _product_grid(grid: Dict[str, List[str]]) -> List[Dict[str, str]]:
    keys = list(grid)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(grid[k] for k in keys))]


def _load_picks() -> Dict[str, List[List[Any]]]:
    path = REPORTS / "STRATEGY_COIN_PICKS_latest.json"
    if not path.exists():
        try:
            from scripts.strategy_coin_picks import main as build_picks

            build_picks(top_n=12)
        except Exception:
            return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("picks"), dict):
        return payload["picks"]
    return payload if isinstance(payload, dict) else {}


def _csv_symbols(raw: str) -> List[str]:
    return [x.strip().upper() for x in str(raw or "").replace(";", ",").split(",") if x.strip()]


def _symbols_for(strategy: str, top_k: int, att1_symbols: str) -> List[str]:
    if strategy == "ATT1":
        return _csv_symbols(os.getenv("ATT1_SYMBOL_ALLOWLIST") or att1_symbols or DEFAULT_ATT1_SYMBOLS)[:top_k]
    picks = _load_picks()
    rows = picks.get(strategy) or []
    out = []
    for row in rows:
        if isinstance(row, (list, tuple)) and row:
            out.append(str(row[0]).upper())
        elif isinstance(row, dict) and row.get("symbol"):
            out.append(str(row["symbol"]).upper())
    return out[:top_k]


def _to_float(v: Any) -> float | None:
    try:
        if v == "inf":
            return float("inf")
        return float(v)
    except Exception:
        return None


def summarize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    details = result.get("details") or []
    trades = 0
    weighted_exp_sum = 0.0
    pfs: List[float] = []
    for d in details:
        m = d.get("metrics") or {}
        n = int(m.get("trades", 0) or 0)
        trades += n
        exp = _to_float(m.get("expectancy_R"))
        if exp is not None:
            weighted_exp_sum += exp * n
        pf = _to_float(m.get("profit_factor"))
        if pf is not None:
            pfs.append(pf)
    nwin = int(result.get("windows_with_trades", 0) or 0)
    pos = int(result.get("positive_windows", 0) or 0)
    return {
        "symbol": result.get("symbol"),
        "windows_with_trades": nwin,
        "positive_windows": pos,
        "positive_frac": round(pos / nwin, 3) if nwin else 0.0,
        "total_trades": trades,
        "weighted_expectancy_R": round(weighted_exp_sum / trades, 4) if trades else 0.0,
        "mean_window_pf": round(mean(pfs), 3) if pfs else None,
        "min_window_pf": round(min(pfs), 3) if pfs else None,
        "verdict": result.get("verdict", ""),
    }


def combo_label(overrides: Dict[str, str]) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(overrides.items()))


def _score_combo(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    traded = [r for r in rows if int(r.get("total_trades", 0) or 0) > 0]
    candidates = [
        r
        for r in traded
        if int(r.get("windows_with_trades", 0) or 0) >= 3
        and float(r.get("positive_frac", 0.0) or 0.0) >= 0.75
        and int(r.get("total_trades", 0) or 0) >= 20
        and float(r.get("weighted_expectancy_R", 0.0) or 0.0) > 0.0
    ]
    return {
        "symbols_tested": len(rows),
        "symbols_with_trades": len(traded),
        "candidate_like_symbols": len(candidates),
        "total_trades": sum(int(r.get("total_trades", 0) or 0) for r in rows),
        "avg_weighted_expectancy_R": round(mean([float(r.get("weighted_expectancy_R", 0.0) or 0.0) for r in traded]), 4)
        if traded
        else 0.0,
        "candidate_like": candidates,
    }


def _run_strategy(strategy: str, symbols: List[str], combos: List[Dict[str, str]], args) -> Dict[str, Any]:
    if strategy == "ASB1":
        from strategies.alt_support_bounce_v1 import AltSupportBounceV1Strategy

        factory = AltSupportBounceV1Strategy
        base_env = {"ASB1_SIGNAL_TF": str(args.signal_tf), "ASB1_REGIME_TF": str(args.regime_tf)}
    elif strategy == "ATT1":
        from strategies.alt_trendline_touch_v1 import AltTrendlineTouchV1Strategy

        factory = AltTrendlineTouchV1Strategy
        base_env = {"ATT1_SIGNAL_TF": str(args.signal_tf)}
    else:
        raise ValueError(strategy)

    out: Dict[str, Any] = {"symbols": symbols, "combos": []}
    for idx, combo in enumerate(combos, 1):
        overrides = {**base_env, **combo}
        print(f"\n## {strategy} combo {idx}/{len(combos)}: {combo_label(overrides)}")
        rows = []
        with temporary_env(overrides):
            for symbol in symbols:
                result = mw_run(
                    factory,
                    symbol,
                    signal_tf=str(args.signal_tf),
                    regime_tf=str(args.regime_tf),
                    k=int(args.windows),
                    fee_bps=float(args.fee_bps),
                    return_details=True,
                )
                rows.append(summarize_result(result))
        score = _score_combo(rows)
        out["combos"].append({"overrides": overrides, "score": score, "symbols": rows})
    out["top_combos"] = sorted(
        out["combos"],
        key=lambda c: (
            c["score"]["candidate_like_symbols"],
            c["score"]["symbols_with_trades"],
            c["score"]["avg_weighted_expectancy_R"],
            c["score"]["total_trades"],
        ),
        reverse=True,
    )[: int(args.top_report)]
    return out


def write_markdown(payload: Dict[str, Any], path: Path) -> None:
    lines = [
        "# Entry Rework Sweep",
        "",
        f"Generated: `{payload['generated_at_utc']}`",
        f"Signal TF: `{payload['signal_tf']}`, regime TF: `{payload['regime_tf']}`, windows: `{payload['windows']}`, fee bps: `{payload['fee_bps']}`",
        "",
        "Purpose: raise ASB1/ATT1 trade frequency enough to validate edge, then reject anything that only adds losing trades.",
        "",
    ]
    for strategy, block in payload["strategies"].items():
        lines += [f"## {strategy}", "", f"Symbols: `{', '.join(block.get('symbols') or [])}`", ""]
        if not block.get("top_combos"):
            lines += ["No combos tested.", ""]
            continue
        lines += [
            "| Rank | Candidate-like | Symbols with trades | Total trades | Avg expectancy R | Overrides |",
            "|---:|---:|---:|---:|---:|---|",
        ]
        for i, combo in enumerate(block["top_combos"], 1):
            s = combo["score"]
            lines.append(
                f"| {i} | {s['candidate_like_symbols']} | {s['symbols_with_trades']} | "
                f"{s['total_trades']} | {s['avg_weighted_expectancy_R']} | `{combo_label(combo['overrides'])}` |"
            )
        lines.append("")
        best = block["top_combos"][0]
        if best["score"]["candidate_like"]:
            lines += ["Candidate-like symbols in best combo:", ""]
            for row in best["score"]["candidate_like"]:
                lines.append(
                    f"- `{row['symbol']}`: {row['positive_windows']}/{row['windows_with_trades']} windows, "
                    f"trades={row['total_trades']}, exp={row['weighted_expectancy_R']}, "
                    f"mean_pf={row['mean_window_pf']}"
                )
            lines.append("")
        else:
            lines += ["Best combo still has no candidate-like symbols under the anti-overfit screen.", ""]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Iterable[str] | None = None) -> Dict[str, Any]:
    parser = argparse.ArgumentParser(description="ASB1/ATT1 relaxed-entry plateau sweep")
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--signal-tf", default="60")
    parser.add_argument("--regime-tf", default="240")
    parser.add_argument("--windows", type=int, default=4)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--strategies", default="ASB1,ATT1")
    parser.add_argument("--att1-symbols", default=DEFAULT_ATT1_SYMBOLS)
    parser.add_argument("--limit-combos", type=int, default=0, help="Smoke/debug: only run first N combos per strategy")
    parser.add_argument("--top-report", type=int, default=8)
    parser.add_argument("--output-json", default=str(REPORTS / "ENTRY_REWORK_SWEEP_latest.json"))
    parser.add_argument("--output-md", default=str(REPORTS / "ENTRY_REWORK_SWEEP_latest.md"))
    args = parser.parse_args(list(argv) if argv is not None else None)

    strategy_names = [s.strip().upper() for s in args.strategies.split(",") if s.strip()]
    payload: Dict[str, Any] = {
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "signal_tf": str(args.signal_tf),
        "regime_tf": str(args.regime_tf),
        "windows": int(args.windows),
        "fee_bps": float(args.fee_bps),
        "strategies": {},
    }

    for strategy in strategy_names:
        grid = ASB1_GRID if strategy == "ASB1" else ATT1_GRID if strategy == "ATT1" else None
        if grid is None:
            print(f"skip unknown strategy {strategy}")
            continue
        combos = _product_grid(grid)
        if args.limit_combos:
            combos = combos[: int(args.limit_combos)]
        symbols = _symbols_for(strategy, int(args.top_k), str(args.att1_symbols))
        payload["strategies"][strategy] = _run_strategy(strategy, symbols, combos, args)

    json_path = Path(args.output_json)
    md_path = Path(args.output_md)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    write_markdown(payload, md_path)
    print(f"\nwrote {json_path}")
    print(f"wrote {md_path}")
    return payload


if __name__ == "__main__":
    main()
