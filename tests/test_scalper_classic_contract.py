import os

from strategies.scalper_classic_v1 import ScalperClassicV1Strategy


class _Store:
    symbol = "BTCUSDT"

    def __init__(self) -> None:
        self.rows_5m = []
        for i in range(70):
            self.rows_5m.append([i * 300_000, 100.0, 101.0, 99.0, 100.0, 100.0])
        self.rows_5m[-1] = [69 * 300_000, 101.0, 102.0, 100.0, 100.5, 1000.0]
        self.rows_15m = [
            [i * 900_000, 100.0, 101.0, 99.0, 100.0, 100.0]
            for i in range(80)
        ]

    def fetch_klines(self, symbol: str, interval: str, limit: int):
        rows = self.rows_5m if interval == "5" else self.rows_15m
        return rows[-limit:]


def test_scalper_sweep_returns_valid_runner_signal() -> None:
    old = {
        key: os.environ.get(key)
        for key in (
            "SC1_MODE",
            "SC1_VOL_Z_MIN",
            "SC1_MIN_ATR_PCT",
            "SC1_MAX_ATR_PCT",
        )
    }
    os.environ.update(
        {
            "SC1_MODE": "sweep",
            "SC1_VOL_Z_MIN": "0.0",
            "SC1_MIN_ATR_PCT": "0.0",
            "SC1_MAX_ATR_PCT": "10.0",
        }
    )
    try:
        strategy = ScalperClassicV1Strategy()
        sig = strategy.maybe_signal(_Store(), 69 * 300_000, 101.0, 102.0, 100.0, 100.5, 1000.0)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert sig is not None
    assert sig.strategy == "scalper_classic_v1"
    assert sig.side == "short"
    assert sig.validate()
    assert len(sig.tps or []) == 2
    assert sig.time_stop_bars > 0
