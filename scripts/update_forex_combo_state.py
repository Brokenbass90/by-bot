#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple


STATE_ORDER = {"ACTIVE": 0, "CANARY": 1, "WATCHLIST": 2, "BANNED": 3}
STATE_HEADERS = [
    "pair",
    "strategy",
    "state",
    "first_seen_utc",
    "last_seen_utc",
    "last_pass_utc",
    "last_fail_utc",
    "pass_streak",
    "fail_streak",
    "cooldown_until_utc",
    "last_base_net_pips",
    "last_stress_net_pips",
    "last_recent_stress_net_pips",
    "last_stress_trades",
    "last_stress_dd_pips",
    "last_reason",
]
ACTION_HEADERS = [
    "ts_utc",
    "pair",
    "strategy",
    "from_state",
    "to_state",
    "reason",
    "stress_net_pips",
    "recent_stress_net_pips",
    "stress_trades",
    "stress_dd_pips",
]
ACTIVE_HEADERS = [
    "pair",
    "strategy",
    "state",
    "last_stress_net_pips",
    "last_recent_stress_net_pips",
    "last_stress_trades",
    "last_stress_dd_pips",
    "last_reason",
    "updated_utc",
]

BASE_STRATEGIES = {
    "trend_retest_session_v1",
    "trend_retest_session_v2",
    "range_bounce_session_v1",
    "breakout_continuation_session_v1",
    "asia_range_reversion_session_v1",
    "failure_reclaim_session_v1",
    "grid_reversion_session_v1",
    "liquidity_sweep_bounce_session_v1",
    "trend_pullback_rebound_v1",
}

# Keep state keys stable when two preset names are config-identical.
STRATEGY_CANONICAL_ALIASES = {
    "trend_retest_session_v1:default": "trend_retest_session_v1:conservative",
}


@dataclass
class ComboState:
    pair: str
    strategy: str
    state: str
    first_seen_utc: str
    last_seen_utc: str
    last_pass_utc: str
    last_fail_utc: str
    pass_streak: int
    fail_streak: int
    cooldown_until_utc: str
    last_base_net_pips: float
    last_stress_net_pips: float
    last_recent_stress_net_pips: float
    last_stress_trades: int
    last_stress_dd_pips: float
    last_reason: str


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_ts(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_ts(s: str) -> datetime | None:
    t = (s or "").strip()
    if not t:
        return None
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(t)
    except ValueError:
        return None


def _to_int(v: str, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


def _to_float(v: str, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _key(pair: str, strategy: str) -> Tuple[str, str]:
    return pair.upper().strip(), _canonical_strategy(strategy.strip())


def _canonical_strategy(strategy: str) -> str:
    s = strategy.strip()
    if not s:
        return s
    if ":" in s:
        canonical = s
    elif s in BASE_STRATEGIES:
        canonical = f"{s}:default"
    else:
        canonical = s
    return STRATEGY_CANONICAL_ALIASES.get(canonical, canonical)


def _load_state(path: Path) -> Dict[Tuple[str, str], ComboState]:
    out: Dict[Tuple[str, str], ComboState] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pair = row.get("pair", "").upper().strip()
            strategy = _canonical_strategy(row.get("strategy", "").strip())
            if not pair or not strategy:
                continue
            st = ComboState(
                pair=pair,
                strategy=strategy,
                state=row.get("state", "WATCHLIST").strip().upper() or "WATCHLIST",
                first_seen_utc=row.get("first_seen_utc", ""),
                last_seen_utc=row.get("last_seen_utc", ""),
                last_pass_utc=row.get("last_pass_utc", ""),
                last_fail_utc=row.get("last_fail_utc", ""),
                pass_streak=_to_int(row.get("pass_streak", "0")),
                fail_streak=_to_int(row.get("fail_streak", "0")),
                cooldown_until_utc=row.get("cooldown_until_utc", ""),
                last_base_net_pips=_to_float(row.get("last_base_net_pips", "0")),
                last_stress_net_pips=_to_float(row.get("last_stress_net_pips", "0")),
                last_recent_stress_net_pips=_to_float(row.get("last_recent_stress_net_pips", "0")),
                last_stress_trades=_to_int(row.get("last_stress_trades", "0")),
                last_stress_dd_pips=_to_float(row.get("last_stress_dd_pips", "0")),
                last_reason=row.get("last_reason", ""),
            )
            out[_key(pair, strategy)] = st
    return out


def _read_gated(path: Path) -> List[dict]:
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            pair = row.get("pair", "").upper().strip()
            strategy = _canonical_strategy(row.get("strategy", "").strip())
            if not pair or not strategy:
                continue
            out.append(
                {
                    "pair": pair,
                    "strategy": strategy,
                    "pass_gate": _to_int(row.get("pass_gate", "0")),
                    "base_net_pips": _to_float(row.get("base_net_pips", "0")),
                    "stress_net_pips": _to_float(row.get("stress_net_pips", "0")),
                    "recent_stress_net_pips": _to_float(row.get("recent_stress_net_pips", "0")),
                    "stress_trades": _to_int(row.get("stress_trades", "0")),
                    "stress_dd_pips": _to_float(row.get("stress_dd_pips", "0")),
                }
            )
    return out


def _record_action(actions: List[dict], now_s: str, st: ComboState, from_state: str, reason: str) -> None:
    if st.state == from_state:
        return
    actions.append(
        {
            "ts_utc": now_s,
            "pair": st.pair,
            "strategy": st.strategy,
            "from_state": from_state,
            "to_state": st.state,
            "reason": reason,
            "stress_net_pips": f"{st.last_stress_net_pips:.4f}",
            "recent_stress_net_pips": f"{st.last_recent_stress_net_pips:.4f}",
            "stress_trades": st.last_stress_trades,
            "stress_dd_pips": f"{st.last_stress_dd_pips:.4f}",
        }
    )


def _state_sort_key(st: ComboState) -> Tuple[int, float, str, str]:
    return (
        STATE_ORDER.get(st.state, 9),
        -st.last_stress_net_pips,
        st.pair,
        st.strategy,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Update ACTIVE/CANARY/BANNED state for forex pair+strategy combos.")
    ap.add_argument("--gated-csv", required=True, help="Path to gated_summary.csv from multi-strategy gate.")
    ap.add_argument("--state-csv", default="docs/forex_combo_state_latest.csv")
    ap.add_argument("--actions-csv", default="docs/forex_combo_actions_latest.csv")
    ap.add_argument("--active-csv", default="docs/forex_combo_active_latest.csv")
    ap.add_argument("--active-txt", default="docs/forex_combo_active_latest.txt")
    ap.add_argument("--pass-streak-to-active", type=int, default=2)
    ap.add_argument("--fail-streak-to-ban", type=int, default=2)
    ap.add_argument("--cooldown-days", type=int, default=7)
    ap.add_argument("--max-active", type=int, default=3)
    ap.add_argument("--max-active-per-pair", type=int, default=1)
    ap.add_argument("--soft-canary-enabled", type=int, default=1)
    ap.add_argument("--soft-canary-base-min", type=float, default=0.0)
    ap.add_argument("--soft-canary-stress-min", type=float, default=25.0)
    ap.add_argument("--soft-canary-recent-min", type=float, default=-2.0)
    ap.add_argument("--soft-canary-min-trades", type=int, default=40)
    ap.add_argument("--soft-canary-max-dd", type=float, default=250.0)
    ap.add_argument("--demote-unseen", type=int, default=1)
    args = ap.parse_args()

    gated_csv = Path(args.gated_csv).resolve()
    if not gated_csv.exists():
        raise SystemExit(f"gated csv not found: {gated_csv}")

    state_csv = Path(args.state_csv).resolve()
    actions_csv = Path(args.actions_csv).resolve()
    active_csv = Path(args.active_csv).resolve()
    active_txt = Path(args.active_txt).resolve()
    for p in (state_csv, actions_csv, active_csv, active_txt):
        p.parent.mkdir(parents=True, exist_ok=True)

    now = _now_utc()
    now_s = _fmt_ts(now)

    state = _load_state(state_csv)
    gated_rows = _read_gated(gated_csv)
    actions: List[dict] = []
    seen: Dict[Tuple[str, str], dict] = {}

    for row in gated_rows:
        k = _key(row["pair"], row["strategy"])
        seen[k] = row
        st = state.get(k)
        if st is None:
            st = ComboState(
                pair=row["pair"],
                strategy=row["strategy"],
                state="WATCHLIST",
                first_seen_utc=now_s,
                last_seen_utc=now_s,
                last_pass_utc="",
                last_fail_utc="",
                pass_streak=0,
                fail_streak=0,
                cooldown_until_utc="",
                last_base_net_pips=0.0,
                last_stress_net_pips=0.0,
                last_recent_stress_net_pips=0.0,
                last_stress_trades=0,
                last_stress_dd_pips=0.0,
                last_reason="new_combo",
            )
            state[k] = st

        prev_state = st.state
        st.last_seen_utc = now_s
        st.last_base_net_pips = float(row["base_net_pips"])
        st.last_stress_net_pips = float(row["stress_net_pips"])
        st.last_recent_stress_net_pips = float(row["recent_stress_net_pips"])
        st.last_stress_trades = int(row["stress_trades"])
        st.last_stress_dd_pips = float(row["stress_dd_pips"])

        if int(row["pass_gate"]) == 1:
            st.pass_streak += 1
            st.fail_streak = 0
            st.last_pass_utc = now_s

            if prev_state == "BANNED":
                cooldown_until = _parse_ts(st.cooldown_until_utc)
                if cooldown_until is not None and cooldown_until > now:
                    st.state = "BANNED"
                    st.last_reason = "cooldown_active"
                else:
                    st.state = "CANARY"
                    st.last_reason = "ban_cooldown_passed"
                    _record_action(actions, now_s, st, prev_state, st.last_reason)
            elif prev_state == "WATCHLIST":
                st.state = "CANARY"
                st.last_reason = "gate_pass"
                _record_action(actions, now_s, st, prev_state, st.last_reason)
            elif prev_state == "CANARY":
                if st.pass_streak >= int(args.pass_streak_to_active):
                    st.state = "ACTIVE"
                    st.last_reason = f"pass_streak_{st.pass_streak}"
                    _record_action(actions, now_s, st, prev_state, st.last_reason)
                else:
                    st.last_reason = f"canary_pass_streak_{st.pass_streak}"
            else:
                st.state = "ACTIVE"
                st.last_reason = "gate_pass_keep_active"
        else:
            soft_ok = (
                int(args.soft_canary_enabled) == 1
                and st.last_base_net_pips >= float(args.soft_canary_base_min)
                and st.last_stress_net_pips >= float(args.soft_canary_stress_min)
                and st.last_recent_stress_net_pips >= float(args.soft_canary_recent_min)
                and st.last_stress_trades >= int(args.soft_canary_min_trades)
                and st.last_stress_dd_pips <= float(args.soft_canary_max_dd)
            )
            st.last_fail_utc = now_s

            if soft_ok and prev_state != "BANNED":
                st.pass_streak = 0
                st.fail_streak = 0
                st.state = "CANARY"
                st.last_reason = "soft_canary_gate"
                _record_action(actions, now_s, st, prev_state, st.last_reason)
            else:
                st.pass_streak = 0
                st.fail_streak += 1

                if prev_state in {"ACTIVE", "CANARY"} and st.fail_streak >= int(args.fail_streak_to_ban):
                    st.state = "BANNED"
                    st.cooldown_until_utc = _fmt_ts(now + timedelta(days=int(args.cooldown_days)))
                    st.last_reason = f"fail_streak_{st.fail_streak}"
                    _record_action(actions, now_s, st, prev_state, st.last_reason)
                elif prev_state in {"ACTIVE", "CANARY"}:
                    st.state = "CANARY"
                    st.last_reason = f"fail_streak_{st.fail_streak}_hold_canary"
                    _record_action(actions, now_s, st, prev_state, st.last_reason)
                elif prev_state == "BANNED":
                    st.state = "BANNED"
                    st.last_reason = "still_banned"
                else:
                    st.state = "WATCHLIST"
                    st.last_reason = "gate_fail"
                    _record_action(actions, now_s, st, prev_state, st.last_reason)

    if int(args.demote_unseen) == 1:
        for k, st in state.items():
            if k in seen:
                continue
            if st.state in {"ACTIVE", "CANARY"}:
                prev_state = st.state
                st.state = "WATCHLIST"
                st.pass_streak = 0
                st.last_reason = "not_in_current_gate"
                _record_action(actions, now_s, st, prev_state, st.last_reason)

    # Active quotas: keep top-N ACTIVE by stress_net among combos that passed this run,
    # plus optional per-pair cap to avoid over-concentration on one instrument.
    active_candidates = []
    for k, st in state.items():
        if st.state != "ACTIVE":
            continue
        row = seen.get(k)
        if row is None or int(row["pass_gate"]) != 1:
            continue
        active_candidates.append(st)
    active_candidates.sort(key=lambda s: s.last_stress_net_pips, reverse=True)

    max_active = max(1, int(args.max_active))
    max_active_per_pair = int(args.max_active_per_pair)
    if max_active_per_pair <= 0:
        max_active_per_pair = 10**9

    keep_keys: set[Tuple[str, str]] = set()
    pair_kept: Dict[str, int] = {}
    pair_overflow: List[ComboState] = []
    quota_overflow: List[ComboState] = []

    for st in active_candidates:
        if len(keep_keys) >= max_active:
            quota_overflow.append(st)
            continue
        used = int(pair_kept.get(st.pair, 0))
        if used >= max_active_per_pair:
            pair_overflow.append(st)
            continue
        keep_keys.add(_key(st.pair, st.strategy))
        pair_kept[st.pair] = used + 1

    for st in pair_overflow:
        prev_state = st.state
        st.state = "CANARY"
        st.last_reason = "demoted_active_pair_quota"
        _record_action(actions, now_s, st, prev_state, st.last_reason)
    for st in quota_overflow:
        prev_state = st.state
        st.state = "CANARY"
        st.last_reason = "demoted_active_quota"
        _record_action(actions, now_s, st, prev_state, st.last_reason)

    ordered = sorted(state.values(), key=_state_sort_key)
    with state_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(STATE_HEADERS)
        for st in ordered:
            w.writerow(
                [
                    st.pair,
                    st.strategy,
                    st.state,
                    st.first_seen_utc,
                    st.last_seen_utc,
                    st.last_pass_utc,
                    st.last_fail_utc,
                    st.pass_streak,
                    st.fail_streak,
                    st.cooldown_until_utc,
                    f"{st.last_base_net_pips:.4f}",
                    f"{st.last_stress_net_pips:.4f}",
                    f"{st.last_recent_stress_net_pips:.4f}",
                    st.last_stress_trades,
                    f"{st.last_stress_dd_pips:.4f}",
                    st.last_reason,
                ]
            )

    with actions_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ACTION_HEADERS)
        w.writeheader()
        w.writerows(actions)

    active_now = [st for st in ordered if st.state == "ACTIVE"]
    with active_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(ACTIVE_HEADERS)
        for st in active_now:
            w.writerow(
                [
                    st.pair,
                    st.strategy,
                    st.state,
                    f"{st.last_stress_net_pips:.4f}",
                    f"{st.last_recent_stress_net_pips:.4f}",
                    st.last_stress_trades,
                    f"{st.last_stress_dd_pips:.4f}",
                    st.last_reason,
                    now_s,
                ]
            )

    with active_txt.open("w", encoding="utf-8") as f:
        f.write(",".join([f"{st.pair}@{st.strategy}" for st in active_now]))

    state_counts: Dict[str, int] = {}
    for st in ordered:
        state_counts[st.state] = state_counts.get(st.state, 0) + 1

    print("forex combo state update done")
    print(f"gated={gated_csv}")
    print(f"state={state_csv}")
    print(f"actions={actions_csv}")
    print(f"active_csv={active_csv}")
    print(f"active_txt={active_txt}")
    print(
        "counts: "
        + " ".join([f"{k}={state_counts.get(k, 0)}" for k in ["ACTIVE", "CANARY", "WATCHLIST", "BANNED"]])
    )
    print(f"active={','.join([f'{st.pair}@{st.strategy}' for st in active_now]) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
