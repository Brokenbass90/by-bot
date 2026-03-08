#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


ROOT = Path(__file__).resolve().parent.parent


def _to_float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value or "")
    except Exception:
        return default


def _to_int(value: str | None, default: int = 0) -> int:
    try:
        return int(float(value or ""))
    except Exception:
        return default


def _safe_pf(gross_profit: float, gross_loss_abs: float) -> float:
    if gross_loss_abs > 0:
        return gross_profit / gross_loss_abs
    if gross_profit > 0:
        return 9999.0
    return 0.0


def _month_key(ts_raw: str | None) -> str:
    ts = _to_int(ts_raw, 0)
    if ts <= 0:
        return ""
    if ts > 10_000_000_000:
        ts = ts // 1000
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")


@dataclass
class SymbolStats:
    symbol: str
    trades: int = 0
    net: float = 0.0
    wins: int = 0
    gross_profit: float = 0.0
    gross_loss_abs: float = 0.0
    pos_months: int = 0
    neg_months: int = 0
    zero_months: int = 0
    months_total: int = 0

    @property
    def winrate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        return _safe_pf(self.gross_profit, self.gross_loss_abs)


def _load_symbol_stats(trades_path: Path, strategy: str) -> Dict[str, SymbolStats]:
    per_symbol: Dict[str, Dict[str, float | int | Dict[str, float]]] = defaultdict(
        lambda: {
            "trades": 0,
            "net": 0.0,
            "wins": 0,
            "gross_profit": 0.0,
            "gross_loss_abs": 0.0,
            "month_net": {},
        }
    )

    with trades_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("strategy") or "").strip() != strategy:
                continue
            symbol = (row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            pnl = _to_float(row.get("pnl"), 0.0)
            stats = per_symbol[symbol]
            stats["trades"] = int(stats["trades"]) + 1
            stats["net"] = float(stats["net"]) + pnl
            if pnl > 0:
                stats["wins"] = int(stats["wins"]) + 1
                stats["gross_profit"] = float(stats["gross_profit"]) + pnl
            elif pnl < 0:
                stats["gross_loss_abs"] = float(stats["gross_loss_abs"]) + abs(pnl)
            month = _month_key(row.get("exit_ts") or row.get("entry_ts"))
            if month:
                month_net = stats["month_net"]
                assert isinstance(month_net, dict)
                month_net[month] = float(month_net.get(month, 0.0)) + pnl

    out: Dict[str, SymbolStats] = {}
    for symbol, raw in per_symbol.items():
        month_net = raw["month_net"]
        assert isinstance(month_net, dict)
        values = list(month_net.values())
        out[symbol] = SymbolStats(
            symbol=symbol,
            trades=int(raw["trades"]),
            net=round(float(raw["net"]), 6),
            wins=int(raw["wins"]),
            gross_profit=round(float(raw["gross_profit"]), 6),
            gross_loss_abs=round(float(raw["gross_loss_abs"]), 6),
            pos_months=sum(1 for v in values if v > 0),
            neg_months=sum(1 for v in values if v < 0),
            zero_months=sum(1 for v in values if v == 0),
            months_total=len(values),
        )
    return out


def _iter_ranked_rows(
    *,
    base_stats: Dict[str, SymbolStats],
    stress_stats: Dict[str, SymbolStats],
) -> Iterable[dict]:
    symbols = sorted(set(base_stats) | set(stress_stats))
    rows: List[dict] = []
    for symbol in symbols:
        base = base_stats.get(symbol, SymbolStats(symbol=symbol))
        stress = stress_stats.get(symbol, SymbolStats(symbol=symbol))
        rows.append(
            {
                "symbol": symbol,
                "base_trades": base.trades,
                "base_net": base.net,
                "base_winrate": base.winrate,
                "base_pf": base.profit_factor,
                "base_neg_months": base.neg_months,
                "base_pos_months": base.pos_months,
                "stress_trades": stress.trades,
                "stress_net": stress.net,
                "stress_winrate": stress.winrate,
                "stress_pf": stress.profit_factor,
                "stress_neg_months": stress.neg_months,
                "stress_pos_months": stress.pos_months,
            }
        )
    rows.sort(
        key=lambda r: (
            -float(r["stress_net"]),
            -float(r["base_net"]),
            -float(r["stress_pf"]),
            -float(r["stress_winrate"]),
            r["symbol"],
        )
    )
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a reproducible breakout allowlist from yearly base/stress trades.")
    ap.add_argument("--base-trades", required=True, help="Path to base trades.csv")
    ap.add_argument("--stress-trades", required=True, help="Path to stress trades.csv")
    ap.add_argument("--strategy", default="inplay_breakout")
    ap.add_argument("--top-n", type=int, default=16)
    ap.add_argument("--min-base-trades", type=int, default=8)
    ap.add_argument("--min-stress-trades", type=int, default=8)
    ap.add_argument("--min-base-net", type=float, default=0.0)
    ap.add_argument("--min-stress-net", type=float, default=0.0)
    ap.add_argument("--max-base-neg-months", type=int, default=2)
    ap.add_argument("--max-stress-neg-months", type=int, default=1)
    ap.add_argument("--out-csv", default="docs/breakout_allowlist_latest.csv")
    ap.add_argument("--out-env", default="configs/breakout_allowlist_latest.env")
    ap.add_argument("--env-top-n", type=int, default=16)
    ap.add_argument("--env-quality-min", type=float, default=0.52)
    ap.add_argument("--env-impulse-atr", type=float, default=0.75)
    ap.add_argument("--env-impulse-body", type=float, default=0.40)
    ap.add_argument("--env-max-chase", type=float, default=0.22)
    ap.add_argument("--env-max-late", type=float, default=0.55)
    ap.add_argument("--env-min-pullback", type=float, default=0.03)
    ap.add_argument("--env-reclaim-atr", type=float, default=0.10)
    ap.add_argument("--env-max-dist-atr", type=float, default=1.50)
    ap.add_argument("--env-buffer-atr", type=float, default=0.06)
    ap.add_argument("--env-allow-shorts", type=int, default=1)
    ap.add_argument("--env-regime-strict", type=int, default=0)
    ap.add_argument("--env-min-quote-5m-usd", type=int, default=70000)
    ap.add_argument("--env-max-spread-pct", type=float, default=0.20)
    args = ap.parse_args()

    base_path = (ROOT / args.base_trades).resolve() if not Path(args.base_trades).is_absolute() else Path(args.base_trades)
    stress_path = (ROOT / args.stress_trades).resolve() if not Path(args.stress_trades).is_absolute() else Path(args.stress_trades)
    if not base_path.exists():
        raise SystemExit(f"base trades not found: {base_path}")
    if not stress_path.exists():
        raise SystemExit(f"stress trades not found: {stress_path}")

    base_stats = _load_symbol_stats(base_path, args.strategy)
    stress_stats = _load_symbol_stats(stress_path, args.strategy)
    ranked = list(_iter_ranked_rows(base_stats=base_stats, stress_stats=stress_stats))

    selected: List[dict] = []
    rejected: List[dict] = []
    for row in ranked:
        reasons: List[str] = []
        if int(row["base_trades"]) < int(args.min_base_trades):
            reasons.append("base_trades")
        if int(row["stress_trades"]) < int(args.min_stress_trades):
            reasons.append("stress_trades")
        if float(row["base_net"]) < float(args.min_base_net):
            reasons.append("base_net")
        if float(row["stress_net"]) < float(args.min_stress_net):
            reasons.append("stress_net")
        if int(row["base_neg_months"]) > int(args.max_base_neg_months):
            reasons.append("base_neg_months")
        if int(row["stress_neg_months"]) > int(args.max_stress_neg_months):
            reasons.append("stress_neg_months")
        row["status"] = "SELECT" if not reasons else "REJECT"
        row["reason"] = ";".join(reasons) if reasons else "ok"
        if not reasons and len(selected) < int(args.top_n):
            selected.append(row)
        else:
            rejected.append(row)

    out_csv = (ROOT / args.out_csv).resolve()
    out_env = (ROOT / args.out_env).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_env.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "status",
                "reason",
                "symbol",
                "base_trades",
                "base_net",
                "base_winrate",
                "base_pf",
                "base_pos_months",
                "base_neg_months",
                "stress_trades",
                "stress_net",
                "stress_winrate",
                "stress_pf",
                "stress_pos_months",
                "stress_neg_months",
            ]
        )
        for row in list(selected) + rejected:
            writer.writerow(
                [
                    row["status"],
                    row["reason"],
                    row["symbol"],
                    row["base_trades"],
                    f"{float(row['base_net']):.6f}",
                    f"{float(row['base_winrate']) * 100.0:.2f}",
                    f"{float(row['base_pf']):.4f}",
                    row["base_pos_months"],
                    row["base_neg_months"],
                    row["stress_trades"],
                    f"{float(row['stress_net']):.6f}",
                    f"{float(row['stress_winrate']) * 100.0:.2f}",
                    f"{float(row['stress_pf']):.4f}",
                    row["stress_pos_months"],
                    row["stress_neg_months"],
                ]
            )

    allowlist = ",".join(row["symbol"] for row in selected)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    out_env.write_text(
        "\n".join(
            [
                "## Auto-generated breakout allowlist candidate",
                f"## generated_at={generated_at}",
                f"## base_trades={base_path}",
                f"## stress_trades={stress_path}",
                "ENABLE_BREAKOUT_TRADING=1",
                f"BREAKOUT_TOP_N={int(args.env_top_n)}",
                "BREAKOUT_TRY_EVERY_SEC=30",
                f"SYMBOL_ALLOWLIST={allowlist}",
                "SYMBOL_DENYLIST=",
                f"BREAKOUT_QUALITY_MIN_SCORE={float(args.env_quality_min):.2f}",
                f"BREAKOUT_IMPULSE_ATR_MULT={float(args.env_impulse_atr):.2f}",
                f"BREAKOUT_IMPULSE_BODY_MIN_FRAC={float(args.env_impulse_body):.2f}",
                f"BREAKOUT_MAX_CHASE_PCT={float(args.env_max_chase):.2f}",
                f"BREAKOUT_MAX_LATE_VS_REF_PCT={float(args.env_max_late):.2f}",
                f"BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT={float(args.env_min_pullback):.2f}",
                f"BREAKOUT_RECLAIM_ATR={float(args.env_reclaim_atr):.2f}",
                f"BREAKOUT_MAX_DIST_ATR={float(args.env_max_dist_atr):.2f}",
                f"BREAKOUT_BUFFER_ATR={float(args.env_buffer_atr):.2f}",
                f"BREAKOUT_ALLOW_SHORTS={int(args.env_allow_shorts)}",
                f"BREAKOUT_REGIME_STRICT={int(args.env_regime_strict)}",
                f"BREAKOUT_MIN_QUOTE_5M_USD={int(args.env_min_quote_5m_usd)}",
                f"BREAKOUT_MAX_SPREAD_PCT={float(args.env_max_spread_pct):.2f}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"selected={len(selected)} rejected={len(rejected)}")
    print(f"allowlist={allowlist}")
    print(f"csv={out_csv}")
    print(f"env={out_env}")
    for row in selected:
        print(
            f"  {row['symbol']}: stress_net={float(row['stress_net']):+.4f} "
            f"stress_trades={int(row['stress_trades'])} "
            f"stress_neg_months={int(row['stress_neg_months'])} "
            f"base_net={float(row['base_net']):+.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
