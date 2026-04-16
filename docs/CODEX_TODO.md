# CODEX_TODO — актуальное состояние и задачи
_Последнее обновление: 2026-04-16 | Автор: Claude (Anthropic) + Николай_
_Используй этот файл как главный источник правды о состоянии проекта_

---

## ⚡ НЕМЕДЛЕННО (деплой этой ночью)

### Задача 0 — Задеплоить скрипт фиксов

```bash
bash scripts/codex_deploy_20260416.sh
```

Скрипт делает всё: git pull + фикс DEGRADED + отключить IVB1 + снизить Elder риск + перезапустить бот + запустить оркестратор.

**После деплоя проверить:**
```bash
# Оркестратор работает?
cat runtime/regime.json | python3 -m json.tool
# Должно быть: "regime": "BEAR_TREND"

# DEGRADED ушёл?
sudo journalctl -u bybit-bot --since "5 minutes ago" | grep -i "DEGRADED\|allocator\|ASB1\|HZBO1"
# Ожидаем: "[ASB1] engine initialised", "[HZBO1] engine initialised", НЕТ "DEGRADED"
```

---

## 🔴 ПРИОРИТЕТ 1 — Устранение просадок (anti-drawdown)

### Корневая причина красных месяцев

**Годовой backtest май2025–апр2026:**
- **Сентябрь 2025**: −5.8% (ASB1 −2.85%, HZBO1 −2.80% — шортили во время разворота вверх)
- **Декабрь 2025**: −15.9% (BTC ATH $108k — все короткие стратегии уничтожены)
- Суммарная "цена": **−21.7%** за год → с оркестратором будет ~0% → +66%/год вместо +44.5%

### Решение A: Оркестратор режимов (УЖЕ СДЕЛАН, нужен деплой)

`bot/regime_orchestrator.py --env-out configs/regime_orchestrator_latest.env`

При BULL_TREND → пишет `ASB1_ALLOW_SHORTS=0, HZBO1_ALLOW_SHORTS=0` в env-файл.
Бот читает файл каждые 300 секунд и применяет изменения.
Это исправило бы ОБА красных месяца.

### Решение B: Portfolio Circuit Breaker (НУЖНО СОЗДАТЬ)

**Файл:** `bot/circuit_breaker.py`

```python
class PortfolioCircuitBreaker:
    """
    Автоматически снижает риск при просадке портфеля.
    Читает equity из runtime/equity.json или из live API.
    """
    NORMAL = 1.0    # < 4% дневная просадка
    CAUTION = 0.5   # 4-8% дневная просадка → размер вдвое меньше
    HALT = 0.0      # > 8% дневная ИЛИ > 12% месячная → стоп новых входов 24h

    def get_risk_mult(self, equity_history: list[float]) -> float:
        ...
```

Подключить в `smart_pump_reversal_bot.py`: перед каждым `try_*_entry_async()` вызывать `cb.get_risk_mult()` и умножать на него риск.

ENV-параметры:
- `CB_DAILY_DD_LIMIT=0.08` — 8% дневная просадка → HALT
- `CB_MONTHLY_DD_LIMIT=0.12` — 12% месячная просадка → HALT
- `CB_CAUTION_THRESHOLD=0.04` — 4% → CAUTION
- `CB_ENABLED=1`

### Решение C: Volatility-adjusted sizing (ИССЛЕДОВАТЬ)

Когда ATR BTC за 4h > 2× нормы (паника/ATH):
- Уменьшать позиции: `position_size = base_size * (normal_atr / current_atr)`
- Уже частично есть в Elder/IVB1 как `max_atr_pct` — сделать портфельным

---

## 🟡 ПРИОРИТЕТ 2 — Среднесрочная стратегия (BTC/ETH midterm)

### ВАЖНО: стратегия уже существует!

`strategies/btc_eth_midterm_pullback.py` (v1) и `btc_eth_midterm_pullback_v2.py`

**Результаты из WORKLOG:**
- Isolated v1: PF=2.30, WR=55%, +43.5R/год, ~80 сделок
- ETH-only строгий: +14.50%, PF=1.890, DD=2.40%, 54 сделки
- **В связке: portfolio_20260325_172613_new_5strat_final → +100.93%/год, PF=2.078, DD=3.65%** ← ЭТО И ЕСТЬ ЦЕЛЬ

### Почему сейчас выключена

В текущем медвежьем стеке `ENABLE_MIDTERM_TRADING=0`. Нужно протестировать совместимость с текущими стратегиями.

### Задача: запустить backtest midterm в текущем стеке

```bash
# НА СЕРВЕРЕ (нужен кеш 365 дней):
python3 backtest/run_portfolio.py \
  --config configs/core3_live_canary_20260411_sloped_momentum.env \
  --override ENABLE_MIDTERM_TRADING=1 \
             MTPB_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT \
             MTPB_TREND_SLOPE_MIN_PCT=0.46 \
             MTPB_RR=2.4 \
             MTPB_COOLDOWN_BARS_5M=108 \
  --days 365 --end 2026-03-31 \
  --out backtest_runs/midterm_in_bear_stack_20260416
```

Если результат лучше текущего (+44.51%) → включить в live config.

### Концепция расширения (циклы + уровни)

Уже есть файлы в strategies/:
- `btc_macro_cycle_v1.py` — 4-летние циклы (halvings)
- `btc_cycle_continuation_v1.py` — продолжение после цикла
- `btc_weekly_zone_reclaim_v2.py` — недельные зоны

Ни один из них не прошёл WF-22. Нужно запустить.

**Что реально работает в среднесроке:**
- 200-week MA (никогда не пробита на закрытии)
- Realized price (покупка ниже = исторически лучший вход)
- MACD weekly crossover (смена тренда)
- RSI weekly < 30 = дно (апрель 2026 ≈ 40, ещё не дно)

---

## 🟡 ПРИОРИТЕТ 3 — Доработка существующих стратегий

### IVB1 — исправить или заменить (ОТКЛЮЧЕНА ПОСЛЕ ДЕПЛОЯ)

**Проблема:** avg_win $0.39 < avg_loss $0.58, всего 11 сделок за год.

**Гипотезы:**
1. Поднять RR: 1.4 → 2.0+
2. Сузить SL: 0.8 ATR → 0.5 ATR
3. Расширить символы на BTC/ETH

**WF-22 для IVB1 (запустить локально или на сервере):**
```bash
python3 scripts/run_generic_wf.py \
  --strategy impulse_volume_breakout_v1 \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --windows 22 --window-days 45 \
  --sweep IVB1_RR=1.8,2.0,2.5 IVB1_SL_ATR=0.5,0.8
```

### Bounce v1 — подключить к боту (СТРАТЕГИЯ ГОТОВА, НУЖНО ИНТЕГРИРОВАТЬ)

`strategies/alt_support_bounce_v1.py` — WF-22 VIABLE, AvgPF=1.421.

**Задача Codex (аналогично ASB1/HZBO1 интеграции):**

1. Создать `strategies/bounce1_live.py`:
```python
# По аналогии с asb1_live.py
from .alt_support_bounce_v1 import AltSupportBounceV1

class Bounce1Engine:
    def __init__(self):
        self._engine = AltSupportBounceV1()

    def generate_signal(self, symbol: str, store) -> TradeSignal | None:
        ...
```

2. В `smart_pump_reversal_bot.py` найти блок с `try_hzbo1_entry_async` и добавить после:
```python
if os.getenv("ENABLE_BOUNCE1_TRADING", "0") == "1":
    sig = await try_bounce1_entry_async(symbol, store, open_trades)
    if sig:
        return sig
```

3. Добавить в `configs/portfolio_allocator_policy.json`:
```json
{
  "enable_env": "ENABLE_BOUNCE1_TRADING",
  "risk_env": "BOUNCE1_RISK_MULT",
  "strategy_names": ["alt_support_bounce_v1"]
}
```

4. Добавить в `configs/core3_live_canary_20260411_sloped_momentum.env`:
```
ENABLE_BOUNCE1_TRADING=1
BOUNCE1_RISK_MULT=0.40
BOUNCE1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT
BOUNCE1_MAX_OPEN_TRADES=1
```

### Elder v2 — объёмный фильтр (МАЛЕНЬКИЙ ПАТЧ)

Добавить в `strategies/elder_triple_screen_v2.py`:
```python
self.require_vol_confirm = _env_bool("ETS2_REQUIRE_VOL_CONFIRM", False)
self.vol_mult_confirm = _env_float("ETS2_VOL_CONFIRM_MULT", 1.5)

# В generate_signal():
if self.require_vol_confirm:
    avg_vol = mean(bar.volume for bar in bars[-20:])
    if bars[-1].volume < self.vol_mult_confirm * avg_vol:
        return None  # слабый объём — пропускаем
```

Добавить в live config:
```
ETS2_REQUIRE_VOL_CONFIRM=1
ETS2_VOL_CONFIRM_MULT=1.5
```

Цель: сократить сделки с 250 → ~150, улучшить PF с 1.098 → 1.25+.

---

## 🔵 ПРИОРИТЕТ 4 — Серверные задачи (нужен Codex с SSH на сервер)

### 4.1 Крон для strategy_health.json (КРИТИЧНО для DEGRADED)

```bash
# Проверить текущий crontab:
crontab -l

# Добавить строку:
(crontab -l 2>/dev/null; echo "0 3 * * * cd /root/by-bot && touch configs/strategy_health.json && python3 scripts/build_portfolio_allocator.py >> logs/allocator_cron.log 2>&1") | crontab -

# Проверить:
crontab -l | grep allocator
```

### 4.2 TS132 — WF-22

```bash
# На сервере (файл только там):
python3 scripts/run_generic_wf.py \
  --strategy triple_screen_v132 \
  --symbols BTCUSDT,ETHUSDT,AVAXUSDT \
  --windows 22 --window-days 45

# Критерий: AvgPF >= 1.05 И PF>1.0 в 55%+ окнах
```

### 4.3 pump_fade_v4r — WF-22 с мемкоинами

```bash
python3 backtest/fetch_klines.py \
  --symbols 1000PEPEUSDT,SUIUSDT,ARBUSDT,ENAUSDT --days 200

python3 scripts/run_generic_wf.py \
  --strategy pump_fade_v4r \
  --symbols 1000PEPEUSDT,SUIUSDT,ARBUSDT,ENAUSDT \
  --windows 22 --window-days 45
```

### 4.4 ASB1/HZBO1 BULL_TREND режим (ИССЛЕДОВАНИЕ)

Добавить режим ЛОНГ при BULL_TREND:
- ASB1 bull mode: лонг при пробое ВВЕРХ восходящей линии (reclaim вверх)
- HZBO1 bull mode: лонг при пробое ВВЕРХ горизонтальной зоны

Это удвоит полезность этих стратегий без написания новых.

---

## 📊 ТЕКУЩЕЕ СОСТОЯНИЕ

### Что работает в лайв (ПОСЛЕ ДЕПЛОЯ 2026-04-16)

| Компонент | Статус | Risk mult |
|-----------|--------|-----------|
| Breakdown (ARD1) | ✅ ACTIVE | 0.80× |
| Flat Resistance (ARF1) | ✅ ACTIVE | 1.00× |
| Range Scalp (ARS1) | ✅ ACTIVE | 0.80× |
| ATT1 trendline bounce | ✅ ACTIVE | 0.70× |
| Elder v2 (shorts only) | ✅ ACTIVE | **0.40×** (снижен) |
| ASB1 (NEW) | ✅ ACTIVE | 0.50× |
| HZBO1 (NEW) | ✅ ACTIVE | 0.40× |
| IVB1 | ❌ DISABLED | 0 |
| Regime Orchestrator | ✅ DAEMON | — |
| Bounce v1 | ❌ NOT WIRED | — |
| Midterm (MTPB) | ❌ TESTING | — |

### Ожидаемые годовые результаты (после деплоя)

| Состояние | Доходность |
|-----------|-----------|
| Текущий backtest (без орк.) | +44.51%/год |
| + Оркестратор (Dec+Sep) | ~+66%/год |
| + Bounce v1 | ~+76%/год |
| + Midterm BTC/ETH | ~+91%/год |
| + IVB1 исправлен | ~+96%/год |
| + Elder объёмный фильтр | ~+99%/год |
| **ЦЕЛЬ** | **≥100%/год** |

---

## 🗂 КЛЮЧЕВЫЕ ФАЙЛЫ

```
smart_pump_reversal_bot.py           # Главный файл бота
bot/regime_orchestrator.py           # Оркестратор режимов
configs/core3_live_canary_20260411_sloped_momentum.env  # ОСНОВНОЙ LIVE КОНФИГ
configs/portfolio_allocator_policy.json                 # Правила аллокатора

strategies/asb1_live.py              # ASB1 ✅
strategies/hzbo1_live.py             # HZBO1 ✅
strategies/att1_live.py              # ATT1 ✅
strategies/elder_triple_screen_v2.py # Elder v2 ✅
strategies/alt_support_bounce_v1.py  # Bounce v1 (нужна интеграция)
strategies/btc_eth_midterm_pullback.py   # Midterm (нужно тестировать)

docs/ROADMAP.md                      # История решений (1066 строк)
docs/ANNUAL_ANALYSIS_20260416.md     # Годовой анализ
docs/CODEX_TODO.md                   # ЭТОТ ФАЙЛ
scripts/codex_deploy_20260416.sh     # Deploy script
scripts/run_annual_analysis.py       # Годовой анализ runner
```

---

## ✅ ЧЕКЛИСТ СИНХРОНИЗАЦИИ

**Для Codex — перед началом работы:**
```bash
git log --oneline -5                              # последние коммиты
cat runtime/regime.json                           # текущий режим
sudo journalctl -u bybit-bot -n 10 --no-pager    # статус бота
cat configs/portfolio_allocator_latest.env | grep -E "RISK_MULT|GLOBAL" | head -5
```

**После работы:**
```bash
# 1. Обновить ЭТОТ файл (docs/CODEX_TODO.md)
# 2. Добавить запись в docs/WORKLOG.md с датой и временем
# 3. git add -p && git commit
```
