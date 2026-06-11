"""Drawdown throttle — тормоз риска при просадке (Claude 2026-06-10).

Проверено на объединённой кривой ядро+Elder (две фазы рынка):
  - худшее окно: maxDD 12.7% → 7.6% при НЕИЗМЕННОМ net (+$8.91 vs +$8.87);
  - хорошее окно: цена тормоза всего −9% net (17.92→16.30), DD 3.6→3.2%.
Механика: пока текущая просадка от пика equity > threshold_pct, весь риск
на новые сделки умножается на cut_mult; восстановились к пику — риск обычный.
Это НЕ мартингейл и не его инверсия по сделкам — только защита капитала
в кластерные плохие периоды (источник «красных месяцев»).

Подключение (Codex): рядом с confidence_risk в сайзинге:
    risk_usd *= throttle.risk_scale(current_equity)
+ env DD_THROTTLE_ENABLE (default OFF → сначала shadow-лог), DD_THROTTLE_PCT=2.0,
DD_THROTTLE_CUT=0.5. Пик хранить в state (переживает рестарт).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DDThrottle:
    threshold_pct: float = 2.0   # просадка от пика, после которой тормозим
    cut_mult: float = 0.5        # множитель риска в режиме торможения
    peak_equity: float = 0.0     # high-water mark (персистить в state)
    _active: bool = field(default=False, repr=False)

    def update_peak(self, equity: float) -> None:
        if equity > self.peak_equity:
            self.peak_equity = float(equity)

    def drawdown_pct(self, equity: float) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - float(equity)) / self.peak_equity * 100.0)

    def risk_scale(self, equity: float) -> float:
        """Вернуть множитель риска для НОВОЙ сделки при данном equity.
        Также обновляет пик (вызывать на каждом решении о входе)."""
        self.update_peak(equity)
        dd = self.drawdown_pct(equity)
        self._active = dd > self.threshold_pct
        return self.cut_mult if self._active else 1.0

    @property
    def active(self) -> bool:
        return self._active

    def status(self, equity: float) -> str:
        return (f"dd_throttle dd={self.drawdown_pct(equity):.2f}% "
                f"thr={self.threshold_pct}% scale={'%.2f' % self.risk_scale(equity)}")
