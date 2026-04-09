#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent.parent
ROUTER_STATE_PATH = ROOT / "runtime" / "router" / "symbol_router_state.json"
MEMORY_PATH = ROOT / "runtime" / "control_plane" / "router_symbol_memory.json"
OUT_PATH = ROOT / "runtime" / "control_plane" / "router_quality_audit.json"


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def _memory_for_symbol(memory: Dict[str, Any], *, env_key: str, regime: str, symbol: str) -> Dict[str, Any]:
    env = dict((memory.get("profiles") or {}).get(env_key) or {})
    symbol_u = str(symbol or "").strip().upper()
    best: Dict[str, Any] = {}
    for regime_key in (regime, "all"):
        info = dict((((env.get(regime_key) or {}).get("symbols") or {}).get(symbol_u) or {}))
        if not info:
            continue
        info["memory_source"] = regime_key
        if not best or float(info.get("penalty", 0.0) or 0.0) >= float(best.get("penalty", 0.0) or 0.0):
            best = info
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit current router selections against per-symbol memory.")
    ap.add_argument("--router-state", default=str(ROUTER_STATE_PATH))
    ap.add_argument("--symbol-memory", default=str(MEMORY_PATH))
    ap.add_argument("--warn-penalty", type=float, default=0.35)
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    router_state = _load_json(Path(args.router_state), {})
    symbol_memory = _load_json(Path(args.symbol_memory), {})
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path

    profiles = dict(router_state.get("profiles") or {})
    regime = str(router_state.get("regime") or "unknown")
    findings: List[Dict[str, Any]] = []
    per_profile: Dict[str, Any] = {}

    for env_key, info in sorted(profiles.items()):
        symbols = list(info.get("symbols") or [])
        flagged: List[Dict[str, Any]] = []
        for symbol in symbols:
            mem = _memory_for_symbol(symbol_memory, env_key=env_key, regime=regime, symbol=symbol)
            penalty = float(mem.get("penalty", 0.0) or 0.0)
            if penalty >= float(args.warn_penalty):
                flagged.append(
                    {
                        "symbol": symbol,
                        "penalty": round(penalty, 4),
                        "reason": str(mem.get("reason") or ""),
                        "trades": int(mem.get("trades") or 0),
                        "memory_source": str(mem.get("memory_source") or ""),
                    }
                )
        per_profile[env_key] = {
            "selected": symbols,
            "flagged": flagged,
            "flagged_count": len(flagged),
        }
        if flagged:
            findings.append(
                {
                    "env_key": env_key,
                    "profile_id": info.get("profile_id"),
                    "flagged": flagged,
                }
            )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "router_state_path": str(Path(args.router_state)),
        "symbol_memory_path": str(Path(args.symbol_memory)),
        "regime": regime,
        "warn_penalty": float(args.warn_penalty),
        "finding_count": len(findings),
        "findings": findings,
        "profiles": per_profile,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")

    if not args.quiet:
        print(f"saved={out_path}")
        print(f"findings={len(findings)}")
        for item in findings:
            flagged = ", ".join(f"{row['symbol']}:{row['penalty']:.2f}" for row in item["flagged"])
            print(f"{item['env_key']}: {flagged}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
