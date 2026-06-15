"""alt_stablecoin_depeg_arb_v1 — арбитраж на отвязке стейблкоинов.

Контекст: события типа USDC March 2023 (depeg до $0.88 за 24h после SVB collapse) —
редкие, но дают +5-15% PnL за 24-48ч при правильной реакции. Бот должен видеть
такие события автоматически и реагировать.

Стейблкоины которые мониторим: USDC, USDT, DAI, BUSD, FDUSD, TUSD, USDD, USDP.

Логика:
    DEPEG entry (LONG арб):
        - Цена стейбла на Bybit/Binance < $0.995 (down depeg)
        - Volume на паре > 2× average последних 24h (паника = много торгов)
        - Не катастрофа (если < $0.85 — слишком рискованно, может быть полный collapse)
        - Открываем LONG позицию на USDC/USDT пару (например USDCUSDT перпы на Bybit)
        - Target: возврат к $0.998 или time stop 48 часов
        - SL: ещё -2% (если до $0.97 — выходим, может быть real collapse)

    DEPEG entry (SHORT арб):
        - Цена стейбла > $1.005 (up depeg — реже случается)
        - SHORT, target $1.002, time stop 24h

Sizing:
    - Risk 0.3% от equity per trade (низкий — это асимметричная ставка)
    - Max 1 одновременно (одна паника = коррелированные depegs всех stablecoins)
    - Cooldown 7 дней после трейда на той же паре (избегаем повторов на slow recovery)

Размер позиции для арба:
    - Депозит $123 → max $50 позиция на USDC pair с leverage 1
    - При depeg -2% и возврате к -0.2% → profit ~1.8% × $50 = $0.90
    - При SL -2% → loss ~$1.00
    - Asymmetric — большинство depegs восстанавливаются (USDC 2023 за 3 дня)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class StablecoinDepegSignal:
    side: str
    entry: float
    sl: float
    tp: float
    time_stop_hours: int
    rationale: str


class AltStablecoinDepegArbV1:
    NAME = "alt_stablecoin_depeg_arb_v1"
    DEFAULT_PARAMS = {
        "DEPEG_LONG_THRESHOLD": 0.995,    # цена ниже $0.995 → потенциал long
        "DEPEG_SHORT_THRESHOLD": 1.005,   # цена выше $1.005 → потенциал short
        "CATASTROPHE_THRESHOLD": 0.85,    # ниже = real collapse, не торгуем
        "VOL_RATIO_MIN": 2.0,
        "TARGET_LONG": 0.998,
        "TARGET_SHORT": 1.002,
        "SL_DEPEG_LONG": 0.97,            # экстра -2% от entry
        "SL_DEPEG_SHORT": 1.03,
        "TIME_STOP_HOURS_LONG": 48,
        "TIME_STOP_HOURS_SHORT": 24,
        "RISK_PCT": 0.3,
        "MAX_OPEN_TRADES": 1,
        "COOLDOWN_HOURS_PER_PAIR": 168,   # 7 дней
        "ALLOWED_PAIRS": "USDCUSDT,DAIUSDT,FDUSDUSDT,TUSDUSDT",
    }

    def __init__(self, params: Optional[dict] = None):
        self.params = {**self.DEFAULT_PARAMS, **(params or {})}
        self._last_trade_ts = {}  # pair -> timestamp последнего трейда

    def evaluate(self, bars_1h, symbol, current_ts=None, open_positions=0):
        """Возвращает signal или None.

        bars_1h — последние 24+ часовые бары для пары стейбла к USDT.
        """
        if not bars_1h or len(bars_1h) < 24:
            return None

        if symbol not in [s.strip() for s in str(self.params["ALLOWED_PAIRS"]).split(",")]:
            return None

        if open_positions >= int(self.params["MAX_OPEN_TRADES"]):
            return None

        # Cooldown
        if current_ts and self._last_trade_ts.get(symbol):
            hours_since = (current_ts - self._last_trade_ts[symbol]) / 3600
            if hours_since < int(self.params["COOLDOWN_HOURS_PER_PAIR"]):
                return None

        current_price = bars_1h[-1]["close"]

        # Catastrophe check — не торгуем полный collapse
        if current_price < float(self.params["CATASTROPHE_THRESHOLD"]):
            return None

        # Volume check (паника = много торгов)
        avg_vol = sum(b["volume"] for b in bars_1h[-24:]) / 24
        if avg_vol <= 0 or bars_1h[-1]["volume"] < float(self.params["VOL_RATIO_MIN"]) * avg_vol:
            return None

        # LONG depeg
        if current_price < float(self.params["DEPEG_LONG_THRESHOLD"]):
            sl = current_price * float(self.params["SL_DEPEG_LONG"])
            tp = float(self.params["TARGET_LONG"])
            if current_ts:
                self._last_trade_ts[symbol] = current_ts
            return StablecoinDepegSignal(
                side="long",
                entry=current_price,
                sl=sl,
                tp=tp,
                time_stop_hours=int(self.params["TIME_STOP_HOURS_LONG"]),
                rationale=(
                    f"DEPEG LONG: {symbol} = ${current_price:.4f} (< $0.995), "
                    f"vol×{bars_1h[-1]['volume']/avg_vol:.1f}, "
                    f"target ${tp}, SL ${sl:.4f}, time stop {self.params['TIME_STOP_HOURS_LONG']}h"
                ),
            )

        # SHORT depeg (premium)
        if current_price > float(self.params["DEPEG_SHORT_THRESHOLD"]):
            sl = current_price * float(self.params["SL_DEPEG_SHORT"])
            tp = float(self.params["TARGET_SHORT"])
            if current_ts:
                self._last_trade_ts[symbol] = current_ts
            return StablecoinDepegSignal(
                side="short",
                entry=current_price,
                sl=sl,
                tp=tp,
                time_stop_hours=int(self.params["TIME_STOP_HOURS_SHORT"]),
                rationale=(
                    f"DEPEG SHORT: {symbol} = ${current_price:.4f} (> $1.005), "
                    f"vol×{bars_1h[-1]['volume']/avg_vol:.1f}, "
                    f"target ${tp}, SL ${sl:.4f}, time stop {self.params['TIME_STOP_HOURS_SHORT']}h"
                ),
            )

        return None


if __name__ == "__main__":
    # Симулируем USDC depeg как было в марте 2023
    bars = []
    for i in range(24):
        # Normal trading
        bars.append({"close": 1.0001, "open": 1.0, "high": 1.0005, "low": 0.9998, "volume": 100000})
    # Force depeg на последнем баре
    bars[-1]["close"] = 0.9712
    bars[-1]["low"] = 0.9650
    bars[-1]["volume"] = 350000  # 3.5× normal

    strat = AltStablecoinDepegArbV1()
    sig = strat.evaluate(bars, symbol="USDCUSDT", current_ts=1700000000)
    if sig:
        print(f"SIGNAL: {sig.side} @ {sig.entry:.4f} SL {sig.sl:.4f} TP {sig.tp:.4f} time_stop {sig.time_stop_hours}h")
        print(f"Rationale: {sig.rationale}")
    else:
        print("No signal")
