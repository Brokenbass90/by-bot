#!/usr/bin/env python3
"""SUPERSEDED standalone checks for the rejected raw-HWM prototype.

Не является pytest/release evidence и не должно подключаться к live. Текущие
release tests находятся в ``tests/test_alpaca_monthly_trailing.py`` и
``tests/test_alpaca_protective_exit_manager.py``.

Проверки пола защиты. Считаны с живой выписки брокера 20 августа 2026.

Запуск:  python3 research_lab/test_alpaca_stop_floor.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpaca_stop_floor import (  # noqa: E402
    load_hwm_state,
    locked_floor,
    protected_stop_price,
    ratchet_floor,
)

# Настоящие числа со счёта. Хайуотермарк SCHW восстановлен из достигнутого
# стопа 108.20 при трейле 3.5%: 108.20 / 0.965 = 112.124.
SCHW = {"entry_price": 101.552, "hwm": 112.124, "qty": 0.563776973}
ABBV = {"entry_price": 247.55, "hwm": 266.457, "qty": 0.135734866}

PASSED = 0
FAILED: list[str] = []


def check(name: str, got, want, tol: float = 0.01) -> None:
    global PASSED
    ok = abs(float(got) - float(want)) <= tol if isinstance(want, (int, float)) else got == want
    if ok:
        PASSED += 1
    else:
        FAILED.append(f"{name}: получено {got}, ожидалось {want}")


# ── 1. Пол воспроизводит то, что храповик реально сделал ──────────────────
check("SCHW пол = достигнутый стоп 108.20", ratchet_floor(**{k: SCHW[k] for k in ("entry_price", "hwm")}), 108.20)
check("ABBV пол = достигнутый стоп 257.13", ratchet_floor(**{k: ABBV[k] for k in ("entry_price", "hwm")}), 257.13)

# ── 2. Невзведённый храповик пола не даёт ─────────────────────────────────
# ABBV 10 августа: цена 245.155 при входе 247.55, то есть минус 0.97%.
check("невзведённый храповик → пола нет", ratchet_floor(247.55, 245.155), 0.0)
# Ровно на пороге 3.5% — уже взведён.
check("ровно на пороге 3.5% → взведён", ratchet_floor(100.0, 103.5) > 0.0, True)
check("чуть ниже порога → не взведён", ratchet_floor(100.0, 103.49), 0.0)

# ── 3. Минимальный замок работает, когда трейл ещё ниже входа ─────────────
# На самом пороге трейл 3.5% от 103.5 = 99.88 — ниже входа. Замок спасает.
check("на пороге держит замок +0.5%, а не трейл", ratchet_floor(100.0, 103.5), 100.5)

# ── 4. Главный инвариант: стоп не опускается ──────────────────────────────
state = {"SCHW": SCHW, "ABBV": ABBV}
check(
    "SCHW: план 96.47 поднят до 108.20",
    protected_stop_price("SCHW", 96.47, state, current_price=110.52),
    108.20,
)
check(
    "ABBV: план 235.17 поднят до 257.13",
    protected_stop_price("ABBV", 235.17, state, current_price=265.50),
    257.13,
)

# ── 5. Отказоустойчивость: хуже, чем было, стать не может ─────────────────
check("нет состояния → стоп из плана", protected_stop_price("ABBV", 235.17, {}), 235.17)
check("незнакомый символ → стоп из плана", protected_stop_price("NVDA", 100.0, state), 100.0)
check("битая запись → стоп из плана", protected_stop_price("X", 50.0, {"X": "мусор"}), 50.0)
check("пустой hwm → стоп из плана", protected_stop_price("X", 50.0, {"X": {"entry_price": 60, "hwm": 0}}), 50.0)
check("нечитаемый файл → пустое состояние", load_hwm_state("/nope/нет-такого.json"), {})
check("план выше пола → берётся план", protected_stop_price("SCHW", 109.00, state, current_price=110.52), 109.00)

# ── 6. Подрезка под рынок: стоп не может оказаться выше цены ──────────────
# Цена рухнула до 105 при поле 108.20 — иначе брокер отобьёт ордер.
check(
    "цена ниже пола → подрезка под рынок",
    locked_floor("SCHW", state, current_price=105.0),
    105.0 * (1 - 10 / 10000),
)
check("без цены подрезки нет", locked_floor("SCHW", state), 108.20)

# ── 7. Денежный итог правки ───────────────────────────────────────────────
saved = (108.20 - 96.47) * SCHW["qty"] + (257.13 - 235.17) * ABBV["qty"]
check("спасённая за ночь защита ≈ $9.59", saved, 9.59, tol=0.02)

print()
for line in FAILED:
    print(f"  ПРОВАЛ  {line}")
print(f"Проверок пройдено: {PASSED}/{PASSED + len(FAILED)}")
if not FAILED:
    print(f"Инвариант держится. Цена одной ночи: ${saved:.2f}")
raise SystemExit(1 if FAILED else 0)
