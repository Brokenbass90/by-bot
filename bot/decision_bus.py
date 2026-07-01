"""AI-legible decision bus — one honest, structured record per trade decision.

Every leg (crypto or forex) emits ONE record for each decision (enter or skip),
carrying the FULL context computed by our helper modules: range_filter,
retest_quality, elder_filter, breakout_confirm, exposure_gate, position_sizing,
plus the plan and (after close) the outcome. This gives:
  * the in-bot AI ONE honest surface to analyze/rank/flag (no blind spots);
  * a uniform schema across ALL strategies (comparable apples-to-apples);
  * the input for meta-labeling and edge-decay monitoring;
  * an honest post-trade audit trail (realized R vs expected).

Pure stdlib (json). Records are plain dicts (JSON-serializable) so live, backtest
and AI all read the same thing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence

SCHEMA_VERSION = "decision_bus_v1"


def _get(obj: Any, name: str, default: Any = None) -> Any:
    """Read attr from a dataclass/obj OR key from a dict, defensively."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


@dataclass
class DecisionRecord:
    ts: int
    symbol: str
    strategy: str
    side: str                       # "long" | "short"
    decision: str                   # "enter" | "skip"
    timeframe: str = ""
    reason: str = ""
    signal_strength: float = float("nan")
    context: Dict[str, Any] = field(default_factory=dict)
    plan: Dict[str, Any] = field(default_factory=dict)
    outcome: Dict[str, Any] = field(default_factory=dict)
    schema: str = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), default=str)


def build_decision(
    *,
    ts: int,
    symbol: str,
    strategy: str,
    side: str,
    decision: str,
    timeframe: str = "",
    reason: str = "",
    signal_strength: float = float("nan"),
    range_state: Any = None,
    retest: Any = None,
    elder: Any = None,
    breakout: Any = None,
    exposure: Any = None,
    size: Any = None,
    entry: Any = None,
    plan: Any = None,
    extra: Optional[Dict[str, Any]] = None,
) -> DecisionRecord:
    """Assemble a uniform record from whatever helper states the leg computed."""
    ctx: Dict[str, Any] = {}
    if range_state is not None:
        ctx["range"] = {"is_range": _get(range_state, "is_range"),
                        "regime": _get(range_state, "regime"),
                        "votes": _get(range_state, "votes"),
                        "pos_in_channel": _get(range_state, "pos_in_channel"),
                        "side_hint": _get(range_state, "side_hint")}
    if retest is not None:
        ctx["retest"] = {"entry_ok": _get(retest, "entry_ok"),
                         "quality": _get(retest, "quality"),
                         "dist_atr": _get(retest, "dist_atr"),
                         "freshness_bars": _get(retest, "freshness_bars"),
                         "touches": _get(retest, "touches")}
    if elder is not None:
        ctx["elder"] = {"tide": _get(elder, "tide"), "bias": _get(elder, "bias"),
                        "allow_long": _get(elder, "allow_long"),
                        "allow_short": _get(elder, "allow_short")}
    if breakout is not None:
        ctx["breakout"] = {"confirmed": _get(breakout, "confirmed"),
                           "direction": _get(breakout, "direction"),
                           "kind": _get(breakout, "kind"),
                           "close_beyond_atr": _get(breakout, "close_beyond_atr")}
    if exposure is not None:
        ctx["exposure"] = {"allow": _get(exposure, "allow"),
                           "cluster_risk_pct": _get(exposure, "cluster_risk_pct"),
                           "scaled_risk_pct": _get(exposure, "scaled_risk_pct"),
                           "correlated": _get(exposure, "correlated")}
    if size is not None:
        ctx["size"] = {"qty": _get(size, "qty"), "risk_pct": _get(size, "risk_pct_effective"),
                       "leverage": _get(size, "leverage"), "vol_scalar": _get(size, "vol_scalar")}
    if extra:
        ctx.update(extra)

    plan_d: Dict[str, Any] = {}
    src = entry if entry is not None else plan
    if src is not None:
        plan_d = {"entry": _get(src, "limit_price", _get(src, "entry")),
                  "stop": _get(src, "stop"), "tp1": _get(src, "tp1"),
                  "tp2": _get(src, "tp2"), "rr2": _get(src, "rr2")}

    return DecisionRecord(
        ts=int(ts), symbol=str(symbol).upper(), strategy=str(strategy), side=str(side),
        decision=str(decision), timeframe=str(timeframe), reason=str(reason),
        signal_strength=float(signal_strength) if signal_strength == signal_strength else float("nan"),
        context=ctx, plan=plan_d,
    )


def attach_outcome(rec: DecisionRecord, *, filled: bool, r_multiple: float = float("nan"),
                   pnl: float = float("nan"), exit_reason: str = "") -> DecisionRecord:
    """Close the loop after the trade resolves (for honest realized-vs-expected)."""
    rec.outcome = {"filled": bool(filled), "r_multiple": r_multiple,
                   "pnl": pnl, "exit_reason": exit_reason}
    return rec


class DecisionBus:
    """Append-only JSONL sink the AI and audits read from."""

    def __init__(self, path: str) -> None:
        self.path = path

    def append(self, rec: DecisionRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(rec.to_json() + "\n")

    def read(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
        except FileNotFoundError:
            pass
        return out


def summarize(records: Sequence[Dict[str, Any]], *, by: str = "strategy") -> Dict[str, Any]:
    """Honest per-group performance the AI/edge-monitor reads.

    Groups filled ENTER decisions by `by` (strategy/side/regime) and computes
    n, wins, win_rate, sum_R, expectancy_R, avg_win_R, avg_loss_R. Skips are counted
    separately so we also see selectivity.
    """
    groups: Dict[str, Dict[str, Any]] = {}
    skips = 0
    for r in records:
        if r.get("decision") != "enter":
            skips += 1
            continue
        oc = r.get("outcome") or {}
        if not oc.get("filled"):
            continue
        rm = oc.get("r_multiple")
        if rm is None or rm != rm:
            continue
        if by == "side":
            key = str(r.get("side", "?"))
        elif by == "regime":
            key = str(((r.get("context") or {}).get("range") or {}).get("regime", "?"))
        else:
            key = str(r.get("strategy", "?"))
        g = groups.setdefault(key, {"n": 0, "wins": 0, "sum_R": 0.0,
                                    "_wins_R": [], "_loss_R": []})
        g["n"] += 1
        g["sum_R"] += rm
        if rm > 0:
            g["wins"] += 1
            g["_wins_R"].append(rm)
        else:
            g["_loss_R"].append(rm)
    out: Dict[str, Any] = {"groups": {}, "skips": skips}
    for k, g in groups.items():
        n = g["n"]
        aw = sum(g["_wins_R"]) / len(g["_wins_R"]) if g["_wins_R"] else float("nan")
        al = sum(g["_loss_R"]) / len(g["_loss_R"]) if g["_loss_R"] else float("nan")
        out["groups"][k] = {
            "n": n, "wins": g["wins"], "win_rate": (g["wins"] / n) if n else float("nan"),
            "sum_R": round(g["sum_R"], 4), "expectancy_R": round(g["sum_R"] / n, 4) if n else float("nan"),
            "avg_win_R": round(aw, 4) if aw == aw else None,
            "avg_loss_R": round(al, 4) if al == al else None,
        }
    return out
