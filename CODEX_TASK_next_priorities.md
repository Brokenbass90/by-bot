# Codex — Приоритеты на следующую сессию

## Уже исправлено вручную (не трогать)
- `configs/dynamic_allowlist_latest.env` — убран FARTCOINUSDT, добавлен IVB1_SYMBOL_ALLOWLIST
- `configs/core3_live_canary_20260410.env` — добавлен IVB1_SYMBOL_ALLOWLIST
- `configs/alpaca_paper_v36_candidate.env` — CAPITAL_OVERRIDE=1000, CLOSE_STALE=1, MAX_POSITIONS=2
- `configs/portfolio_allocator_policy.json` — breakdown bull_trend/bull_chop → 0.0
- `scripts/build_regime_state.py` — ER_PERIOD=30, ER_THRESH=0.28

---

## ЗАДАЧА 1 — Оркестратор не пишет applied_regime (СРОЧНО, 30 мин)

`runtime/regime/orchestrator_state.json` имеет `"applied_regime": null`.
Это значит live env не обновляется режимом.

### Диагностика на сервере:
```bash
python3 scripts/build_regime_state.py --dry-run 2>&1 | tail -30
cat runtime/regime/orchestrator_state.json | python3 -m json.tool | head -20
ls -la configs/regime_orchestrator_latest.env
crontab -l | grep build_regime
```

### Вероятные причины:
1. Скрипт не запускается по cron (нет записи или путь неверный)
2. Ошибка при записи файла (права доступа)
3. Bybit API недоступен → скрипт падает до записи

### Фикс:
Если cron не настроен — добавить:
```cron
0 * * * * cd /root/bybot && python3 scripts/build_regime_state.py >> logs/regime_orchestrator.log 2>&1
```
Если API ошибка — оркестратор должен писать LAST KNOWN state даже при ошибке,
не оставлять `applied_regime: null`. Добавить fallback:
```python
# В build_regime_state.py, в блоке исключений:
if state.get("applied_regime") is None and state.get("pending_regime"):
    state["applied_regime"] = state["pending_regime"]
    state["applied_by"] = "fallback_pending"
```

---

## ЗАДАЧА 2 — FARTCOINUSDT защита в роутере (20 мин)

Монета возвращается в allowlist при каждой регенерации роутера (degraded fallback).
Нужно зашить её в глобальный denylist в коде роутера.

В `scripts/build_symbol_router.py` найти место где формируется fallback список.
Добавить глобальный denylist константой:

```python
GLOBAL_SYMBOL_DENYLIST = {
    "FARTCOINUSDT",   # meme, extreme volatility, no edge
    "PEPEUSDT",       # meme
    "BONKUSDT",       # meme
    "WIFUSDT",        # meme
}

def _clean_symbols(symbols: list) -> list:
    return [s for s in symbols if s not in GLOBAL_SYMBOL_DENYLIST]
```

Применить `_clean_symbols()` к каждому fallback списку перед записью в env.

---

## ЗАДАЧА 3 — Elder диагностика (1 час)

`strategy_health.json` говорит "rescue sweep failed". Нужно понять ПОЧЕМУ нет сигналов.

### Добавить verbose logging в `strategies/elder_triple_screen_v2.py`:

В метод `maybe_signal()` добавить детальный лог каждого отказа:
```python
# Пример — для каждого символа логировать на каком экране застряли
self.last_screen1_fail_reason = ""
self.last_screen2_fail_reason = ""
self.last_screen3_fail_reason = ""
```

### Запустить диагностический бэктест:
```bash
python3 scripts/run_backtest.py \
  --strategy elder_triple_screen_v2 \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --tf 15 \
  --days 30 \
  --verbose-signals \
  --env configs/core3_live_canary_20260410.env \
  2>&1 | grep -E "screen|fail|reason|signal" | head -50
```

Если Screen 1 (4H тренд) блокирует всё в bear_chop — это нормально.
Если Screen 2 (1H RSI) блокирует — снизить `osc_os` с 42 до 38.
Если Screen 3 (15m вход) блокирует — снизить `entry_retest_bars` с 5 до 3.

---

## ЗАДАЧА 4 — Флэт-стратегии для bear_chop (2 часа)

Текущий режим bear_chop — лучшее время для:
1. ARF1 (fade от сопротивления) — уже работает, нужно больше символов
2. AVEF1 (volume exhaustion fade) — ещё не реализована
3. alt_range_scalp_v1 — в PAUSE, нужна валидация

### Добавить ARF1 символы в bear_chop:
В `configs/core3_live_canary_20260410.env` добавить:
```bash
ARF1_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,XRPUSDT
```
(сейчас передаётся из dynamic_allowlist который имеет 5 символов, но в canary нет явного override)

### Проверить alt_range_scalp_v1 в bear_chop:
```bash
python3 scripts/run_backtest.py \
  --strategy alt_range_scalp_v1 \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --tf 15 \
  --days 180 \
  --regime bear_chop \
  2>&1 | tail -20
```
Если PF > 1.3 и DD < 10% → добавить в canary как `ENABLE_RANGE_TRADING=1`.

---

## ЗАДАЧА 5 — Alpaca advisory обновление (15 мин)

Advisory файл от 1 апреля, пики появились 9 апреля. Нужно перезапустить:

```bash
cd /root/bybot
source .venv/bin/activate
source configs/alpaca_paper_v36_candidate.env
source configs/alpaca_paper_local.env
ALPACA_AUTOPILOT_RUNTIME_DIR=runtime/equities_monthly_v36 \
python3 scripts/equities_alpaca_paper_bridge.py --dry-run
```

Убедиться что:
- `status` не `dry_run_no_current_cycle`
- `new_buy_symbols` содержит NET и/или NFLX
- `per_position_notional` > 0 (при capital=1000 должно быть ~$400)

---

## НЕ ТРОГАТЬ сейчас

- AVEF1 стратегию (задача описана в CODEX_TASK_vef_strategy.md, реализация после Elder)
- Crypto rotation (задача концептуальная, реализовывать после Alpaca live)
- Support bounce (backtest repair запущен, ждём результатов)
- Elder parameters (сначала диагностика, потом параметры)

---

## Порядок выполнения

1. Задача 1 (оркестратор) — блокирует режимную логику всего бота
2. Задача 2 (FARTCOIN denylist) — защита от мусора
3. Задача 5 (Alpaca advisory) — быстрый win
4. Задача 3 (Elder диагностика) — понять проблему
5. Задача 4 (флэт стратегии) — расширить покрытие bear_chop
