#!/usr/bin/env python3
"""
tests/smoke_test.py — Smoke tests for bot/ modules, risk sizing, news_filter.

Run from project root:
    python tests/smoke_test.py
    # or:
    python -m pytest tests/smoke_test.py -v

All tests are pure Python — no live API, no external dependencies.
"""
from __future__ import annotations

import sys
import os
import time

# ── Path setup ────────────────────────────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# 1. bot/env_helpers — _env_bool
# ─────────────────────────────────────────────────────────────────────────────
def test_env_bool():
    from bot.env_helpers import _env_bool, _env_bool_any, _env_float_any, _mirror_env_aliases

    # Defaults
    assert _env_bool("__NONEXISTENT_VAR__", True)  is True
    assert _env_bool("__NONEXISTENT_VAR__", False) is False

    # Truthy strings
    for val in ("1", "true", "True", "TRUE", "yes", "on"):
        os.environ["_TEST_BOOL"] = val
        assert _env_bool("_TEST_BOOL", False) is True, f"expected True for {val!r}"

    # Falsy strings
    for val in ("0", "false", "False", "FALSE", "no", "off"):
        os.environ["_TEST_BOOL"] = val
        assert _env_bool("_TEST_BOOL", True) is False, f"expected False for {val!r}"

    os.environ.pop("_TEST_ALIAS_BOOL", None)
    os.environ.pop("_TEST_ALIAS_FLOAT", None)
    os.environ["_TEST_ALIAS_BOOL"] = "1"
    os.environ["_TEST_ALIAS_FLOAT"] = "0.60"
    assert _env_bool_any("_TEST_MISSING_BOOL", "_TEST_ALIAS_BOOL", default=False) is True
    assert abs(_env_float_any("_TEST_MISSING_FLOAT", "_TEST_ALIAS_FLOAT", default=1.0) - 0.60) < 1e-9
    _mirror_env_aliases({"_TEST_CANON_BOOL": "_TEST_ALIAS_BOOL"})
    assert os.environ.get("_TEST_CANON_BOOL") == "1"
    os.environ["_TEST_CANON_BOOL"] = "0"
    _mirror_env_aliases({"_TEST_CANON_BOOL": "_TEST_ALIAS_BOOL"})
    assert os.environ.get("_TEST_CANON_BOOL") == "0", "canonical env must win over alias"

    os.environ.pop("_TEST_BOOL", None)
    os.environ.pop("_TEST_ALIAS_BOOL", None)
    os.environ.pop("_TEST_ALIAS_FLOAT", None)
    os.environ.pop("_TEST_CANON_BOOL", None)
    print("  ✓ env_helpers._env_bool")


# ─────────────────────────────────────────────────────────────────────────────
# 2. bot/auth — auth_disabled cooldown
# ─────────────────────────────────────────────────────────────────────────────
def test_auth_disabled():
    from bot.auth import auth_disabled, mark_auth_fail, auth_cooldown_remaining, AUTH_DISABLED_UNTIL

    # In DRY_RUN mode auth is always considered enabled
    os.environ["DRY_RUN"] = "True"
    assert auth_disabled("test_acct") is False, "DRY_RUN=True → auth always enabled"

    # In live mode: mark a failure and check cooldown
    os.environ["DRY_RUN"] = "False"
    try:
        AUTH_DISABLED_UNTIL.pop("test_acct", None)
        assert auth_disabled("test_acct") is False, "no failure yet → not disabled"

        mark_auth_fail("test_acct", Exception("test error"), cooldown_sec=60)
        assert auth_disabled("test_acct") is True, "after mark_auth_fail → should be disabled"

        remaining = auth_cooldown_remaining("test_acct")
        assert 50 < remaining <= 60, f"cooldown remaining should be ~60, got {remaining}"

        # Expire the cooldown artificially
        AUTH_DISABLED_UNTIL["test_acct"] = int(time.time()) - 1
        assert auth_disabled("test_acct") is False, "after expiry → enabled again"
        assert auth_cooldown_remaining("test_acct") == 0
    finally:
        AUTH_DISABLED_UNTIL.pop("test_acct", None)
        os.environ["DRY_RUN"] = "True"

    print("  ✓ auth.auth_disabled / mark_auth_fail / auth_cooldown_remaining")


# ─────────────────────────────────────────────────────────────────────────────
# 3. bot/diagnostics — _diag_inc shared counter
# ─────────────────────────────────────────────────────────────────────────────
def test_diagnostics():
    from bot.diagnostics import _diag_inc, _diag_get_int, _diag_reset, RUNTIME_COUNTER

    _diag_reset()
    assert _diag_get_int("smoke_key") == 0

    _diag_inc("smoke_key", 3)
    assert _diag_get_int("smoke_key") == 3
    assert int(RUNTIME_COUNTER.get("smoke_key", 0)) == 3, "RUNTIME_COUNTER singleton shared"

    _diag_inc("smoke_key")
    assert _diag_get_int("smoke_key") == 4

    _diag_reset()
    assert _diag_get_int("smoke_key") == 0

    # Graceful handling of bad input
    _diag_inc(None)       # should not raise
    _diag_inc("x", "bad")  # should not raise

    print("  ✓ diagnostics._diag_inc / _diag_get_int / _diag_reset")


# ─────────────────────────────────────────────────────────────────────────────
# 4. bot/symbol_state — SymState, update_5m_bar, trim
# ─────────────────────────────────────────────────────────────────────────────
def test_symbol_state():
    import bot.symbol_state as symbol_state
    from bot.symbol_state import SymState, S, update_5m_bar, trim, STATE

    if os.getenv("ALLOW_INDICATOR_FALLBACK", "0").strip() not in {"1", "true", "yes", "on"}:
        assert symbol_state._INDICATORS_OK is True, (
            "bot.symbol_state is running on fallback indicators. "
            "Use the project .venv or install numpy/indicator deps before trusting smoke tests."
        )

    # Clean registry for test
    STATE.clear()

    st = S("Bybit", "TESTUSDT")
    assert isinstance(st, SymState)
    assert S("Bybit", "TESTUSDT") is st, "S() should return same object"

    # update_5m_bar: two ticks in the same bar
    t0 = (int(time.time()) // 300) * 300  # start of current 5m bar
    update_5m_bar(st, t0 + 10, 100.0, 500.0)
    update_5m_bar(st, t0 + 60, 102.0, 300.0)
    assert st.cur5_o == 100.0
    assert st.cur5_h == 102.0
    assert st.cur5_l == 100.0
    assert st.cur5_c == 102.0
    assert abs(st.cur5_quote - 800.0) < 1e-9

    # advance to next bar
    t1 = t0 + 300
    update_5m_bar(st, t1 + 1, 99.0, 100.0)
    # previous bar should be stored
    assert len(st.bars5m) == 1
    assert st.bars5m[-1]["o"] == 100.0

    # trim
    st.trades.append((t0 - 9999, "Buy", 100.0))
    st.prices.append((t0 - 9999, 100.0))
    trim(st, t0 + 700)
    assert len(st.trades) == 0, "stale trade should be trimmed"
    assert len(st.prices) == 0, "stale price should be trimmed"

    STATE.clear()
    print("  ✓ symbol_state.SymState / S / update_5m_bar / trim")


# ─────────────────────────────────────────────────────────────────────────────
# 5. bot/utils — dist_pct (must be SIGNED, not absolute)
# ─────────────────────────────────────────────────────────────────────────────
def test_utils_dist_pct():
    from bot.utils import dist_pct

    # price ABOVE level → positive
    assert dist_pct(105.0, 100.0) > 0, "price above level → positive"
    result = dist_pct(105.0, 100.0)
    assert abs(result - 5.0) < 1e-9, f"expected 5.0, got {result}"

    # price BELOW level → negative
    assert dist_pct(95.0, 100.0) < 0, "price below level → negative"
    result = dist_pct(95.0, 100.0)
    assert abs(result - (-5.0)) < 1e-9, f"expected -5.0, got {result}"

    # zero level → no crash
    result_zero = dist_pct(100.0, 0.0)
    assert result_zero != 0 or result_zero == 0  # just must not raise

    print("  ✓ utils.dist_pct (signed, not abs)")


# ─────────────────────────────────────────────────────────────────────────────
# 6. trade_state — property aliases, add_fill, realized_pnl_from_fills
# ─────────────────────────────────────────────────────────────────────────────
def test_trade_state():
    from trade_state import TradeState, TradeStatus
    import time as _t

    # Constructor
    tr = TradeState(symbol="BTCUSDT", side="Buy", strategy="breakout")
    assert tr.avg == 0.0
    assert tr.entry_avg_price is None  # property
    assert tr.close_reason is None
    assert tr.reason_close is None     # property alias

    # entry_avg_price alias
    tr.avg = 45000.0
    assert tr.entry_avg_price == 45000.0
    tr.entry_avg_price = 46000.0
    assert tr.avg == 46000.0

    # reason_close alias
    tr.close_reason = "TP"
    assert tr.reason_close == "TP"
    tr.reason_close = "SL"
    assert tr.close_reason == "SL"

    # getattr (used in main bot line 750)
    val = getattr(tr, "reason_close", "") or getattr(tr, "close_reason", "") or ""
    assert val == "SL"

    # add_fill + realized_pnl_from_fills (Long)
    tr2 = TradeState(symbol="ETHUSDT", side="Buy")
    assert tr2.realized_pnl_from_fills is None  # no fills

    ts = int(_t.time())
    tr2.add_fill("entry", price=2000.0, qty=1.0, fee=1.0, ts=ts)
    assert tr2.realized_pnl_from_fills is None  # no exit

    tr2.add_fill("exit", price=2100.0, qty=1.0, fee=1.05, ts=ts + 60)
    pnl = tr2.realized_pnl_from_fills
    assert abs(pnl - 97.95) < 1e-6, f"expected 97.95, got {pnl}"
    assert abs(tr2.fees - 2.05) < 1e-6

    # Short PnL
    tr3 = TradeState(symbol="BTCUSDT", side="Sell")
    tr3.add_fill("entry", price=50000.0, qty=0.01, fee=0.5, ts=ts)
    tr3.add_fill("exit",  price=49000.0, qty=0.01, fee=0.49, ts=ts + 120)
    pnl3 = tr3.realized_pnl_from_fills
    assert abs(pnl3 - 9.01) < 1e-6, f"expected 9.01, got {pnl3}"

    # best_pnl
    assert tr3.best_pnl == pnl3
    tr3.realized_pnl = 99.0
    assert tr3.best_pnl == pnl3  # fills take priority

    tr4 = TradeState(symbol="BTCUSDT", side="Buy")
    tr4.realized_pnl = 42.0
    assert tr4.best_pnl == 42.0  # no fills → manual

    # TradeStatus constants
    assert TradeStatus.PENDING_ENTRY == "PENDING_ENTRY"
    assert TradeStatus.PLACING_ENTRY == "PLACING_ENTRY"

    print("  ✓ trade_state.TradeState — aliases, fills, PnL")


# ─────────────────────────────────────────────────────────────────────────────
# 7. news_filter — is_news_blocked
# ─────────────────────────────────────────────────────────────────────────────
def test_news_filter():
    from news_filter import load_news_events, load_news_policy, is_news_blocked, NewsEvent

    events_path = os.path.join(_ROOT, "runtime", "news_filter", "events.csv")
    policy_path = os.path.join(_ROOT, "runtime", "news_filter", "policy.json")

    events = load_news_events(events_path)
    assert len(events) >= 10, f"Expected ≥10 events, got {len(events)}"

    policy = load_news_policy(policy_path)
    assert policy.get("enabled") is True

    # FOMC 2026-03-19 19:00 UTC = ts 1773946800
    fomc_ts = 1773946800
    ts_inside  = fomc_ts - 15 * 60    # 15 min before → inside blackout
    ts_outside = fomc_ts + 50 * 60    # 50 min after  → outside 45-min window

    blocked, reason = is_news_blocked(
        symbol="BTCUSDT", ts_utc=ts_inside,
        strategy_name="inplay_breakout", events=events, policy=policy,
    )
    assert blocked, f"BTCUSDT should be blocked before FOMC, got reason={reason!r}"

    blocked2, _ = is_news_blocked(
        symbol="BTCUSDT", ts_utc=ts_outside,
        strategy_name="inplay_breakout", events=events, policy=policy,
    )
    assert not blocked2, "BTCUSDT should NOT be blocked 50min after FOMC"

    # Non-crypto symbol is not blocked by CRYPTO-scoped event
    blocked3, _ = is_news_blocked(
        symbol="EURUSD", ts_utc=ts_inside,
        strategy_name="inplay_breakout", events=events, policy=policy,
    )
    assert not blocked3, "EURUSD should not be blocked by CRYPTO event"

    # High-impact blocking: medium impact (PPI) should NOT block when only high is in policy
    ppi_ts = 1775914200  # ppi_2026_apr11
    blocked4, _ = is_news_blocked(
        symbol="BTCUSDT", ts_utc=ppi_ts,
        strategy_name="inplay_breakout", events=events, policy=policy,
    )
    assert not blocked4, "PPI (medium) should not block when policy only blocks 'high'"

    # policy disabled → never blocks
    disabled_policy = {"enabled": False}
    blocked5, _ = is_news_blocked(
        symbol="BTCUSDT", ts_utc=ts_inside,
        strategy_name="inplay_breakout", events=events, policy=disabled_policy,
    )
    assert not blocked5, "disabled policy → should not block"

    print("  ✓ news_filter.is_news_blocked — high/medium/FX/disabled scenarios")


# ─────────────────────────────────────────────────────────────────────────────
# 8. diagnostics snapshot — includes new histogram keys
# ─────────────────────────────────────────────────────────────────────────────
def test_diagnostics_snapshot():
    from bot.diagnostics import _runtime_diag_snapshot, _diag_reset, _diag_inc

    _diag_reset()
    _diag_inc("breakout_ns_impulse_q1", 10)
    _diag_inc("breakout_ns_impulse_q4", 5)
    _diag_inc("breakout_skip_news", 2)

    snap = _runtime_diag_snapshot()
    assert "breakout_ns_impulse_q1=10" in snap, f"q1 not in snapshot: {snap[:200]}"
    assert "breakout_ns_impulse_q4=5"  in snap, f"q4 not in snapshot"
    assert "breakout_skip_news=2"       in snap, f"skip_news not in snapshot"
    _diag_reset()

    print("  ✓ diagnostics._runtime_diag_snapshot — histogram + news keys present")


# ─────────────────────────────────────────────────────────────────────────────
# 9. entry_guard — circuit breaker opens and recovers
# ─────────────────────────────────────────────────────────────────────────────
def test_entry_guard():
    from bot.entry_guard import EntryCircuitBreaker

    br = EntryCircuitBreaker(failure_threshold=2, cooldown_sec=30)
    assert br.is_open(now=100.0) is False

    snap1 = br.note_failure("first", now=100.0)
    assert snap1.open is False
    assert snap1.failures == 1

    snap2 = br.note_failure("second", now=101.0)
    assert snap2.open is True
    assert snap2.remaining_sec >= 29
    assert br.is_open(now=110.0) is True
    assert br.is_open(now=132.0) is False

    br.note_success()
    snap3 = br.snapshot(now=132.0)
    assert snap3.open is False
    assert snap3.failures == 0
    assert snap3.reason == ""

    print("  ✓ entry_guard.EntryCircuitBreaker — open/recover cycle")


# ─────────────────────────────────────────────────────────────────────────────
# 10. runner_state — hydrates live runner fields consistently
# ─────────────────────────────────────────────────────────────────────────────
def test_runner_state():
    from trade_state import TradeState
    from bot.runner_state import apply_runner_state

    class _Sig:
        tps = [101.0, 102.5]
        tp_fracs = [0.4, 0.6]
        trailing_atr_mult = 1.25
        trailing_atr_period = 21
        trail_activate_rr = 1.1
        be_trigger_rr = 0.8
        be_lock_rr = 0.1
        time_stop_bars = 6

    tr = TradeState(symbol="BTCUSDT", side="Buy")
    tr.sl_price = 95.0
    enabled = apply_runner_state(tr, _Sig(), 0.75, use_runner=True)
    assert enabled is True
    assert tr.runner_enabled is True
    assert tr.initial_qty == 0.75
    assert tr.remaining_qty == 0.75
    assert tr.initial_sl_price == 95.0
    assert tr.tps == [101.0, 102.5]
    assert tr.tp_fracs == [0.4, 0.6]
    assert tr.tp_hit == [False, False]
    assert tr.trail_mult == 1.25
    assert tr.trail_period == 21
    assert tr.trail_activate_rr == 1.1
    assert tr.be_trigger_rr == 0.8
    assert tr.be_lock_rr == 0.1
    assert tr.time_stop_sec == 1800

    tr2 = TradeState(symbol="ETHUSDT", side="Sell")
    tr2.sl_price = 2050.0
    enabled_dynamic = apply_runner_state(tr2, _Sig(), 1.0, use_runner=False)
    assert enabled_dynamic is True
    assert tr2.runner_enabled is True
    assert tr2.initial_qty == 1.0
    assert tr2.remaining_qty == 1.0
    assert tr2.tps == []
    assert tr2.initial_sl_price == 2050.0
    assert tr2.be_trigger_rr == 0.8
    assert tr2.time_stop_sec == 1800

    print("  ✓ runner_state.apply_runner_state — shared hydration")


def test_midterm_v3_legacy_hist_sign():
    from strategies.btc_eth_midterm_v3 import BTCETHMidtermV3Strategy

    saved = {k: os.environ.get(k) for k in (
        "MTPB3_REQUIRE_HIST_SIGN",
        "MTPB3_REQUIRE_HIST_SIGN_SHORTS",
        "MTPB3_REQUIRE_HIST_SIGN_LONGS",
    )}
    try:
        os.environ["MTPB3_REQUIRE_HIST_SIGN"] = "1"
        os.environ.pop("MTPB3_REQUIRE_HIST_SIGN_SHORTS", None)
        os.environ.pop("MTPB3_REQUIRE_HIST_SIGN_LONGS", None)
        strat = BTCETHMidtermV3Strategy()
        assert strat.cfg.macro_require_hist_sign_shorts is True
        assert strat.cfg.macro_require_hist_sign_longs is True

        os.environ["MTPB3_REQUIRE_HIST_SIGN"] = "1"
        os.environ["MTPB3_REQUIRE_HIST_SIGN_SHORTS"] = "1"
        os.environ["MTPB3_REQUIRE_HIST_SIGN_LONGS"] = "0"
        strat_explicit = BTCETHMidtermV3Strategy()
        assert strat_explicit.cfg.macro_require_hist_sign_shorts is True
        assert strat_explicit.cfg.macro_require_hist_sign_longs is False
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print("  ✓ btc_eth_midterm_v3 legacy MACD env fallback")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        test_env_bool,
        test_auth_disabled,
        test_diagnostics,
        test_symbol_state,
        test_utils_dist_pct,
        test_trade_state,
        test_news_filter,
        test_diagnostics_snapshot,
        test_entry_guard,
        test_runner_state,
        test_midterm_v3_legacy_hist_sign,
    ]
    print(f"\n{'─' * 55}")
    print("  smoke_test.py — running all tests")
    print(f"{'─' * 55}")
    failed = []
    for t in tests:
        try:
            t()
        except Exception as e:
            import traceback
            failed.append(t.__name__)
            print(f"  ✗ {t.__name__}: {e}")
            traceback.print_exc()
    print(f"{'─' * 55}")
    if failed:
        print(f"  FAILED: {len(failed)}/{len(tests)} — {failed}")
        sys.exit(1)
    else:
        print(f"  ALL {len(tests)} TESTS PASSED ✓")
        print(f"{'─' * 55}\n")
