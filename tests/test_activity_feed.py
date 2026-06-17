"""Tests for the unified web activity feed (web↔TG one-entity feed)."""
from web.activity_feed import (
    render_trade_event_ru,
    build_activity_feed,
    read_trade_events,
)


def test_render_close_event_is_human_russian():
    evt = {"event": "close", "side": "Sell", "symbol": "LTCUSDT",
           "strategy": "flat_resistance_fade", "exit_price": 43.6, "pnl": 0.174, "ts": 100}
    txt = render_trade_event_ru(evt)
    assert "Закрытие" in txt
    assert "шорт" in txt
    assert "LTCUSDT" in txt
    assert "шорт от сопротивления" in txt
    assert "P&L +0.17" in txt


def test_render_order_submitted_shows_price_and_stop():
    evt = {"event": "order_submitted", "side": "Sell", "symbol": "LTCUSDT",
           "strategy": "alt_range_scalp_v1", "request_price": 43.91, "request_sl": 44.13, "ts": 1}
    txt = render_trade_event_ru(evt)
    assert "Заявка на вход" in txt
    assert "пила во флэте" in txt
    assert "цена 43.91" in txt and "стоп 44.13" in txt


def test_feed_merges_and_sorts_by_time():
    trades = [
        {"event": "close", "side": "Buy", "symbol": "SOLUSDT", "strategy": "alt_range_scalp_v1",
         "exit_price": 150.0, "pnl": 1.2, "ts": 300},
    ]
    chat = [
        {"role": "user", "content": "как дела у бота?", "ts": 100},
        {"role": "assistant", "content": "торгует пилу во флэте", "ts": 200},
    ]
    feed = build_activity_feed(trade_events=trades, chat_history=chat,
                               pulse_text="ПУЛЬС БОТА — 1 ч назад", pulse_ts=50, limit=50)
    ts_order = [i["ts"] for i in feed]
    assert ts_order == sorted(ts_order)
    kinds = [i["kind"] for i in feed]
    assert {"trade", "chat", "pulse"} <= set(kinds)
    # tg-channel items (alerts/pulse) and web-channel items (chat) both present
    channels = {i["channel"] for i in feed}
    assert "tg" in channels and "web" in channels


def test_feed_limit_keeps_newest():
    trades = [{"event": "close", "side": "Buy", "symbol": "X", "strategy": "range",
               "exit_price": 1.0, "pnl": 0.0, "ts": t} for t in range(1, 11)]
    feed = build_activity_feed(trade_events=trades, limit=3)
    assert len(feed) == 3
    assert [i["ts"] for i in feed] == [8, 9, 10]


def test_read_trade_events_filters_lifecycle(tmp_path):
    p = tmp_path / "ev.jsonl"
    p.write_text(
        '\n'.join([
            '{"event":"heartbeat","ts":1}',
            '{"event":"close","side":"Sell","symbol":"LTCUSDT","strategy":"flat_resistance_fade","exit_price":43.6,"pnl":0.17,"ts":2}',
            'not-json',
            '{"event":"entry_filled","side":"Sell","symbol":"LTCUSDT","strategy":"flat_resistance_fade","entry_price":43.9,"ts":3}',
        ]),
        encoding="utf-8",
    )
    evts = read_trade_events(p, limit=10)
    assert len(evts) == 2  # heartbeat + junk dropped
    assert {e["event"] for e in evts} == {"close", "entry_filled"}
