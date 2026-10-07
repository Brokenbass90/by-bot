"""Synthetic data only; no market archive or broker account."""
import hashlib
import json

HOUR = 3_600_000
END = 1_790_000_000_000 // (4 * HOUR) * (4 * HOUR)


def pin(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def repin(bundle):
    for name in ("source", "positions", "correlations"):
        bundle[name]["sha256"] = pin(bundle[name]["rows"])
    return bundle


def signal(identity="s1", symbol="ETHUSDT", side="long", cluster="eth", rank=0.5):
    return {"type": "SIGNAL", "id": identity, "source_id": "synthetic-intents",
            "source_pin": "a" * 64, "strategy": "fixture", "version": "f1",
            "dependencies": {"strategy": "b" * 64}, "symbol": symbol, "side": side,
            "beta_cluster": cluster, "risk_pct": 0.5, "rank": rank,
            "signal_ms": END, "available_ms": END + 1000}


def bundle(events=None):
    rows = []
    for i in range(240):
        t = END - 240 * HOUR + i * HOUR
        rows.append([t, 100.0, 101.0, 99.0, 100.0, 10.0, t + HOUR + 1000])
    return repin({"schema": "OS2_SHADOW_BUNDLE_V1", "request_id": "r1", "mode": "FIXTURE",
                  "decision_ms": END + 2000, "clock_uncertainty_ms": 0,
                  "source": {"id": "synthetic-btc-h1", "observed_ms": END + 1500, "rows": rows},
                  "positions": {"id": "synthetic-positions", "observed_ms": END + 1500,
                                "coverage_ms": END + 1500, "complete": True, "rows": []},
                  "correlations": {"id": "synthetic-correlations", "observed_ms": END + 1500,
                                   "coverage_ms": END + 1500, "complete": True, "rows": []},
                  "policy": {"schema": "FIXTURE_POLICY_V1", "allowed_regimes": {
                      "fixture": ["NEUTRAL", "BULL_TREND", "BEAR_TREND"]}},
                  "events": [signal()] if events is None else events})


def terminal(origin="s1", identity="t1", **changes):
    value = {"type": "TERMINAL", "id": identity, "source_id": "synthetic-intents",
             "source_pin": "a" * 64, "origin_id": origin, "terminal_ms": END + 1600,
             "available_ms": END + 1700, "filled": True, "continuity": "CLEAN",
             "costs_complete": True, "finality": True, "net_r": -2.0}
    value.update(changes)
    return value
