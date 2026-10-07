"""Isolated orders-OFF wiring assessor. Fixtures exercise policy; real policy is blocked.

No broker, transport, environment overlay, model or live caller is reachable here.
H1 rows are [open_ms, o, h, l, c, v, available_ms]. Supplied hashes bind
content, not its authenticity: external research/account acceptance is separate.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re

from bot import regime_orchestrator, strategy_priority_router, exposure_gate
from bot import strategy_regime_gate, decision_bus, edge_monitor, research_orchestrator

HOUR = 3_600_000
MAX_BYTES = 2 * 1024 * 1024
MAX_EVENTS = 64
MAX_IDENTITIES = 4096
FRESH_MS = 300_000
COOLDOWN_MS = 600_000  # Synthetic fixture policy only; never a LIVE setting.
REGIME_CODE_PIN = "56952650bd2dcb09421e87a2f5d4f9a27d1184b7ce64504f7f8ed54e00f85370"
LABELS = {"NEUTRAL", "BULL_TREND", "BEAR_TREND"}


class BridgeBlocked(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status, self.reason = status, reason


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def require(condition, reason):
    if not condition:
        raise BridgeBlocked("BLOCKED_DATA", reason)


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def integer(value):
    return type(value) is int and value >= 0


def identity(value):
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value) is not None


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def wiring_pins():
    modules = (regime_orchestrator, strategy_priority_router, exposure_gate,
               strategy_regime_gate, decision_bus, edge_monitor, research_orchestrator)
    return {m.__name__: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in modules}


def empty_state():
    return {"schema": "OS2_SHADOW_STATE_V1", "domain_pin": None, "last_decision_ms": 0,
            "source_rows": {}, "reservations": {}, "event_hashes": {}, "cooldowns": {}, "terminals": []}


def _envelope(bundle, pins):
    source = bundle["source"]
    decision = bundle["decision_ms"]
    uncertainty = bundle["clock_uncertainty_ms"]
    require(integer(decision) and integer(uncertainty) and uncertainty <= 250, "invalid_clock")
    cutoff = decision - uncertainty
    require(pins["bot.regime_orchestrator"] == REGIME_CODE_PIN, "regime_code_pin_mismatch")
    require(isinstance(source, dict) and identity(source["id"]), "invalid_regime_source")
    observed = source["observed_ms"]
    require(integer(observed) and 0 <= cutoff - observed <= FRESH_MS, "stale_or_future_source")
    rows = source["rows"]
    require(isinstance(rows, list) and 240 <= len(rows) <= 800 and len(rows) % 4 == 0, "incomplete_warmup")
    require(source["sha256"] == digest(rows), "regime_source_hash_mismatch")
    previous = None
    for row in rows:
        require(isinstance(row, list) and len(row) == 7, "invalid_h1_schema")
        t, o, h, l, c, v, available = row
        require(integer(t) and t % HOUR == 0 and (previous is None or t == previous + HOUR), "h1_gap_order_or_duplicate")
        require(all(number(x) for x in (o, h, l, c, v)) and min(o, h, l, c) > 0
                and v >= 0 and l <= min(o, c) <= max(o, c) <= h, "invalid_ohlcv")
        require(integer(available) and t + HOUR <= available <= observed <= cutoff, "unclosed_or_late_h1")
        previous = t
    closed = rows[-1][0] + HOUR
    require(rows[0][0] % (4 * HOUR) == 0 and closed == cutoff // (4 * HOUR) * (4 * HOUR), "closed_cutoff_mismatch")
    four_h = []
    for offset in range(0, len(rows), 4):
        group = rows[offset:offset + 4]
        four_h.append([group[0][0], group[0][1], max(r[2] for r in group),
                       min(r[3] for r in group), group[-1][4], sum(r[5] for r in group)])
    label = regime_orchestrator.compute_regime(four_h)["regime"]
    require(label in LABELS, "unknown_classifier_label")
    envelope = {"schema": "OS2_REGIME_ENVELOPE_V1", "validity": "VALID", "label": label,
                "source_id": source["id"], "source_pin": source["sha256"], "code_pin": REGIME_CODE_PIN,
                "closed_cutoff_ms": closed, "observed_ms": observed, "decision_ms": decision,
                "clock_uncertainty_ms": uncertainty, "four_h_count": len(four_h)}
    envelope["sha256"] = digest(envelope)
    return envelope


def _view(bundle, name, cutoff):
    view = bundle[name]
    require(isinstance(view, dict) and identity(view["id"]) and view["complete"] is True, "unknown_" + name)
    require(integer(view["coverage_ms"]) and integer(view["observed_ms"])
            and 0 <= cutoff - view["observed_ms"] <= FRESH_MS
            and 0 <= view["observed_ms"] - view["coverage_ms"] <= FRESH_MS, "stale_or_future_" + name)
    require(isinstance(view["rows"], list) and len(view["rows"]) <= 4096
            and view["sha256"] == digest(view["rows"]), "unbound_" + name)
    return view["rows"]


def _position(p):
    require(isinstance(p, dict) and identity(p["symbol"]) and p["symbol"].isupper()
            and p["side"] in ("long", "short") and number(p["risk_pct"]) and 0 < p["risk_pct"] <= 1.5
            and identity(p["beta_cluster"]) and p["beta_cluster"].islower(), "invalid_position")
    return {k: p[k] for k in ("symbol", "side", "risk_pct", "beta_cluster")}


def _decision(event, envelope, decision_ms, reason, selected=False, exposure=None):
    value = decision_bus.build_decision(
        ts=decision_ms // 1000, symbol=str(event.get("symbol", "UNKNOWN")),
        strategy=str(event.get("strategy", "UNKNOWN")), side=str(event.get("side", "UNKNOWN")),
        decision="enter" if selected else "skip", reason=reason, signal_strength=0.0,
        exposure=exposure, extra={"observer": "OS2_SHADOW_BRIDGE_V1", "event_id": event.get("id"),
                                 "regime_envelope_sha256": envelope.get("sha256"),
                                 "source_id": event.get("source_id"), "source_pin": event.get("source_pin"),
                                 "money_authorized": False, "ranking_basis": "FIXTURE_NORMALIZATION_1_NOT_EXPECTANCY"}).to_dict()
    return value


def _diagnostics(state, mode):
    by_sleeve = {}
    if mode == "FIXTURE":
        for terminal in sorted(state["terminals"], key=lambda t: (t["terminal_ms"], t["id"])):
            by_sleeve.setdefault(terminal["strategy"], []).append(terminal["net_r"])
    health = {s: asdict(edge_monitor.assess_sleeve(rs, sleeve=s)) for s, rs in by_sleeve.items()}
    proposal = asdict(research_orchestrator.weekly_review(
        [{"name": s, "stage": "shadow", "paper_r": rs} for s, rs in sorted(by_sleeve.items())],
        [], period_label="OS2_FIXTURE_REPLAY"))
    # Existing diagnostics use NaN for unknown expectancy. Preserve UNKNOWN as null.
    def finite(value):
        if isinstance(value, dict): return {k: finite(v) for k, v in value.items()}
        if isinstance(value, list): return [finite(v) for v in value]
        if isinstance(value, float) and not math.isfinite(value): return None
        return value
    return finite({"health": health, "proposal": proposal, "evidence_kind": mode,
                   "money_authorized": False, "policy_authority": False})


def assess_bundle(bundle, state):
    """Pure assessment; a separate durable wrapper owns transactions and replay."""
    original = deepcopy(state)
    envelope = {"validity": "UNKNOWN", "label": None}
    events = bundle.get("events", []) if isinstance(bundle, dict) else []
    decision_ms = bundle.get("decision_ms", 0) if isinstance(bundle, dict) else 0
    decisions = []
    try:
        require(isinstance(bundle, dict) and len(canonical(bundle)) <= MAX_BYTES, "invalid_or_oversize_bundle")
        require(bundle["schema"] == "OS2_SHADOW_BUNDLE_V1" and identity(bundle["request_id"]), "invalid_bundle_identity")
        require(bundle["mode"] in ("FIXTURE", "EXTERNAL_PUBLIC"), "invalid_mode")
        require(state["schema"] == "OS2_SHADOW_STATE_V1", "invalid_state")
        require(isinstance(events, list) and len(events) <= MAX_EVENTS and all(isinstance(e, dict) for e in events), "invalid_events")
        pins = wiring_pins()
        envelope = _envelope(bundle, pins)
        cutoff = decision_ms - bundle["clock_uncertainty_ms"]
        require(decision_ms >= state["last_decision_ms"], "decision_clock_regressed")
        positions = [_position(p) for p in _view(bundle, "positions", cutoff)]
        require(len({p["symbol"] for p in positions}) == len(positions), "duplicate_position")
        correlations = {}
        for row in _view(bundle, "correlations", cutoff):
            require(isinstance(row, list) and len(row) == 3, "invalid_correlation")
            a, b, c = row
            require(identity(a) and identity(b) and a.isupper() and b.isupper()
                    and a != b and number(c) and -1 <= c <= 1, "invalid_correlation")
            key = tuple(sorted((a, b)))
            require(key not in correlations, "duplicate_correlation")
            correlations[key] = c
        policy = bundle["policy"]
        require(isinstance(policy, dict) and policy["schema"] == "FIXTURE_POLICY_V1", "unapproved_policy_schema")
        require(isinstance(policy["allowed_regimes"], dict) and all(identity(k) and isinstance(v, list)
                and len(v) == len(set(v)) and set(v) <= LABELS for k, v in policy["allowed_regimes"].items()), "invalid_fixture_policy")
        domain = digest({"mode": bundle["mode"], "source": bundle["source"]["id"], "policy": policy, "wiring": pins})
        require(state["domain_pin"] in (None, domain), "source_or_policy_conflict")
        for row in bundle["source"]["rows"]:
            old = state["source_rows"].get(str(row[0]))
            require(old is None or old == digest(row), "regime_source_revision")
        next_state = deepcopy(state)
        next_state["domain_pin"] = domain
        next_state["source_rows"] = {str(row[0]): digest(row) for row in bundle["source"]["rows"]}
        next_state["last_decision_ms"] = decision_ms
        require(len(next_state["event_hashes"]) + len(events) <= MAX_IDENTITIES, "identity_bound")
        seen = dict(state["event_hashes"])
        for e in events:
            require(identity(e.get("id")), "missing_event_identity")
            body = digest(e)
            require(e["id"] not in seen or seen[e["id"]] == body, "event_identity_conflict")
            seen[e["id"]] = body
        if bundle["mode"] == "EXTERNAL_PUBLIC":
            return {"status": "BLOCKED_DATA", "reason": "POLICY_UNAPPROVED", "regime_envelope": envelope,
                    "decisions": [_decision(e, envelope, decision_ms, "POLICY_UNAPPROVED") for e in events],
                    "state_after": original, "diagnostics": _diagnostics(original, "EXTERNAL_PUBLIC")}

        candidates = []
        for e in events:
            if e["id"] in next_state["event_hashes"]:
                decisions.append(_decision(e, envelope, decision_ms, "duplicate_event")); continue
            if e.get("type") == "NO_SIGNAL":
                decisions.append(_decision(e, envelope, decision_ms, "no_signal"))
                next_state["event_hashes"][e["id"]] = digest(e); continue
            if e.get("type") == "TERMINAL":
                held = next_state["reservations"].get(e.get("origin_id"))
                valid = (held is not None and e.get("source_id") == held["source_id"]
                         and e.get("source_pin") == held["source_pin"]
                         and e.get("filled") is True and e.get("continuity") == "CLEAN"
                         and e.get("costs_complete") is True and e.get("finality") is True
                         and number(e.get("net_r")) and integer(e.get("terminal_ms"))
                         and integer(e.get("available_ms"))
                         and held["signal_ms"] <= e["terminal_ms"] <= e["available_ms"] <= cutoff)
                decisions.append(_decision(e, envelope, decision_ms, "terminal_accepted" if valid else "terminal_unproven"))
                if valid:
                    next_state["terminals"].append({**e, "strategy": held["strategy"]})
                    next_state["cooldowns"][held["symbol"]] = e["terminal_ms"] + COOLDOWN_MS
                    del next_state["reservations"][e["origin_id"]]
                    next_state["event_hashes"][e["id"]] = digest(e)
                continue
            try:
                require(e.get("type") == "SIGNAL" and e.get("money_authorized", False) is False, "invalid_candidate")
                p = _position(e)
                require(identity(e["source_id"]) and sha(e["source_pin"]) and identity(e["strategy"])
                        and identity(e["version"]) and isinstance(e["dependencies"], dict)
                        and bool(e["dependencies"]) and all(identity(k) and sha(v) for k, v in e["dependencies"].items()), "invalid_candidate")
                require(integer(e["signal_ms"]) and integer(e["available_ms"])
                        and 0 <= cutoff - e["signal_ms"] <= FRESH_MS
                        and e["signal_ms"] <= e["available_ms"] <= cutoff
                        and number(e["rank"]) and 0 <= e["rank"] <= 1, "invalid_candidate")
                gate = strategy_regime_gate.strategy_regime_gate_decision(
                    envelope["label"], overlay_fresh=True, allowed_regimes=policy["allowed_regimes"].get(e["strategy"], []))
                if not gate.allowed:
                    decisions.append(_decision(e, envelope, decision_ms, gate.reason)); continue
                candidates.append((strategy_priority_router.StrategyCandidate(
                    e["id"], e["signal_ms"] // 1000, p["symbol"], e["strategy"], p["side"],
                    expected_net_r=1.0, symbol_rank=e["rank"], requested_risk_pct=p["risk_pct"],
                    beta_cluster=p["beta_cluster"], money_authorized=False), e))
            except (BridgeBlocked, KeyError, TypeError, ValueError):
                decisions.append(_decision(e, envelope, decision_ms, "invalid_candidate"))

        for candidate, e in sorted(candidates, key=lambda pair: (-strategy_priority_router.priority_score(pair[0]), -pair[0].ts, pair[0].decision_id)):
            if e["id"] in next_state["event_hashes"]:
                decisions.append(_decision(e, envelope, decision_ms, "duplicate_event")); continue
            owned = [_position(v) for v in next_state["reservations"].values()]
            occupied = {p["symbol"]: p for p in positions}
            for p in owned:
                require(p["symbol"] not in occupied or occupied[p["symbol"]] == p, "position_shadow_conflict")
                occupied[p["symbol"]] = p
            held_positions = list(occupied.values())
            rank = strategy_priority_router.rank_candidates(
                [candidate], now_ts=decision_ms // 1000, mode="shadow", max_slots=3, max_same_side=2, max_same_cluster=1,
                open_symbols=list(occupied), open_sides=[p["side"] for p in held_positions],
                open_clusters=[p["beta_cluster"] for p in held_positions])[0]
            reason, selected, exposure = rank.reason, rank.selected, None
            if next_state["cooldowns"].get(e["symbol"], 0) > cutoff:
                reason, selected = "cooldown", False
            elif selected:
                if any(p["symbol"] != e["symbol"] and tuple(sorted((p["symbol"], e["symbol"]))) not in correlations for p in held_positions):
                    reason, selected = "UNKNOWN_CORRELATION", False
                else:
                    exposure = exposure_gate.check_exposure(e, held_positions, correlations,
                                                          corr_threshold=0.6, max_cluster_risk_pct=1.5, allow_scale=False)
                    reason, selected = exposure.reason, exposure.allow
            decisions.append(_decision(e, envelope, decision_ms, reason, selected, exposure))
            next_state["event_hashes"][e["id"]] = digest(e)
            if selected:
                next_state["reservations"][e["id"]] = deepcopy(e)
        return {"status": "SHADOW_WIRING_PASS", "reason": "FIXTURE_ONLY_NO_POLICY_AUTHORITY",
                "regime_envelope": envelope, "decisions": decisions, "state_after": next_state,
                "diagnostics": _diagnostics(next_state, "FIXTURE")}
    except (BridgeBlocked, KeyError, TypeError, ValueError, OverflowError) as error:
        reason = error.reason if isinstance(error, BridgeBlocked) else "malformed_bundle"
        safe_events = [e for e in events[:MAX_EVENTS] if isinstance(e, dict)] if isinstance(events, list) else []
        safe_ms = decision_ms if integer(decision_ms) else 0
        return {"status": "BLOCKED_DATA", "reason": reason, "regime_envelope": envelope,
                "decisions": [_decision(e, envelope, safe_ms, reason) for e in safe_events],
                "state_after": original, "diagnostics": _diagnostics(original, "EXTERNAL_PUBLIC")}
