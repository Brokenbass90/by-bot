from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class FundingHoldV1Config:
    max_top_symbol_share: float = 0.45
    min_symbol_net_usd: float = -0.25
    top_n: int = 8


class FundingHoldV1Strategy:
    """Funding carry selector with concentration guardrails.

    Expects candidate rows with at least:
    - symbol
    - net_usd
    - funding_events
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

    def select(self, candidates: List[Dict[str, float]]) -> List[Dict[str, float]]:
        """Greedy select rows by net with concentration cap.

        Preference:
        1) high net_usd
        2) enough events
        3) keep top-share under cap when possible
        """
        if not candidates:
            return []

        eligible = [
            r for r in candidates
            if float(r.get("net_usd", 0.0)) >= float(self.cfg.min_symbol_net_usd)
        ]
        eligible.sort(
            key=lambda r: (
                float(r.get("net_usd", 0.0)),
                int(r.get("funding_events", 0)),
            ),
            reverse=True,
        )

        selected: List[Dict[str, float]] = []
        for row in eligible:
            if len(selected) >= int(self.cfg.top_n):
                break
            trial = selected + [row]
            # Let first 2 symbols pass freely, then enforce concentration cap.
            if len(trial) <= 2 or self._top_share(trial) <= float(self.cfg.max_top_symbol_share):
                selected.append(row)

        # Backfill if cap prevented reaching target basket size.
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
