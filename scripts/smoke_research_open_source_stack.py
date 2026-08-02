#!/usr/bin/env python3
"""Deterministic smoke for the optional research-only acceleration stack."""
from __future__ import annotations

import json

import numpy as np
import optuna
import pandas as pd
import vectorbt as vbt


def main() -> int:
    prices = pd.Series([100.0, 101.0, 99.0, 102.0, 104.0], name="close")
    entries = pd.Series([True, False, False, False, False])
    exits = pd.Series([False, False, False, False, True])
    portfolio = vbt.Portfolio.from_signals(
        prices,
        entries,
        exits,
        init_cash=1000.0,
        fees=0.001,
        freq="1D",
    )

    sampler = optuna.samplers.GridSampler({"x": [-1.0, 0.0, 1.0]})
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(lambda trial: -(trial.suggest_float("x", -1.0, 1.0) - 1.0) ** 2, n_trials=3)

    payload = {
        "schema_id": "research_open_source_stack_smoke_v1",
        "vectorbt_version": vbt.__version__,
        "optuna_version": optuna.__version__,
        "numpy_version": np.__version__,
        "portfolio_total_return": float(portfolio.total_return()),
        "optuna_trials": len(study.trials),
        "optuna_best_x": float(study.best_params["x"]),
        "live_authority": False,
    }
    assert payload["portfolio_total_return"] > 0
    assert payload["optuna_trials"] == 3
    assert payload["optuna_best_x"] == 1.0
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
