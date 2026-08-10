#!/usr/bin/env python3
"""Run the pre-forward Alpaca daily-portfolio diagnostic.

The output is deliberately promotion-ineligible while its universes are
current-survivor proxies.  It repairs execution timing, cash/exposure,
deployable fractional protection, costs, and daily drawdown without opening or
peeking at the sealed August-November forward outcomes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.alpaca_bakeoff_v2_contract import spy200_gate  # noqa: E402
from backtest.alpaca_exact_parity_contract import DailyBar  # noqa: E402
from backtest.alpaca_honest_portfolio import (  # noqa: E402
    Candidate,
    HonestPortfolioError,
    MonthlyDecision,
    select_v38_successor,
    simulate_live_protection_daily_proxy,
)
from strategies.alpaca_adaptive_v1 import AdaptiveConfig, select  # noqa: E402
from strategies.alpaca_dynamic_v4_event import SECTOR_MAP  # noqa: E402
from forex.data import load_m5_csv  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs" / "preregistered" / "alpaca_honest_diagnostic_v1_20260810.json"
DEFAULT_OUTPUT = ROOT / "reports" / "research" / "alpaca_honest_diagnostic_v1_20260810" / "receipt.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_path(raw: str) -> Path:
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or ".." in candidate.parts:
        raise HonestPortfolioError(f"unsafe repo path: {raw!r}")
    return ROOT / candidate


def _load_frame(symbol: str, suffix: str) -> tuple[pd.DataFrame, Path]:
    path = ROOT / "runtime" / "equities_yf_cache" / f"{symbol}_{suffix}.csv"
    if not path.is_file():
        raise HonestPortfolioError(f"missing cache: {path.relative_to(ROOT)}")
    try:
        frame = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    except ValueError:
        frame = pd.read_csv(path, header=[0, 1], index_col=0, parse_dates=True)
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    required = ["Open", "High", "Low", "Close"]
    if not set(required).issubset(frame.columns):
        raise HonestPortfolioError(f"{path.relative_to(ROOT)}: missing OHLC")
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    frame = frame.dropna(subset=required).sort_index()
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise HonestPortfolioError(f"{path.relative_to(ROOT)}: duplicate or unordered dates")
    for column in required:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[required].isna().any().any():
        raise HonestPortfolioError(f"{path.relative_to(ROOT)}: non-numeric OHLC")
    invalid = (
        (frame[required] <= 0).any(axis=1)
        | (frame["High"] < frame[["Open", "Close"]].max(axis=1))
        | (frame["Low"] > frame[["Open", "Close"]].min(axis=1))
        | (frame["Low"] > frame["High"])
    )
    if bool(invalid.any()):
        raise HonestPortfolioError(f"{path.relative_to(ROOT)}: invalid OHLC geometry")
    return frame, path


def _daily_bars(frame: pd.DataFrame) -> list[DailyBar]:
    return [
        DailyBar(
            session_date=timestamp.date(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
        )
        for timestamp, row in frame.iterrows()
    ]


def _load_aggregated_intraday(symbol: str, directory: str) -> tuple[list[DailyBar], Path]:
    path = _repo_path(directory) / f"{symbol}_M5.csv"
    if not path.is_file():
        raise HonestPortfolioError(f"missing intraday cache: {path.relative_to(ROOT)}")
    grouped: dict[date, list[Any]] = defaultdict(list)
    for candle in load_m5_csv(str(path)):
        session = datetime.fromtimestamp(int(candle.ts), timezone.utc).date()
        grouped[session].append(candle)
    rows = [
        DailyBar(
            session_date=session,
            open=float(candles[0].o),
            high=max(float(candle.h) for candle in candles),
            low=min(float(candle.l) for candle in candles),
            close=float(candles[-1].c),
        )
        for session, candles in sorted(grouped.items())
    ]
    if not rows:
        raise HonestPortfolioError(f"empty intraday cache: {path.relative_to(ROOT)}")
    return rows, path


def _load_window_symbol(window: dict[str, Any], symbol: str) -> tuple[list[DailyBar], Path, str]:
    source = str(window.get("data_source") or "yfinance_auto_adjust_true_cache")
    if source == "yfinance_auto_adjust_true_cache":
        frame, path = _load_frame(symbol, str(window["cache_suffix"]))
        return _daily_bars(frame), path, source
    if source == "cached_intraday_aggregate":
        rows, path = _load_aggregated_intraday(symbol, str(window["data_directory"]))
        return rows, path, source
    raise HonestPortfolioError(f"unsupported data source: {source}")


def _atr20(rows: list[DailyBar]) -> float:
    if len(rows) < 21:
        return float("nan")
    values = []
    for index in range(len(rows) - 20, len(rows)):
        row = rows[index]
        previous = rows[index - 1].close
        values.append(max(row.high - row.low, abs(row.high - previous), abs(row.low - previous)))
    return sum(values) / len(values)


def _schedule(all_sessions: list[date], start: date, end_exclusive: date) -> list[tuple[date, date]]:
    month_last: dict[str, int] = {}
    for index, session in enumerate(all_sessions):
        month_last[session.strftime("%Y-%m")] = index
    rows = []
    for _month, index in sorted(month_last.items()):
        if index + 1 >= len(all_sessions):
            continue
        signal = all_sessions[index]
        entry = all_sessions[index + 1]
        if start <= entry < end_exclusive:
            rows.append((signal, entry))
    return rows


def _adaptive_picks(
    history: dict[str, list[DailyBar]], *, use_gate: bool
) -> tuple[tuple[Candidate, ...], str]:
    spy = history.get("SPY") or []
    index_closes = [row.close for row in spy]
    universe = {
        symbol: [row.close for row in rows]
        for symbol, rows in history.items()
        if symbol != "SPY" and len(rows) >= 202
    }
    selected = select(
        universe,
        index_closes,
        sectors=SECTOR_MAP,
        cfg=AdaptiveConfig(max_positions=4),
        force_regime_ok=not use_gate,
    )
    picks = []
    for pick in selected.get("picks") or []:
        symbol = str(pick["symbol"])
        rows = history[symbol]
        atr = _atr20(rows)
        signal_close = rows[-1].close
        # Adaptive's current bridge CSV leaves stop_price blank; the bridge
        # therefore falls back to the configured 5% stop.  Express that through
        # the common Candidate shape as 2 ATR == 5% of signal close.
        stop_equivalent_atr = signal_close * 0.025
        picks.append(
            Candidate(
                symbol=symbol,
                score=float(pick.get("score") or 0.0),
                atr_at_signal=stop_equivalent_atr if math.isfinite(atr) else stop_equivalent_atr,
                atr_pct_at_signal=stop_equivalent_atr / signal_close * 100.0,
                signal_close=signal_close,
                weight=float(pick.get("weight") or 0.0),
            )
        )
    return tuple(picks), str(selected.get("reason") or "")


def _decisions(
    arm: str,
    data: dict[str, list[DailyBar]],
    schedule: list[tuple[date, date]],
    clusters: list[set[str]],
) -> list[MonthlyDecision]:
    use_gate = arm.endswith("_gated")
    out: list[MonthlyDecision] = []
    for signal, entry in schedule:
        history = {
            symbol: [row for row in rows if row.session_date <= signal]
            for symbol, rows in data.items()
        }
        # Do not treat a stale last observation as a tradable signal bar.
        history = {
            symbol: rows
            for symbol, rows in history.items()
            if rows and rows[-1].session_date == signal
        }
        spy = history.get("SPY") or []
        if not spy:
            raise HonestPortfolioError(f"SPY missing on signal session {signal}")
        gate_ok = spy200_gate([row.close for row in spy])
        if use_gate and not gate_ok:
            picks: tuple[Candidate, ...] = ()
            reason = "spy200_gate_cash"
        elif arm.startswith("v38_successor"):
            picks = select_v38_successor(history, sectors=SECTOR_MAP, clusters=clusters)
            reason = "ok" if picks else "no_qualifying_names"
        elif arm.startswith("adaptive_v1"):
            picks, reason = _adaptive_picks(history, use_gate=use_gate)
        else:
            raise HonestPortfolioError(f"unknown arm: {arm}")
        out.append(MonthlyDecision(signal, entry, picks, reason))
    return out


def _validate_config(cfg: dict[str, Any]) -> None:
    required_true = [
        "research_only",
        "capital_authorized_false",
        "safe_hold_unchanged",
        "forward_outcomes_embargoed",
        "no_broker_calls",
        "no_parameter_scan",
    ]
    for key in required_true:
        if cfg.get(key) is not True:
            raise HonestPortfolioError(f"mandatory fail-closed flag changed: {key}")
    expected_arms = {
        "v38_successor_gated",
        "v38_successor_ungated",
        "adaptive_v1_gated",
        "adaptive_v1_ungated",
    }
    if set(cfg.get("arms") or []) != expected_arms:
        raise HonestPortfolioError("frozen arm set changed")
    embargo = date.fromisoformat(str(cfg["outcome_embargo_start_session"]))
    for window in cfg.get("windows") or []:
        if date.fromisoformat(str(window["evaluation_end_exclusive"])) > embargo:
            raise HonestPortfolioError("window crosses the sealed forward embargo")
    for name, pin in (cfg.get("source_pins") or {}).items():
        path = _repo_path(str(pin.get("path") or ""))
        if not path.is_file() or _sha256(path) != str(pin.get("sha256") or ""):
            raise HonestPortfolioError(f"source pin mismatch: {name}")


def _markdown(receipt: dict[str, Any]) -> str:
    lines = [
        "# Alpaca honest diagnostic v1",
        "",
        "Verdict: `NEEDS_REVISION / RESEARCH_ONLY` until PIT membership, authoritative XNYS sessions, corporate actions and broker-calibrated intraday data are pinned.",
        "",
        "| window | arm | cost/side | return | daily DD | PF realized | trades | avg exposure |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in receipt["results"]:
        summary = row["summary"]
        profit_factor = summary["profit_factor_realized"]
        profit_factor_text = "n/a" if profit_factor is None else f"{profit_factor:.3f}"
        lines.append(
            f"| {row['window']} | {row['arm']} | {row['cost_bps_per_side']:.0f} bps | "
            f"{summary['return_pct']:+.2f}% | {summary['daily_max_drawdown_pct']:.2f}% | "
            f"{profit_factor_text} | {summary['realized_trades']} | "
            f"{summary['average_gross_exposure_pct']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "## What is repaired",
            "",
            "- completed calendar-month close -> next observed session open;",
            "- one cash ledger, fractional quantities and 70% target gross exposure;",
            "- costs on every buy and sell, including gaps and rotations;",
            "- deployable simple-stop plus next-session daily ratchet proxy;",
            "- retained positions are not fictitiously sold/rebought;",
            "- daily MTM and drawdown include initial capital.",
            "",
            "## Why this is still not promotion grade",
            "",
            *[f"- {item};" for item in receipt["capital_blockers"]],
        ]
    )
    return "\n".join(lines).rstrip(";\n") + ".\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG.relative_to(ROOT)))
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT.relative_to(ROOT)))
    args = parser.parse_args()
    config_path = _repo_path(args.config)
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    _validate_config(cfg)
    embargo = date.fromisoformat(str(cfg["outcome_embargo_start_session"]))
    clusters = [{str(symbol) for symbol in group} for group in cfg["clusters"]]

    results: list[dict[str, Any]] = []
    manifests: dict[str, list[dict[str, Any]]] = {}
    for window in cfg["windows"]:
        symbols = [str(symbol) for symbol in window["symbols"]]
        data: dict[str, list[DailyBar]] = {}
        manifest: list[dict[str, Any]] = []
        for symbol in [*symbols, "SPY"]:
            rows, path, source = _load_window_symbol(window, symbol)
            if rows and rows[-1].session_date >= embargo:
                raise HonestPortfolioError(f"{symbol}: cache contains embargoed outcome session")
            data[symbol] = rows
            manifest.append(
                {
                    "symbol": symbol,
                    "path": str(path.relative_to(ROOT)),
                    "sha256": _sha256(path),
                    "rows": len(rows),
                    "first_session": rows[0].session_date.isoformat(),
                    "last_session": rows[-1].session_date.isoformat(),
                    "source": source,
                }
            )
        manifests[str(window["id"])] = manifest
        all_spy_sessions = [row.session_date for row in data["SPY"]]
        start = date.fromisoformat(str(window["evaluation_start"]))
        end = date.fromisoformat(str(window["evaluation_end_exclusive"]))
        sessions = [session for session in all_spy_sessions if start <= session < end]
        schedule = _schedule(all_spy_sessions, start, end)
        if not sessions or not schedule:
            raise HonestPortfolioError(f"{window['id']}: no evaluation sessions or decisions")
        for arm in cfg["arms"]:
            decisions = _decisions(str(arm), data, schedule, clusters)
            for cost in cfg["cost_bps_per_side"]:
                replay = simulate_live_protection_daily_proxy(
                    data,
                    sessions,
                    decisions,
                    initial_capital=float(cfg["initial_capital"]),
                    target_gross_exposure=float(cfg["target_gross_exposure"]),
                    cost_bps_per_side=float(cost),
                )
                summary_keys = [
                    "initial_capital",
                    "final_equity",
                    "return_pct",
                    "daily_max_drawdown_pct",
                    "profit_factor_realized",
                    "realized_trades",
                    "red_months",
                    "months",
                    "worst_month_pct",
                    "average_gross_exposure_pct",
                ]
                summary = {key: replay[key] for key in summary_keys}
                if not math.isfinite(float(summary["profit_factor_realized"])):
                    summary["profit_factor_realized"] = None
                results.append(
                    {
                        "window": window["id"],
                        "arm": arm,
                        "cost_bps_per_side": float(cost),
                        "summary": summary,
                        "decisions": replay["decisions"],
                        "trades": replay["trades"],
                        "daily_equity": replay["daily_equity"],
                    }
                )
                print(
                    f"{window['id']} {arm} cost={float(cost):.0f}: "
                    f"return={summary['return_pct']:+.2f}% "
                    f"DD={summary['daily_max_drawdown_pct']:.2f}% "
                    f"PF={summary['profit_factor_realized'] if summary['profit_factor_realized'] is not None else 'n/a'} "
                    f"trades={summary['realized_trades']}"
                )

    receipt = {
        "schema_id": "alpaca_honest_diagnostic_receipt_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "capital_authorized": False,
        "safe_hold_changed": False,
        "broker_or_network_calls": False,
        "forward_outcomes_read": False,
        "outcome_embargo_start_session": embargo.isoformat(),
        "config_path": str(config_path.relative_to(ROOT)),
        "config_sha256": _sha256(config_path),
        "methodology_status": "REPAIRED_DIAGNOSTIC_NOT_PROMOTION_GRADE",
        "data_quality_rating": "NEEDS_REVISION",
        "results": results,
        "input_manifests": manifests,
        "capital_blockers": cfg["capital_blockers"],
    }
    output = _repo_path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    summary_path = output.with_name("summary.md")
    summary_path.write_text(_markdown(receipt), encoding="utf-8")
    print(f"receipt={output.relative_to(ROOT)}")
    print(f"summary={summary_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
