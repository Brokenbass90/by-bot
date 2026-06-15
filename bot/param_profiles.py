"""Resolve per-coin-family parameter sets for a strategy.

One strategy, different params per coin tier (the owner's idea): majors mean-
revert cleaner -> tighter stops; micro-caps are noisier -> wider stops / shorter
holds. Profiles live in configs/strategy_param_profiles.json and are HYPOTHESES
to validate via walk-forward, not proven optima.

Usage:
    from bot.param_profiles import resolve_params, classify_tier
    tier = classify_tier("SOLUSDT")                  # -> "major"
    env  = resolve_params("ASB1", "SOLUSDT")          # -> {"ASB1_SL_ATR_MULT": "0.70", ...}
    # apply env overrides before instantiating the strategy for that coin.

Pure stdlib. Read-only. A realized-vol value can be passed to classify unseen
coins; without it they fall to the default tier.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
_PROFILE_PATH = ROOT / "configs" / "strategy_param_profiles.json"


def _load() -> dict:
    try:
        return json.loads(_PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tiers": {}, "profiles": {}, "default_tier": "micro", "vol_fallback": {}}


def classify_tier(symbol: str, realized_vol: Optional[float] = None, cfg: Optional[dict] = None) -> str:
    cfg = cfg or _load()
    tiers = cfg.get("tiers", {})
    for tier, members in tiers.items():
        if symbol in members:
            return tier
    vf = cfg.get("vol_fallback", {})
    if realized_vol is not None and vf:
        if realized_vol <= float(vf.get("major_max_vol", 0)):
            return "major"
        if realized_vol <= float(vf.get("mid_max_vol", 0)):
            return "mid"
    return cfg.get("default_tier", "micro")


def resolve_params(strategy: str, symbol: str, realized_vol: Optional[float] = None,
                   cfg: Optional[dict] = None) -> Dict[str, str]:
    """Env-var overrides for (strategy, symbol). Empty dict if no profile."""
    cfg = cfg or _load()
    tier = classify_tier(symbol, realized_vol, cfg)
    prof = (cfg.get("profiles", {}).get(strategy) or {})
    return dict(prof.get(tier, {}))


def explain(strategy: str, symbol: str, realized_vol: Optional[float] = None) -> str:
    cfg = _load()
    tier = classify_tier(symbol, realized_vol, cfg)
    params = resolve_params(strategy, symbol, realized_vol, cfg)
    kv = " ".join(f"{k}={v}" for k, v in params.items()) or "(no profile)"
    return f"{strategy}/{symbol}: tier={tier} -> {kv}"
