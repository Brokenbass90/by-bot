"""Tests for bot.news_session_filter — forex news/session entry gate (H2)."""
from bot.news_session_filter import entry_allowed, session_of, FilterState

H = 3600


def test_session_classification():
    assert session_of(2 * H) == "asian"
    assert session_of(9 * H) == "london"
    assert session_of(14 * H) == "london_ny_overlap"
    assert session_of(18 * H) == "newyork"


def test_news_blackout_blocks_before_event():
    ev = [{"ts": 12 * H + 30 * 60, "impact": 3}]      # NFP 12:30 UTC
    st = entry_allowed(12 * H, events=ev)             # 30 min before
    assert st.allow is False and st.reason == "news_blackout"
    assert st.in_news_blackout is True


def test_news_blackout_blocks_after_event():
    ev = [{"ts": 14 * H, "impact": 3}]
    st = entry_allowed(14 * H + 10 * 60, events=ev)   # 10 min after (within 30)
    assert st.allow is False and st.in_news_blackout is True


def test_outside_blackout_allowed():
    ev = [{"ts": 12 * H + 30 * 60, "impact": 3}]
    st = entry_allowed(9 * H, events=ev)              # 3.5h before, london
    assert st.allow is True and st.reason == "ok"
    assert abs(st.minutes_to_event - 210) < 1


def test_low_impact_event_ignored():
    ev = [{"ts": 9 * H + 10 * 60, "impact": 1}]       # low impact
    st = entry_allowed(9 * H, events=ev, min_impact=2)
    assert st.allow is True and st.in_news_blackout is False


def test_asian_session_blocked_by_default():
    st = entry_allowed(2 * H, events=[])
    assert st.allow is False and st.reason == "low_liquidity_session"
    assert st.is_low_liq_session is True


def test_asian_allowed_when_opt_out():
    st = entry_allowed(2 * H, events=[], avoid_low_liq_session=False)
    assert st.allow is True


def test_round_number_flag():
    assert entry_allowed(9 * H, events=[], price=1.1000).near_round_number is True
    assert entry_allowed(9 * H, events=[], price=1.1043).near_round_number is False


def test_returns_state():
    st = entry_allowed(9 * H)
    assert isinstance(st, FilterState) and st.ok is True
