"""Funding-carry promotion gate — objective "ready for hedged shadow/canary?".

Funding-carry is the FIRST positive mechanical edge (research: ~+$27 on $800
notional / 180d after fees). But carry is not a directional win-rate bet — its
risks are different: the gross funding must beat ALL real costs (taker/maker
fees, the hedge leg's cost/borrow, basis drift) AND survive the tail (a
liquidation cascade or basis blow-out at the un-hedged moment). This gate
encodes exactly that, so carry only goes live when the net edge is real and the
tail is survivable — not on a single rosy 180d number.

Pure / testable / additive. Feed it the measured economics (Codex provides real
hedge-cost / basis / worst-window numbers); it returns net edge + GO/NO-GO.
"""
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class CarryThresholds:
    min_net_usd: float = 0.0            # net carry must be positive after ALL costs
    min_annual_pct: float = 4.0         # on notional; below this the risk isn't worth it
    min_pos_window_frac: float = 0.6    # carry consistent across sub-windows
    max_worst_window_pct: float = 5.0   # worst sub-window loss <= this % of notional (tail)


@dataclass
class CarryResult:
    go: bool
    net_usd: float
    annual_pct: float
    passed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)


def evaluate(*, gross_funding_usd: float, fees_usd: float, hedge_cost_usd: float,
             basis_pnl_usd: float, notional_usd: float, days: float,
             windows: int = 0, positive_windows: int = 0,
             worst_window_usd: float = 0.0,
             thr: Optional[CarryThresholds] = None) -> CarryResult:
    """All-in carry economics -> objective readiness verdict.

    net = gross_funding - fees - hedge_cost +/- basis_pnl

    IMPORTANT (reviewer 2026-06-16): the hedge is two legs (spot + perp), so
    `hedge_cost_usd` must include round-trip commissions on BOTH legs — i.e.
    (spot maker/taker in + out) + (perp in + out). Don't pass a single-leg cost.
    """
    t = thr or CarryThresholds()
    net = float(gross_funding_usd) - float(fees_usd) - float(hedge_cost_usd) + float(basis_pnl_usd)
    ann = (net / notional_usd) * (365.0 / days) * 100.0 if notional_usd > 0 and days > 0 else 0.0
    worst_pct = abs(min(0.0, float(worst_window_usd))) / notional_usd * 100.0 if notional_usd > 0 else 0.0
    frac = (positive_windows / windows) if windows > 0 else 0.0

    passed: List[str] = []
    failed: List[str] = []

    def chk(ok: bool, msg: str):
        (passed if ok else failed).append(msg)

    chk(net > t.min_net_usd, f"net ${net:.2f} > ${t.min_net_usd} after fees+hedge+basis")
    chk(ann >= t.min_annual_pct, f"annualized {ann:.1f}% >= {t.min_annual_pct}% on notional")
    chk(windows >= 2 and frac >= t.min_pos_window_frac,
        f"consistency {frac:.2f} >= {t.min_pos_window_frac} ({positive_windows}/{windows} windows)")
    chk(worst_pct <= t.max_worst_window_pct,
        f"worst-window tail {worst_pct:.1f}% <= {t.max_worst_window_pct}% (liquidation/basis)")

    return CarryResult(
        go=(len(failed) == 0),
        net_usd=round(net, 2),
        annual_pct=round(ann, 1),
        passed=passed,
        failed=failed,
        details={
            "gross_funding_usd": round(float(gross_funding_usd), 6),
            "fees_usd": round(float(fees_usd), 6),
            "hedge_cost_usd": round(float(hedge_cost_usd), 6),
            "basis_pnl_usd": round(float(basis_pnl_usd), 6),
            "notional_usd": round(float(notional_usd), 6),
            "days": round(float(days), 6),
            "windows": int(windows),
            "positive_windows": int(positive_windows),
            "worst_window_usd": round(float(worst_window_usd), 6),
        },
    )


def _f(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _read_first_csv_row(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return rows[0] if rows else {}


def _read_monthly_values(path: Path) -> List[float]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out: List[float] = []
    for row in rows:
        raw = row.get("gross_funding_usd")
        if raw is None:
            raw = row.get("month_pnl")
        if raw is None:
            continue
        out.append(_f(raw))
    return out


def _read_per_symbol_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as f:
        return sum(1 for _ in csv.DictReader(f))


def evaluate_run_dir(
    run_dir: Path,
    *,
    extra_hedge_cost_usd: float = 0.0,
    extra_spread_bps: float = 0.0,
    basis_pnl_usd: float = 0.0,
    thr: Optional[CarryThresholds] = None,
) -> CarryResult:
    """Evaluate a scripts/backtest_funding_capture.py run directory.

    summary.csv already contains explicit spot+perp open/close fees from the
    funding-capture run. extra_spread_bps/extra_hedge_cost_usd are additional
    conservative costs such as live spread/slippage or basis hedge overhead.
    """
    run_dir = Path(run_dir)
    summary = _read_first_csv_row(run_dir / "summary.csv")
    if not summary:
        raise FileNotFoundError(f"missing or empty summary.csv in {run_dir}")

    days = _f(summary.get("days"))
    gross = _f(summary.get("gross_funding_total_usd"))
    fees = _f(summary.get("fees_total_usd"))
    notional_per_symbol = _f(summary.get("notional_per_symbol"))
    symbols_raw = str(summary.get("symbols") or "")
    symbol_count = len([s for s in symbols_raw.replace(",", ";").split(";") if s.strip()])
    symbol_count = max(symbol_count, _read_per_symbol_count(run_dir / "funding_per_symbol.csv"), 1)
    notional = notional_per_symbol * symbol_count
    extra_cost = float(extra_hedge_cost_usd) + notional * (float(extra_spread_bps) / 10000.0)

    monthly = _read_monthly_values(run_dir / "monthly_pnl.csv")
    windows = len(monthly)
    if windows:
        total_cost = fees + extra_cost - float(basis_pnl_usd)
        per_window_cost = total_cost / windows
        window_net = [x - per_window_cost for x in monthly]
        positive_windows = sum(1 for x in window_net if x > 0)
        worst_window = min(window_net)
    else:
        positive_windows = 0
        worst_window = 0.0

    result = evaluate(
        gross_funding_usd=gross,
        fees_usd=fees,
        hedge_cost_usd=extra_cost,
        basis_pnl_usd=float(basis_pnl_usd),
        notional_usd=notional,
        days=days,
        windows=windows,
        positive_windows=positive_windows,
        worst_window_usd=worst_window,
        thr=thr,
    )
    result.details.update(
        {
            "run_dir": str(run_dir),
            "symbols": [s for s in symbols_raw.replace(",", ";").split(";") if s.strip()],
            "notional_per_symbol": notional_per_symbol,
            "monthly_gross_usd": [round(x, 6) for x in monthly],
            "monthly_net_after_allocated_costs_usd": [round(x, 6) for x in (window_net if windows else [])],
            "extra_spread_bps": float(extra_spread_bps),
            "extra_hedge_cost_usd": float(extra_hedge_cost_usd),
        }
    )
    return result


def _write_markdown(result: CarryResult, path: Path) -> None:
    status = "GO" if result.go else "NO-GO"
    d = result.details
    lines = [
        "# Funding Carry Gate",
        "",
        f"Verdict: **{status}**",
        f"Net: `${result.net_usd:.2f}`",
        f"Annualized on notional: `{result.annual_pct:.1f}%`",
        f"Run dir: `{d.get('run_dir', '')}`",
        "",
        "## Inputs",
        "",
        f"- symbols: `{', '.join(d.get('symbols') or [])}`",
        f"- notional: `${d.get('notional_usd', 0):.2f}` total / `${d.get('notional_per_symbol', 0):.2f}` per symbol",
        f"- gross funding: `${d.get('gross_funding_usd', 0):.2f}`",
        f"- fees from funding run: `${d.get('fees_usd', 0):.2f}`",
        f"- extra hedge/spread cost: `${d.get('hedge_cost_usd', 0):.2f}`",
        f"- basis P&L: `${d.get('basis_pnl_usd', 0):.2f}`",
        "",
        "## Window Check",
        "",
        f"- positive windows: `{d.get('positive_windows', 0)}/{d.get('windows', 0)}`",
        f"- worst window after allocated costs: `${d.get('worst_window_usd', 0):.2f}`",
        f"- monthly net after allocated costs: `{d.get('monthly_net_after_allocated_costs_usd', [])}`",
        "",
        "## Failed",
        "",
    ]
    lines += [f"- {x}" for x in result.failed] or ["- none"]
    lines += ["", "## Passed", ""]
    lines += [f"- {x}" for x in result.passed] or ["- none"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a funding-carry run for hedged shadow/canary readiness")
    parser.add_argument("--run-dir", required=True, help="Directory produced by scripts/backtest_funding_capture.py")
    parser.add_argument("--extra-hedge-cost-usd", type=float, default=0.0)
    parser.add_argument("--extra-spread-bps", type=float, default=0.0)
    parser.add_argument("--basis-pnl-usd", type=float, default=0.0)
    parser.add_argument("--min-net-usd", type=float, default=0.0)
    parser.add_argument("--min-annual-pct", type=float, default=4.0)
    parser.add_argument("--min-pos-window-frac", type=float, default=0.6)
    parser.add_argument("--max-worst-window-pct", type=float, default=5.0)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args(argv)

    thr = CarryThresholds(
        min_net_usd=float(args.min_net_usd),
        min_annual_pct=float(args.min_annual_pct),
        min_pos_window_frac=float(args.min_pos_window_frac),
        max_worst_window_pct=float(args.max_worst_window_pct),
    )
    result = evaluate_run_dir(
        Path(args.run_dir),
        extra_hedge_cost_usd=float(args.extra_hedge_cost_usd),
        extra_spread_bps=float(args.extra_spread_bps),
        basis_pnl_usd=float(args.basis_pnl_usd),
        thr=thr,
    )
    payload = {
        "go": result.go,
        "net_usd": result.net_usd,
        "annual_pct": result.annual_pct,
        "passed": result.passed,
        "failed": result.failed,
        "details": result.details,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.out_md:
        _write_markdown(result, Path(args.out_md))
    return 0


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        raise SystemExit(main())
    # Research number (base fees) WITHOUT hedge/basis/tail guards yet -> should NOT pass
    raw = evaluate(gross_funding_usd=40.0, fees_usd=12.72, hedge_cost_usd=0.0,
                   basis_pnl_usd=0.0, notional_usd=800.0, days=180,
                   windows=1, positive_windows=1, worst_window_usd=0.0)
    print(f"RAW research (no guards modelled): go={raw.go} net=${raw.net_usd} ann={raw.annual_pct}%")
    for f in raw.failed:
        print(f"   FAIL: {f}")
    # With guards measured + consistency across 6 monthly windows + bounded tail
    guarded = evaluate(gross_funding_usd=48.0, fees_usd=13.0, hedge_cost_usd=6.0,
                       basis_pnl_usd=-2.0, notional_usd=800.0, days=180,
                       windows=6, positive_windows=5, worst_window_usd=-18.0)
    print(f"GUARDED + windows: go={guarded.go} net=${guarded.net_usd} ann={guarded.annual_pct}%")
    for f in guarded.failed:
        print(f"   FAIL: {f}")
