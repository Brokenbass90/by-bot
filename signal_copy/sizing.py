# -*- coding: utf-8 -*-
"""Расчёт лота от риска. Работает для forex, металлов, индексов и акций,
потому что берёт спецификацию символа у брокера, а не зашитую формулу.

Главное правило: если посчитать честно нельзя — отказ, а не догадка.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, asdict


@dataclass
class LotDecision:
    accepted: bool
    lot: float = 0.0
    risk_cash: float = 0.0          # желаемый риск в валюте счёта
    actual_risk: float = 0.0        # риск при округлённом лоте
    actual_risk_pct: float = 0.0
    loss_per_lot: float = 0.0       # убыток на 1 лот в валюте счёта
    raw_lot: float = 0.0            # до округления
    reason: str = ""
    note: str = ""

    def as_dict(self): return asdict(self)


def _rate(from_ccy: str, to_ccy: str, quotes: dict[str, float]) -> float | None:
    """Курс пересчёта from → to по котировкам Обзора рынка."""
    if from_ccy == to_ccy:
        return 1.0
    direct = quotes.get(f"{from_ccy}{to_ccy}")
    if direct:
        return float(direct)
    inverse = quotes.get(f"{to_ccy}{from_ccy}")
    if inverse:
        return 1.0 / float(inverse)
    return None


def loss_per_lot(spec: dict, entry: float, stop: float,
                 account_ccy: str, quotes: dict[str, float]) -> tuple[float | None, str]:
    """Сколько теряет 1 лот при движении от entry до stop, в валюте счёта.

    Считаем ДВУМЯ независимыми способами и сверяем. Если расходятся больше чем
    на 5% — отказ. Так поймали случай, когда у свежедобавленного XAUUSD
    tick_value был мусорным и лот выходил в 5 раз больше нужного.
    """
    distance = abs(float(entry) - float(stop))
    if distance <= 0:
        return None, "нулевое расстояние до стопа"

    # Предохранитель: без котировок символ считать нельзя.
    bid = float(spec.get("bid") or 0)
    ask = float(spec.get("ask") or 0)
    if bid <= 0 or ask <= 0:
        return None, "нет котировок по символу (терминал ещё не прогрузил его)"

    tick_size  = float(spec.get("tick_size") or 0)
    tick_value = float(spec.get("tick_value") or 0)
    contract   = float(spec.get("contract_size") or 0)
    profit_ccy = (spec.get("currency_profit") or "").upper()

    by_tick = None
    if tick_size > 0 and tick_value > 0:
        by_tick = (distance / tick_size) * tick_value

    by_contract = None
    if contract > 0 and profit_ccy:
        rate = _rate(profit_ccy, account_ccy.upper(), quotes)
        if rate is not None:
            by_contract = distance * contract * rate

    if by_tick is not None and by_contract is not None:
        spread = abs(by_tick - by_contract) / max(by_tick, by_contract)
        if spread > 0.05:
            return None, (f"два способа расчёта разошлись: по tick_value {by_tick:.2f}, "
                          f"по contract_size {by_contract:.2f} — расхождение "
                          f"{spread*100:.0f}%. Считать нельзя.")
        return by_tick, "tick_value (сверено с contract_size)"

    if by_tick is not None:
        return by_tick, "tick_value"
    if by_contract is not None:
        return by_contract, "contract_size"
    if contract > 0 and profit_ccy:
        return None, f"нет курса {profit_ccy}\u2192{account_ccy} в Обзоре рынка"
    return None, "в спецификации нет ни tick_value, ни contract_size"


def calculate_lot(*, spec: dict, entry: float, stop: float, equity: float,
                  risk_pct: float, account_ccy: str, quotes: dict[str, float],
                  max_lot: float | None = None,
                  max_risk_pct: float | None = None) -> LotDecision:
    if equity <= 0:
        return LotDecision(False, reason="нулевой депозит")
    if risk_pct <= 0:
        return LotDecision(False, reason="риск не задан")

    per_lot, how = loss_per_lot(spec, entry, stop, account_ccy, quotes)
    if per_lot is None or per_lot <= 0:
        return LotDecision(False, reason=how)

    vol_min = float(spec.get("volume_min") or 0.01)
    vol_max = float(spec.get("volume_max") or 100.0)
    step = float(spec.get("volume_step") or 0.01)

    risk_cash = equity * risk_pct / 100.0
    raw = risk_cash / per_lot
    # Никогда не округляем риск вверх: ближайший шаг мог почти удвоить
    # фактический риск на инструментах с крупным volume_step.
    lot = math.floor((raw / step) + 1e-12) * step
    lot = round(lot, 8)

    if lot < vol_min:
        min_risk = vol_min * per_lot
        return LotDecision(
            False, raw_lot=raw, risk_cash=risk_cash, loss_per_lot=per_lot,
            actual_risk=min_risk, actual_risk_pct=min_risk / equity * 100,
            reason="риск меньше минимального лота",
            note=(f"минимальный лот {vol_min} даёт риск {min_risk:.2f} {account_ccy} "
                  f"({min_risk/equity*100:.2f}% вместо {risk_pct}%)"),
        )

    note = ""
    if lot > vol_max:
        lot, note = vol_max, f"зажат максимумом брокера {vol_max}"
    if max_lot and lot > max_lot:
        lot, note = max_lot, f"зажат нашим лимитом {max_lot}"

    actual = lot * per_lot
    actual_pct = actual / equity * 100
    if max_risk_pct and actual_pct > max_risk_pct:
        return LotDecision(
            False, lot=lot, raw_lot=raw, risk_cash=risk_cash, loss_per_lot=per_lot,
            actual_risk=actual, actual_risk_pct=actual_pct,
            reason="превышен потолок риска",
            note=f"{actual_pct:.2f}% больше разрешённых {max_risk_pct}%",
        )

    return LotDecision(True, lot=lot, raw_lot=raw, risk_cash=risk_cash,
                       loss_per_lot=per_lot, actual_risk=actual,
                       actual_risk_pct=actual_pct, reason=how, note=note)


def quotes_from_symbols(symbols: list[dict]) -> dict[str, float]:
    return {s["symbol"]: float(s.get("bid") or 0) for s in symbols if s.get("bid")}
