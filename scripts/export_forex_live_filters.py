#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def _to_float(v: str, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _to_int(v: str, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _combo_id(pair: str, strategy: str) -> str:
    return f"{pair}@{strategy}"


def _write_txt(path: Path, values: List[str]) -> None:
    path.write_text(",".join(values), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Export forex ACTIVE/CANARY state into live filter files.")
    ap.add_argument("--state-csv", default="docs/forex_combo_state_latest.csv")
    ap.add_argument("--out-dir", default="docs")
    ap.add_argument("--prefix", default="forex_live_filter_latest")
    ap.add_argument("--canary-risk-mult", type=float, default=0.5)
    args = ap.parse_args()

    state_csv = Path(args.state_csv).resolve()
    if not state_csv.exists():
        raise SystemExit(f"state csv not found: {state_csv}")

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = list(csv.DictReader(state_csv.open(newline="", encoding="utf-8")))
    for r in rows:
        r["pair"] = (r.get("pair") or "").strip().upper()
        r["strategy"] = (r.get("strategy") or "").strip()
        r["state"] = (r.get("state") or "").strip().upper()
        r["last_stress_net_pips_f"] = _to_float(r.get("last_stress_net_pips", "0"))
        r["last_recent_stress_net_pips_f"] = _to_float(r.get("last_recent_stress_net_pips", "0"))
        r["last_stress_trades_i"] = _to_int(r.get("last_stress_trades", "0"))
        r["last_stress_dd_pips_f"] = _to_float(r.get("last_stress_dd_pips", "0"))

    ranked = sorted(
        [r for r in rows if r["state"] in {"ACTIVE", "CANARY"} and r["pair"] and r["strategy"]],
        key=lambda r: (
            0 if r["state"] == "ACTIVE" else 1,
            -r["last_stress_net_pips_f"],
            -r["last_recent_stress_net_pips_f"],
            r["pair"],
            r["strategy"],
        ),
    )
    active_rows = [r for r in ranked if r["state"] == "ACTIVE"]
    canary_rows = [r for r in ranked if r["state"] == "CANARY"]

    active_pairs = sorted({r["pair"] for r in active_rows})
    canary_pairs = sorted({r["pair"] for r in canary_rows})
    enabled_pairs = sorted(set(active_pairs) | set(canary_pairs))

    active_combos = [_combo_id(r["pair"], r["strategy"]) for r in active_rows]
    canary_combos = [_combo_id(r["pair"], r["strategy"]) for r in canary_rows]
    enabled_combos = active_combos + canary_combos

    # Text exports
    _write_txt(out_dir / "forex_live_active_pairs_latest.txt", active_pairs)
    _write_txt(out_dir / "forex_live_canary_pairs_latest.txt", canary_pairs)
    _write_txt(out_dir / "forex_live_enabled_pairs_latest.txt", enabled_pairs)
    _write_txt(out_dir / "forex_live_active_combos_latest.txt", active_combos)
    _write_txt(out_dir / "forex_live_canary_combos_latest.txt", canary_combos)
    _write_txt(out_dir / "forex_live_enabled_combos_latest.txt", enabled_combos)

    # Flat CSV export for quick grep/debug.
    summary_csv = out_dir / f"{args.prefix}.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "state",
                "pair",
                "strategy",
                "stress_net_pips",
                "recent_stress_net_pips",
                "stress_trades",
                "stress_dd_pips",
                "last_reason",
                "last_seen_utc",
            ]
        )
        for r in ranked:
            w.writerow(
                [
                    r["state"],
                    r["pair"],
                    r["strategy"],
                    f"{r['last_stress_net_pips_f']:.4f}",
                    f"{r['last_recent_stress_net_pips_f']:.4f}",
                    r["last_stress_trades_i"],
                    f"{r['last_stress_dd_pips_f']:.4f}",
                    r.get("last_reason", ""),
                    r.get("last_seen_utc", ""),
                ]
            )

    # JSON export for future live adapter.
    js = {
        "generated_utc": _now_utc_iso(),
        "source_state_csv": str(state_csv),
        "canary_risk_mult": float(args.canary_risk_mult),
        "active": [
            {
                "pair": r["pair"],
                "strategy": r["strategy"],
                "stress_net_pips": r["last_stress_net_pips_f"],
                "recent_stress_net_pips": r["last_recent_stress_net_pips_f"],
                "stress_trades": r["last_stress_trades_i"],
                "stress_dd_pips": r["last_stress_dd_pips_f"],
                "last_reason": r.get("last_reason", ""),
            }
            for r in active_rows
        ],
        "canary": [
            {
                "pair": r["pair"],
                "strategy": r["strategy"],
                "stress_net_pips": r["last_stress_net_pips_f"],
                "recent_stress_net_pips": r["last_recent_stress_net_pips_f"],
                "stress_trades": r["last_stress_trades_i"],
                "stress_dd_pips": r["last_stress_dd_pips_f"],
                "last_reason": r.get("last_reason", ""),
            }
            for r in canary_rows
        ],
        "active_pairs": active_pairs,
        "canary_pairs": canary_pairs,
        "enabled_pairs": enabled_pairs,
        "active_combos": active_combos,
        "canary_combos": canary_combos,
        "enabled_combos": enabled_combos,
    }
    (out_dir / f"{args.prefix}.json").write_text(json.dumps(js, ensure_ascii=True, indent=2), encoding="utf-8")

    # Env export for shell-based wiring.
    env_path = out_dir / f"{args.prefix}.env"
    env_path.write_text(
        "\n".join(
            [
                f"FOREX_ACTIVE_PAIRS={','.join(active_pairs)}",
                f"FOREX_CANARY_PAIRS={','.join(canary_pairs)}",
                f"FOREX_ENABLED_PAIRS={','.join(enabled_pairs)}",
                f"FOREX_ACTIVE_COMBOS={','.join(active_combos)}",
                f"FOREX_CANARY_COMBOS={','.join(canary_combos)}",
                f"FOREX_ENABLED_COMBOS={','.join(enabled_combos)}",
                f"FOREX_CANARY_RISK_MULT={float(args.canary_risk_mult):.2f}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print("forex live filter export done")
    print(f"source={state_csv}")
    print(f"summary_csv={summary_csv}")
    print(f"json={out_dir / f'{args.prefix}.json'}")
    print(f"env={env_path}")
    print(f"active_pairs={','.join(active_pairs) or 'none'}")
    print(f"canary_pairs={','.join(canary_pairs) or 'none'}")
    print(f"active_combos={','.join(active_combos) or 'none'}")
    print(f"canary_combos={','.join(canary_combos) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
