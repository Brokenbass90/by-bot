# Codex Batch Task — 4 конкретных улучшения

---

## Задача 1: ARF1 частота — расширить allowlist + смягчить RSI

**Цель**: увеличить частоту с 3 до 8-12 сделок в месяц.

### Файл: `configs/core3_impulse_candidate_20260408.env`

Добавить/изменить:
```bash
# ARF1 — расширенный allowlist + мягче RSI
ARF1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT
ARF1_RSI_SHORT_MIN=54          # было 58 (или дефолт выше)
ARF1_RESISTANCE_LOOKBACK=24    # было 48 (ищем более свежие уровни)
```

### Backtest для проверки:
Создать `configs/autoresearch/arf1_frequency_boost_v1.json`:
```json
{
  "name": "arf1_frequency_boost_v1",
  "command": ["{python}", "backtest/run_portfolio.py",
    "--symbols", "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT",
    "--strategies", "alt_resistance_fade_v1",
    "--days", "360", "--end", "2026-04-01",
    "--tag", "{tag}", "--starting_equity", "100",
    "--risk_pct", "0.008", "--leverage", "2",
    "--max_positions", "3", "--fee_bps", "6", "--slippage_bps", "2"],
  "base_env": {
    "ARF1_ALLOW_LONGS": "0", "ARF1_ALLOW_SHORTS": "1"
  },
  "grid": {
    "ARF1_SYMBOL_ALLOWLIST": [
      "BTCUSDT,ETHUSDT",
      "BTCUSDT,ETHUSDT,SOLUSDT",
      "BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,DOTUSDT"
    ],
    "ARF1_RSI_SHORT_MIN": [54, 56, 58],
    "ARF1_RESISTANCE_LOOKBACK": [24, 36, 48]
  },
  "constraints": {
    "min_trades": 30,
    "min_profit_factor": 1.25,
    "max_drawdown": 8.0,
    "min_net_pnl": 6.0
  }
}
```

Запустить: `python backtest/run_autoresearch.py configs/autoresearch/arf1_frequency_boost_v1.json`

---

## Задача 2: Support Bounce — исправить 3 бага

**Цель**: поднять pass rate с 0.7% до хотя бы 15-20%.

### Файл: `strategies/alt_support_bounce_v1.py`

**Фикс 1** — убрать slope ограничение из `_regime_ok`:
```python
# БЫЛО:
ok = (
    (ema_fast >= ema_slow or gap_pct <= self.cfg.regime_max_gap_pct)
    and slope_pct <= self.cfg.regime_max_slope_pct   # ← УБРАТЬ ЭТО
    and self.cfg.regime_min_atr_pct <= atr_pct <= self.cfg.regime_max_atr_pct
)

# СТАЛО:
ok = (
    (ema_fast >= ema_slow or gap_pct <= self.cfg.regime_max_gap_pct)
    and self.cfg.regime_min_atr_pct <= atr_pct <= self.cfg.regime_max_atr_pct
)
```

**Фикс 2** — расширить RSI диапазон:
```python
# В AltSupportBounceV1Config:
min_rsi: float = 25.0   # было 30
max_rsi: float = 50.0   # было 42
```

**Фикс 3** — добавить volume confirmation:
```python
# В AltSupportBounceV1Config добавить:
vol_mult: float = 1.2           # текущий бар >= 1.2x средний объём
vol_avg_bars: int = 20

# В maybe_signal загрузить объёмы:
vols = [float(r[5]) for r in rows]
vol_avg = sum(vols[-self.cfg.vol_avg_bars:-1]) / max(1, self.cfg.vol_avg_bars - 1)
vol_ok = vols[-1] >= self.cfg.vol_mult * vol_avg if vol_avg > 0 else True

# Добавить vol_ok в условие входа:
if not (touched_supp and reclaimed_above and body_frac >= ... and vol_ok):
    ...
```

ENV переменные добавить:
```
ASB1_VOL_MULT=1.2
ASB1_VOL_AVG_BARS=20
```

### Backtest после фиксов:
```bash
python backtest/run_autoresearch.py configs/autoresearch/support_bounce_v1_regime_gap_repair_v1.json
```
(тот же конфиг что и был, но теперь без slope gate)

---

## Задача 3: Inplay Breakout Long v1 — лонговый близнец breakdown

**Цель**: ловить локальные взлёты монет (импульс вверх + ретест уровня).

Создать новый файл `strategies/alt_inplay_breakout_long_v1.py`.
Это зеркало `alt_inplay_breakdown_v1.py` для лонгов.

### Логика:
1. **Детекция пробоя (1H)**: цена пробивает максимум последних `BREAKOUT_LOOKBACK_H=8` часов
   - Пробой минимум `BREAKOUT_MIN_ATR=1.0` ATR выше уровня
   - Тело пробойной свечи ≥ 40% диапазона
   - Объём пробоя ≥ `BREAKOUT_VOL_MULT=1.5` × средний за 20 баров
2. **Ожидание ретеста (1H)**: за последние `RETEST_BARS=3` бара цена возвращалась к пробитому уровню (в пределах 0.3 ATR)
3. **Вход (5m)**: текущий бар бычий (close > open), тело ≥ 30%, close выше уровня на ≥ 0.2 ATR
4. **RSI фильтр**: RSI(14) на 1H между 45 и 70 (не перекуплен)

### Параметры:
```python
STRATEGY_NAME = "alt_inplay_breakout_long_v1"
ENV_PREFIX = "AIBL1_"
```

### SL/TP:
- SL: уровень пробоя − 0.9 ATR  
- TP1: entry + 1.2 ATR (50% позиции)
- TP2: entry + 2.8 ATR (50% позиции)
- Time stop: 144 пятиминутных бара (12 часов)
- Cooldown: 24 бара (2 часа)

### Подключить в бот:
По образцу IVB1 (`_IVB1Store`, `try_ivb1_entry_async`):
- Создать класс `_AIBLStore`
- Создать `try_aibl1_entry_async(symbol, price)`
- Добавить env флаг `ENABLE_AIBL1_TRADING=0` (пока выключить до валидации)

### Allocator sleeve:
```json
{
  "name": "inplay_long",
  "enable_env": "ENABLE_AIBL1_TRADING",
  "strategy_names": ["alt_inplay_breakout_long_v1"],
  "base_risk_mult_by_regime": {
    "bull_trend": 1.3,
    "bull_chop": 0.7,
    "bear_chop": 0.0,
    "bear_trend": 0.0
  }
}
```

### Backtest:
```json
configs/autoresearch/aibl1_current90_v1.json
--symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT
--days 90 (сначала 90 дней, потом если OK — 360)
```

---

## Задача 4: Проверить Alpaca на сервере

```bash
# Выполнить на сервере:
crontab -l | grep alpaca
ls -la data_cache/equities_1h/ | head -10
ls -la runtime/equities_intraday_dynamic_v1/
tail -20 logs/intraday_bridge.log 2>/dev/null || echo "no log"

# Если data_cache пустой — запустить разово:
source configs/alpaca_intraday_dynamic_v1.env
python3 scripts/equities_alpaca_intraday_bridge.py --live --once

# Если всё ОК — убедиться что cron запускает с --live (не --dry-run)
crontab -l | grep alpaca
```

**Если cron есть но без --live**, изменить запись на:
```cron
*/5 14-21 * * 1-5 cd /root/bybot && source configs/alpaca_intraday_dynamic_v1.env && python3 scripts/equities_alpaca_intraday_bridge.py --live --once >> logs/intraday_bridge.log 2>&1
```

---

## Приоритет выполнения:
1. Задача 4 (Alpaca проверка) — 10 минут
2. Задача 3 (новая стратегия) — 2-3 часа  
3. Задача 1 (ARF1 boost) — 1 час
4. Задача 2 (Support Bounce fix) — 1 час

## Ожидаемый результат:
- ARF1: 8-12 сделок/месяц (сейчас 3)
- AIBL1: новая живая стратегия для лонговых инплэй движений
- Support Bounce: pass rate > 10% (сейчас 0.7%)
- Alpaca: торгует на paper account
