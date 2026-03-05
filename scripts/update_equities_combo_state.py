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
    "ticker",
    "strategy",
    "state",
    "first_seen_utc",
    "last_seen_utc",
    "last_pass_utc",
    "last_fail_utc",
    "pass_streak",
    "fail_streak",
    "cooldown_until_utc",
    "last_segments",
    "last_both_positive_share_pct",
    "last_stress_net_cents",
    "last_stress_trades",
    "last_reason",
]
ACTION_HEADERS = [
    "ts_utc",
    "ticker",
    "strategy",
    "from_state",
    "to_state",
    "reason",
    "segments",
    "both_positive_share_pct",
    "stress_net_cents",
    "stress_trades",
]
ACTIVE_HEADERS = [
    "ticker",
    "strategy",
    "state",
    "last_segments",
    "last_both_positive_share_pct",
    "last_stress_net_cents",
    "last_stress_trades",
    "last_reason",
    "updated_utc",
]


@dataclass
class ComboState:
    ticker: str
    strategy: str
    state: str
    first_seen_utc: str
    last_seen_utc: str
    last_pass_utc: str
    last_fail_utc: str
    pass_streak: int
    fail_streak: int
    cooldown_until_utc: str
    last_segments: int
    last_both_positive_share_pct: float
    last_stress_net_cents: float
    last_stress_trades: int
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


def _key(ticker: str, strategy: str) -> Tuple[str, str]:
    return ticker.upper().strip(), strategy.strip()


def _load_state(path: Path) -> Dict[Tuple[str, str], ComboState]:
    out: Dict[Tuple[str, str], ComboState] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ticker = row.get("ticker", "").upper().strip()
            strategy = row.get("strategy", "").strip()
            if not ticker or not strategy:
                continue
            st = ComboState(
                ticker=ticker,
                strategy=strategy,
                state=row.get("state", "WATCHLIST").strip().upper() or "WATCHLIST",
                first_seen_utc=row.get("first_seen_utc", ""),
                last_seen_utc=row.get("last_seen_utc", ""),
                last_pass_utc=row.get("last_pass_utc", ""),
                last_fail_utc=row.get("last_fail_utc", ""),
                pass_streak=_to_int(row.get("pass_streak", "0")),
                fail_streak=_to_int(row.get("fail_streak", "0")),
                cooldown_until_utc=row.get("cooldown_until_utc", ""),
                last_segments=_to_int(row.get("last_segments", "0")),
                last_both_positive_share_pct=_to_float(row.get("last_both_positive_share_pct", "0")),
                last_stress_net_cents=_to_float(row.get("last_stress_net_cents", "0")),
                last_stress_trades=_to_int(row.get("last_stress_trades", "0")),
                last_reason=row.get("last_reason", ""),
            )
            out[_key(ticker, strategy)] = st
    return out


def _read_raw(path: Path, min_segments: int, min_both_pct: float, min_stress_cents: float) -> List[dict]:
    out = []
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ticker = row.get("ticker", "").upper().strip()
            strategy = row.get("strategy", "").strip()
            if not ticker or not strategy:
                continue
            status_ok = row.get("status", "").strip().lower() == "ok"
            segments = _to_int(row.get("segments", "0"))
            both_pct = _to_float(row.get("both_positive_share_pct", "0"))
            stress_cents = _to_float(row.get("total_stress_net_cents", "0"))
            stress_trades = _to_int(row.get("total_stress_trades", "0"))
            pass_gate = int(
                status_ok
                and segments >= int(min_segments)
                and both_pct >= float(min_both_pct)
                and stress_cents > float(min_stress_cents)
            )
            out.append(
                {
                    "ticker": ticker,
                    "strategy": strategy,
                    "pass_gate": pass_gate,
                    "segments": segments,
                    "both_positive_share_pct": both_pct,
                    "stress_net_cents": stress_cents,
                    "stress_trades": stress_trades,
                }
            )
    return out


def _record_action(actions: List[dict], now_s: str, st: ComboState, from_state: str, reason: str) -> None:
    if st.state == from_state:
        return
    actions.append(
        {
            "ts_utc": now_s,
            "ticker": st.ticker,
            "strategy": st.strategy,
            "from_state": from_state,
            "to_state": st.state,
            "reason": reason,
            "segments": st.last_segments,
            "both_positive_share_pct": f"{st.last_both_positive_share_pct:.2f}",
            "stress_net_cents": f"{st.last_stress_net_cents:.4f}",
            "stress_trades": st.last_stress_trades,
        }
    )


def _state_sort_key(st: ComboState) -> Tuple[int, float, str, str]:
    return (
        STATE_ORDER.get(st.state, 9),
        -st.last_stress_net_cents,
        st.ticker,
        st.strategy,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Update ACTIVE/CANARY/BANNED state for equities ticker+strategy combos.")
    ap.add_argument("--raw-csv", required=True, help="Path to raw_walkforward.csv from equities walkforward gate.")
    ap.add_argument("--state-csv", default="docs/equities_combo_state_latest.csv")
    ap.add_argument("--actions-csv", default="docs/equities_combo_actions_latest.csv")
    ap.add_argument("--active-csv", default="docs/equities_combo_active_latest.csv")
    ap.add_argument("--active-txt", default="docs/equities_combo_active_latest.txt")
    ap.add_argument("--active-tickers-txt", default="docs/equities_active_tickers_latest.txt")
    ap.add_argument("--pass-streak-to-active", type=int, default=2)
    ap.add_argument("--fail-streak-to-ban", type=int, default=2)
    ap.add_argument("--cooldown-days", type=int, default=7)
    ap.add_argument("--max-active", type=int, default=6)
    ap.add_argument("--min-segments", type=int, default=4)
    ap.add_argument("--min-both-positive-pct", type=float, default=55.0)
    ap.add_argument("--min-stress-total-cents", type=float, default=0.0)
    ap.add_argument("--soft-canary-enabled", type=int, default=1)
    ap.add_argument("--soft-canary-min-both-pct", type=float, default=50.0)
    ap.add_argument("--soft-canary-min-stress-cents", type=float, default=100.0)
    ap.add_argument("--soft-canary-min-trades", type=int, default=20)
    ap.add_argument("--demote-unseen", type=int, default=1)
    args = ap.parse_args()

    raw_csv = Path(args.raw_csv).resolve()
    if not raw_csv.exists():
        raise SystemExit(f"raw csv not found: {raw_csv}")

    state_csv = Path(args.state_csv).resolve()
    actions_csv = Path(args.actions_csv).resolve()
    active_csv = Path(args.active_csv).resolve()
    active_txt = Path(args.active_txt).resolve()
    active_tickers_txt = Path(args.active_tickers_txt).resolve()
    for p in (state_csv, actions_csv, active_csv, active_txt, active_tickers_txt):
        p.parent.mkdir(parents=True, exist_ok=True)

    now = _now_utc()
    now_s = _fmt_ts(now)

    state = _load_state(state_csv)
    rows = _read_raw(
        raw_csv,
        min_segments=int(args.min_segments),
        min_both_pct=float(args.min_both_positive_pct),
        min_stress_cents=float(args.min_stress_total_cents),
    )
    actions: List[dict] = []
    seen: Dict[Tuple[str, str], dict] = {}

    for row in rows:
        k = _key(row["ticker"], row["strategy"])
        seen[k] = row
        st = state.get(k)
        if st is None:
            st = ComboState(
                ticker=row["ticker"],
                strategy=row["strategy"],
                state="WATCHLIST",
                first_seen_utc=now_s,
                last_seen_utc=now_s,
                last_pass_utc="",
                last_fail_utc="",
                pass_streak=0,
                fail_streak=0,
                cooldown_until_utc="",
                last_segments=0,
                last_both_positive_share_pct=0.0,
                last_stress_net_cents=0.0,
                last_stress_trades=0,
                last_reason="new_combo",
            )
            state[k] = st

        prev_state = st.state
        st.last_seen_utc = now_s
        st.last_segments = int(row["segments"])
        st.last_both_positive_share_pct = float(row["both_positive_share_pct"])
        st.last_stress_net_cents = float(row["stress_net_cents"])
        st.last_stress_trades = int(row["stress_trades"])

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
                and st.last_both_positive_share_pct >= float(args.soft_canary_min_both_pct)
                and st.last_stress_net_cents >= float(args.soft_canary_min_stress_cents)
                and st.last_stress_trades >= int(args.soft_canary_min_trades)
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

    active_candidates = []
    for k, st in state.items():
        if st.state != "ACTIVE":
            continue
        row = seen.get(k)
        if row is None or int(row["pass_gate"]) != 1:
            continue
        active_candidates.append(st)
    active_candidates.sort(key=lambda s: s.last_stress_net_cents, reverse=True)
    for st in active_candidates[int(args.max_active) :]:
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
                    st.ticker,
                    st.strategy,
                    st.state,
                    st.first_seen_utc,
                    st.last_seen_utc,
                    st.last_pass_utc,
                    st.last_fail_utc,
                    st.pass_streak,
                    st.fail_streak,
                    st.cooldown_until_utc,
                    st.last_segments,
                    f"{st.last_both_positive_share_pct:.2f}",
                    f"{st.last_stress_net_cents:.4f}",
                    st.last_stress_trades,
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
                    st.ticker,
                    st.strategy,
                    st.state,
                    st.last_segments,
                    f"{st.last_both_positive_share_pct:.2f}",
                    f"{st.last_stress_net_cents:.4f}",
                    st.last_stress_trades,
                    st.last_reason,
                    now_s,
                ]
            )

    with active_txt.open("w", encoding="utf-8") as f:
        f.write(",".join([f"{st.ticker}@{st.strategy}" for st in active_now]))

    active_tickers = sorted({st.ticker for st in active_now})
    with active_tickers_txt.open("w", encoding="utf-8") as f:
        f.write(",".join(active_tickers))

    state_counts: Dict[str, int] = {}
    for st in ordered:
        state_counts[st.state] = state_counts.get(st.state, 0) + 1

    print("equities combo state update done")
    print(f"raw={raw_csv}")
    print(f"state={state_csv}")
    print(f"actions={actions_csv}")
    print(f"active_csv={active_csv}")
    print(f"active_txt={active_txt}")
    print(f"active_tickers_txt={active_tickers_txt}")
    print(
        "counts: "
        + " ".join([f"{k}={state_counts.get(k, 0)}" for k in ["ACTIVE", "CANARY", "WATCHLIST", "BANNED"]])
    )
    print(f"active={','.join([f'{st.ticker}@{st.strategy}' for st in active_now]) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
