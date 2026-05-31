#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_strategy_registry.py — produce a single source of truth for strategy state.

Scans:
  - strategies/*.py                       (module files + class names)
  - smart_pump_reversal_bot.py            (ENABLE_*_TRADING, *_RISK_MULT,
                                            *_SYMBOL_ALLOWLIST, wired-in tuples)
  - configs/autoresearch/*.json           (active/historical sweeps per family)
  - configs/approved_strategy_params.env  (reviewed live overlay)
  - configs/auto_apply_params.env         (auto-applied overlay)
  - configs/att1_shadow_candidate.env etc (candidate envs)

Outputs:
  runtime/strategy_registry.json          (machine-readable)
  prints text summary to stdout

Why this exists:
  Today, the answer to "is ATT1 actually live?" requires reading 4 places.
  The predecessor session conflated v1/v2 of alt_trendline_touch because
  there was no canonical map. With this registry, drift is one diff away.

Usage:
  python3 scripts/build_strategy_registry.py            # build + print
  python3 scripts/build_strategy_registry.py --json     # raw JSON
  python3 scripts/build_strategy_registry.py --drift    # only show drift entries
  python3 scripts/build_strategy_registry.py --tg       # send drift via Telegram
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_DIR = ROOT / "strategies"
BOT_PATH = ROOT / "smart_pump_reversal_bot.py"
SWEEP_DIR = ROOT / "configs" / "autoresearch"
ENV_FILES = [
    ROOT / "configs" / "approved_strategy_params.env",
    ROOT / "configs" / "auto_apply_params.env",
    ROOT / "configs" / "att1_shadow_candidate.env",
    ROOT / "configs" / "asb1_canary.env",
    ROOT / "configs" / "asb1_bear_bounce_canary.env",
]
OUTPUT_PATH = ROOT / "runtime" / "strategy_registry.json"

# Module-name → strategy-family-prefix (used to attribute env vars to strategies)
# Built dynamically below from class introspection.
_FAMILY_OVERRIDES = {
    "alt_resistance_fade_v1":         "ARF1",
    "alt_sloped_channel_v1":          "ASC1",
    "alt_support_bounce_v1":          "BOUNCE1",
    "alt_range_scalp_v1":             "RANGE",
    "alt_range_reclaim_v1":           "RANGE",
    "impulse_volume_breakout_v1":     "IVB1",
    "alt_inplay_breakdown_v1":        "BREAKDOWN",
    "alt_inplay_breakdown_v2":        "BREAKDOWN2",
    "alt_trendline_touch_v1":         "ATT1",
    "alt_trendline_touch_v2":         "ATT2",
    "alt_slope_break_v1":             "ASB1",
    "alt_bear_regime_continuation_v1":"BRC1",
    "alt_horizontal_break_v1":        "HZBO1",
    "alt_sloped_momentum_v1":         "ASM1",
    "alt_support_reclaim_v1":         "SUPPORT_RECLAIM",
    "elder_triple_screen_v2":         "ETS2",
    "elder_triple_screen_v3":         "ETS3",
    "btc_eth_midterm_pullback":       "MTPB",
    "btc_eth_midterm_pullback_v2":    "MTPB2",
    "btc_eth_midterm_v3":             "MTPB3",
    "session_open_breakout_v1":       "SOB1",
    "funding_rate_reversion_v1":      "FR",
    "liquidation_cascade_entry_v1":   "LC",
    "micro_scalper_v1":               "MSCALP",
    "alt_spike_rejection_v1":         "ASR1",
    "alt_pullback_continuation_v1":   "APC1",
    "alt_squeeze_breakout_v1":        "ASQB1",
    "alt_whale_print_follow_v1":      "AWPF1",
    "alt_vwap_mean_reversion_v1":     "AVW1",
    "alt_liquidity_sweep_reversal_v2":"ALSR2",
    "alt_volume_spike_momentum_v1":   "AVSM1",
    "alt_momentum_breakout_v1":       "AMB1",
    "inplay_breakout":                "BREAKOUT",
}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _scan_strategy_modules() -> Dict[str, Dict[str, str]]:
    """For each strategies/*.py file, extract the main class name."""
    if not STRATEGIES_DIR.exists():
        return {}
    result: Dict[str, Dict[str, str]] = {}
    for f in sorted(STRATEGIES_DIR.glob("*.py")):
        if f.stem.startswith("_"):
            continue
        src = _read(f)
        # Heuristic: first class definition
        m = re.search(r'^class\s+(\w+)', src, re.MULTILINE)
        cls = m.group(1) if m else ""
        result[f.stem] = {
            "module_path": str(f.relative_to(ROOT)),
            "class_name": cls,
            "loc": src.count("\n"),
        }
    return result


def _scan_bot_imports(bot_src: str) -> Set[str]:
    """Return module names imported via 'from strategies.X import ...' AND
    transitive imports via *_live wrapper modules in strategies/.
    """
    found = set()
    for m in re.finditer(r'from\s+strategies\.(\w+)\s+import', bot_src):
        found.add(m.group(1))
    # Transitive: scan strategies/*_live.py for nested imports
    for live_mod in list(found):
        if live_mod.endswith("_live"):
            live_path = STRATEGIES_DIR / f"{live_mod}.py"
            if live_path.exists():
                live_src = _read(live_path)
                for m in re.finditer(r'from\s+strategies\.(\w+)\s+import', live_src):
                    found.add(m.group(1))
                for m in re.finditer(r'from\s+\.(\w+)\s+import', live_src):
                    # relative import: from .X import Y
                    found.add(m.group(1))
    return found


def _scan_bot_wired_tuples(bot_src: str) -> Dict[str, str]:
    """Find lines like (ENABLE_X_TRADING, "module_name"); these are 'wired in'."""
    wired = {}
    for m in re.finditer(r'\((ENABLE_\w+_TRADING),\s*"(\w+)"\)', bot_src):
        wired[m.group(2)] = m.group(1)
    return wired


def _scan_bot_env_vars(bot_src: str) -> Dict[str, Dict[str, Any]]:
    """Extract all *_RISK_MULT and ENABLE_*_TRADING declarations from the bot."""
    env_map: Dict[str, Dict[str, Any]] = {}

    # ENABLE_*_TRADING = os.getenv("ENABLE_X_TRADING", "Y")
    for m in re.finditer(
        r'(ENABLE_\w+_TRADING)\s*=\s*os\.getenv\(\s*"(ENABLE_\w+_TRADING)",\s*"([^"]*)"\)',
        bot_src,
    ):
        if m.group(1) == m.group(2):
            env_map[m.group(1)] = {
                "type": "enable_flag",
                "default": m.group(3),
            }

    # X_RISK_MULT — both old max(0.05, ...) and new _risk_mult_or_pause(...)
    # Old pattern
    for m in re.finditer(
        r'(\w+_RISK_MULT)\s*=\s*max\(([\d\.]+),\s*float\(os\.getenv\(\s*"(\w+_RISK_MULT)",\s*"([^"]*)"',
        bot_src,
    ):
        if m.group(1) == m.group(3):
            env_map[m.group(1)] = {
                "type": "risk_mult",
                "floor": float(m.group(2)),
                "default": m.group(4),
            }
    # New helper pattern
    for m in re.finditer(
        r'(\w+_RISK_MULT)\s*=\s*_risk_mult_or_pause\(\s*"(\w+_RISK_MULT)",\s*"([^"]*)"',
        bot_src,
    ):
        if m.group(1) == m.group(2):
            env_map[m.group(1)] = {
                "type": "risk_mult",
                "floor": 0.05,
                "default": m.group(3),
                "pause_supported": True,
            }
    # ATT1/BRC1 use max(0.0, ...) directly
    for m in re.finditer(
        r'(\w+_RISK_MULT)\s*=\s*max\(0\.0,\s*float\(os\.getenv\(\s*"(\w+_RISK_MULT)",\s*"([^"]*)"',
        bot_src,
    ):
        if m.group(1) == m.group(2):
            env_map.setdefault(m.group(1), {})
            env_map[m.group(1)].update({
                "type": "risk_mult",
                "floor": 0.0,
                "default": m.group(3),
                "pause_supported": True,
            })

    return env_map


def _scan_bot_allowlists(bot_src: str) -> Dict[str, str]:
    """Find X_SYMBOL_ALLOWLIST defaults in the bot."""
    aw = {}
    for m in re.finditer(
        r'(\w+_SYMBOL_ALLOWLIST).*?os\.getenv\(\s*"(\w+_SYMBOL_ALLOWLIST)",\s*"([^"]*)"\)',
        bot_src,
        re.DOTALL,
    ):
        if m.group(1) == m.group(2):
            aw[m.group(1)] = m.group(3)
    return aw


def _scan_sweep_configs() -> Dict[str, List[str]]:
    """Map module-name → list of sweep JSON files that mention it in --strategies."""
    if not SWEEP_DIR.exists():
        return {}
    result: Dict[str, List[str]] = {}
    for path in SWEEP_DIR.glob("*.json"):
        try:
            data = json.loads(_read(path))
        except json.JSONDecodeError:
            continue
        strats: List[str] = []
        cmd = data.get("command") or []
        if isinstance(cmd, list):
            try:
                i = cmd.index("--strategies")
                strats = [s.strip() for s in str(cmd[i + 1]).split(",") if s.strip()]
            except (ValueError, IndexError):
                pass
        if not strats and isinstance(data.get("strategies"), list):
            strats = data["strategies"]
        for s in strats:
            result.setdefault(s, []).append(path.name)
    return result


def _read_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out = {}
    for line in _read(path).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _aggregate_env_overlays() -> Dict[str, Dict[str, str]]:
    """Read every env file in ENV_FILES, return {file_name: {key: val}}."""
    out = {}
    for f in ENV_FILES:
        d = _read_env_file(f)
        if d:
            out[f.name] = d
    return out


def _family_of(module_name: str) -> str:
    """Return short family prefix (ATT1, ARF1, etc.) for a module name."""
    return _FAMILY_OVERRIDES.get(module_name, module_name.upper())


def _build_registry() -> Dict[str, Any]:
    bot_src = _read(BOT_PATH)
    modules = _scan_strategy_modules()
    wired = _scan_bot_wired_tuples(bot_src)
    imports = _scan_bot_imports(bot_src)
    env_vars = _scan_bot_env_vars(bot_src)
    allowlists = _scan_bot_allowlists(bot_src)
    sweep_map = _scan_sweep_configs()
    env_overlays = _aggregate_env_overlays()

    registry: Dict[str, Any] = {}
    drift_warnings: List[str] = []

    # For each module, build a registry entry
    for mod_name, info in modules.items():
        family = _family_of(mod_name)
        risk_mult_var = f"{family}_RISK_MULT"
        enable_flag = wired.get(mod_name)
        if not enable_flag:
            # Some strategies use family-based naming like ENABLE_ATT1_TRADING
            candidate = f"ENABLE_{family}_TRADING"
            if candidate in env_vars:
                enable_flag = candidate

        # Risk mult metadata
        risk_meta = env_vars.get(risk_mult_var, {})
        enable_meta = env_vars.get(enable_flag, {}) if enable_flag else {}

        # Allowlist default
        allowlist_var = f"{family}_SYMBOL_ALLOWLIST"
        allowlist_default = allowlists.get(allowlist_var, "")

        # Sweep configs that touch this module
        sweeps = sweep_map.get(mod_name, [])

        # Env overlays that mention this family
        in_envs: Dict[str, Dict[str, str]] = {}
        for env_name, kvs in env_overlays.items():
            relevant = {k: v for k, v in kvs.items() if k.startswith(family + "_") or k == enable_flag or k == risk_mult_var}
            if relevant:
                in_envs[env_name] = relevant

        entry = {
            "family":            family,
            "module":            mod_name,
            "module_path":       info["module_path"],
            "class_name":        info["class_name"],
            "loc":               info["loc"],
            "imported_in_bot":   mod_name in imports,
            "wired_in_runner":   mod_name in wired,
            "enable_flag":       enable_flag,
            "enable_default":    enable_meta.get("default", ""),
            "risk_mult_var":     risk_mult_var if risk_meta else None,
            "risk_mult_default": risk_meta.get("default", ""),
            "risk_mult_floor":   risk_meta.get("floor"),
            "pause_supported":   risk_meta.get("pause_supported", False),
            "allowlist_var":     allowlist_var if allowlist_default else None,
            "allowlist_default": allowlist_default,
            "sweep_configs":     sorted(sweeps),
            "sweep_count":       len(sweeps),
            "in_env_overlays":   in_envs,
        }

        # Drift detection — only flag things actually concerning
        is_live_wrapper = mod_name.endswith("_live")

        if entry["wired_in_runner"] and not entry["imported_in_bot"]:
            entry.setdefault("drift", []).append(
                "wired in tuple but not imported (direct or via _live wrapper) — likely ImportError"
            )
        if entry["wired_in_runner"] and not entry["enable_flag"]:
            entry.setdefault("drift", []).append(
                f"wired in but no ENABLE_{family}_TRADING flag found"
            )
        # Risk mult/floor consistency — only for strategies actually wired
        if entry["wired_in_runner"] and entry["risk_mult_var"] and not entry["pause_supported"]:
            entry.setdefault("drift", []).append(
                f"{risk_mult_var} has floor>0 — live_vs_backtest_monitor pause via 0.0 will NOT zero risk"
            )

        if "drift" in entry:
            drift_warnings.extend(f"{mod_name}: {x}" for x in entry["drift"])

        registry[mod_name] = entry

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_modules": len(modules),
        "total_wired": len(wired),
        "total_drift": len(drift_warnings),
        "drift_warnings": drift_warnings,
        "modules": registry,
    }


def _print_summary(reg: Dict[str, Any], drift_only: bool = False) -> None:
    print(f"Strategy Registry — generated {reg['generated_at']}")
    print(f"  modules in strategies/:  {reg['total_modules']}")
    print(f"  wired in bot runner:     {reg['total_wired']}")
    print(f"  drift warnings:          {reg['total_drift']}")
    print()
    if drift_only:
        if not reg["drift_warnings"]:
            print("No drift detected ✅")
        else:
            print("Drift warnings:")
            for w in reg["drift_warnings"]:
                print(f"  ⚠️  {w}")
        return

    print(f"{'family':<12} {'module':<38} {'enable':<8} {'risk':<8} {'floor':<6} {'sweeps':<7} {'drift'}")
    print("-" * 110)
    for mod, e in sorted(reg["modules"].items()):
        if not e["wired_in_runner"] and e["sweep_count"] == 0 and not e["imported_in_bot"]:
            continue  # skip dormant modules
        enable = "✓" if e["wired_in_runner"] else "—"
        risk_def = e["risk_mult_default"] or "—"
        floor = "—" if e["risk_mult_floor"] is None else str(e["risk_mult_floor"])
        sweeps = str(e["sweep_count"]) if e["sweep_count"] else "—"
        drift = "🔶" if e.get("drift") else ""
        print(f"{e['family']:<12} {mod:<38} {enable:<8} {risk_def:<8} {floor:<6} {sweeps:<7} {drift}")


def _tg_send(text: str) -> None:
    token = os.getenv("TG_TOKEN", "").strip()
    chat = (os.getenv("TG_CHAT_ID") or os.getenv("TG_CHAT") or "").strip()
    if not token or not chat:
        return
    try:
        payload = json.dumps({"chat_id": chat, "text": text[:3500], "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload, headers={"Content-Type": "application/json"}, method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as exc:
        print(f"[registry] TG send failed: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build canonical strategy registry from code + configs.")
    ap.add_argument("--json", action="store_true", help="Emit machine-readable JSON only.")
    ap.add_argument("--drift", action="store_true", help="Print only drift warnings.")
    ap.add_argument("--tg", action="store_true", help="Send drift report to Telegram.")
    ap.add_argument("--no-write", action="store_true", help="Don't write runtime/strategy_registry.json")
    args = ap.parse_args()

    reg = _build_registry()

    if not args.no_write:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = OUTPUT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(reg, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(OUTPUT_PATH)

    if args.json:
        print(json.dumps(reg, indent=2, ensure_ascii=False))
    else:
        _print_summary(reg, drift_only=args.drift)

    if args.tg and reg["drift_warnings"]:
        lines = [f"🔶 <b>Strategy registry drift</b> — {reg['total_drift']} issues:"]
        for w in reg["drift_warnings"][:20]:
            lines.append(f"  • <code>{w[:100]}</code>")
        if reg["total_drift"] > 20:
            lines.append(f"  …and {reg['total_drift'] - 20} more")
        _tg_send("\n".join(lines))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
