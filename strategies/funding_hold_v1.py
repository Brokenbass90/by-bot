from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class FundingHoldV1Config:
    max_top_symbol_share: float = 0.45
    min_symbol_net_usd: float = -0.25
    top_n: int = 8
    # Min historical funding events needed (rejects new/illiquid symbols)
    # Added 2026-05-29: avoid selecting NEWUSDT which only has 2 funding payments
    min_funding_events: int = 60
    # Penalty weight for variance — favor STABLE funding over occasional spikes
    # Added 2026-05-29: σ-weighted scoring instead of pure net_usd
    sigma_penalty_weight: float = 0.3
    # Min mean funding rate (per 8h) to be considered (avoids tiny funding)
    min_mean_funding_rate: float = 5e-6


class FundingHoldV1Strategy:
    """Funding carry selector with concentration guardrails.

    This is a lightweight portfolio selector used by the funding backtest and
    gating scripts. It intentionally stays outside the live control-plane and
    only ranks/selects candidate symbols after a funding replay has already
    estimated their standalone net contribution.

    2026-05-29 enhancements:
      - Reject symbols with too few funding events (illiquidity guard)
      - Reject symbols with mean funding too small (no edge)
      - Sigma-weighted scoring: favor stable funding over occasional spikes
    """

    def __init__(self, cfg: FundingHoldV1Config | None = None):
        self.cfg = cfg or FundingHoldV1Config()

    @staticmethod
    def _top_share(rows: List[Dict[str, float]]) -> float:
        if not rows:
            return 0.0
        vals = [abs(float(r.get("net_usd", 0.0))) for r in rows]
        denom = sum(vals)
        if denom <= 1e-12:
            return 0.0
        return max(vals) / denom

    def _quality_score(self, row: Dict[str, float]) -> float:
        """Composite score: net_usd × stability × liquidity_proxy.

        Favors symbols with:
          - High net_usd (raw PnL contribution)
          - Many funding events (long history = more trustworthy)
          - Low std/mean ratio (stable funding, not random spikes)
        """
        net = float(row.get("net_usd", 0.0))
        events = int(row.get("funding_events", 0))
        mean_rate = float(row.get("mean_funding_rate", 0.0))
        std_rate = float(row.get("std_funding_rate", abs(mean_rate)))

        # Liquidity proxy: more events = more reliable estimate
        # 60 events ≈ 20 days × 3 payments/day — minimum credibility
        events_score = min(1.0, events / 540.0)  # 540 events = ~180 days

        # Stability: lower std/mean → more predictable
        # If std is 5x mean, score = 0.1; if std = mean, score = 0.5
        if abs(mean_rate) < 1e-9:
            stability_score = 0.0
        else:
            ratio = std_rate / max(abs(mean_rate), 1e-12)
            stability_score = 1.0 / (1.0 + ratio)

        # Apply sigma penalty (configurable)
        penalty = self.cfg.sigma_penalty_weight * (1.0 - stability_score)
        score = net * events_score * (1.0 - penalty)
        return score

    def select(self, candidates: List[Dict[str, float]]) -> List[Dict[str, float]]:
        if not candidates:
            return []

        # Phase 1: hard filters (illiquidity + tiny funding + negative PnL floor)
        eligible = []
        for r in candidates:
            events = int(r.get("funding_events", 0))
            mean_rate = abs(float(r.get("mean_funding_rate", 0.0)))
            net = float(r.get("net_usd", 0.0))

            if events < int(self.cfg.min_funding_events):
                continue
            if mean_rate < float(self.cfg.min_mean_funding_rate):
                continue
            if net < float(self.cfg.min_symbol_net_usd):
                continue
            eligible.append(r)

        if not eligible:
            return []

        # Phase 2: rank by quality score (was: just net_usd)
        for r in eligible:
            r["_quality_score"] = self._quality_score(r)
        eligible.sort(
            key=lambda r: (
                float(r.get("_quality_score", 0.0)),
                int(r.get("funding_events", 0)),
            ),
            reverse=True,
        )

        # Phase 3: greedy fill with concentration guardrail
        selected: List[Dict[str, float]] = []
        for row in eligible:
            if len(selected) >= int(self.cfg.top_n):
                break
            trial = selected + [row]
            if len(trial) <= 2 or self._top_share(trial) <= float(self.cfg.max_top_symbol_share):
                selected.append(row)

        # Fallback: fill remaining slots ignoring concentration if not enough
        if len(selected) < int(self.cfg.top_n):
            chosen = {str(r.get("symbol", "")) for r in selected}
            for row in eligible:
                sym = str(row.get("symbol", ""))
                if sym in chosen:
                    continue
                selected.append(row)
                chosen.add(sym)
                if len(selected) >= int(self.cfg.top_n):
                    break

        return selected
