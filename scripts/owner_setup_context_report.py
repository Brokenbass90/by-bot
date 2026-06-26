#!/usr/bin/env python3
"""Build a cache-only owner-style setup context report.

This is a research/diagnostic bridge between the owner's manual logic and the
existing strategy stack.  It does not trade.  It reads cached candles and ranks
symbols by whether they currently satisfy:

  volume-inplay → strong 1H level → close entry distance → room to next level.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.geometry_cache import load_rows
from bot.owner_setup_context import OwnerSetupConfig, score_owner_retest_context


DEFAULT_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "LINKUSDT",
    "ADAUSDT",
    "DOTUSDT",
    "LTCUSDT",
    "DOGEUSDT",
    "XRPUSDT",
    "AVAXUSDT",
    "SUIUSDT",
    "ONDOUSDT",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_symbols(raw: str) -> list[str]:
    return [s.strip().upper() for s in str(raw or "").replace(";", ",").split(",") if s.strip()]


def _md(rows: list[dict[str, Any]]) -> str:
    lines = [
        f"# Owner setup context report — {_utc_now_iso()}",
        "",
        "Read-only diagnostic. Scores whether current cached candles resemble the owner's manual setup logic:",
        "`volume-inplay → strong 1H level → close retest → room to next level`.",
        "",
        "| rank | symbol | side | ok | score | rejects | price | level | dist ATR | target | room ATR | RR proxy | inflow x | inflow z |",
        "|---:|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(rows, 1):
        rejects = ",".join(r.get("rejects") or [])[:70]
        lines.append(
            "| {rank} | {symbol} | {side} | {ok} | {score:.3f} | {rejects} | {price:.6g} | {level} | {dist} | {target} | {room} | {rr} | {mult:.2f} | {z:.2f} |".format(
                rank=i,
                symbol=r.get("symbol", ""),
                side=r.get("side", ""),
                ok=1 if r.get("ok") else 0,
                score=float(r.get("score") or 0.0),
                rejects=rejects or "-",
                price=float(r.get("price") or 0.0),
                level="-" if r.get("level_price") is None else f"{float(r['level_price']):.6g}",
                dist="-" if r.get("distance_to_level_atr") is None else f"{float(r['distance_to_level_atr']):.2f}",
                target="-" if r.get("target_price") is None else f"{float(r['target_price']):.6g}",
                room="-" if r.get("room_to_target_atr") is None else f"{float(r['room_to_target_atr']):.2f}",
                rr="-" if r.get("rr_proxy") is None else f"{float(r['rr_proxy']):.2f}",
                mult=float(r.get("inflow_mult") or 0.0),
                z=float(r.get("inflow_z") or 0.0),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Owner setup context cache-only report")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--cache-dir", default=str(ROOT / "data_cache"))
    ap.add_argument("--out-json", default=str(ROOT / "reports" / "OWNER_SETUP_CONTEXT_latest.json"))
    ap.add_argument("--out-md", default=str(ROOT / "reports" / "OWNER_SETUP_CONTEXT_latest.md"))
    ap.add_argument("--min-recent-quote-usd", type=float, default=250_000.0)
    ap.add_argument("--min-inflow-mult", type=float, default=1.8)
    ap.add_argument("--min-inflow-z", type=float, default=1.5)
    ap.add_argument("--max-entry-dist-atr", type=float, default=0.85)
    ap.add_argument("--allow-non-inplay", action="store_true", help="Score levels even when volume-inplay fails")
    args = ap.parse_args()

    cache_dir = Path(args.cache_dir).expanduser()
    cfg = OwnerSetupConfig(
        min_recent_quote_usd=float(args.min_recent_quote_usd),
        min_inflow_mult=float(args.min_inflow_mult),
        min_inflow_z=float(args.min_inflow_z),
        max_entry_dist_atr=float(args.max_entry_dist_atr),
        require_inplay_volume=not bool(args.allow_non_inplay),
    )

    rows_out: list[dict[str, Any]] = []
    for symbol in _parse_symbols(args.symbols):
        rows_5 = load_rows(symbol, "5", data_cache_dir=cache_dir)
        rows_60 = load_rows(symbol, "60", data_cache_dir=cache_dir)
        if len(rows_5) < cfg.baseline_bars + cfg.recent_bars or len(rows_60) < 60:
            rows_out.append(
                {
                    "symbol": symbol,
                    "side": "both",
                    "ok": False,
                    "score": 0.0,
                    "rejects": ["data_missing"],
                    "rows_5m": len(rows_5),
                    "rows_1h": len(rows_60),
                }
            )
            continue
        for side in ("long", "short"):
            ctx = score_owner_retest_context(rows_5, rows_60, side=side, cfg=cfg).to_dict()
            ctx["symbol"] = symbol
            ctx["rows_5m"] = len(rows_5)
            ctx["rows_1h"] = len(rows_60)
            rows_out.append(ctx)

    rows_out.sort(key=lambda r: (bool(r.get("ok")), float(r.get("score") or 0.0)), reverse=True)

    payload = {
        "generated_at_utc": _utc_now_iso(),
        "cache_dir": str(cache_dir),
        "config": cfg.__dict__,
        "rows": rows_out,
    }
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md.write_text(_md(rows_out), encoding="utf-8")
    print(f"json={out_json}")
    print(f"md={out_md}")
    print(f"candidates_ok={sum(1 for r in rows_out if r.get('ok'))}/{len(rows_out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

