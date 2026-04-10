# Аудит кодовой базы — 2026-04-08

## Что проверялось

- `build_regime_state.py` — оркестратор режима
- `build_portfolio_allocator.py` — аллокатор капитала
- `smart_pump_reversal_bot.py` — основной live-бот
- `bot_health_watchdog.sh` + `control_plane_watchdog.py` — watchdog
- `setup_server_crons.sh` — cron-конфигурация
- Стратегии: `impulse_volume_breakout_v1.py`, `alt_resistance_fade_v1.py`
- `configs/strategy_health.json`, `portfolio_allocator_policy.json`

---

## КРИТИЧНО (исправить до масштабирования)

### 🔴 1. IVB1 не подключён к живому боту

**Проблема:**
`smart_pump_reversal_bot.py` не импортирует и не использует `ImpulseVolumeBreakoutV1Strategy`. Файл `core3_impulse_candidate_20260408.env` содержит параметры `IVB1_*`, но бот их игнорирует — они мёртвые переменные.

**Последствие:** Стратегия IVB1 работает только в бэктесте. В live её нет вообще.

**Исправление (Codex задача):**
- Импортировать `ImpulseVolumeBreakoutV1Strategy` в основной бот
- Добавить её в цикл обработки сигналов (рядом с ARF1 и breakdown)
- Добавить `"impulse"` sleeve в `portfolio_allocator_policy.json`
- Добавить `ENABLE_IMPULSE_TRADING` / `IMPULSE_RISK_MULT` в политику

---

### 🔴 2. AUTO_RESTART выключен

**Проблема:**
`WATCHDOG_AUTO_RESTART=0` (дефолт). Если бот упадёт ночью — останется мёртвым до ручного перезапуска.

**Последствие:** Пропущенные сделки, стоп-лоссы не выставляются, открытые позиции без управления.

**Исправление:**
В `scripts/setup_watchdog_cron.sh` или env сервера добавить:
```bash
WATCHDOG_AUTO_RESTART=1
```
Systemd уже установлен — рестарт безопасен.

---

### 🔴 3. Минимальный ордер в safe mode при $100

**Проблема:**
`MIN_NOTIONAL_USD = $10`. Эффективный риск в safe mode:
`1.0% × ORCH_GLOBAL_RISK_MULT(0.7) × ALLOCATOR_GLOBAL_RISK_MULT(0.25 safe) = 0.175%`
При $100 капитале: risk_usd = $0.175. При stop_pct=2%: notional = $8.75 < $10 → ВСЕ СИГНАЛЫ ПРОПУСКАЮТСЯ.

**Последствие:** В safe mode бот физически не может торговать при $100 депозите.

**Исправление:**
```python
MIN_NOTIONAL_USD = 5.0  # вместо 10.0
```
Или установить `MIN_NOTIONAL_USD=5` в env. Bybit позволяет ордера от $5.

---

## ВЫСОКИЙ ПРИОРИТЕТ

### 🟠 4. strategy_health.json управляется вручную

**Проблема:**
Большинство стратегий в статусе PAUSE. `equity_curve_autopilot.py` обновляет этот файл раз в неделю (воскресенье), но:
- при свежем $100 счёте нет истории живых сделок
- autopilot использует данные из `backtest_runs/`, но не всегда находит последний run
- PAUSE стратегии → allocator в degraded mode навсегда → риск снижен на 25%

**Текущее состояние:**
`alt_inplay_breakdown_v1=WATCH, alt_resistance_fade_v1=OK, остальные=PAUSE`

**Исправление:**
Запустить `equity_curve_autopilot.py` принудительно после каждого значимого бэктеста. Или вручную обновить `strategy_health.json` для активных стратегий:
```json
{
  "strategies": {
    "alt_inplay_breakdown_v1": {"status": "OK"},
    "alt_resistance_fade_v1": {"status": "OK"},
    "impulse_volume_breakout_v1": {"status": "OK"}
  },
  "overall_health": "OK"
}
```

---

### 🟠 5. Двойное умножение риска (возможно избыточно)

**Проблема:**
Бот применяет ОБА множителя умножением (строка 9443):
```python
eff = BASE_RISK_PER_TRADE_PCT * ORCH_GLOBAL_RISK_MULT * ALLOCATOR_GLOBAL_RISK_MULT
```

В bear_chop + degraded:
`1.0% × 0.7 × 0.6 = 0.42%` — это нормально при $100.

Но если обе системы независимо срезают риск по одной причине (плохой рынок) — двойной срез избыточен.

**Рекомендация:**
Оставить архитектуру как есть (это intentional design), но документировать. При росте капитала до $1000+ — пересмотреть.

---

## СРЕДНИЙ ПРИОРИТЕТ

### 🟡 6. IVB1 нет в portfolio_allocator_policy.json

Даже когда IVB1 будет подключён к live боту — его риск не будет управляться аллокатором. Нужно добавить:
```json
{
  "name": "impulse",
  "enable_env": "ENABLE_IMPULSE_TRADING",
  "symbol_env_key": "IVB1_SYMBOL_ALLOWLIST",
  "risk_env": "IMPULSE_RISK_MULT",
  "strategy_names": ["impulse_volume_breakout_v1"],
  "base_risk_mult_by_regime": {
    "bull_trend": 1.2,
    "bull_chop": 0.6,
    "bear_chop": 0.0,
    "bear_trend": 0.0
  }
}
```

---

### 🟡 7. Классификация bull_chop слишком широкая

**Проблема (в `build_regime_state.py`):**
```python
elif bull_ema or above_55:  # ema21>ema55 OR цена>ema55
    regime = REGIME_BULL_CHOP
```
Если `ema21` чуть выше `ema55` но цена значительно ниже обеих — всё равно `bull_chop` → breakout лонги ВКЛЮЧЕНЫ. Это рискованно в начале медвежьего рынка.

**Исправление:**
```python
elif bull_ema and above_55:   # оба условия
    regime = REGIME_BULL_CHOP
elif bull_ema or above_55:    # одно из двух — это переходный режим
    regime = REGIME_BEAR_CHOP  # более консервативно
```
ИЛИ добавить `REGIME_TRANSITION` как промежуточное состояние.

---

### 🟡 8. Alpaca cron может сломать setup

`setup_server_crons.sh` использует `set -e` и требует `run_equities_alpaca_intraday_dynamic_v1.sh`. Если файл не существует на сервере — весь cron setup падает с ошибкой. Исправление: добавить `|| true` или проверку перед `set -e`.

---

## НИЗКИЙ ПРИОРИТЕТ

### 🟢 9. ARF1 — дефолтный allowlist BCHUSDT

Если `ARF1_SYMBOL_ALLOWLIST` не задан в env — стратегия торгует только BCH. Вероятно задан в live env, но это хрупко. Лучше: дефолт `""` (пусто = не торгует).

### 🟢 10. IVB1 `_armed` сбрасывается при рестарте

Незначительно — пропускается один setup после рестарта. Можно игнорировать.

---

## Что работает хорошо ✅

- **Атомарная запись файлов** во всех скриптах (tmp → replace) — нет частичных записей
- **Hysteresis** в оркестраторе (3 цикла) — нет флуктуаций при пограничных значениях
- **Fallback на кэш** при недоступности Bybit API — оркестратор не падает
- **Три уровня защиты**: systemd + watchdog + control_plane watchdog
- **Overlap haircuts** в аллокаторе — снижает риск при пересекающихся корзинах символов
- **Safe mode** при устаревших данных — блокирует новые входы если данные > 4ч
- **Telegram cooldown** в watchdog — не спамит при длительном падении
- **Regime gating** в IVB1 стратегии (код уже есть, нужно только включить)
- **Детализированный PnL tracking** — `tp1_frac`, `trail_atr_mult`, `time_stop_bars` везде правильно

---

## Итоговая таблица

| Проблема | Приоритет | Усилие | Кто |
|---|---|---|---|
| IVB1 не подключён к live | 🔴 КРИТИЧНО | Высокое | Codex |
| AUTO_RESTART выключен | 🔴 КРИТИЧНО | Минуты | Ты (env на сервере) |
| MIN_NOTIONAL $10 → $5 | 🔴 КРИТИЧНО | Минуты | Codex |
| strategy_health.json обновить | 🟠 ВЫСОКИЙ | Минуты | Ты (вручную) |
| IVB1 добавить в allocator policy | 🟠 ВЫСОКИЙ | Часы | Codex |
| Двойной риск-множитель | 🟠 ВЫСОКИЙ | Нет действий, документировать | — |
| bull_chop классификация | 🟡 СРЕДНИЙ | Строки кода | Codex |
| Alpaca cron хрупкость | 🟡 СРЕДНИЙ | Строки кода | Codex |
| ARF1 дефолтный allowlist | 🟢 НИЗКИЙ | Строки кода | Codex |

---

## Следующий шаг

После исправления критичных проблем — качество стратегий:
1. Проверить входы и выходы IVB1 в live условиях (paper trading)
2. pump_fade: прогнать fresh bektst на current90, зафиксировать лучшие параметры
3. core2 walkforward (360d) — убедиться что backbone стабилен

Дата аудита: 2026-04-08
