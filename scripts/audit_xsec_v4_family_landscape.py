#!/usr/bin/env python3
"""Run the preregistered survivor-only XSEC V4 family landscape.

This is a cheap selection-bias diagnostic, not an OOS backtest.  It measures
the whole fixed neighbouring family before spending time on PIT reconstruction.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stdev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) >= 2 else 0.0


def _compound(returns: list[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1.0 + value
    return equity


def _metrics(returns: list[float], rebalance_days: int) -> dict:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for value in returns:
        equity *= 1.0 + value
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
    mean = statistics.fmean(returns) if returns else 0.0
    std = _stdev(returns)
    years = max(len(returns) * rebalance_days / 365.0, 1.0 / 365.0)
    annualized = equity ** (1.0 / years) - 1.0 if equity > 0 else -1.0
    annualized_sharpe = (
        mean / std * math.sqrt(365.0 / rebalance_days)
        if std > 0
        else 0.0
    )
    folds = []
    for fold in range(4):
        start = fold * len(returns) // 4
        end = (fold + 1) * len(returns) // 4
        folds.append((_compound(returns[start:end]) - 1.0) * 100.0)
    return {
        "n_rebalances": len(returns),
        "compounded_total_return_pct": (equity - 1.0) * 100.0,
        "annualized_return_pct": annualized * 100.0,
        "annualized_sharpe": annualized_sharpe,
        "max_drawdown_pct": max_dd * 100.0,
        "positive_time_folds": sum(value > 0 for value in folds),
        "fold_returns_pct": folds,
    }


class Landscape:
    def __init__(self, data: dict[str, dict[str, float]], maturity_days: int = 390):
        self.px = {
            symbol: {int(day): float(price) for day, price in closes.items()}
            for symbol, closes in data.items()
        }
        self.days = sorted({day for closes in self.px.values() for day in closes})
        self.mature = sorted(
            symbol for symbol, closes in self.px.items()
            if len(closes) >= maturity_days
        )
        self._market_stress_cache: dict[int, bool] = {}

    def _returns(self, symbol: str, index: int, window: int) -> list[float]:
        values = []
        for cursor in range(max(1, index - window), index):
            before = self.px[symbol].get(self.days[cursor - 1])
            after = self.px[symbol].get(self.days[cursor])
            if before and after and before > 0:
                values.append(after / before - 1.0)
        return values

    def _market_stress(self, index: int) -> bool:
        if index in self._market_stress_cache:
            return self._market_stress_cache[index]

        current = []
        for symbol in self.mature:
            before = self.px[symbol].get(self.days[index - 1])
            after = self.px[symbol].get(self.days[index])
            if before and after and before > 0:
                current.append(abs(after / before - 1.0))
        if len(current) < 10:
            self._market_stress_cache[index] = False
            return False

        history = []
        for cursor in range(max(1, index - 60), index):
            cross_section = []
            for symbol in self.mature:
                before = self.px[symbol].get(self.days[cursor - 1])
                after = self.px[symbol].get(self.days[cursor])
                if before and after and before > 0:
                    cross_section.append(abs(after / before - 1.0))
            if len(cross_section) >= 10:
                history.append(statistics.median(cross_section))
        if len(history) < 30:
            result = False
        else:
            history.sort()
            result = statistics.median(current) > history[int(len(history) * 0.90)]
        self._market_stress_cache[index] = result
        return result

    def phase_returns(
        self,
        *,
        lookbacks: list[int],
        rebalance_days: int,
        basket_k: int,
        target_annual_vol: float,
        phase_offset: int,
        total_cost_bps: float,
    ) -> list[float]:
        start = max(lookbacks) + 1 + phase_offset
        bars = range(start, len(self.days) - rebalance_days - 1, rebalance_days)
        raw = []
        for index in bars:
            if self._market_stress(index):
                raw.append(0.0)
                continue
            per_lookback = []
            for lookback in lookbacks:
                if index - lookback < 0:
                    continue
                now = self.days[index]
                before_day = self.days[index - lookback]
                after_day = self.days[index + rebalance_days]
                candidates = []
                for symbol in self.mature:
                    p0 = self.px[symbol].get(before_day)
                    p1 = self.px[symbol].get(now)
                    p2 = self.px[symbol].get(after_day)
                    if not (p0 and p1 and p2 and p0 > 0 and p1 > 0):
                        continue
                    local_returns = self._returns(symbol, index, lookback)
                    volatility = _stdev(local_returns)
                    if volatility <= 0:
                        continue
                    previous = self.px[symbol].get(self.days[index - 1])
                    if previous and previous > 0 and abs(p1 / previous - 1.0) > 3.0 * volatility:
                        continue
                    candidates.append((symbol, p1 / p0 - 1.0, volatility))
                if len(candidates) < 2 * basket_k + 4:
                    continue

                by_momentum = sorted(range(len(candidates)), key=lambda i: candidates[i][1])
                by_volatility = sorted(range(len(candidates)), key=lambda i: candidates[i][2])
                rank: dict[str, int] = {}
                for position, candidate_index in enumerate(by_momentum):
                    rank[candidates[candidate_index][0]] = position
                for position, candidate_index in enumerate(by_volatility):
                    rank[candidates[candidate_index][0]] += position
                ordered = sorted(rank.items(), key=lambda item: item[1], reverse=True)
                longs = [symbol for symbol, _ in ordered[:basket_k]]
                shorts = [symbol for symbol, _ in ordered[-basket_k:]]

                def forward(symbol: str) -> float:
                    return self.px[symbol][after_day] / self.px[symbol][now] - 1.0

                gross = (
                    statistics.fmean(forward(symbol) for symbol in longs)
                    - statistics.fmean(forward(symbol) for symbol in shorts)
                )
                per_lookback.append(gross - total_cost_bps / 10_000.0)
            if per_lookback:
                raw.append(statistics.fmean(per_lookback))

        scaled = []
        for index, value in enumerate(raw):
            history = raw[max(0, index - 20):index]
            if len(history) < 8:
                leverage = 0.5
            else:
                volatility = _stdev(history)
                annualized = volatility * math.sqrt(365.0 / rebalance_days)
                leverage = min(1.0, target_annual_vol / annualized) if annualized > 0 else 1.0
            scaled.append(value * leverage)
        return scaled

    def run_variant(self, **params) -> dict:
        phases = [
            self.phase_returns(phase_offset=offset, **params)
            for offset in range(params["rebalance_days"])
        ]
        length = min(len(phase) for phase in phases)
        combined = [
            statistics.fmean(phase[index] for phase in phases)
            for index in range(length)
        ]
        return _metrics(combined, params["rebalance_days"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prereg",
        default="configs/preregistered/xsec_v4_family_landscape_20260728.json",
    )
    parser.add_argument(
        "--out-dir",
        default="reports/research/xsec_v4_family_landscape_20260728",
    )
    args = parser.parse_args()

    prereg_path = (ROOT / args.prereg).resolve()
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    data_path = ROOT / prereg["data"]["path"]
    model = Landscape(json.loads(data_path.read_text(encoding="utf-8")))
    grid = prereg["grid"]
    variants = list(itertools.product(
        grid["lookback_sets"],
        grid["rebalance_days"],
        grid["basket_k"],
        grid["target_annual_vol"],
    ))
    if len(variants) != int(prereg["n_trials_planned"]):
        raise RuntimeError("preregistered n_trials_planned does not match grid")

    rows = []
    for trial, (lookbacks, rebalance_days, basket_k, target_vol) in enumerate(variants, 1):
        metrics = model.run_variant(
            lookbacks=list(lookbacks),
            rebalance_days=int(rebalance_days),
            basket_k=int(basket_k),
            target_annual_vol=float(target_vol),
            total_cost_bps=float(prereg["fixed_model"]["total_round_trip_cost_bps"]),
        )
        rows.append({
            "trial": trial,
            "lookbacks": json.dumps(lookbacks, separators=(",", ":")),
            "rebalance_days": rebalance_days,
            "basket_k": basket_k,
            "target_annual_vol": target_vol,
            **metrics,
        })
        print(
            f"[{trial:02d}/{len(variants)}] L={lookbacks} R={rebalance_days} "
            f"K={basket_k} TV={target_vol:.2f} total="
            f"{metrics['compounded_total_return_pct']:+.2f}% "
            f"Sharpe={metrics['annualized_sharpe']:.2f}"
        )

    valid = [row for row in rows if row["n_rebalances"] > 0]
    totals = [row["compounded_total_return_pct"] for row in valid]
    sharpes = [row["annualized_sharpe"] for row in valid]
    positive_fraction = sum(value > 0 for value in totals) / len(totals) if totals else 0.0
    champion = next(
        row for row in valid
        if row["lookbacks"] == "[7,14,21,30,45]"
        and row["rebalance_days"] == 3
        and row["basket_k"] == 5
        and row["target_annual_vol"] == 0.15
    )
    champion_percentile = (
        sum(value <= champion["compounded_total_return_pct"] for value in totals)
        / len(totals)
        * 100.0
    )
    pit_justified = (
        len(valid) >= 24
        and statistics.median(totals) > 0
        and positive_fraction >= 0.60
    )
    receipt = {
        "schema_id": "xsec_v4_family_landscape_receipt_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "capital_authorized": False,
        "prereg_path": str(prereg_path.relative_to(ROOT)),
        "prereg_sha256": _sha256(prereg_path),
        "data_path": str(data_path.relative_to(ROOT)),
        "data_sha256": _sha256(data_path),
        "survivor_only": True,
        "n_trials_planned": len(variants),
        "n_trials_evaluated": len(valid),
        "n_trials_effective_independent": None,
        "family": {
            "mean_total_return_pct": statistics.fmean(totals),
            "median_total_return_pct": statistics.median(totals),
            "stdev_total_return_pct": _stdev(totals),
            "min_total_return_pct": min(totals),
            "max_total_return_pct": max(totals),
            "positive_fraction": positive_fraction,
            "mean_annualized_sharpe": statistics.fmean(sharpes),
            "median_annualized_sharpe": statistics.median(sharpes),
        },
        "published_champion": champion,
        "champion_percentile": champion_percentile,
        "pit_work_justified": pit_justified,
        "promotion": "RESEARCH_ONLY",
        "binding_reason": (
            "PIT reconstruction is justified by a broad positive family."
            if pit_justified else
            "PIT reconstruction is deprioritized because the neighbouring family is not broadly positive."
        ),
        "capital_blockers": [
            "survivor-only universe",
            "no independent untouched OOS",
            "funding absent",
            "slippage unmeasured",
            "execution parity absent"
        ],
    }

    output_dir = ROOT / args.out_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "variants.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    receipt_path = output_dir / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt["family"], ensure_ascii=False, indent=2))
    print(f"pit_work_justified={pit_justified}")
    print(f"receipt={receipt_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
