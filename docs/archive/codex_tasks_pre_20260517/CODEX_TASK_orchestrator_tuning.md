# Codex Task: Orchestrator + Infrastructure Tuning

## Контекст

Аудит выявил три системных проблемы в основе бота:
1. Аллокатор пропускал шорты в бычьем рынке (ИСПРАВЛЕНО напрямую)
2. Детектор режима работал с слишком жёсткими параметрами (ЧАСТИЧНО ИСПРАВЛЕНО)
3. Backtest gate числится включённым но фактически отключён

---

## Уже исправлено напрямую (не нужно делать Codex)

### Исправление 1: breakdown sleeve в bull режимах
**Файл**: `configs/portfolio_allocator_policy.json`
- `bull_trend`: 0.35 → **0.0** ✓
- `bull_chop`: 0.60 → **0.0** ✓

Шорты через breakdown больше не могут открываться в бычьем рынке.

### Исправление 2: ER параметры оркестратора
**Файл**: `scripts/build_regime_state.py` строки 89-91:
- `ER_TREND_THRESH` дефолт: 0.35 → **0.28** ✓
- `ER_PERIOD` добавлен как новая переменная, дефолт **30** ✓ (было хардкод 20)
- Строка 339: `_efficiency_ratio(closes, 20)` → `_efficiency_ratio(closes, ER_PERIOD)` ✓

---

## Задача Codex: Применить новые параметры через env файл

### Файл для создания/обновления: `configs/regime_orchestrator_v2.env`

Создать новый файл с актуальными параметрами:
```bash
# Orchestrator parameters — v2 (tuned 2026-04-09)
# ER period lengthened: 20→30 bars (5 days on 4H) for less noise
# ER threshold lowered: 0.35→0.28 (crypto is choppier than equities)
ORCH_ER_TREND_THRESH=0.28
ORCH_ER_PERIOD=30
ORCH_MIN_HOLD_CYCLES=3
ORCH_BARS=120
ORCH_BULL_TREND_FLAT_ER_MAX=0.55

# Alerts — заполнить TG credentials если нет
TG_TOKEN=${TG_TOKEN:-}
TG_CHAT_ID=${TG_CHAT_ID:-}
```

Убедиться что этот файл подключается в cron запуске оркестратора:
```bash
# В crontab или запускающем скрипте должно быть:
source configs/regime_orchestrator_v2.env
python3 scripts/build_regime_state.py
```

Проверить текущий crontab:
```bash
crontab -l | grep build_regime_state
```

---

## Задача Codex: Подключить Backtest Gate

### Проблема
В `configs/strategy_profile_registry.json` у многих профилей стоит `"bt_require_history": true`,
но в `runtime/router/symbol_router_state.json` поле `backtest_path` пустое — gate не работает.

### Найти CSV с трейдами

```bash
# На сервере найти где хранятся сделки:
ls -la runtime/trades/ 2>/dev/null
ls -la logs/*.csv 2>/dev/null | head -10
find /root/bybot -name "*.csv" -newer runtime/ 2>/dev/null | head -20
```

### Подключить в router env

Если CSV найден (например `runtime/trades/live_trades.csv`):
```bash
# Добавить в configs/router_live.env или основной .env:
ROUTER_TRADES_CSV=runtime/trades/live_trades.csv
```

Если CSV пустой или не существует — временно отключить gate во всех профилях:

В `configs/strategy_profile_registry.json` найти все профили с `"bt_require_history": true`
и изменить на `false` (пока backtest gate не подключён к реальным данным).

```bash
python3 -c "
import json
with open('configs/strategy_profile_registry.json') as f:
    reg = json.load(f)
changed = 0
for p in reg.get('profiles', []):
    if p.get('bt_require_history'):
        p['bt_require_history'] = False
        changed += 1
print(f'Changed {changed} profiles')
with open('configs/strategy_profile_registry.json', 'w') as f:
    json.dump(reg, f, indent=2)
"
```

---

## Задача Codex: Проверить geometry pipeline

```bash
# На сервере:
ls -la runtime/geometry/ 2>/dev/null || echo "NO geometry dir"
wc -l runtime/geometry/geometry_state.json 2>/dev/null || echo "NO geometry state"
python3 -c "
import json
g = json.load(open('runtime/geometry/geometry_state.json'))
print(f'Symbols with geometry: {len(g)}')
if g:
    k = list(g.keys())[0]
    print(f'Sample {k}:', g[k])
" 2>/dev/null

# Проверить crontab:
crontab -l | grep geometry
```

Если geometry_state.json пустой или отсутствует в cron — добавить:
```cron
30 * * * * cd /root/bybot && python3 scripts/build_geometry_state.py >> logs/geometry.log 2>&1
```

---

## Задача Codex: Добавить поддержку нескольких монет в оркестраторе

### Текущее состояние (NOT URGENT — будущая работа)

Сейчас оркестратор смотрит только BTC 4H. Это значит если BTC в bull_trend,
но ETH и SOL в боковике — бот рискует по всем позициям с bull_trend весами.

### Предложение: добавить BTC+ETH weighted consensus

В `scripts/build_regime_state.py` в функции `_classify_regime()`:

```python
# Сейчас: только BTC
er = _efficiency_ratio(closes, ER_PERIOD)

# Улучшение (опционально): ETH consensus
ETH_WEIGHT = float(os.getenv("ORCH_ETH_WEIGHT", "0.3"))  # 30% ETH
if ETH_WEIGHT > 0:
    # Загрузить ETH 4H closes
    eth_candles = _fetch_klines("ETHUSDT", "240", FETCH_BARS + 60)
    if eth_candles and len(eth_candles) > ER_PERIOD + 5:
        eth_closes = [float(c[4]) for c in eth_candles]
        eth_er = _efficiency_ratio(eth_closes, ER_PERIOD)
        # Weighted ER
        er = er * (1 - ETH_WEIGHT) + eth_er * ETH_WEIGHT
```

Это НЕ СРОЧНО. Реализовать только если одиночный BTC-сигнал нестабилен после
тюнинга ER периода.

---

## Приоритет:

1. **Сейчас**: применить env файл `regime_orchestrator_v2.env` через cron (15 мин)
2. **Сейчас**: подключить backtest gate к реальному CSV или отключить флаг (30 мин)
3. **Потом**: проверить geometry pipeline (30 мин)
4. **Не срочно**: ETH consensus в оркестраторе (2-3 часа)

## Ожидаемый результат:

- Более стабильный детектор режима (меньше ложных переходов)
- Шорты больше не открываются в bull_trend/bull_chop
- Backtest gate либо работает либо честно отключён
- Geometry scoring либо работает либо отключён

## Статус исправлений в репозитории:
- `portfolio_allocator_policy.json` — ИСПРАВЛЕНО (breakdown 0.0/0.0 в bull) ✓
- `build_regime_state.py` — ИСПРАВЛЕНО (ER_PERIOD=30, thresh=0.28) ✓
- `regime_orchestrator_v2.env` — НУЖНО СОЗДАТЬ
- backtest gate — НУЖНО ПОЧИНИТЬ
- geometry pipeline — НУЖНО ПРОВЕРИТЬ
