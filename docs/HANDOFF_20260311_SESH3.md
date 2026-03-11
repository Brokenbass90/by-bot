# HANDOFF — Сессия 3 — 2026-03-11
# Документ для следующего чата. Читать первым делом.

---

## 1. КАК ЗАДЕПЛОИТЬ (ПРЯМО СЕЙЧАС)

### Шаг 1 — Push в GitHub
```bash
cd /path/to/bybit-bot-clean-v28
git push origin codex/dynamic-symbol-filters
```
Если нужен PR → merge в main. Если работаешь напрямую в main — сначала сделай merge или cherry-pick коммита `145c2fd`.

### Шаг 2 — Залить на сервер
```bash
# На сервере:
cd /path/to/bybit-bot-clean-v28
git pull origin main   # или codex/dynamic-symbol-filters если не мержили
```

### Шаг 3 — Создать runtime файлы на сервере (только если их там нет)
```bash
mkdir -p runtime/news_filter
# Скопировать или они уже есть после git pull:
# runtime/news_filter/events.csv    ← 15 событий FOMC/NFP/CPI до июль 2026
# runtime/news_filter/policy.json   ← политика блокировок по стратегиям
```

### Шаг 4 — Проверить запуск
```bash
python3 -c "from smart_pump_reversal_bot import *" 2>&1 | head -20
# Не должно быть ошибок
```

### Шаг 5 — Перезапустить бот
```bash
# Найти PID текущего бота:
cat runtime/live_breakout_allowv2.pid
# Убить и перезапустить:
kill <PID>
bash scripts/run_breakout_allowv2_live.sh &
```

### Что изменится после деплоя:
1. **News filter активен** — за 20 мин до/30 мин после FOMC/NFP/CPI бот пропускает breakout входы
2. **Impulse histogram работает** — в `/diag` появятся `breakout_ns_impulse_q1..q4`
3. **TradeState** — property алиасы, `add_fill()`, `realized_pnl_from_fills` (обратно совместимо)
4. **strategies/** стал чистым — только 4 активных файла

---

## 2. СТАТУС ВСЕХ РУКАВОВ

### 🟢 КРИПТO (Bybit) — LIVE
**Стратегия:** InPlayBreakoutStrategy (sr_inplay_retest.py)
**Параметры:** impulse_atr_mult=1.0, tf_break=240m, tf_entry=5m
**Проблема:** 82.44% сигналов блокируются как `impulse_weak`

**Что делать после деплоя:**
1. Подождать 1-2 недели, смотреть `/diag` → `breakout_ns_impulse_q1..q4`
2. Если `q4 > q1+q2` (почти проходит) → поставить `BREAKOUT_IMPULSE_ATR_MULT=0.75` в .env
3. Если `q1+q2 > q4` (глубокий flat) → рынок не торгуется, ждать или запустить adaptive_range_short

**Следующие улучшения крипты (в порядке приоритета):**
- [P1] Runner exits: `BREAKOUT_EXIT_MODE=runner` — нужен бэктест (1-2 дня работы)
- [P2] Режимный фильтр: `BREAKOUT_REGIME_MODE=ema` — бэктест на 6-12 мес
- [P3] Сессионный фильтр: US+Europe только (13:00-22:00 UTC)
- [P4] Funding carry — отдельный рукав (см. ниже)
- [P5] Оптимизация символьной вселенной — топ-20 по OI

**Бэктест нужен для:**
- Runner exits vs fixed TP (какое улучшение expectancy?)
- impulse_atr_mult=0.75 vs 1.0 (сколько лишних сигналов + качество?)
- Режимный фильтр EMA (сколько плохих входов убирает?)
- Bэктест доступен через `backtest/run_portfolio.py`

---

### 🟡 CRYPTO — Funding Rate Carry (НЕ ЗАПУЩЕН)
**Статус:** Данные собираются, план генерируется, исполнения НЕТ
**Файлы:**
- `scripts/funding_carry_live_plan.py` — генерирует план (CSV/JSON с символами и их funding)
- `scripts/run_funding_carry_live_plan.sh` — скрипт запуска
- `runtime/funding_carry/latest_plan.json` — последний план
- `runtime/funding_carry/live_scan_20260310_*.json` — живые данные

**Состояние рынка сейчас (2026-03-10):**
- 543/548 символов имеют ненулевой funding
- Большинство: ОТРИЦАТЕЛЬНЫЙ funding (медвежий рынок)
- Топ negatives: PIXELUSDT -1375% APR, LYNUSDT -895% APR
- При отрицательном funding: ЛОНГ perp получает выплату

**Стратегия при НЕГАТИВНОМ funding (медвежий рынок):**
```
position = LONG perp (получаешь funding от шортистов)
hedge    = SHORT spot (нейтральная delta)
# Если нет возможности шортить spot → только LONG perp с tight stop
```

**Что нужно дописать:**
1. `scripts/funding_carry_executor.py` — исполнение позиций через Bybit API
2. Entry logic: открыть когда |funding_8h| > 0.05% (= >5.4% APR)
3. Exit logic: закрыть когда funding нормализуется ниже 0.02%
4. Risk: максимум 10-15% капитала на carry позиции
5. Telegram уведомления об открытии/закрытии/выплатах
6. ВАЖНО: carry не работает если символ неликвидный (OI < $5M)

**Оценка доходности:** при $100 капитале и 10% аллокации ($10) на символе с 100% APR = ~$10/год. Смысл появляется при капитале >$500.

---

### 🔴 FOREX — НЕТ РАБОЧИХ СТРАТЕГИЙ
**Статус:** Нет API ключей (cTrader ожидание), ВСЕ бэктесты отрицательные

**Результаты последних бэктестов:**
- AUDJPY breakout_continuation: net=-189 пипов, winrate=34%
- AUDJPY liquidity_sweep_bounce: net=-416 пипов, return=-40.6%
- Стресс-тест ещё хуже

**Почему не работает:**
- Forex движется медленнее крипты — нужны другие параметры
- breakout_continuation без regime filter входит против тренда
- liquidity_sweep_bounce: avg_win(5.4pip) < avg_loss(6.2pip) = отрицательный expectancy

**Что делать дальше:**
1. Написать новые Forex стратегии с нуля (задача следующей сессии)
2. Фокус на: EURUSD, GBPUSD, USDJPY, XAUUSD
3. Обязательно: position filter (только по тренду старшего TF), news filter (уже есть!)
4. Данные: скачать через `yfinance` или MetaTrader 5 Python API
5. Параметры под Forex: pip_size разные, spread выше чем в крипте, нет круглосуточной торговли

**Альтернативный API (не cTrader):**
- **OANDA**: python-oanda-api, не требует одобрения, paper trading бесплатно, мин. депозит $1
- **Interactive Brokers**: мощнее, сложнее, мин $100, paper trading через TWS
- **OANDA выгоднее** для старта — простой REST API, много документации
- Рекомендация: подключить OANDA сейчас параллельно с ожиданием cTrader

---

### 🔴 EQUITIES (Alpaca) — ОЖИДАНИЕ КЛЮЧЕЙ
**Статус:** Waiting for Alpaca live approval. PAPER TRADING доступен сразу.

**Что готово:**
- `scripts/equities_alpaca_paper_bridge.py` (304 строки) — почти готов к запуску
- Умеет: загрузить picks.csv → открыть позиции → отчёт
- Есть dry-run режим (`ALPACA_SEND_ORDERS=False` по умолчанию)

**Что нужно:**
1. Зарегистрировать бесплатный аккаунт Alpaca: https://app.alpaca.markets/signup
2. Создать Paper Trading API ключи (бесплатно, сразу)
3. Добавить в .env:
   ```
   ALPACA_API_KEY_ID=ваш_ключ
   ALPACA_API_SECRET_KEY=ваш_секрет
   ALPACA_BASE_URL=https://paper-api.alpaca.markets
   ALPACA_SEND_ORDERS=True
   ALPACA_MAX_POSITIONS=5
   ALPACA_TARGET_ALLOC_PCT=0.20
   ```
4. Запустить backtest чтобы получить `picks.csv`: `scripts/equities_monthly_research_sim.py`
5. Запустить bridge: `python3 scripts/equities_alpaca_paper_bridge.py`

**Что нужно дописать:**
1. Telegram уведомления (вход/выход/P&L) — ~50 строк
2. Earnings filter (аналог news_filter но для отчётностей) — ~100 строк
3. Monthly scheduler — автоматический запуск 1-го числа каждого месяца

**Диверсификация по символам:**
Текущий лучший бэктест: +79.67% на ОДНОМ символе. Один символ = полный риск на одну компанию (earnings miss → -20% за ночь). Нужно 5-10 символов из разных секторов:
- Tech: NVDA, MSFT, AAPL
- Finance: JPM, GS
- Consumer: AMZN, COST
- Healthcare: UNH
- Industrials: CAT
Бэктест на каждом → выбрать 5 с лучшим Sharpe и низкой корреляцией.

---

## 3. ВСЕ ИДЕИ (записаны, будут реализованы позже)

### 💡 AI-Доктор (реализовать когда будет Pro токен)
- Ежедневный скрипт: собирает `/diag` + trade stats → отправляет Claude API → ответ в Telegram
- Человек смотрит → решает применять ли → никакого автоприменения
- Стоимость: ~$0.10/день (API Claude) при кратком промпте
- Файл: `scripts/ai_daily_review.py` (создать)

### 💡 Параметрическая self-optimization
- Еженедельный walk-forward sweep ±20% основных параметров
- Лучшая комбинация → предложение в Telegram с auto-reject если нет подтверждения 24h
- Безопасно: только предлагает, не применяет
- Файл: `scripts/weekly_param_sweep.py` (создать)

### 💡 ML Entry Filter (долгосрочно, нужны 50+ трейдов)
- После накопления 50+ трейдов с полными метаданными
- XGBoost/LightGBM: features = [impulse_ratio, ATR, session, volume_ratio, regime]
- Target = profitability (бинарный: profit/loss)
- Обучение раз в месяц, не онлайн — без overfit
- Файл: `bot/ml_entry_filter.py` (создать позже)

### 💡 RL Trading Agent (очень долгосрочно, нужны миллионы трейдов)
- Теоретически красиво, при 0-5 трейдов в месяц нереализуемо
- Revisit при масштабировании на HFT или multi-exchange
- Не делать в ближайший год

### 💡 Market Sentiment Layer
- Fear & Greed Index (бесплатный API: alternative.me/crypto/fear-and-greed-index/)
- On-chain: Exchange inflows/outflows (Glassnode бесплатный tier)
- Правило: не входить в лонги при F&G > 80, не в шорты при F&G < 20
- Файл: `bot/sentiment_filter.py` (создать)
- Стоимость: бесплатно

### 💡 DeFi Yield Monitor
- Мониторинг APY на Aave/Compound для USDT/USDC
- Уведомление в Telegram когда появляется >10% APY
- Не автоматическое перемещение средств — только alert
- Файл: `scripts/defi_yield_monitor.py` (создать)

### 💡 Statistical Arbitrage (крипто)
- Коинтегрированные пары: BTC/ETH spread
- Когда spread > 2σ → шорт дорогого, лонг дешёвого
- Требует одновременно двух биржевых подключений
- Реализовывать при капитале >$1000

### 💡 Volatility-Adjusted Position Sizing (улучшение текущего)
- Сейчас: фиксированный риск 0.5%
- Предлагается: при ATR выше среднего 30d → уменьшить риск до 0.35%
- При ATR ниже среднего (тихий рынок) → увеличить до 0.7%
- Файл: `bot/risk/adaptive_sizer.py` (создать)

---

## 4. ПРИОРИТЕТНЫЙ ПЛАН СЛЕДУЮЩИХ СЕССИЙ

### Сессия 4 (следующая)
1. **ЗАДЕПЛОИТЬ** текущие изменения (пользователь pushes, бот перезапускается)
2. **Alpaca**: зарегистрировать, добавить ключи в .env, запустить paper bridge
3. **Alpaca**: добавить Telegram уведомления (50 строк) + earnings filter (100 строк)

### Сессия 5
1. **Форекс**: написать 3 новые стратегии с нуля (trend-following + regime filter)
2. **Форекс**: бэктест на EURUSD, GBPUSD, XAUUSD за 3+ года
3. **OANDA**: подключить как альтернативу cTrader (parallel testing)

### Сессия 6
1. **Крипто runner**: бэктест BREAKOUT_EXIT_MODE=runner vs fixed TP
2. **Крипто regime**: бэктест BREAKOUT_REGIME_MODE=ema
3. **Funding carry**: написать executor, протестировать на paper

### Сессия 7+
1. **ML Entry Filter** (если накопилось 50+ трейдов)
2. **AI-Доктор** скрипт (если куплен Pro план)
3. **Sentiment layer**: Fear&Greed API

---

## 5. ТЕХНИЧЕСКИЙ ДОЛГ (записан, не горит)

1. `smart_pump_reversal_bot.py`: `load_dotenv()` вызывается на строке ~640 ПОСЛЕ чтения env переменных (строки 284-435) — pre-existing bug, требует аккуратного рефакторинга
2. `smart_pump_reversal_bot.py`: заполнять `fills` в `TradeState` при entry/exit confirm — примерные места: строки ~2672, ~3606, ~3266
3. `bot/` Phase 2: выделить BybitClient (~400 строк) в `bot/exchange/client.py`
4. `bot/` Phase 3: выделить Telegram функции в `bot/telegram/`, DB в `bot/db.py`
5. Обновлять `runtime/news_filter/events.csv` каждый квартал вручную

---

## 6. КОМАНДЫ ДЛЯ БЫСТРОЙ ДИАГНОСТИКИ

```bash
# Посмотреть живую диагностику
python3 - <<'EOF'
from bot.diagnostics import _runtime_diag_snapshot
print(_runtime_diag_snapshot())
EOF

# Запустить smoke тесты
python3 tests/smoke_test.py

# Проверить состояние git
git log --oneline -5

# Сгенерировать новый funding carry план
python3 scripts/funding_carry_live_plan.py --dry-run

# Посмотреть последний funding carry план
python3 -c "
import json
with open('runtime/funding_carry/latest_plan.json') as f:
    print(json.dumps(json.load(f), indent=2))
"
```

---

## 7. ENV ПЕРЕМЕННЫЕ К ДОБАВЛЕНИЮ

```bash
# .env изменения после деплоя:

# News filter (уже встроен, но можно настроить)
NEWS_FILTER_ENABLE=1              # 1=включён (по умолчанию)
NEWS_EVENTS_PATH=runtime/news_filter/events.csv
NEWS_POLICY_PATH=runtime/news_filter/policy.json

# Impulse threshold (добавить ПОСЛЕ анализа q1-q4 гистограммы)
# Если q4 доминирует:
# BREAKOUT_IMPULSE_ATR_MULT=0.75

# Runner exits (добавить после бэктеста)
# BREAKOUT_EXIT_MODE=runner
# BREAKOUT_TRAIL_ATR_MULT=2.2
# BREAKOUT_PARTIAL_RS=1.0,2.0,3.5
# BREAKOUT_PARTIAL_FRACS=0.50,0.25,0.15

# Alpaca paper trading
ALPACA_API_KEY_ID=...
ALPACA_API_SECRET_KEY=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_SEND_ORDERS=True
ALPACA_MAX_POSITIONS=5
```

---

_Дата: 2026-03-11 | Автор: Claude Sonnet 4.6_
_Следующий чат: читай этот файл первым делом_
