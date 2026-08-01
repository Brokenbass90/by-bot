#!/usr/bin/env python3
"""Sealed H4 regime mean-reversion using the shared FX cost/OOS harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forex.strategies.h4_regime_mean_reversion_v1 import Config, H4RegimeMeanReversionV1
from scripts.run_fx_h4_momentum_v1 import main as momentum_main


# The runner contract is identical to H4 momentum.  Temporarily substitute its
# strategy factory and defaults, then execute the already tested aggregation,
# fold and terminal-receipt path without copying a second metrics engine.
if __name__ == "__main__":
    import scripts.run_fx_h4_momentum_v1 as shared

    def strategy(fixed: dict):
        fields = Config.__dataclass_fields__
        return H4RegimeMeanReversionV1(Config(**{key: value for key, value in fixed.items() if key in fields}))

    shared._strategy = strategy
    shared.DEFAULT_PREREG = ROOT / "configs" / "research" / "fx_h4_regime_mean_reversion_v1_prereg_20260801.json"
    default_out = ROOT / "reports" / "research" / "fx_h4_regime_mean_reversion_v1_20260801"
    if "--out-dir" not in sys.argv:
        sys.argv.extend(["--out-dir", str(default_out)])
    raise SystemExit(momentum_main())
