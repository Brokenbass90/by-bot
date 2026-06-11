"""Edge canary — канарейка эджа: авто-затухание умирающих стратегий (Claude 2026-06-10).

Сердце «не деградирующей» системы. Каждый рукав живёт, пока его скользящий
live-PF подтверждает эдж. Эдж тает → mult гаснет ступенями → архив-алерт.
Стратегии умирают тихо и дёшево, а не громко и с деньгами.

Логика (по окну последних `window` закрытых сделок рукава):
    PF >= 1.15            → mult 1.0  (здоров)
    1.00 <= PF < 1.15     → mult 0.75 (тускнеет)
    0.85 <= PF < 1.00     → mult 0.50 (болен)
    PF < 0.85             → mult 0.25 (умирает)
    PF < 0.70 два окна подряд → mult 0.0 + рекомендация в архив (алерт человеку)
Мало сделок (< min_trades) → mult 1.0, вердикт unknown (не наказываем за тишину).
Восстановление симметрично: PF вернулся → mult вернулся (без залипания).

Подключение (Codex): cron-скрипт раз в час читает live_trade_events.jsonl,
зовёт EdgeCanary.assess() по каждому рукаву, пишет runtime/edge_canary.json;
allocator умножает свой mult на canary.mult; при verdict='archive' — TG-алерт
(решение об архиве — за человеком). Env: EDGE_CANARY_ENABLE (default OFF→shadow).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

PF_HEALTHY = 1.15
PF_FADING = 1.00
PF_SICK = 0.85
PF_DYING = 0.70
MULTS = {"healthy": 1.0, "fading": 0.75, "sick": 0.50, "dying": 0.25, "archive": 0.0}


@dataclass
class CanaryVerdict:
    sleeve: str
    verdict: str        # healthy|fading|sick|dying|archive|unknown
    mult: float
    pf: Optional[float]
    trades: int
    note: str


def rolling_pf(pnls: Sequence[float]) -> Optional[float]:
    wins = sum(p for p in pnls if p > 0)
    losses = -sum(p for p in pnls if p < 0)
    if losses <= 0:
        return 99.0 if wins > 0 else None
    return wins / losses


class EdgeCanary:
    def __init__(self, window: int = 40, min_trades: int = 12):
        self.window = int(window)
        self.min_trades = int(min_trades)
        self._dying_streak: Dict[str, int] = {}

    def assess(self, sleeve: str, pnls_closed: Sequence[float]) -> CanaryVerdict:
        """pnls_closed — P&L закрытых сделок рукава в хронологическом порядке."""
        recent: List[float] = list(pnls_closed)[-self.window:]
        n = len(recent)
        if n < self.min_trades:
            self._dying_streak.pop(sleeve, None)
            return CanaryVerdict(sleeve, "unknown", 1.0, None, n,
                                 f"trades {n} < {self.min_trades}: не наказываем за тишину")
        pf = rolling_pf(recent)
        if pf is None:
            return CanaryVerdict(sleeve, "unknown", 1.0, None, n, "нет убытков и нет прибыли")

        if pf < PF_DYING:
            streak = self._dying_streak.get(sleeve, 0) + 1
            self._dying_streak[sleeve] = streak
            if streak >= 2:
                return CanaryVerdict(sleeve, "archive", MULTS["archive"], round(pf, 3), n,
                                     f"PF<{PF_DYING} два окна подряд → СТОП + алерт (архив решает человек)")
            return CanaryVerdict(sleeve, "dying", MULTS["dying"], round(pf, 3), n,
                                 f"PF<{PF_DYING}, окно {streak}/2 до архив-алерта")
        self._dying_streak.pop(sleeve, None)

        if pf >= PF_HEALTHY:
            v = "healthy"
        elif pf >= PF_FADING:
            v = "fading"
        elif pf >= PF_SICK:
            v = "sick"
        else:
            v = "dying"
        return CanaryVerdict(sleeve, v, MULTS[v], round(pf, 3), n, f"rolling PF {pf:.2f} за {n} сделок")

    def assess_all(self, sleeves: Dict[str, Sequence[float]]) -> Dict[str, CanaryVerdict]:
        return {name: self.assess(name, pnls) for name, pnls in sleeves.items()}
