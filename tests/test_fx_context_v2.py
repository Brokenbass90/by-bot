from bot.fx_context import build_fx_context
from bot.fx_instruments import get_instrument


def test_context_uses_closed_bar_decision_timestamp():
    rows = []
    start = 1_750_000_000
    for i in range(180):
        price = 1.10 + i * 0.00001
        rows.append([
            start + i * 3600, price, price + 0.0005,
            price - 0.0005, price + 0.0001, 10.0,
        ])
    context = build_fx_context(
        rows, instrument=get_instrument("EURUSD"),
        events=None, avoid_low_liquidity=False, bar_seconds=3600,
    )
    assert context.bar_ts == int(rows[-1][0])
    assert context.ts == context.bar_ts + 3600
    assert context.bar_seconds == 3600
