#!/usr/bin/env python3
"""Drawdown doctor for strategy/portfolio trade CSVs.

This is intentionally read-only. It turns a `trades.csv` file from
`backtest/run_portfolio.py` plus optional `trade_forensics_report.py` JSONL into
an operator-facing diagnosis:

- where the max drawdown started and ended;
- which symbols/sides/reasons contributed most inside that DD window;
- whether losses look like entry failures, stop-too-tight, or exit giveback;
- which concrete hypotheses should be tested next.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return default
        return out
    except Exception:
        return default


def _int_ts_ms(value: Any) -> int:
    try:
        raw = int(float(value))
    except Exception:
        return 0
    return raw * 1000 if 0 < raw < 10_000_000_000 else raw


def _utc(ms: int) -> str:
    if not ms:
        return ""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _month(ms: int) -> str:
    if not ms:
        return "unknown"
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m")


def _hour(ms: int) -> str:
    if not ms:
        return "unknown"
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%H")


@dataclass
class Trade:
    source: str
    strategy: str
    symbol: str
    side: str
    entry_ts_ms: int
    exit_ts_ms: int
    pnl: float
    outcome: str
    reason: str
    row: dict[str, str]


@dataclass
class Bucket:
    n: int = 0
    wins: int = 0
    losses: int = 0
    net: float = 0.0
    gross_win: float = 0.0
    gross_loss: float = 0.0

    def add(self, pnl: float) -> None:
        self.n += 1
        self.net += pnl
        if pnl > 0:
            self.wins += 1
            self.gross_win += pnl
        elif pnl < 0:
            self.losses += 1
            self.gross_loss += -pnl

    @property
    def pf(self) -> float:
        if self.gross_loss <= 0:
            return math.inf if self.gross_win > 0 else 0.0
        return self.gross_win / self.gross_loss

    @property
    def wr(self) -> float:
        return self.wins / self.n if self.n else 0.0


def _fmt_pf(value: float) -> str:
    return "inf" if math.isinf(value) else f"{value:.3f}"


def _load_trades(paths: Iterable[Path]) -> list[Trade]:
    trades: list[Trade] = []
    for path in paths:
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                trades.append(
                    Trade(
                        source=str(path),
                        strategy=(row.get("strategy") or "").strip(),
                        symbol=(row.get("symbol") or "").strip().upper(),
                        side=(row.get("side") or "").strip().lower(),
                        entry_ts_ms=_int_ts_ms(row.get("entry_ts")),
                        exit_ts_ms=_int_ts_ms(row.get("exit_ts")),
                        pnl=_float(row.get("pnl")),
                        outcome=(row.get("outcome") or "").strip(),
                        reason=(row.get("reason") or "").strip(),
                        row=row,
                    )
                )
    return sorted(
        [t for t in trades if t.symbol and t.exit_ts_ms],
        key=lambda t: (t.exit_ts_ms, t.entry_ts_ms, t.symbol, t.strategy),
    )


def _load_forensics(paths: Iterable[Path]) -> dict[tuple[str, str, int], dict[str, Any]]:
    out: dict[tuple[str, str, int], dict[str, Any]] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                symbol = str(row.get("symbol") or "").upper()
                strategy = str(row.get("strategy") or "")
                exit_utc = str(row.get("exit_utc") or "")
                try:
                    dt = datetime.strptime(exit_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    exit_ms = int(dt.timestamp() * 1000)
                except Exception:
                    exit_ms = 0
                if symbol and exit_ms:
                    out[(strategy, symbol, exit_ms)] = row
    return out


def _bucket_by(trades: Iterable[Trade], key_fn) -> dict[str, Bucket]:
    buckets: dict[str, Bucket] = defaultdict(Bucket)
    for t in trades:
        buckets[str(key_fn(t) or "unknown")].add(t.pnl)
    return dict(buckets)


def _max_drawdown_window(trades: list[Trade]) -> dict[str, Any]:
    equity = 0.0
    peak = 0.0
    peak_idx = -1
    max_dd = 0.0
    trough_idx = -1
    dd_start_idx = -1
    curve: list[float] = []
    for i, t in enumerate(trades):
        equity += t.pnl
        curve.append(equity)
        if equity > peak:
            peak = equity
            peak_idx = i
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
            trough_idx = i
            dd_start_idx = peak_idx + 1
    window = trades[max(0, dd_start_idx) : trough_idx + 1] if trough_idx >= 0 else []
    return {
        "max_dd": max_dd,
        "start_idx": dd_start_idx,
        "trough_idx": trough_idx,
        "start_utc": _utc(window[0].exit_ts_ms) if window else "",
        "trough_utc": _utc(window[-1].exit_ts_ms) if window else "",
        "trades": window,
        "equity_curve": curve,
    }


def _top_table(title: str, buckets: dict[str, Bucket], *, limit: int = 10) -> list[str]:
    rows = [f"### {title}", "", "| bucket | trades | net | PF | WR | wins/losses |", "|---|---:|---:|---:|---:|---:|"]
    for key, b in sorted(buckets.items(), key=lambda kv: kv[1].net)[:limit]:
        rows.append(
            f"| {key} | {b.n} | {b.net:.4f} | {_fmt_pf(b.pf)} | {b.wr*100:.1f}% | {b.wins}/{b.losses} |"
        )
    rows.append("")
    return rows


def _hypotheses(trades: list[Trade], forensics: dict[tuple[str, str, int], dict[str, Any]]) -> list[str]:
    items: list[dict[str, Any]] = []
    for t in trades:
        row = forensics.get((t.strategy, t.symbol, t.exit_ts_ms))
        if row:
            items.append(row)
    if not items:
        return [
            "Run trade_forensics_report.py for MFE/MAE labels; current DD report has only raw trade CSV fields.",
            "Start with symbol allowlist tests: remove the worst net symbols and rerun the same candidate.",
            "Check exit_reason distribution: if most losses are SL, sweep wider SL/delayed confirmation.",
        ]

    verdicts = Counter(str(x.get("verdict") or "") for x in items)
    out: list[str] = []
    n = max(1, len(items))
    if verdicts["entry_failed_fast"] / n >= 0.10:
        out.append("Entry timing/filter hypothesis: many losses failed fast. Test stricter reclaim/CHoCH/body confirmation and regime+symbol gating.")
    if verdicts["stop_then_reversed"] / n >= 0.20:
        out.append("Stop geometry hypothesis: many stops reversed soon after exit. Test wider SL, delayed entry, or stop behind level/ATR structure.")
    if verdicts["gave_back_profit"] / n >= 0.20:
        out.append("Exit management hypothesis: many trades had profit then hit SL. Test breakeven/trailing after MFE threshold or earlier partial TP.")
    if verdicts["tp_then_continued"] / n >= 0.08:
        out.append("Runner hypothesis: winners often continued after TP. Test wider TP2 / ATR trailing runner instead of fixed early exit.")
    if not out:
        out.append("No dominant forensic pattern; prioritize symbol/month/regime cuts before changing parameters.")
    return out


def write_report(trades: list[Trade], forensics: dict[tuple[str, str, int], dict[str, Any]], out_dir: Path, tag: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = tag or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"drawdown_doctor_{tag}.json"
    md_path = out_dir / f"drawdown_doctor_{tag}.md"

    overall = Bucket()
    for t in trades:
        overall.add(t.pnl)
    dd = _max_drawdown_window(trades)
    dd_trades: list[Trade] = dd["trades"]

    payload = {
        "tag": tag,
        "trades": overall.n,
        "net": overall.net,
        "profit_factor": overall.pf,
        "winrate": overall.wr,
        "max_drawdown": dd["max_dd"],
        "dd_start_utc": dd["start_utc"],
        "dd_trough_utc": dd["trough_utc"],
        "dd_trades": len(dd_trades),
        "hypotheses": _hypotheses(trades, forensics),
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    lines: list[str] = [
        f"# Drawdown Doctor — {tag}",
        "",
        f"Generated UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Summary",
        "",
        f"- Trades: **{overall.n}**",
        f"- Net PnL: **{overall.net:.4f}**",
        f"- PF: **{_fmt_pf(overall.pf)}**",
        f"- WR: **{overall.wr*100:.1f}%**",
        f"- Max DD: **{dd['max_dd']:.4f}** from `{dd['start_utc']}` to `{dd['trough_utc']}` over **{len(dd_trades)}** trades",
        "",
        "## Main hypotheses to test",
        "",
    ]
    for h in payload["hypotheses"]:
        lines.append(f"- {h}")
    lines.append("")

    lines.extend(_top_table("Worst total contributors by symbol", _bucket_by(trades, lambda t: t.symbol)))
    lines.extend(_top_table("Worst total contributors by side", _bucket_by(trades, lambda t: t.side)))
    lines.extend(_top_table("Worst total contributors by exit reason", _bucket_by(trades, lambda t: t.reason or t.outcome)))
    lines.extend(_top_table("Worst total contributors by exit month", _bucket_by(trades, lambda t: _month(t.exit_ts_ms))))
    lines.extend(_top_table("Worst total contributors by UTC exit hour", _bucket_by(trades, lambda t: _hour(t.exit_ts_ms))))
    if dd_trades:
        lines.extend(_top_table("Inside max-DD window: contributors by symbol", _bucket_by(dd_trades, lambda t: t.symbol)))
        lines.extend(_top_table("Inside max-DD window: contributors by reason", _bucket_by(dd_trades, lambda t: t.reason or t.outcome)))

    if forensics:
        frows = [forensics.get((t.strategy, t.symbol, t.exit_ts_ms)) for t in trades]
        frows = [x for x in frows if x]
        verdict_buckets: dict[str, Bucket] = defaultdict(Bucket)
        for x in frows:
            verdict_buckets[str(x.get("verdict") or "unknown")].add(_float(x.get("pnl")))
        lines.extend(_top_table("Forensic verdict contribution", verdict_buckets))

    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Diagnose drawdown contributors from backtest trades.csv files.")
    ap.add_argument("--trades-csv", action="append", required=True, help="Path to trades.csv. Can be repeated.")
    ap.add_argument("--forensics-jsonl", action="append", default=[], help="Optional trade_forensics_report.py JSONL. Can be repeated.")
    ap.add_argument("--out-dir", default="reports/drawdown_doctor")
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    trades = _load_trades(Path(p).expanduser() for p in args.trades_csv)
    if not trades:
        raise SystemExit("No trades loaded.")
    forensics = _load_forensics(Path(p).expanduser() for p in args.forensics_jsonl)
    md_path, json_path = write_report(trades, forensics, Path(args.out_dir).expanduser(), args.tag)
    print(f"wrote_md={md_path}")
    print(f"wrote_json={json_path}")
    print(f"trades={len(trades)} forensics_matched={len(forensics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
