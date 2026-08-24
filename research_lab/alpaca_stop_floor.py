#!/usr/bin/env python3
"""SUPERSEDED prototype; do not import into live Alpaca code.

Этот прототип восстанавливает floor из сырого HWM. Аудит показал, что HWM
может быть записан до broker acceptance, в dry-run или после rejected PATCH,
поэтому он не является доказательством реально принятой защиты. Live release
использует broker-accepted floor ledger и lifecycle reconciliation в
``scripts/equities_alpaca_paper_bridge.py`` и
``scripts/alpaca_protective_exit_manager.py``.

Пол защиты для Альпаки: уровень, ниже которого стоп опускаться не вправе.

Зачем это существует
--------------------
Мост при переармировании ставит стоп из плана — вход минус 5%
(``equities_alpaca_paper_bridge.py``, ветка ``rearm_stop_sell``).
Он не знает, что храповик ``alpaca_protective_exit_manager.py`` уже поднял
стоп выше. В ночь с истечением DAY-ордера вся дневная работа храповика
обнуляется. Замерено 20 августа 2026: пять ночей подряд, $9.59 за ночь.

Этот модуль восстанавливает уровень храповика из уже существующего файла
состояния ``protective_exit_hwm.json``. Он повторяет ровно ту же формулу,
что и храповик, поэтому **менять сам храповик не нужно** — он уже пишет
всё необходимое (hwm, entry_price).

Инвариант, ради которого всё это
--------------------------------
    Уровень защиты не имеет права опускаться. Никогда.

Живёт в research_lab, потому что live-ядро ведёт Кодекс: так правка
в его файле сводится к одной строке вместо двадцати.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

# Умолчания синхронизированы с alpaca_protective_exit_manager.py.
# Если там меняют — менять и здесь, иначе пол разъедется с храповиком.
DEFAULT_ACTIVATE_GAIN_PCT = 3.5
DEFAULT_TRAIL_PCT = 3.5
DEFAULT_MIN_LOCK_GAIN_PCT = 0.5
DEFAULT_MARKET_GAP_BPS = 10.0


def _f(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    return result if result == result else float(default)  # отсекаем NaN


def ratchet_floor(
    entry_price: float,
    hwm: float,
    *,
    activate_gain_pct: float = DEFAULT_ACTIVATE_GAIN_PCT,
    trail_pct: float = DEFAULT_TRAIL_PCT,
    min_lock_gain_pct: float = DEFAULT_MIN_LOCK_GAIN_PCT,
) -> float:
    """Уровень, который храповик уже заслужил по достигнутому максимуму.

    Возвращает 0.0, если храповик ещё не взведён — тогда пола нет
    и план распоряжается стопом единолично.

    Формула повторяет build_ratchet_plan: пол = максимум из трейла
    от хайуотермарка и минимального замка от входа.

    >>> round(ratchet_floor(101.552, 112.124), 2)   # SCHW, 19 августа
    108.2
    >>> ratchet_floor(247.55, 245.155)              # ABBV, ещё в минусе
    0.0
    """
    entry_price = _f(entry_price)
    hwm = _f(hwm)
    if entry_price <= 0.0 or hwm <= 0.0:
        return 0.0

    peak_gain_pct = (hwm / entry_price - 1.0) * 100.0
    if peak_gain_pct + 1e-9 < activate_gain_pct:
        return 0.0

    trail_floor = hwm * (1.0 - trail_pct / 100.0)
    locked_floor = entry_price * (1.0 + min_lock_gain_pct / 100.0)
    return max(trail_floor, locked_floor)


def locked_floor(
    symbol: str,
    hwm_state: Mapping[str, Any],
    *,
    current_price: float = 0.0,
    market_gap_bps: float = DEFAULT_MARKET_GAP_BPS,
    activate_gain_pct: float = DEFAULT_ACTIVATE_GAIN_PCT,
    trail_pct: float = DEFAULT_TRAIL_PCT,
    min_lock_gain_pct: float = DEFAULT_MIN_LOCK_GAIN_PCT,
) -> float:
    """Пол защиты для одного символа из состояния храповика.

    ``current_price`` — если передана, пол подрезается ниже рынка, чтобы
    стоп-ордер не отбился брокером как немедленно исполнимый. Это та же
    страховка ``market_ceiling``, что стоит в храповике.

    Возвращает 0.0, когда пола нет: нет записи, нет данных, храповик
    не взведён, или рынок уже ниже заслуженного уровня.
    """
    record = hwm_state.get(str(symbol).strip().upper())
    if not isinstance(record, Mapping):
        return 0.0

    floor = ratchet_floor(
        record.get("entry_price"),
        record.get("hwm"),
        activate_gain_pct=activate_gain_pct,
        trail_pct=trail_pct,
        min_lock_gain_pct=min_lock_gain_pct,
    )
    if floor <= 0.0:
        return 0.0

    current_price = _f(current_price)
    if current_price > 0.0:
        ceiling = current_price * (1.0 - max(1.0, market_gap_bps) / 10000.0)
        if ceiling <= 0.0:
            return 0.0
        floor = min(floor, ceiling)

    return floor if floor > 0.0 else 0.0


def load_hwm_state(path: str | Path) -> dict[str, Any]:
    """Читает protective_exit_hwm.json. Любая беда — пустое состояние.

    Пустое состояние означает «пола нет», то есть поведение в точности
    как до этой правки. Отказ этого модуля не может ухудшить защиту.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def protected_stop_price(
    symbol: str,
    plan_stop_price: float,
    hwm_state: Mapping[str, Any],
    *,
    current_price: float = 0.0,
) -> float:
    """Итоговая точка входа для моста: стоп из плана, поднятый до пола.

    Именно эту функцию зовёт rearm_stop_sell вместо голого
    ``float(spec["stop_loss_price"])``.

    >>> state = {"SCHW": {"entry_price": 101.552, "hwm": 112.124}}
    >>> round(protected_stop_price("SCHW", 96.47, state, current_price=110.52), 2)
    108.2
    >>> protected_stop_price("ABBV", 235.17, {})   # нет состояния — как раньше
    235.17
    """
    plan_stop_price = _f(plan_stop_price)
    floor = locked_floor(symbol, hwm_state, current_price=current_price)
    return max(plan_stop_price, floor)


if __name__ == "__main__":
    import doctest

    failures, tests = doctest.testmod(verbose=False)
    print(f"doctests: {tests - failures}/{tests} passed")
    raise SystemExit(1 if failures else 0)
