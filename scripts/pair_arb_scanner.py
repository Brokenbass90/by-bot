#!/usr/bin/env python3
"""Multi-pair stat-arb scanner — market-neutral, regime-agnostic (Opus 2026-06-08).

Expands pair_stat_arb_v1 from a single hardcoded ETH/BTC to a PORTFOLIO of pairs.
Market-neutral statarb trades the spread between correlated majors, so it works in
chop / bear / bull alike and adds entry frequency WITHOUT needing a directional
edge — directly answering "bot goes days without trading".

Honest guardrails: more entries only help if they clear costs. Each pair must be
cointegrated (half-life filter) AND liquid; candidates are ranked by |z|; a max
concurrent cap keeps risk bounded. Validate via validate_pair_arb (walk-forward +
fee_sensitivity) before any live capital — pair trades had ~43% fee drag.

Pure-stdlib over close-price series; live 2-leg execution is a separate Codex step.
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from strategies.pair_stat_arb_v1 import PairStatArbV1, PairConfig

# Sensible liquid-major default universe (Bybit perps). Tune on server.
DEFAULT_UNIVERSE = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT", "LTCUSDT"]


def make_pairs(symbols: Sequence[str]) -> List[Tuple[str, str]]:
    return list(combinations(sorted(set(symbols)), 2))


def scan_pairs(
    price_map: Dict[str, Sequence[float]],
    pairs: Optional[Sequence[Tuple[str, str]]] = None,
    cfg: Optional[PairConfig] = None,
    max_candidates: int = 5,
) -> List[Dict[str, Any]]:
    """Return ranked entry candidates (tradeable + |z|>=entry_z), best first."""
    cfg = cfg or PairConfig()
    eng = PairStatArbV1(cfg)
    if pairs is None:
        pairs = make_pairs(list(price_map.keys()))
    out: List[Dict[str, Any]] = []
    for a, b in pairs:
        pa, pb = price_map.get(a), price_map.get(b)
        if not pa or not pb:
            continue
        sig = eng.signal(a, b, pa, pb)
        if sig is None:
            continue
        out.append({
            "pair": f"{a}/{b}", "long": sig.long_symbol, "short": sig.short_symbol,
            "z": round(sig.z, 3), "abs_z": abs(sig.z), "beta": round(sig.beta, 3),
            "half_life": round(sig.half_life, 2), "corr": round(sig.corr, 3),
        })
    out.sort(key=lambda c: c["abs_z"], reverse=True)
    return out[:max_candidates]


def _load_closes(sym: str, interval: str) -> List[float]:
    import glob, csv, json as _json
    rows: Dict[int, float] = {}
    for f in glob.glob(f"data_cache/{sym}_{interval}_*.json"):
        try:
            for r in _json.load(open(f)):
                rows[int(r["ts"])] = float(r["c"])
        except Exception:
            pass
    return [rows[t] for t in sorted(rows)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default=",".join(DEFAULT_UNIVERSE))
    ap.add_argument("--interval", default="60")
    ap.add_argument("--lookback", type=int, default=336)
    ap.add_argument("--max", type=int, default=5)
    args = ap.parse_args()
    syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    price_map = {s: _load_closes(s, args.interval) for s in syms}
    price_map = {s: v for s, v in price_map.items() if len(v) >= args.lookback}
    print(f"symbols with data: {sorted(price_map)}")
    cands = scan_pairs(price_map, cfg=PairConfig(lookback=args.lookback), max_candidates=args.max)
    print(json.dumps({"candidates": cands}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
