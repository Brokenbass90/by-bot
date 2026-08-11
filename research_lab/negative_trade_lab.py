#!/usr/bin/env python3
"""Evidence-first phenotype analysis for backtest trade ledgers.

The lab performs arithmetic and bucketing deterministically.  It may emit a
small, sanitized proposal packet for a local LLM, but the model gets no market
credentials, order authority, code-write authority, or permission to promote a
strategy.  Its job is limited to proposing falsifiable follow-up experiments.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import statistics
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


SCHEMA_ID = "negative_trade_phenotype_lab_v1"
REQUIRED = {
    "strategy", "symbol", "side", "entry_ts", "exit_ts", "pnl", "fees",
    "reason", "initial_risk_usd", "entry_price", "initial_sl",
}
_REGIME = re.compile(r"\bregime=([^, +]+)")
_HTF = re.compile(r"\bhtf=([^, +]+)")
_SQUEEZE = re.compile(r"\bsqueeze\s+(\d+(?:\.\d+)?)%\s+of\s+max", re.I)
_VOL_MULT = re.compile(r"\bvol[×x](\d+(?:\.\d+)?)", re.I)
_ATR_PCT = re.compile(r"\bATR\s+(\d+(?:\.\d+)?)%", re.I)


def _number(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _ts_ms(value: Any) -> int:
    raw = _number(value)
    if raw is None or raw <= 0:
        return 0
    out = int(raw)
    return out * 1000 if out < 10_000_000_000 else out


def _month(ts_ms: int) -> str:
    if not ts_ms:
        return "unknown"
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m")


def _hour(ts_ms: int) -> str:
    if not ts_ms:
        return "unknown"
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%H")


def _bucket(value: float | None, edges: list[float], suffix: str = "") -> str:
    if value is None:
        return "unknown"
    low = -math.inf
    for high in edges:
        if value <= high:
            left = "-inf" if math.isinf(low) else f"{low:g}"
            return f"({left},{high:g}]{suffix}"
        low = high
    return f"({edges[-1]:g},inf){suffix}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


@dataclass(frozen=True)
class Trade:
    source: str
    strategy: str
    symbol: str
    side: str
    entry_ts_ms: int
    exit_ts_ms: int
    net_r: float
    gross_r: float
    cost_r: float
    hold_minutes: float
    stop_pct: float | None
    terminal_exit: str
    exit_path: str
    regime: str
    htf: str
    squeeze_pct: float | None
    volume_multiple: float | None
    atr_pct: float | None


def _terminal_exit(reason: str) -> str:
    for token in ("SL_same_bar", "TRAIL_SL", "TIME", "EOP", "TP2", "SL"):
        if re.search(rf"(?:^|\+){re.escape(token)}(?:$|\+)", reason):
            if token in {"SL", "TRAIL_SL", "TIME", "EOP", "TP2"} and reason.endswith(token):
                return token
            if token == "SL_same_bar":
                return token
    return "unknown"


def _exit_path(reason: str, terminal: str) -> str:
    flags = [token for token in ("TP1", "TP2") if f"+{token}" in reason]
    if terminal not in flags:
        flags.append(terminal)
    return "+".join(flags)


def load_trades(paths: Iterable[Path]) -> tuple[list[Trade], dict[str, Any]]:
    trades: list[Trade] = []
    input_rows = 0
    invalid_rows: list[dict[str, Any]] = []
    duplicate_keys: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    sources: list[dict[str, Any]] = []
    for path in paths:
        path = path.resolve()
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            missing = sorted(REQUIRED - set(reader.fieldnames or []))
            if missing:
                raise ValueError(f"{path}: missing required columns: {','.join(missing)}")
            rows = list(reader)
        sources.append({"path": str(path), "sha256": _sha256(path), "rows": len(rows)})
        for row_number, row in enumerate(rows, start=2):
            input_rows += 1
            risk = _number(row.get("initial_risk_usd"))
            pnl = _number(row.get("pnl"))
            fees = _number(row.get("fees"))
            entry = _number(row.get("entry_price"))
            initial_sl = _number(row.get("initial_sl"))
            entry_ts = _ts_ms(row.get("entry_ts"))
            exit_ts = _ts_ms(row.get("exit_ts"))
            if not risk or risk <= 0 or pnl is None or fees is None or not entry_ts or not exit_ts or exit_ts < entry_ts:
                invalid_rows.append({"path": str(path), "row": row_number, "reason": "invalid_economics_or_time"})
                continue
            key = (
                str(row.get("strategy") or ""), str(row.get("symbol") or "").upper(),
                str(entry_ts), str(exit_ts), str(row.get("side") or "").lower(),
            )
            if key in seen:
                duplicate_keys.append(key)
                continue
            seen.add(key)
            reason = str(row.get("reason") or "")
            signal_reason = str(row.get("signal_reason") or reason)
            terminal = _terminal_exit(reason)
            regime = (_REGIME.search(signal_reason).group(1) if _REGIME.search(signal_reason) else "unknown")
            htf = (_HTF.search(signal_reason).group(1) if _HTF.search(signal_reason) else "unknown")
            squeeze_match = _SQUEEZE.search(signal_reason)
            volume_match = _VOL_MULT.search(signal_reason)
            atr_match = _ATR_PCT.search(signal_reason)
            stop_pct = abs(entry - initial_sl) / entry * 100 if entry and entry > 0 and initial_sl else None
            net_r = pnl / risk
            cost_r = fees / risk
            trades.append(
                Trade(
                    source=str(path), strategy=str(row.get("strategy") or "").strip(),
                    symbol=str(row.get("symbol") or "").strip().upper(),
                    side=str(row.get("side") or "").strip().lower(),
                    entry_ts_ms=entry_ts, exit_ts_ms=exit_ts,
                    net_r=net_r, gross_r=net_r + cost_r, cost_r=cost_r,
                    hold_minutes=(exit_ts - entry_ts) / 60_000,
                    stop_pct=stop_pct, terminal_exit=terminal,
                    exit_path=_exit_path(reason, terminal), regime=regime, htf=htf,
                    squeeze_pct=float(squeeze_match.group(1)) if squeeze_match else None,
                    volume_multiple=float(volume_match.group(1)) if volume_match else None,
                    atr_pct=float(atr_match.group(1)) if atr_match else None,
                )
            )
    quality = {
        "status": "pass" if not invalid_rows and not duplicate_keys else "warn",
        "input_rows": input_rows,
        "usable_rows": len(trades),
        "invalid_rows": invalid_rows[:50],
        "duplicate_count": len(duplicate_keys),
        "duplicate_examples": [list(key) for key in duplicate_keys[:20]],
        "sources": sources,
    }
    return trades, quality


def metrics(rows: Iterable[Trade]) -> dict[str, Any]:
    values = list(rows)
    net = [row.net_r for row in values]
    gross = [row.gross_r for row in values]
    costs = [row.cost_r for row in values]
    wins = sum(value > 0 for value in net)
    gross_win = sum(value for value in net if value > 0)
    gross_loss = -sum(value for value in net if value < 0)
    mean = statistics.fmean(net) if net else 0.0
    sd = statistics.stdev(net) if len(net) > 1 else 0.0
    return {
        "trades": len(values),
        "symbols": len({row.symbol for row in values}),
        "net_r": sum(net),
        "gross_r": sum(gross),
        "cost_r": sum(costs),
        "mean_net_r": mean,
        "mean_gross_r": statistics.fmean(gross) if gross else 0.0,
        "mean_cost_r": statistics.fmean(costs) if costs else 0.0,
        "t_stat_net_r": mean / (sd / math.sqrt(len(net))) if len(net) > 1 and sd > 0 else 0.0,
        "profit_factor_net_r": gross_win / gross_loss if gross_loss else ("inf" if gross_win else 0.0),
        "win_rate": wins / len(net) if net else 0.0,
    }


def _dimensions() -> dict[str, Callable[[Trade], str]]:
    return {
        "strategy": lambda row: row.strategy or "unknown",
        "symbol": lambda row: row.symbol or "unknown",
        "side": lambda row: row.side or "unknown",
        "entry_month": lambda row: _month(row.entry_ts_ms),
        "entry_utc_hour": lambda row: _hour(row.entry_ts_ms),
        "terminal_exit": lambda row: row.terminal_exit,
        "exit_path": lambda row: row.exit_path,
        "regime": lambda row: row.regime,
        "htf": lambda row: row.htf,
        "hold_minutes": lambda row: _bucket(row.hold_minutes, [15, 60, 240, 720, 1440], "m"),
        "initial_stop_pct": lambda row: _bucket(row.stop_pct, [0.25, 0.5, 1, 2, 4], "%"),
        "cost_r": lambda row: _bucket(row.cost_r, [0.05, 0.1, 0.15, 0.25, 0.5], "R"),
        "squeeze_pct": lambda row: _bucket(row.squeeze_pct, [20, 30, 40, 50, 70], "%"),
        "volume_multiple": lambda row: _bucket(row.volume_multiple, [1.5, 2, 3, 5, 10], "x"),
        "atr_pct": lambda row: _bucket(row.atr_pct, [0.25, 0.5, 0.75, 1, 2, 4], "%"),
    }


def analyze(paths: Iterable[Path]) -> dict[str, Any]:
    trades, quality = load_trades(paths)
    if not trades:
        raise ValueError("no usable trades")
    overall = metrics(trades)
    rows: list[dict[str, Any]] = []
    for dimension, key_fn in _dimensions().items():
        groups: dict[str, list[Trade]] = defaultdict(list)
        for trade in trades:
            groups[key_fn(trade)].append(trade)
        for bucket, members in groups.items():
            row = {"dimension": dimension, "bucket": bucket, **metrics(members)}
            row["net_r_share"] = row["net_r"] / overall["net_r"] if overall["net_r"] else 0.0
            rows.append(row)
    rows.sort(key=lambda row: (row["dimension"], row["net_r"], row["bucket"]))
    if overall["gross_r"] <= 0 and overall["net_r"] < 0:
        mechanism = "negative_gross_edge_plus_cost_drag"
    elif overall["gross_r"] > 0 and overall["net_r"] <= 0:
        mechanism = "positive_gross_edge_killed_by_costs"
    elif overall["net_r"] > 0:
        mechanism = "positive_after_costs"
    else:
        mechanism = "flat_or_ambiguous"
    min_n = max(5, int(math.ceil(len(trades) * 0.02)))
    material = [row for row in rows if row["trades"] >= min_n and row["dimension"] not in {"strategy", "side", "htf"}]
    return {
        "schema_id": SCHEMA_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "authority": "research_only_no_live_or_order_authority",
        "quality": quality,
        "overall": overall,
        "diagnostic_class": mechanism,
        "material_bucket_min_trades": min_n,
        "phenotypes": rows,
        "worst_material_buckets": sorted(material, key=lambda row: row["net_r"])[:20],
        "best_material_buckets": sorted(material, key=lambda row: row["net_r"], reverse=True)[:20],
        "claim_boundary": (
            "Buckets are descriptive diagnostics, not causal filters. Any proposed exclusion or "
            "parameter change requires preregistration and untouched time/symbol replication."
        ),
    }


def _fmt(value: Any, digits: int = 3) -> str:
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    return f"{float(value):.{digits}f}"


def render_markdown(payload: dict[str, Any], tag: str) -> str:
    overall = payload["overall"]
    rows = payload["phenotypes"]
    lines = [
        f"# Negative Trade Lab — {tag}", "",
        f"Generated: `{payload['generated_at_utc']}`", "",
        "## Technical result", "",
        f"**Diagnostic class: `{payload['diagnostic_class']}`.**",
        f"Across **{overall['trades']}** trades / **{overall['symbols']}** symbols, net was "
        f"**{_fmt(overall['net_r'])}R**: gross **{_fmt(overall['gross_r'])}R** minus "
        f"costs **{_fmt(overall['cost_r'])}R**. Mean net was "
        f"**{_fmt(overall['mean_net_r'], 4)}R/trade**, t=**{_fmt(overall['t_stat_net_r'], 2)}**, "
        f"PF=**{_fmt(overall['profit_factor_net_r'])}**.", "",
        "This is a descriptive decomposition. It rejects or diagnoses the measured run; it does not prove that a bucket filter will work out of sample.", "",
        "## Exit-path decomposition separates entry failure from cost drag", "",
        "| Exit path | Trades | Gross R | Costs R | Net R | Mean net R |", "|---|---:|---:|---:|---:|---:|",
    ]
    exit_rows = sorted((row for row in rows if row["dimension"] == "exit_path"), key=lambda row: row["net_r"])
    for row in exit_rows:
        lines.append(
            f"| {row['bucket']} | {row['trades']} | {_fmt(row['gross_r'])} | {_fmt(row['cost_r'])} | "
            f"{_fmt(row['net_r'])} | {_fmt(row['mean_net_r'], 4)} |"
        )
    lines += ["", "## Regime and symbol concentration", ""]
    for dimension, title in (("regime", "Regime"), ("symbol", "Worst symbols")):
        lines += [f"### {title}", "", "| Bucket | Trades | Gross R | Costs R | Net R | t |", "|---|---:|---:|---:|---:|---:|"]
        selected = sorted((row for row in rows if row["dimension"] == dimension), key=lambda row: row["net_r"])
        if dimension == "symbol":
            selected = selected[:12]
        for row in selected:
            lines.append(
                f"| {row['bucket']} | {row['trades']} | {_fmt(row['gross_r'])} | {_fmt(row['cost_r'])} | "
                f"{_fmt(row['net_r'])} | {_fmt(row['t_stat_net_r'], 2)} |"
            )
        lines.append("")
    lines += [
        "## Falsifiable next experiments", "",
        "1. Separate direct-stop trades from trades that reached TP1/trailing; do not tune one exit rule across both phenotypes.",
        "2. For direct stops, add MFE/MAE and time-to-failure labels, then preregister one entry/regime hypothesis on the next untouched window.",
        "3. For gross-positive but net-negative paths, test a minimum gross-edge-to-cost gate and lower-turnover exit variants. Do not assume maker entry helps impulse setups.",
        "4. Treat worst-symbol and regime exclusions as hypotheses only; verify with leave-one-symbol-out and forward time splits before any ban or promotion.",
        "5. Pass only the summarized proposal packet to the local LLM. The model may rank hypotheses but may not alter code, risk, orders, or promotion state.",
        "", "## Data and limitations", "",
        f"- Data quality status: `{payload['quality']['status']}`; usable {payload['quality']['usable_rows']} / {payload['quality']['input_rows']}; duplicates {payload['quality']['duplicate_count']}.",
        f"- Material bucket threshold: {payload['material_bucket_min_trades']} trades.",
        f"- {payload['claim_boundary']}",
        "- Raw trade ledgers do not contain full intratrade price paths. MFE/MAE attribution requires the existing candle-forensics stage.",
    ]
    return "\n".join(lines).rstrip() + "\n"


def _proposal_packet(payload: dict[str, Any], tag: str) -> dict[str, Any]:
    def shrink(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: row[key]
            for key in ("dimension", "bucket", "trades", "net_r", "gross_r", "cost_r", "mean_net_r", "t_stat_net_r")
        }
    return {
        "schema_id": "negative_trade_ai_proposal_packet_v1",
        "tag": tag,
        "authority": "proposal_only_no_secrets_no_raw_orders_no_code_write_no_live_mutation",
        "facts": {
            "overall": payload["overall"],
            "diagnostic_class": payload["diagnostic_class"],
            "worst_material_buckets": [shrink(row) for row in payload["worst_material_buckets"][:12]],
            "best_material_buckets": [shrink(row) for row in payload["best_material_buckets"][:8]],
            "claim_boundary": payload["claim_boundary"],
        },
        "requested_output": {
            "max_hypotheses": 5,
            "fields": ["hypothesis", "mechanism", "falsifying_test", "required_data", "leakage_risk", "do_not_change"],
            "rules": [
                "Do not claim causality from descriptive buckets.",
                "Do not recommend live risk or order changes.",
                "Use one primary change per preregistered experiment.",
                "Preserve untouched holdout windows.",
            ],
        },
    }


def write_outputs(payload: dict[str, Any], out_dir: Path, tag: str) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "analysis.json"
    md_path = out_dir / "report.md"
    csv_path = out_dir / "phenotypes.csv"
    ai_path = out_dir / "ai_proposal_packet.json"
    _atomic_text(json_path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    _atomic_text(md_path, render_markdown(payload, tag))
    fields = [
        "dimension", "bucket", "trades", "symbols", "net_r", "gross_r", "cost_r",
        "mean_net_r", "mean_gross_r", "mean_cost_r", "t_stat_net_r",
        "profit_factor_net_r", "win_rate", "net_r_share",
    ]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=fields,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(payload["phenotypes"])
    _atomic_text(csv_path, buffer.getvalue())
    _atomic_text(ai_path, json.dumps(_proposal_packet(payload, tag), ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return {"analysis": str(json_path), "report": str(md_path), "phenotypes": str(csv_path), "ai_packet": str(ai_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Decompose negative trade ledgers into auditable R phenotypes.")
    parser.add_argument("--trades-csv", action="append", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--tag", default="negative_trade_case")
    args = parser.parse_args()
    payload = analyze(Path(value) for value in args.trades_csv)
    outputs = write_outputs(payload, Path(args.out_dir), args.tag)
    print(json.dumps({"overall": payload["overall"], "diagnostic_class": payload["diagnostic_class"], "outputs": outputs}, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
