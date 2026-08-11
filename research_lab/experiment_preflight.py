#!/usr/bin/env python3
"""ПРЕДОХРАНИТЕЛЬ ЭКСПЕРИМЕНТА: доказать, что варианты различаются, ДО прогона.

    python3 research_lab/experiment_preflight.py inplay_retest_v3 \
        IRV3_STOP_BUFFER_ATR stop_buffer_atr 0.35 0.525 0.70 0.875

Как библиотека:
    from research_lab.experiment_preflight import assert_handle_differentiates
    assert_handle_differentiates("inplay_retest_v3", "IRV3_STOP_BUFFER_ATR",
                                 "stop_buffer_atr", [0.35, 0.525, 0.70, 0.875])

ЗАЧЕМ ЭТО СУЩЕСТВУЕТ
  За две недели харнесс соврал семь раз, и КАЖДЫЙ раз по одной схеме:
  вывод делался из инструмента, который не проверили перед запуском.

    кэш не тот              прогон «540 дней» шёл на 180
    ручка не та             четыре «ступени стопа» были одной конфигурацией
    порог придуманный       правило дало 81 находку и 0 верных

  Обещания «буду внимательнее» проверены трижды и не работают.
  Работает только код, который падает раньше, чем родится ложный вывод.

  Приём придуман Codex 10 августа для retest3 stop ladder. Здесь он вынесен
  в общий модуль, чтобы каждый следующий эксперимент был обязан им
  пользоваться, а не переписывать заново.

ДВА ПРАВИЛА
  1. ДО прогона: env-ручка обязана менять поле конфига, и разные значения
     обязаны давать разные результаты. Иначе эксперимент — копия себя.
  2. ПОСЛЕ прогона: результаты вариантов обязаны различаться. Если совпали
     до последнего знака — это не находка «эффекта нет», это сломанная ручка.
"""
from __future__ import annotations

import importlib
import os
import sys
from typing import Any

sys.path.insert(0, ".")


class PreflightError(RuntimeError):
    """Эксперимент не может ничего различить. Прогон запускать нельзя."""


def _strategy_class(module_name: str):
    mod = importlib.import_module(f"strategies.{module_name}")
    classes = [
        getattr(mod, n) for n in dir(mod)
        if isinstance(getattr(mod, n), type)
        and any(hasattr(getattr(mod, n), a) for a in ("maybe_signal", "evaluate"))
    ]
    if not classes:
        raise PreflightError(f"в strategies.{module_name} нет класса стратегии")
    return classes[0]


def assert_handle_differentiates(
    module_name: str,
    env_name: str,
    cfg_field: str,
    values: list,
    *,
    quiet: bool = False,
) -> list:
    """Проверяет, что env_name реально управляет cfg_field и что значения различны.

    Возвращает список фактически разрешённых значений.
    Бросает PreflightError, если ручка не читается или не различает варианты.
    """
    cls = _strategy_class(module_name)
    saved = os.environ.get(env_name)
    resolved = []
    try:
        for want in values:
            os.environ[env_name] = str(want)
            inst = cls()
            cfg = getattr(inst, "cfg", None)
            if cfg is None:
                raise PreflightError(
                    f"{module_name} не имеет .cfg — параметры в self.params, "
                    f"ручка {env_name} проверяется иначе"
                )
            if not hasattr(cfg, cfg_field):
                raise PreflightError(
                    f"{module_name}.cfg не имеет поля {cfg_field}; "
                    f"доступные: {sorted(vars(cfg))[:12]}"
                )
            got = float(getattr(cfg, cfg_field))
            if abs(got - float(want)) > 1e-12:
                raise PreflightError(
                    f"ручка не читается: {env_name}={want} -> {cfg_field}={got}. "
                    f"Эксперимент прогонит одну и ту же конфигурацию."
                )
            resolved.append(got)
    finally:
        if saved is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = saved

    if len(set(resolved)) != len(values):
        raise PreflightError(
            f"значения не различаются: {resolved}. Варианты будут копиями."
        )
    if not quiet:
        print(f"[preflight] {module_name}.{cfg_field} <- {env_name}: "
              f"{resolved}  PASS")
    return resolved


def assert_param_handle_differentiates(
    module_name: str,
    env_name: str,
    param_name: str,
    values: list,
    *,
    quiet: bool = False,
) -> list:
    """Prove that an env handle changes a strategy backed by ``.params``.

    Some newer strategy families do not expose a dataclass ``.cfg``. They use
    a dictionary of resolved parameters instead. Treating those experiments as
    exempt recreated the same silent-grid failure that this module prevents.
    """
    cls = _strategy_class(module_name)
    saved = os.environ.get(env_name)
    resolved = []
    try:
        for want in values:
            os.environ[env_name] = str(want)
            inst = cls()
            params = getattr(inst, "params", None)
            if not isinstance(params, dict):
                raise PreflightError(
                    f"{module_name} has no .params mapping; cannot verify {env_name}"
                )
            if param_name not in params:
                raise PreflightError(
                    f"{module_name}.params has no key {param_name}"
                )
            try:
                got = float(params[param_name])
                expected = float(want)
            except (TypeError, ValueError) as exc:
                raise PreflightError(
                    f"non-numeric preflight handle {env_name}->{param_name}"
                ) from exc
            if abs(got - expected) > 1e-12:
                raise PreflightError(
                    f"handle unread: {env_name}={want} -> {param_name}={got}"
                )
            resolved.append(got)
    finally:
        if saved is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = saved

    if len(set(resolved)) != len(values):
        raise PreflightError(f"values do not differentiate: {resolved}")
    if not quiet:
        print(f"[preflight] {module_name}.params[{param_name}] <- {env_name}: "
              f"{resolved}  PASS")
    return resolved


def assert_symbol_handle_differentiates(
    module_name: str,
    env_name: str,
    cfg_field: str,
    values: list[str],
    *,
    quiet: bool = False,
) -> list[tuple[str, ...]]:
    """Prove that a CSV universe handle resolves to distinct symbol sets.

    Numeric preflight cannot validate universe handles. This check compares
    normalized sets and therefore catches both an unwired env var and two
    differently formatted values that select the same universe.
    """
    cls = _strategy_class(module_name)
    saved = os.environ.get(env_name)
    resolved: list[tuple[str, ...]] = []
    try:
        for want in values:
            os.environ[env_name] = str(want)
            inst = cls()
            cfg = getattr(inst, "cfg", None)
            if cfg is None or not hasattr(cfg, cfg_field):
                raise PreflightError(
                    f"{module_name}.cfg has no universe field {cfg_field}"
                )
            got = tuple(
                sorted(
                    {
                        item.strip().upper()
                        for item in str(getattr(cfg, cfg_field) or "")
                        .replace(";", ",")
                        .split(",")
                        if item.strip()
                    }
                )
            )
            expected = tuple(
                sorted(
                    {
                        item.strip().upper()
                        for item in str(want).replace(";", ",").split(",")
                        if item.strip()
                    }
                )
            )
            if got != expected:
                raise PreflightError(
                    f"universe handle unread: {env_name}={want} -> {cfg_field}={got}"
                )
            resolved.append(got)
    finally:
        if saved is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = saved

    if len(set(resolved)) != len(values):
        raise PreflightError(f"universe values do not differentiate: {resolved}")
    if not quiet:
        print(
            f"[preflight] {module_name}.{cfg_field} <- {env_name}: "
            f"{resolved}  PASS"
        )
    return resolved


def assert_results_differ(values: list, what: str = "результаты") -> None:
    """ПОСЛЕ прогона: варианты обязаны отличаться.

    Совпадение до последнего знака означает не «эффекта нет», а «ручка
    не сработала». Именно так четыре ступени стопа оказались одним
    базовым прогоном, повторённым четырежды.
    """
    rounded = [round(float(v), 9) for v in values]
    if len(set(rounded)) != len(rounded):
        raise PreflightError(
            f"{what} совпадают между вариантами: {rounded}. "
            f"Это сломанная ручка, а не отсутствие эффекта. "
            f"Интерпретировать запрещено."
        )


def assert_autoresearch_spec_preflight(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Require executable handle checks for every varied autoresearch knob.

    Specs without ``experiment_preflight`` fail before an output directory or
    expensive subprocess is created. Every grid key with two or more distinct
    values must be mapped to a strategy config field and proven to resolve to
    distinct values.
    """
    checks = spec.get("experiment_preflight")
    if not isinstance(checks, list) or not checks:
        raise PreflightError(
            "spec has no experiment_preflight; running an unverified grid is forbidden"
        )

    grid = spec.get("grid") if isinstance(spec.get("grid"), dict) else {}
    varied = {
        str(name)
        for name, values in grid.items()
        if isinstance(values, list) and len({str(value) for value in values}) > 1
    }
    covered: set[str] = set()
    receipt: list[dict[str, Any]] = []
    for raw in checks:
        if not isinstance(raw, dict):
            raise PreflightError("experiment_preflight rows must be objects")
        module = str(raw.get("module") or "").strip()
        env_name = str(raw.get("env") or "").strip()
        cfg_field = str(raw.get("cfg_field") or "").strip()
        values = raw.get("values")
        if not isinstance(values, list) or len(values) < 2:
            values = grid.get(env_name)
        if not module or not env_name or not cfg_field or not isinstance(values, list) or len(values) < 2:
            raise PreflightError(
                f"invalid preflight row for {env_name or '?'}: module/env/cfg_field and two values required"
            )
        resolved = assert_handle_differentiates(
            module,
            env_name,
            cfg_field,
            list(values),
            quiet=True,
        )
        covered.add(env_name)
        receipt.append(
            {
                "module": module,
                "env": env_name,
                "cfg_field": cfg_field,
                "resolved": resolved,
                "status": "pass",
            }
        )

    missing = sorted(varied - covered)
    if missing:
        raise PreflightError(
            "varied grid knobs lack executable preflight: " + ",".join(missing)
        )
    return receipt


def main() -> int:
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    module_name, env_name, cfg_field = sys.argv[1], sys.argv[2], sys.argv[3]
    values = [float(v) for v in sys.argv[4:]]
    try:
        assert_handle_differentiates(module_name, env_name, cfg_field, values)
    except PreflightError as e:
        print(f"[preflight] FAIL: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
