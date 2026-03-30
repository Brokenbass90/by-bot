"""
bot/family_profiles.py — Per-Symbol-Family Dynamic Parameter Profiles
======================================================================
Different coins behave differently. BTC/ETH are liquid, trend slowly, have
tighter spreads. SOL/BNB/AVAX are volatile large-caps. Mid-cap alts are
thinner, faster, more prone to false breakouts.

Using one universal parameter set for all coins is suboptimal. This module
provides per-family parameter MULTIPLIERS that scale the base strategy
parameters at runtime — no strategy code changes needed.

Families (defined in configs/family_profiles.json):
  BTC_ETH     → BTCUSDT, ETHUSDT
  LARGE_ALTS  → SOLUSDT, BNBUSDT, AVAXUSDT, LINKUSDT, DOTUSDT
  MID_ALTS    → everything else (default family)

How it works:
  Each family has a dict of multipliers. A strategy reads its base param,
  then calls `profiles.scale(symbol, param_name, base_value)` to get the
  family-adjusted value.

  Example:
      atr_stop = 1.5   # base config
      atr_stop = profiles.scale("SOLUSDT", "sl_atr_mult", atr_stop)
      # Returns 1.5 * 1.25 = 1.875 for LARGE_ALTS family (wider stop)

Integration in strategy:
    from bot.family_profiles import profiles
    sl = profiles.scale(symbol, "sl_atr_mult", base_sl_atr)
    tp = profiles.scale(symbol, "tp_atr_mult", base_tp_atr)
    cooldown = profiles.scale_int(symbol, "cooldown_bars", base_cooldown)

Config file: configs/family_profiles.json
    Reloaded every PROFILE_RELOAD_INTERVAL_S seconds (default 3600).
    Edit the JSON file on the server — takes effect within 1h, no bot restart.

ENV overrides (per-symbol, highest priority):
    FAMILY_OVERRIDE_{SYMBOL}=MID_ALTS  # force a symbol into a specific family
    PROFILE_RELOAD_INTERVAL_S=3600

Multiplier reference (defaults — override in JSON):
  BTC_ETH:
    sl_atr_mult:     0.85   (tighter stop, BTC doesn't need wide SL)
    tp_atr_mult:     1.10   (slightly wider TP, trends are persistent)
    cooldown_bars:   0.80   (can re-enter faster, fewer false breakouts)
    vol_spike_x:     1.20   (need bigger volume spike to confirm signal)
    rsi_os:          1.05   (slightly less oversold needed — more liquid)
    rsi_ob:          0.95

  LARGE_ALTS:
    sl_atr_mult:     1.25   (wider stop, SOL/AVAX chop a lot)
    tp_atr_mult:     1.15   (wider TP, momentum can extend)
    cooldown_bars:   1.00   (neutral)
    vol_spike_x:     0.90   (lower bar — thinner books, spikes are easier)
    rsi_os:          0.95   (more extreme required)
    rsi_ob:          1.05

  MID_ALTS (default):
    sl_atr_mult:     1.40   (widest stops — thin market, lots of noise)
    tp_atr_mult:     1.30   (but when they move, they MOVE)
    cooldown_bars:   1.50   (wait longer between signals — more false starts)
    vol_spike_x:     0.80   (even small spikes are meaningful in thin markets)
    rsi_os:          0.90   (needs to be more extreme)
    rsi_ob:          1.10
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

ROOT         = Path(__file__).resolve().parent.parent
PROFILE_FILE = ROOT / "configs" / "family_profiles.json"
RELOAD_INTERVAL = int(os.getenv("PROFILE_RELOAD_INTERVAL_S", "3600"))

# ── Default families ──────────────────────────────────────────────────────────

_DEFAULT_FAMILIES: Dict[str, list] = {
    "BTC_ETH":    ["BTCUSDT", "ETHUSDT"],
    "LARGE_ALTS": ["SOLUSDT", "BNBUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
                   "MATICUSDT", "ADAUSDT", "XRPUSDT", "TRXUSDT", "LTCUSDT"],
    # MID_ALTS = everything else (catch-all)
}

_DEFAULT_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "BTC_ETH": {
        "sl_atr_mult":    0.85,
        "tp_atr_mult":    1.10,
        "cooldown_bars":  0.80,
        "vol_spike_x":    1.20,
        "rsi_os":         1.05,
        "rsi_ob":         0.95,
        "ext_pct":        0.80,
        "drop_pct":       0.90,
        "be_pct":         0.90,
        "time_stop_bars": 0.80,
    },
    "LARGE_ALTS": {
        "sl_atr_mult":    1.25,
        "tp_atr_mult":    1.15,
        "cooldown_bars":  1.00,
        "vol_spike_x":    0.90,
        "rsi_os":         0.95,
        "rsi_ob":         1.05,
        "ext_pct":        1.10,
        "drop_pct":       1.10,
        "be_pct":         1.00,
        "time_stop_bars": 1.00,
    },
    "MID_ALTS": {
        "sl_atr_mult":    1.40,
        "tp_atr_mult":    1.30,
        "cooldown_bars":  1.50,
        "vol_spike_x":    0.80,
        "rsi_os":         0.90,
        "rsi_ob":         1.10,
        "ext_pct":        1.20,
        "drop_pct":       1.20,
        "be_pct":         1.10,
        "time_stop_bars": 1.25,
    },
}

# ── Data structures ──────────────────────────────────────────────────────────

@dataclass
class FamilyProfile:
    name: str
    multipliers: Dict[str, float] = field(default_factory=dict)

    def scale(self, param: str, base_value: float) -> float:
        """Return base_value * multiplier[param]. Returns base unchanged if no multiplier."""
        mult = self.multipliers.get(param)
        if mult is None:
            return base_value
        return base_value * mult

    def scale_int(self, param: str, base_value: int) -> int:
        return max(1, round(self.scale(param, float(base_value))))

    def __repr__(self) -> str:
        return f"FamilyProfile({self.name}, {len(self.multipliers)} params)"


# ── Manager ──────────────────────────────────────────────────────────────────

class FamilyProfileManager:
    """
    Singleton manager. Reads configs/family_profiles.json and provides
    per-symbol profile lookups with TTL-based hot-reload.

    Usage:
        from bot.family_profiles import profiles
        sl = profiles.scale("SOLUSDT", "sl_atr_mult", 1.5)
        family = profiles.family_name("BTCUSDT")   # → "BTC_ETH"
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, FamilyProfile] = {}
        self._symbol_map: Dict[str, str] = {}  # symbol → family_name
        self._last_load: float = 0.0
        self._load()

    # ── Internal loading ─────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load (or reload) profile definitions from JSON file + defaults."""
        families_def  = dict(_DEFAULT_FAMILIES)
        multipliers   = {k: dict(v) for k, v in _DEFAULT_MULTIPLIERS.items()}

        if PROFILE_FILE.exists():
            try:
                raw = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
                # Merge families
                for fname, symbols in raw.get("families", {}).items():
                    families_def[fname] = [s.upper() for s in symbols]
                # Deep-merge multipliers (skip metadata keys like _doc)
                for fname, mults in raw.get("multipliers", {}).items():
                    if fname.startswith("_") or not isinstance(mults, dict):
                        continue
                    if fname not in multipliers:
                        multipliers[fname] = {}
                    multipliers[fname].update({
                        k: float(v) for k, v in mults.items()
                        if not str(k).startswith("_")
                    })
                logger.debug(f"[family_profiles] loaded {PROFILE_FILE}")
            except Exception as e:
                logger.warning(f"[family_profiles] error loading {PROFILE_FILE}: {e}")

        # Build symbol → family map
        symbol_map: Dict[str, str] = {}
        for fname, symbols in families_def.items():
            for sym in symbols:
                symbol_map[sym.upper()] = fname

        # Build profile objects
        profiles: Dict[str, FamilyProfile] = {}
        all_families = set(families_def) | set(multipliers)
        for fname in all_families:
            profiles[fname] = FamilyProfile(
                name=fname,
                multipliers=multipliers.get(fname, {}),
            )
        # Ensure MID_ALTS always exists (catch-all)
        if "MID_ALTS" not in profiles:
            profiles["MID_ALTS"] = FamilyProfile(
                name="MID_ALTS",
                multipliers=multipliers.get("MID_ALTS", {}),
            )

        self._profiles   = profiles
        self._symbol_map = symbol_map
        self._last_load  = time.monotonic()

    def _maybe_reload(self) -> None:
        if time.monotonic() - self._last_load > RELOAD_INTERVAL:
            self._load()

    # ── Public API ───────────────────────────────────────────────────────────

    def family_name(self, symbol: str) -> str:
        """Return the family name for a symbol. Falls back to MID_ALTS."""
        self._maybe_reload()
        sym = symbol.upper()
        # ENV override takes priority
        override = os.getenv(f"FAMILY_OVERRIDE_{sym}", "").strip().upper()
        if override and override in self._profiles:
            return override
        return self._symbol_map.get(sym, "MID_ALTS")

    def get_profile(self, symbol: str) -> FamilyProfile:
        """Return the FamilyProfile for a symbol."""
        self._maybe_reload()
        fname = self.family_name(symbol)
        return self._profiles.get(fname, self._profiles["MID_ALTS"])

    def scale(self, symbol: str, param: str, base_value: float) -> float:
        """Scale a float parameter by the family multiplier."""
        return self.get_profile(symbol).scale(param, base_value)

    def scale_int(self, symbol: str, param: str, base_value: int) -> int:
        """Scale an int parameter by the family multiplier (rounds, min 1)."""
        return self.get_profile(symbol).scale_int(param, base_value)

    def all_families(self) -> Dict[str, FamilyProfile]:
        self._maybe_reload()
        return dict(self._profiles)

    def summary(self) -> str:
        """One-line summary for logging."""
        self._maybe_reload()
        parts = []
        for fname, prof in sorted(self._profiles.items()):
            syms = [s for s, f in self._symbol_map.items() if f == fname]
            parts.append(f"{fname}({len(syms)} syms)")
        return "FamilyProfiles: " + ", ".join(parts) + " + MID_ALTS(catch-all)"

    def force_reload(self) -> None:
        self._load()
        logger.info("[family_profiles] force-reloaded")


# ── Singleton ─────────────────────────────────────────────────────────────────
profiles = FamilyProfileManager()
