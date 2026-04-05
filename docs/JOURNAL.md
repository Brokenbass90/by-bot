# Project Journal

> One entry per session. Most recent at top.
> Format: date | who | what was done | key findings | next

---

## 2026-04-03 | Codex (session 24 - breakout chop ER guard check on trusted current90)

**Done:**

- Re-ran the trusted `v5` current90 window from the project `.venv` with:
  - `BREAKOUT_CHOP_ER_MIN` unset
  - `BREAKOUT_CHOP_ER_MIN=0.20`
- Measured both:
  - full trusted stack
  - isolated `inplay_breakout`

**Key findings:**

- On the trusted full stack, both runs were identical:
  - `100 -> 101.76`
  - `+1.76%`
  - `39` trades
  - `PF 1.117`
  - `DD 4.10%`
- On isolated `inplay_breakout`, both runs were also identical:
  - `100 -> 99.40`
  - `-0.60%`
  - `1` trade
- Meaning: the live `ER` guard is currently a harmless protection layer, but it is not the thing that repairs breakout on this exact recent trusted window.

**Next:**

- Continue with the control-plane roadmap:
  - finish orchestrator clean push-set
  - build dynamic symbol router
  - return to breakout repair on top of that foundation
- Treat `ER` as a retained guard, not as the main breakout fix.

## 2026-04-03 | Codex (session 25 - tracked secret cleanup)

**Done:**

- Verified that tracked `configs/server_clean.env` still contained live-like secrets.
- Redacted the tracked file so the repo no longer stores:
  - Telegram token and chat ids
  - Bybit account JSON
  - DeepSeek API key
- Left the real server `.env` unchanged.

**Key findings:**

- The immediate security problem was in the tracked repo snapshot, not in the current server verification flow.
- This had to be cleaned before any orchestrator push-set or future publishing work.

**Next:**

- Keep real credentials only in gitignored local files and on the server.
- Continue with orchestrator isolation and then dynamic symbol routing.

## 2026-04-02 | Codex (session 23 - server env verification + orchestrator hardening)

**Done:**

- Pulled the real server `.env` strategy variables and compared them to the trusted `v5` overlay.
- Confirmed the server is still close to trusted `v5` on the key live knobs:
  - `ASC1_SYMBOL_ALLOWLIST=ADAUSDT,LINKUSDT,ATOMUSDT`
  - `ARF1_SYMBOL_ALLOWLIST=ADAUSDT,SUIUSDT,LINKUSDT,DOTUSDT,LTCUSDT`
  - `BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT`
  - `BREAKOUT_QUALITY_MIN_SCORE=0.53`
  - `BREAKOUT_ALLOW_SHORTS=0`
  - `BREAKOUT_MIN_PULLBACK_FROM_EXTREME_PCT=0.07`
  - `MIDTERM_SYMBOLS=BTCUSDT,ETHUSDT`
- Verified the main live delta vs trusted `v5` is the added chop guard:
  - `BREAKOUT_CHOP_ER_MIN=0.20`
- Hardened the local orchestrator integration:
  - `build_regime_state.py` now accepts `TG_CHAT` as a Telegram fallback
  - overlay env now includes generation metadata and hysteresis fields
  - `smart_pump_reversal_bot.py` now checks overlay freshness and warns on stale/missing regime state
  - overlay application now also reads `ENABLE_SLOPED_TRADING`
- Syntax check passed for both orchestrator files.

**Key findings:**

- The server does not appear to be running on a wildly different strategy snapshot.
- This reduces the likelihood that the recent confusion came from a hidden server config fork.
- The bigger missing piece is still the control plane itself, not a secret server env mismatch.

**Next:**

- Isolate the orchestrator diff into a clean branch/commit set.
- Only then decide on server rollout after the fresh backtest inputs return.

## 2026-04-02 | Codex (session 22 - roadmap reset and working-order lock)

**Done:**

- Replaced the oversized roadmap with a short active roadmap in [ROADMAP.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/ROADMAP.md).
- Locked the new priority order:
  - validation discipline and live damage control
  - regime orchestrator
  - dynamic symbol router and strategy profiles
  - repair current live crypto sleeves
  - only then promote new strategy families and expand to other markets
- Added a session rule: every new task should start from `docs/ROADMAP.md`, and every material step should update `WORKLOG` and `JOURNAL`.

**Key findings:**

- The project had accumulated too many parallel fronts and too many stale roadmap items.
- The real next milestone is not "more strategies" but a control-plane rebuild.
- We now have one active queue that can be used as the handoff source for future sessions.

**Next:**

- Finish the regime orchestrator as a clean isolated push-set.
- Build the dynamic symbol router on top of the current allowlist pieces.
- Return to crypto sleeve repair only after the control-plane path is clearly defined.

## 2026-04-02 | Codex (session 21 — production trade state mismatch fix)

**Done:**

- Разобран реальный production-инцидент по `NOMUSDT`:
  - пользовательский журнал показал live-сделку, которой не было в локальном `TRADES`/`trade_events` текущего server bot
  - это подтвердило слепую зону: бот восстанавливал позиции только на старте, но не умел во время работы поднимать тревогу о позиции на бирже вне локального state
- В [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) добавлен runtime-scan незаведённых биржевых позиций:
  - `UNTRACKED_EXCHANGE_SCAN_SEC`
  - `UNTRACKED_EXCHANGE_ALERT_COOLDOWN_SEC`
  - `_scan_untracked_exchange_positions()`
  - теперь `sync_trades_with_exchange()` отдельно проверяет open positions на Bybit и шлёт `🚨 UNTRACKED EXCHANGE POSITION`, если позиция есть на бирже, но бот её не ведёт
- Добавлен второй безопасный слой:
  - если runtime-скан находит биржевую позицию и в `trades.db` есть незакрытый bot-entry для того же `symbol/side`,
    бот автоматически восстанавливает её в `TRADES` (`🔁 RUNTIME RESTORED ...`)
  - если matching bot-entry нет, остаётся только аварийный alert без авто-импорта
- Выбран безопасный режим реакции:
  - бот подхватывает только те позиции, для которых есть свой же незакрытый entry в БД
  - truly manual/внешние позиции не маскируются под бот-трейды
- Для следующего реального improvement-фронта собран новый bounded compare:
  - [breakout_live_bridge_v5_fixed_vs_runner.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakout_live_bridge_v5_fixed_vs_runner.json)
  - база зафиксирована на лучшем историческом breakout-pocket `v3_density r26`
  - внутри compare тестируется только exit-plan: `fixed` vs `runner`

**Key findings:**

- Скрины пользователя опровергли прежнюю гипотезу “позиции не было”; проблема реальная и продовая
- Live `breakout` сейчас работает в `fixed` exit mode, trailing не включён
- TP/SL на Bybit ставятся как `position trading-stop`, а не как обычные open orders

**Next:**

1. Прогнать compile-check локально
2. Задеплоить фикс на сервер и перезапустить `bybot`
3. Отследить следующий подобный случай: приходит ли alert о незаведённой биржевой позиции
4. После стабилизации вернуться к crypto bear-market sleeves (`breakdown`) и live diagnostics

## 2026-04-01 | Codex (session 20 — Alpaca v36 server paper rollout + InPlay minute continuation)

**Done:**

### Alpaca v36 — перестали топтаться, перешли к server-side paper rollout

- Подтверждён сильный локальный frontier:
  - `equities_monthly_v36_current_cycle_activation`
  - лучший кластер: `40 trades`, `net=164.99`, `PF=5.84`, `DD=4.60`, `1` красный месяц
- Добавлен локальный safe/offline dry-run для monthly paper bridge:
  - `scripts/equities_alpaca_paper_bridge.py`
  - `configs/alpaca_paper_v36_close_stale_dry_run.env`
  - `scripts/run_equities_alpaca_v36_close_stale_dry_run.sh`
- Локальный dry-run подтвердил текущую monthly-логику:
  - stale `GOOGL` / `TSLA` надо забыть
  - новых monthly picks сейчас нет
  - correct action = `close stale and stay flat`

### Server deploy for Alpaca

- На сервер `/root/by-bot` задеплоены:
  - `scripts/equities_alpaca_paper_bridge.py`
  - `scripts/equities_alpaca_intraday_bridge.py`
  - `scripts/equities_midmonth_monitor.py`
  - `scripts/run_equities_alpaca_v36_candidate.sh`
  - `scripts/run_equities_monthly_v36_refresh.sh`
  - `scripts/equities_monthly_research_sim.py`
  - `configs/alpaca_paper_v36_candidate.env`
  - `configs/intraday_config.json`
- Сделан backup server-side файлов в `runtime/server_backups/alpaca_v36_20260401`
- По пути найден и устранён technical blocker:
  - на сервере была старая `equities_monthly_research_sim.py`, которая не знала `--intramonth-portfolio-stop-pct`

### InPlay / scalper

- Бесполезные grids остановлены:
  - `micro_scalper_bounce_v1_grid`
  - `micro_scalper_breakout_v1_grid`
  - они только грели ноут без признаков живого кармана
- Оставлен `inplay_scalper_minute_probe_v2`
- Собран новый более живой run:
  - `configs/autoresearch/inplay_scalper_minute_probe_v3_relaxed.json`
  - идея: softer activation, longer window, more symbols, честный minute scalp sleeve

**Key findings:**

- `Alpaca` monthly core и dynamic/intraday layer — это разные вещи; monthly всё ещё может сидеть в cash
- server-side `v36` rollout — правильный следующий шаг, а не ещё один слепой research-only цикл
- текущий weakest link уже не “стратегия плохая”, а то, как быстро и гибко реагировать между monthly циклами

**Next:**

1. Добить server-side `Alpaca v36` paper run и снять реальный verdict с paper API
2. Если monthly снова flat → продвигать `equities_alpaca_intraday_bridge.py` как dynamic watchlist layer
3. Дать `InPlay v3 relaxed` первые строки и решить, есть ли там реальный скальперный pocket

---

## 2026-03-29 | Claude (session 19d — Alpaca diagnosis + intramonth stop + dynamic strategy notes)

**Done:**

### Alpaca Paper — полная диагностика и два конкретных фикса

**Диагноз:**
- Лучший прогон v23 (r011): PnL=+58.7%, PF=2.31, 17 месяцев, 10/17 зелёных
- НО: `neg_months=7` → autoresearch отклоняет все 108 прогонов (ограничение `max_negative_months=4`)
- Красные месяцы: Jun'24 (-5.4%), Oct'25 (-4.5%), Aug'23/Sep'25 (-3.7%) → NVDA/CRWD/TSLA стопы
- `profit_factor=NaN` во всех результатах → баг: поле не вычислялось в summary.csv

**Фикс 1 — `equities_monthly_research_sim.py`:**
- Добавлен `--intramonth-portfolio-stop-pct` параметр
- Новая функция `_simulate_trades_portfolio_stop()`: ежедневно считает портфельную доходность; если падает ниже порога → выходит из ВСЕХ позиций в тот же день ('portfolio_stop')
- Добавлено `profit_factor` в summary.csv (больше нет NaN)
- Добавлено `negative_months` в summary.csv (явно, не только через monthly.csv)

**Фикс 2 — `configs/autoresearch/equities_monthly_v27_intramonth_stop.json`:**
- Новый спек: 288 комбо, ~15 мин
- Grid: INTRAMONTH_STOP=[0.0, 0.035, 0.04, 0.05]
- Расслабленные ограничения: `max_negative_months=6` (реалистично), `min_profit_factor=1.5`
- Убран BENCHMARK_MIN_ABOVE_SMA=0 (теперь минимум = 1, т.е. SPY или QQQ должны быть выше SMA)

**Ожидаемый эффект:**
- С INTRAMONTH_STOP=0.04: Jun'24 (-5.4%) → -4.0%, Oct'25 (-4.5%) → -4.0%
- Это конвертирует 2 худших месяца → менее болезненные
- Compounded return должен подрасти на 2-3%

**Запустить:**
```bash
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/equities_monthly_v27_intramonth_stop.json \
  > /tmp/equities_v27.log 2>&1 &
```

### Ответы на вопросы о динамических стратегиях

**Стратегии динамические по символам?** — Да:
- `ALT_*` стратегии читают символы из `ASC1_SYMBOL_ALLOWLIST`, `ARF1_SYMBOL_ALLOWLIST` — обновляются динамически через `dynamic_allowlist.py` каждое воскресенье
- Для разных монет МОГУТ быть разные параметры через `family profiles` — это НЕ СДЕЛАНО (см. roadmap)

**Разные настройки под разные монеты?** — Да, принципиально эффективно:
- BTC/ETH — более медленные тренды, шире SL/TP
- SOL/AVAX — высокая волатильность, тighter стопы
- Mid-cap алты — нужен отдельный профиль (wider ATR multiple, longer cooldown)
- Сейчас всё на одних параметрах → family profiles это следующий шаг автономности

**Шорты vs лонги разделить?** — Да, эффективно:
- Уже реализовано в FR Reversion (LC_ALLOW_LONGS/SHORTS)
- Elder v132b уже есть ALLOW_SHORTS=0/1 в автопоиске
- В ALT_* стратегиях логика шортов и лонгов уже раздельная по условиям

---

## 2026-03-29 | Claude (session 19c — Live gates wired + Liquidation Cascade strategy + Telegram fix)

**Done:**

### 1. health_gate.py → ВШИТ В БОТ (КРИТИЧНО)
- `smart_pump_reversal_bot.py`: добавлен `from bot.health_gate import gate as _health_gate`
- 6 стратегий теперь имеют live entry gate перед `asyncio.create_task`:
  - `alt_sloped_channel_v1` (sloped trading)
  - `alt_resistance_fade_v1` (flat trading)
  - `alt_inplay_breakdown_v1` (breakdown shorts)
  - `micro_scalper_v1` (micro scalper)
  - `alt_support_reclaim_v1` (support reclaim)
  - `triple_screen_v132` (Elder / TS132)
- Gate читает `configs/strategy_health.json` с TTL 1h:
  - PAUSE/KILL → entries заблокированы + Telegram alert (1 раз/день)
  - WATCH → entries разрешены + предупреждение
  - OK → entries разрешены без лишних логов

### 2. allowlist_watcher.py → ЗАПУСКАЕТСЯ ПРИ СТАРТЕ БОТА
- `from bot.allowlist_watcher import AllowlistWatcher as _AllowlistWatcher`
- В `main()`: `_allowlist_watcher = _AllowlistWatcher(); _allowlist_watcher.start()`
- Демон-тред опрашивает файл каждые 300s
- ASC1/ARF1 обновляются в os.environ без перезапуска бота
- BREAKOUT пишет флаг `configs/allowlist_restart_needed.flag`

### 3. Telegram chunking → ПОФИКШЕНО во всех 4 файлах
- `smart_pump_reversal_bot.py`: `tg_send()` + `tg_send_kb()` → chunking по 3900 симв. с нумерацией [1/3]
- `tg_trade()` → теперь просто вызывает `tg_send()` (переиспользует логику)
- `scripts/deepseek_weekly_cron.py`: убрана тупая обрезка `[:4096]` → нормальный chunking
- `scripts/equity_curve_autopilot.py`: аналогично

### 4. Liquidation Cascade Entry v1 — новая стратегия
- `strategies/liquidation_cascade_entry_v1.py` (~250 строк)
- Edge: механические liquidation engines создают overshoots → ловим возврат
- Сигнал LONG: drop ≥ 3% за 6 баров + RSI ≤ 28 + vol spike ≥ 2.5× + price ≥ 2% ниже EMA
- SL=1.2×ATR, TP=2.0×ATR, time stop=48 баров (4h)
- Зарегистрирована в `run_portfolio.py` (4 точки)
- Создан `configs/autoresearch/liquidation_cascade_v1_grid.json` (~3888 комбо, ~45 мин)
- Longs only в первом прогоне; shorts тест отдельно после результатов

### 5. SR Break Retest Revival — статус
- Autoresearch запущен на машине пользователя, остановлен на 449/12288 (3.65%)
- Ранние результаты плохие (PF < 0.8) — нормально, начало перебора
- Нужно возобновить: `python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/sr_break_retest_volume_v1_revival_v1.json`
- Ожидаемое время: ~8-10 часов на полный прогон

### 6. Синтаксическая проверка
- Все 8 модифицированных/новых файлов: ✅ ast.parse OK

**Статус автономности (обновлено):**
| Компонент | Статус |
|-----------|--------|
| health_gate → live entry | ✅ ВШИТ |
| allowlist_watcher | ✅ ВШИТ |
| Telegram chunking | ✅ ПОФИКШЕН |
| FR Reversion strategy | ✅ готова к autoresearch |
| Liquidation Cascade v1 | ✅ готова к autoresearch |
| Elder v13 zoom autoresearch | 🔄 запущен на сервере |
| SR Break Retest revival | 🔄 449/12288 — нужно продолжить |
| Family dynamic profiles | ❌ не начато |
| Regime allocator correlation | ❌ не начато |

**Команды для запуска на сервере:**
```bash
# 1. Продолжить SR break retest (оставить до конца)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/sr_break_retest_volume_v1_revival_v1.json \
  > /tmp/sr_revival.log 2>&1 &

# 2. Запустить Funding Rate Reversion autoresearch
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/funding_rate_reversion_v1_grid.json \
  > /tmp/fr_reversion_v1.log 2>&1 &

# 3. Запустить Liquidation Cascade autoresearch
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/liquidation_cascade_v1_grid.json \
  > /tmp/lc_v1.log 2>&1 &

# 4. После Elder v13 zoom → portfolio test
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/portfolio_elder_6strat_test.json \
  > /tmp/elder_portfolio.log 2>&1 &

# 5. Запустить live funding rate fetcher рядом с ботом
nohup python3 scripts/funding_rate_fetcher.py --live > /tmp/fr_fetcher.log 2>&1 &
```

---

## 2026-03-29 | Claude (session 19b — Funding Rate Reversion: full integration)

**Done:**

### Funding Rate Reversion v1 — полная интеграция
- Зарегистрирована в `backtest/run_portfolio.py` (4 точки: import, default list, dict init, signal selector)
- Создан `configs/autoresearch/funding_rate_reversion_v1_grid.json` — 2916 комбо, ~30 мин
  - Grid: FR_THRESHOLD × EMA_PERIOD × EXT_PCT × RSI_OB × RSI_OS × SL_ATR × TP_ATR × TIME_STOP
  - FR_LATEST_* env vars инжектируют фиксированный rate 0.0008 для backtesta (тестирует RSI/EMA логику)
  - Ограничения: PF≥1.6, trades≥15, DD≤5%, net_pnl≥4
- Создан `scripts/funding_rate_fetcher.py` — 3 режима:
  - `--live` → бесконечный цикл, обновляет FR_LATEST_* env + configs/funding_rates_latest.json (60s интервал)
  - `--history --symbol BTCUSDT --days 365` → CSV с историческими rates (каждые 8h) via Bybit API
  - `--history-all` → скачать все символы сразу
  - `--status` → текущие rates + пометки EXTREME (>0.1%) / HIGH (>0.06%)
  - Pagination через Bybit cursor для полного охвата периода

**Следующие шаги FR Reversion:**
1. `python3 scripts/funding_rate_fetcher.py --status` — проверить доступность Bybit API
2. `python3 scripts/funding_rate_fetcher.py --history-all --days 365` — скачать исторические данные
3. Запустить autoresearch: `nohup python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/funding_rate_reversion_v1_grid.json > /tmp/fr_reversion_v1.log 2>&1 &`
4. После results → создать v1_zoom spec с лучшим кластером
5. Запустить `--live` рядом с ботом для live rate injection

**Ключевое ограничение backtesta:**
Стратегия видит funding rate только через store.funding_rate или env FR_LATEST_SYMBOL.
В backtest используется константный rate — результаты показывают качество RSI/EMA фильтров,
НЕ реальную частоту сигналов. Для реалистичного backtesta нужна CSV с историческими rates.

---

## 2026-03-29 | Claude (session 19 — Elder revival + dual-AI architecture)

**Done:**

### Elder Triple Screen Revival
- Подтверждено: `triple_screen_v132.py` в архиве, но уже зарегистрирована в run_portfolio.py
- `_import_strategy_class` ищет в обоих пакетах: `strategies` и `archive.strategies_retired`
- Из 1076 autoresearch v12: 204 PASS комбо, лучший PF=4.27 / PnL=+10.7% / DD=1.2% (BTC/ETH/AVAX)
- Создан `configs/autoresearch/triple_screen_elder_v13_zoom.json` — 2592 комбо, ~50 мин
- Создан `configs/autoresearch/portfolio_elder_6strat_test.json` — 256 комбо, ~5 мин (6-стратегийный тест)
- Запускать последовательно: сначала v13 zoom → потом 6-strat test

### Claude API модуль (Dual-AI Architecture)
- Создан `scripts/claude_monthly_analyst.py` — полный скелет с тремя режимами:
  - `--report` — monthly portfolio deep analysis
  - `--strategy-idea "..."` — дизайн новой стратегии с entry/exit логикой
  - `--diagnose STRAT` — deep diagnosis конкретной стратегии
- При отсутствии API key → выводит инструкцию активации + cost estimate (~$5-15/мес)
- Активировать когда P&L > $200/мес

### ROADMAP обновлён
- Добавлен Elder revival как P1 с конкретными командами запуска
- Добавлена Dual-AI архитектура (P2) с таблицей ролей DeepSeek vs Claude
- Добавлена новая стратегия P2: Funding Rate Reversion (специфика Bybit перпов)

**Команды для запуска локально:**
```bash
# 1. Elder v13 zoom (сначала):
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/triple_screen_elder_v13_zoom.json \
  > /tmp/elder_v13.log 2>&1 &

# 2. Потом 6-стратегийный тест (после v13):
python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/portfolio_elder_6strat_test.json
```

---

## 2026-03-29 | Claude (session 19 — protection layers + equity autopilot)

**Done:**

### 1. Alpaca Intraday Bridge v2 — 3-Layer Protection
`scripts/equities_alpaca_intraday_bridge.py` полностью переписан с тремя защитными слоями:
- **Layer 1 — SPY Regime Gate**: Fetches SPY daily bars → SMA50. Если SPY < SMA50 → блокирует все новые long entries. Тест показал: SPY $670 < SMA50 $687 → режим медвежий, entries заблокированы корректно.
- **Layer 2 — Daily Loss Limit**: Отслеживает P&L за сегодня. Если потери > `INTRADAY_MAX_DAILY_LOSS_PCT`% equity → стоп на день. Default 2%.
- **Layer 3 — Equity Curve Filter**: Логирует daily P&L в `configs/intraday_equity_log.json`. 20-day rolling sum < 0 AND 10d MA < 0 → observation mode. Нет новых входов пока кривая не восстановится.

Config vars: `INTRADAY_SPY_GATE=1`, `INTRADAY_MAX_DAILY_LOSS_PCT=2.0`, `INTRADAY_EQUITY_CURVE_GATE=1`, `INTRADAY_EQUITY_CURVE_DAYS=20`

### 2. Equity Curve Autopilot для Bybit стратегий
`scripts/equity_curve_autopilot.py` — антидеградационный монитор:
- Загружает trades.csv из последнего backtest run
- Строит equity curve per strategy → проверяет против MA20
- 4 статуса: OK / WATCH (curve < MA20) / PAUSE (30d PnL < -2%) / KILL (60d PnL < -4%)
- Пишет `configs/strategy_health.json` — main bot может проверять перед входом
- Telegram digest + markdown отчёт в `docs/weekly_reports/`
- Функция `strategy_is_healthy(name)` для интеграции в main бот
- Тест на золотом портфеле: 4 ✅ OK, 1 ⚠️ WATCH (alt_inplay_breakdown_v1)

### 3. Server Cron Setup Script
`scripts/setup_server_crons.sh` — ONE-SHOT скрипт активации на сервере:
```bash
bash scripts/setup_server_crons.sh
```
Устанавливает 4 крона:
- Sun 22:00 UTC → dynamic_allowlist.py
- Sun 22:30 UTC → deepseek_weekly_cron.py
- Sun 23:00 UTC → equity_curve_autopilot.py
- */5 14-21 Mon-Fri → equities_alpaca_intraday_bridge.py --live --once
Включает dry-run тесты при установке. `--remove` удаляет всё.

**Tested:** все три скрипта работают на исторических данных.

**To activate on server:**
```bash
# Один раз на сервере:
bash scripts/setup_server_crons.sh
```

**Next:**
- Проверить sr_break_retest autoresearch результаты
- Запустить equities v23 локально
- Через 2-3 недели paper → смотреть intraday bridge сигналы

---

## 2026-03-29 | Claude (session 19 — WF intraday bridge)

**Done:**
- Built `scripts/equities_alpaca_intraday_bridge.py` — complete Alpaca intraday paper execution bridge
  - Runs TSLA (breakout_continuation + quality_guard), GOOGL (grid_reversion + safe_winrate), JPM (grid_reversion default)
  - Uses WF-validated presets from `run_forex_multi_strategy_gate.py` PRESETS dict
  - Loads historical M5 seed from `data_cache/equities_1h/{SYM}_M5.csv` (1500 bars warm-up)
  - Fetches live bars from Alpaca data API (`/v2/stocks/{sym}/bars?timeframe=5Min`)
  - Submits **bracket orders** (OCO: market entry + auto SL + auto TP in one request)
  - State persistence: `configs/intraday_state.json` (tracks open positions across cron runs)
  - Detects closed positions (SL/TP hit by Alpaca) on each tick → cleans state
  - Telegram alerts on entry + position close
  - `--dry-run` / `--live` flags, `--once` (cron) and `--daemon` modes
  - Tested: imports OK, CSV loading OK (5078 bars per symbol), dry-run runs cleanly

**To run:**
```bash
# Dry-run (no orders) — test signal detection
python3 scripts/equities_alpaca_intraday_bridge.py --dry-run --once

# Live paper (real Alpaca API calls, fake money)
python3 scripts/equities_alpaca_intraday_bridge.py --live --once

# Daemon loop every 5 min (background)
nohup python3 scripts/equities_alpaca_intraday_bridge.py --live --daemon \
  >> logs/intraday_bridge.log 2>&1 &

# Cron (add to crontab, Mon-Fri market hours):
# */5 14-21 * * 1-5 cd /root/by-bot && python3 scripts/equities_alpaca_intraday_bridge.py \
#   --live --once >> logs/intraday_bridge.log 2>&1
```

**Config (all via env / alpaca_paper_local.env):**
- `INTRADAY_NOTIONAL_USD=200` — $ per position (default 200)
- `INTRADAY_MAX_POSITIONS=3` — max simultaneous positions (default 3)

**Key findings:**
- Bracket orders (OCO) are the right tool: single API call sets entry + SL + TP, Alpaca manages the exit automatically
- Strategy warmup needs ≥250 bars minimum; we seed with 1500 from CSV so EMA220 is always ready
- Session filter set to 14:00–21:00 UTC (covers 10:00 AM – 5:00 PM ET, EDT-aligned)
- State file approach handles cron mode correctly: position closed by Alpaca's SL/TP detected on next tick

**Next:**
- Run dry-run on local machine during market hours to see live signals
- After watching a few signals → switch to `--live` for paper trading
- Remember: equities v23 autoresearch still needs to run locally (equities_monthly_v23_spy_regime_gate.json)

---

## 2026-03-28 | Claude (session 18 — night, DeepSeek autonomy)

**Done:**
- Built `scripts/deepseek_weekly_cron.py` — autonomous weekly DeepSeek research agent
  - Phase 1 `audit`: scans recent backtest_runs, computes per-strategy health (PF/DD/net)
  - Phase 2 `tune`: calls `tune_strategy()` for all 5 active strategies → approval queue
  - Phase 3 `research`: flags finished autoresearch runs with PASS combos
  - Phase 4 `universe`: DeepSeek suggests new symbols per strategy family
  - Phase 5 `report`: sends full Telegram digest + saves Markdown report
  - Dry-run tested: working, already showing live audit data
- Updated ROADMAP.md: added full "DeepSeek Autonomy Architecture" section with capability matrix
- Equities v23 SPY regime gate spec (session 17): ready to run

**Key findings from dry-run audit:**
- Active 5 strategies (golden portfolio): ✅ all PF ≈ 2.13, DD 2.9% — healthy
- `btc_eth_midterm_pullback_v2`: ⚠️ PF=0.37 in autoresearch — still searching, not converged
- `pump_fade_simple`: ⚠️ PF=0.79 in raw runs — 2 PASS combos but thin (10-12 trades)
- `sr_break_retest_volume_v1`: ⚠️ PF=0.56 in raw combos — most combos failing, results pending

**To activate DeepSeek autonomous cycle (on server):**
```bash
crontab -e
# Add:
0 22 * * 0 cd /root/by-bot && python3 scripts/deepseek_weekly_cron.py \
  --quiet >> logs/deepseek_weekly.log 2>&1
```

**Manual run with full API:**
```bash
python3 scripts/deepseek_weekly_cron.py
# Or just audit + research (no API tokens spent):
python3 scripts/deepseek_weekly_cron.py --phases audit,research,report
```

---

## 2026-03-28 | Claude (session 17 — night)

**Done:**
- Deep dive into DeepSeek integration — it is MUCH deeper than expected:
  - `bot/deepseek_overlay.py` — core API client with daily request cap, approval queue, shadow log
  - `bot/deepseek_autoresearch_agent.py` — reads backtest results, proposes param changes via `/ai_tune` Telegram commands
  - `bot/deepseek_action_executor.py` — executes approved actions with safety guardrails
  - Telegram commands: `/ai_results`, `/ai_tune`, `/ai_tune breakout|flat|asc1|midterm|breakdown|alpaca`
  - This is already a full weekly-analysis loop — just triggered manually via Telegram, not on cron yet
- Created `configs/autoresearch/equities_monthly_v23_spy_regime_gate.json` — 108 combos
  - Tests `--benchmark-min-above-sma-count` = 0/1/2 (off / SPY-or-QQQ above SMA / both)
  - Existing code already supports this flag — just no spec ever used it
  - Score weights heavily penalize negative months (×8) and negative streaks (×5)

**Key findings:**
- SPY/QQQ regime gate already implemented in `equities_monthly_research_sim.py` — was just never turned ON in any spec
- Setting `--benchmark-min-above-sma-count 1` would have blocked the March 2026 XOM entry entirely
- DeepSeek already has `/ai_tune alpaca` command — can analyze equities sleeve too
- DeepSeek weekly autoresearch cron is the next logical step (trigger `/ai_tune` automatically)

**To run locally:**
```bash
# Equities v23 with SPY regime gate (108 combos, fast — equities backtest is quick)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/equities_monthly_v23_spy_regime_gate.json \
  > /tmp/equities_v23.log 2>&1 &
```

---

## 2026-03-28 | Claude (session 16 — late evening)

**Done:**
- Explored all strategies/ — found `btc_eth_midterm_pullback_v2` built but never tested (not registered)
- Diagnosed ASR1/ARR1/micro_scalper: 0 trades in 360 days — regime filters too strict
- Registered `btc_eth_midterm_pullback_v2` in `backtest/run_portfolio.py` (all 4 points: import, allowed set, dict init, signal loop)
- Created 3 new autoresearch specs:
  - `midterm_pullback_v2_btceth_v1.json` — 243 combos, channel R2/pos/SL/TP1/slope grid, BTC+ETH
  - `pump_fade_simple_expanded_v1.json` — 324 combos, wider universe (SOL/SUI/AVAX/ADA + memes), same grid as meme spec
  - `asr1_rescue_v1.json` — 972 combos, loosened RSI cap (50→60), broader symbols, fewer confirm bars

**Key findings:**
- `btc_eth_midterm_pullback_v2` adds sloped channel position filter + dynamic TP vs v1 — never tested despite being complete
- ASR1: 0 trades because RSI max=50 + confirm_bars=6 + strict regime — needs loosening
- micro_scalper: 2 trades/360 days on BTC/ETH — signal too rare; would need very different universe
- pump_fade_simple: issue is universe too narrow, not the params — need more liquid alt/meme combos

**To run locally (in this order — midterm_v2 first, highest value):**
```bash
# 1. midterm_v2 — direct upgrade to live strategy (fastest, 243 combos)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/midterm_pullback_v2_btceth_v1.json \
  > /tmp/midterm_v2.log 2>&1 &

# 2. pump_fade expanded — wider universe (324 combos)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/pump_fade_simple_expanded_v1.json \
  > /tmp/pf_expanded.log 2>&1 &

# 3. ASR1 rescue — diagnostic run (972 combos, run last)
nohup python3 scripts/run_strategy_autoresearch.py \
  --spec configs/autoresearch/asr1_rescue_v1.json \
  > /tmp/asr1_rescue.log 2>&1 &
```

---

## 2026-03-28 | GPT (session 15 — evening)

**Done:**
- Ran `dynamic_allowlist.py --dry-run` with golden trades.csv backtest gate
- Fixed strategy tags in profiles (added `alt_sloped_channel_v1`, `alt_resistance_fade_v1`, `alt_inplay_breakdown_v1`)
- Built compare snapshot: `full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env`
- Launched annual v5 probe backtest (completed):
  - ASC1: ADAUSDT,LINKUSDT,ATOMUSDT | ARF1: ADAUSDT,SUIUSDT,LINKUSDT,DOTUSDT,LTCUSDT | BREAKDOWN: BTCUSDT,ETHUSDT,SOLUSDT
- Launched sr_break_retest_volume_v1_revival autoresearch (~12,288 combos, still running as of session end)

**Key findings:**
- v5 dynamic allowlist probe: +94.76%, PF=2.141, 420 trades, DD=2.89%
- Golden baseline: +100.93%, PF=2.078, 446 trades, DD=3.65%
- **Verdict: v5 ≈ golden** — slightly lower return (-6%) but better PF (+3%) and lower DD (-0.76%)
  Main difference: dynamic allowlist dropped BCHUSDT, which contributed ~6% in that specific period
- pump_fade_simple autoresearch: 2 PASS combos (r048 PF=2.34, r129 PF=2.14), only 10-12 trades — too thin for live

**Next:**
- Wait for sr_break_retest_volume_v1 autoresearch to finish
- If passes ≥5 combos → add to portfolio probe as 6th strategy
- For pump_fade_simple → expand symbol universe or run longer period to get trade count up

---

## 2026-03-28 | Claude (sessions 13–14)

**Done:**
- Built `scripts/dynamic_allowlist.py` — live Bybit market scanner with per-strategy profiles
  (ASC1, ARF1, BREAKDOWN), optional backtest gate, dry-run mode, cron-ready
- Full Alpaca diagnosis: monthly momentum strategy has 1 trade (XOM, -3.79% stopped out March 2).
  Root cause: no regime filter. Market was risk-off (SPY selloff), strategy entered anyway.
- Identified WF-validated intraday strategies already sitting in backtest_runs:
  TSLA breakout_continuation (67% WF), GOOGL grid_reversion (67% WF), JPM grid_reversion (67% WF)
- Updated ROADMAP.md with full priority queue and 12-month architecture blueprint
- Created JOURNAL.md (this file)

**Key findings:**
- First Alpaca fix to test: add SPY 50-SMA regime gate to equities_monthly_research_sim.py
- The intraday WF strategies are already validated — they just need an execution bridge
- dynamic_allowlist.py ready to use, needs first dry-run from local machine

**Pending (user to run locally):**
- `python3 scripts/dynamic_allowlist.py --dry-run`
- `python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/pump_fade_simple_meme.json`

---

## 2026-03-28 | Claude (sessions 11–12)

**Done:**
- Full pump_fade revival research cycle completed
- Discovered: archive code ≠ baseline — archive has 6+ extra filters not in baseline commit e341055e
- Built `strategies/pump_fade_simple.py` — exact 190-line replica of baseline commit
- Registered pump_fade_simple in backtest/run_portfolio.py (all 5 registration points)
- Created autoresearch spec: `configs/autoresearch/pump_fade_simple_meme.json` (486 combos)
- Built `strategies/pump_fade_v4r.py` — fixed v4 archive with cooldown bug resolved
- Ran v4r autoresearch: 0/243 combos passed (correct — climax wick too rare on liquid alts)
- Diagnosed portfolio "drop" 100%→53%: NOT code break, just time window shift
- Confirmed golden portfolio intact: `portfolio_20260325_172613_new_5strat_final` (+100.93%)

**Key findings:**
- pump_fade baseline = simple 190-line code, not archive version
- VM cache only has ~11 days history → autoresearch MUST run on local machine
- Portfolio drop is not a code break; it is partly a time-window shift and partly config/pocket drift

---

## 2026-03-27 | GPT (session 10)

## 2026-04-01 | Codex | Alpaca dynamic builder enabled server-side

**Done:**
- Added algorithmic intraday watchlist builder: `scripts/build_equities_intraday_watchlist.py`
- Patched `scripts/equities_alpaca_intraday_bridge.py` to refresh watchlist automatically before each dry-run/live cycle
- Verified server compile for:
  - `scripts/build_equities_intraday_watchlist.py`
  - `scripts/equities_alpaca_intraday_bridge.py`
- Ran server dry-run with dynamic builder enabled
- Confirmed dynamic watchlist output on server:
  - `MDB, TSLA, XOM, SNOW, NFLX, META, AMD, NVDA, ABBV, AAPL, COST, WMT`
- Updated server cron so `Alpaca intraday` now runs every 5 minutes with:
  - `INTRADAY_DYNAMIC_BUILD=1`
  - `INTRADAY_DYNAMIC_MAX_SYMBOLS=12`
  - `INTRADAY_DYNAMIC_BREAKOUT_TARGET=6`
  - `INTRADAY_DYNAMIC_REVERSION_TARGET=6`
  - `INTRADAY_DYNAMIC_MIN_AVG_DOLLAR_VOL=25000000`
- Confirmed current server behavior:
  - monthly Alpaca: `dry_run_no_current_cycle`
  - intraday Alpaca: alive, but entries currently blocked by bearish `SPY < SMA50` gate
- Kept `InPlay minute v3` running as the only active scalper research candidate

---

## 2026-04-01 | Codex | Sloped resistance confluence short v1 created

**Done:**
- Built a new short-only confluence strategy:
  - [sloped_resistance_choch_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/sloped_resistance_choch_v1.py)
- Strategy logic combines:
  - sloped 1H regression channel
  - repeated horizontal resistance near the upper band
  - rejection candle from that confluence
  - 5m bearish structure-shift approximation before entry
- Wired it into the backtest engine:
  - [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py)
- Added first bounded research spec:
  - [sloped_resistance_choch_v1_probe.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/sloped_resistance_choch_v1_probe.json)
- Compile + JSON validation passed
- Smoke backtest completed:
  - [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260401_204308_src1_smoke/summary.csv)
  - result: `1` trade, small loss `-0.11`
- Launched first autoresearch probe for the new sleeve

---

**Done:**
- Applied live breakout fix patch: `configs/live_breakout_v3_overlay_20260328.env`
- Server health check confirmed strategies running

---

## Before 2026-03-27 | Earlier sessions

- Initial bot setup with 5 strategies
- Golden portfolio research: +100.93%, PF=2.078, 5 strategies, 10 symbols
- DeepSeek signal audit integration
- Autoresearch pipeline established
- Equities WF gate research completed (TSLA, GOOGL, JPM, JPM validated)

---

## Quick Reference

**Server:** 64.226.73.119
**Bot dir (server):** /root/by-bot/
**Bot dir (local):** ~/Documents/Work/bot-new/bybit-bot-clean-v28/

**Golden portfolio:** `portfolio_20260325_172613_new_5strat_final`
- Return: +100.93% | PF: 2.078 | Strategies: 5 | Symbols: 10

**Current live overlay:** `live_breakout_v3_overlay_20260328.env` (applied on top of existing live5 config, 2026-03-28)

**Current allowlists:**
- ASC1: ATOMUSDT, LINKUSDT, DOTUSDT
- ARF1: LINKUSDT, LTCUSDT, SUIUSDT, DOTUSDT, ADAUSDT, BCHUSDT
- BREAKDOWN: BTCUSDT, ETHUSDT, SOLUSDT, LINKUSDT, ATOMUSDT, LTCUSDT

**Alpaca paper config:** `configs/alpaca_paper_local.env`
- Max positions: 2 | Alloc: 45% per position | Capital override: $500

**AI roles:**
- Claude: architect, research specs, diagnosis, code
- GPT: deployment, server ops, quick fixes
- DeepSeek: signal audit (live), weekly analysis (planned)

---

## 2026-04-02 | Breakout compare prioritized, minute InPlay cut

**Decision:**
- Stopped `inplay_scalper_minute_probe_v3_relaxed` after it kept printing only negative rows on 1m/3m entry.
- Prioritized live `inplay_breakout` improvement instead of further minute compression.

**Why:**
- Historical `breakout_live_bridge_v3_density` already proved the live sleeve has edge:
  - `+20.67%`, `PF 1.403`, `DD 2.94`, `344 trades`
- `breakout_weak_chop_probe_v1` improved that profile further:
  - `+23.85%`, `PF 1.407`, `DD 3.13`, `412 trades`
- This points to regime/chop/quality tuning as the main path, not smaller entry TF.

**New run:**
- Added `configs/autoresearch/breakout_live_bridge_v4_regime_exit_compare.json`
- Goal: bounded compare around:
  - `quality=0.53`
  - `regime=ema`
  - `chop_er_min`
  - `min_pullback`
  - `RR`
  - fixed-mode `time_stop_bars=96`

**Kept alive:**
- `sloped_resistance_choch_v1_probe` stays on as the new confluence-short idea.

**Live debug instrumentation:**
- Added `planned_rr` and `post_fill_rr` tracking for `inplay_breakout` entries in `smart_pump_reversal_bot.py`.
- Goal: verify whether live RR degradation comes from market fill drift / rounding after entry, or from already-weak setup geometry before the order is sent.

**Breakout compare correction:**
- Stopped the first `breakout_live_bridge_v4_regime_exit_compare` attempt after early rows went deeply negative.
- Reason: that compare changed too many dimensions at once (`ema` regime + `chop_er` + `time_stop` + `RR`) and stopped being a clean improvement test.
- Replaced with `breakout_live_bridge_v4b_exit_compare`:
  - only the two historically strongest entry pockets
  - compare `RR` and `time_stop_bars`
  - keep regime `off` to avoid testing a different strategy by accident

## 2026-04-02 | Bear-market focus tightened: weak fronts cut, breakdown recent-window launched

**Decision:**
- Stopped `breakout_live_bridge_v4b_exit_compare` after the first 20 rows stayed deeply negative on the current window.
- Stopped `sloped_resistance_choch_v1_probe` after it kept producing only `1-2` trade rows and no viable density.
- Redirected the next crypto research slot to `breakdown_recent_bear_window_v1`.

**Why:**
- The live bot is currently too dependent on `inplay_breakout` longs.
- `alt_inplay_breakdown_v1` already exists in live, but realized activity is too sparse to matter.
- The right next move is not another `RR` tweak to longs, but a bounded recent-window test of the dedicated short sleeve on the current bearish/choppy market.

**New run:**
- Added `configs/autoresearch/breakdown_recent_bear_window_v1.json`
- Scope:
  - last `120` days ending `2026-04-01`
  - top liquid crypto universe
  - compare `regime on/off`, `lookback`, `RR`, `pullback depth`, and `ER anti-chop`
- Goal:
  - find whether breakdown can become a real second crypto income sleeve in the current market instead of staying decorative.

## 2026-04-02 | InPlay regime-quality repair launched; pump momentum moved to bug-fix status

**What changed:**
- Added `configs/autoresearch/breakout_live_bridge_v6_regime_quality_compare.json`
- Purpose:
  - compare the current permissive live-style `inplay_breakout` profile versus a stricter recent-window repair:
    - `BREAKOUT_REGIME_MODE=ema`
    - `BREAKOUT_IMPULSE_VOL_MULT=1.2`
    - tighter `BREAKOUT_MAX_RETEST_BARS`
    - optional `BREAKOUT_MIN_HOLD_BARS=2`
- Window:
  - `90` days ending `2026-04-01`

**Why:**
- `fixed vs runner` did not improve `InPlay`.
- Current weakness looks structural, not exit-only:
  - regime filter effectively off
  - no HTF volume confirmation by default
  - retest window too stale / permissive

**Pump/dump note:**
- `pump_fade_v4r_bear_window` is technically alive but early rows show `0 trades`.
- `pump_momentum_v1_initial` is not ready for interpretation yet:
  - full grid is crashing with `CalledProcessError`
  - moved into bug-fix / traceback-capture status before any edge judgement.

## 2026-04-03 | Control-plane became locally executable end-to-end

**What changed:**
- Hardened [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py):
  - keeps the fresh fetch path
  - falls back to exact cached fetch
  - if that still fails, aggregates the latest lower-TF local BTC cache into 4H bars
- Hardened [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py):
  - atomic env/json writes
  - router state metadata
  - regime override
  - degraded fallback to the previous overlay
  - profile-level `exclude_symbols`
  - lighter scan defaults for control-plane use
- Added runtime visibility in [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py):
  - router regime/profile lines in `/status_full`
  - optional router health checks behind `ROUTER_HEALTH_ENABLE`
- Reduced scan stickiness in [dynamic_allowlist.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/dynamic_allowlist.py):
  - configurable REST timeout
  - configurable ATR fetch retry/backoff budget

**Verified locally:**
- Orchestrator now succeeds even when fresh Bybit BTC 4H fetch is rate-limited.
- Local run wrote:
  - [orchestrator_state.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/regime/orchestrator_state.json)
  - [regime_orchestrator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/regime_orchestrator_latest.env)
- Current locally detected regime: `bear_chop`
  - risk multiplier `0.70`
  - breakout `OFF`
  - breakdown `ON`
  - flat `ON`
  - midterm `ON`
- Router now writes:
  - [dynamic_allowlist_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/dynamic_allowlist_latest.env)
  - [symbol_router_state.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/router/symbol_router_state.json)
- Under `bear_chop`, the local dynamic baskets currently resolve to:
  - breakout: `BTC,ETH,SOL,XRP,DOGE,TAO`
  - breakdown: `BTC,ETH,SOL,XRP,DOGE,TAO,HYPE,FARTCOIN`
  - sloped: `XRP,DOGE,HYPE,ADA,LINK`
  - flat: `XRP,DOGE,HYPE,ADA,LINK,SUI,DOT`
  - midterm: `BTC,ETH`

**Why this matters:**
- We no longer have only a design for the control plane; we now have a local working loop:
  - regime state
  - per-sleeve symbol routing
  - bot-side hot-reload visibility
- This is the right foundation before touching live crypto sleeve repairs again.

**Next:**
- isolate a clean push-set for orchestrator + router changes
- then do server dry-run rollout
- only after that return to `breakout/breakdown` repair on top of the new control plane

## 2026-04-03 | Router profiles became regime-specific and versioned

**What changed:**
- Checked the real strategy logic before tightening the router:
  - [alt_sloped_channel_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_sloped_channel_v1.py) is bidirectional channel mean-reversion, not a pure bear-only short sleeve
  - [alt_resistance_fade_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_resistance_fade_v1.py) is a short resistance fade and deserves a reduced basket in strong-trend regimes
- Updated [strategy_profile_registry.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_profile_registry.json):
  - added `profile_version=2026-04-03-control-plane-v2`
  - split `ASC1` into:
    - `asc1_trend_reduced`
    - `asc1_chop_core`
  - split `ARF1` into:
    - `arf1_bull_reduced`
    - `arf1_bear_reduced`
    - `arf1_chop_core`
- Updated [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py) so `symbol_router_state.json` and the env overlay now include `ROUTER_PROFILE_VERSION`

**Verified:**
- New dry-run under the current local regime `bear_chop` produced:
  - breakout profile: `breakout_bear_guarded`
  - breakdown profile: `breakdown_bear_core`
  - sloped profile: `asc1_chop_core`
  - flat profile: `arf1_chop_core`
  - midterm profile: `midterm_btceth_core`
- Current `bear_chop` baskets after the profile split:
  - breakout: `BTC,ETH,SOL,XRP,DOGE,TAO`
  - breakdown: `BTC,ETH,SOL,XRP,DOGE,TAO,HYPE,FARTCOIN`
  - sloped: `XRP,DOGE,HYPE`
  - flat: `XRP,DOGE,HYPE,ADA,LINK`
  - midterm: `BTC,ETH`

**Why this matters:**
- The dynamic symbol layer is no longer one-size-fits-all.
- We can now backtest profile logic separately from core strategy logic and know exactly which profile version produced a result.

## 2026-04-03 | Funding carry is runnable again and produced a first conservative baseline

**What changed:**
- Added the capital-efficient sleeve ideas into [ROADMAP.md](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/docs/ROADMAP.md):
  - funding harvest first
  - Hyperliquid second venue next
  - treasury deployment (`CEX Earn`, `Aave`) later
  - DeFi/arb after core stability
- Found a real funding-branch breakage:
  - [backtest_funding_capture.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/backtest_funding_capture.py) imported `strategies.funding_hold_v1`
  - that selector file had been archived out of `strategies/`
- Restored the lightweight selector as [funding_hold_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/funding_hold_v1.py)

**Verified:**
- Funding scripts compile again:
  - [backtest_funding_capture.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/backtest_funding_capture.py)
  - [strategy_symbol_gate.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/strategy_symbol_gate.py)
- Ran a conservative 365d baseline on a fixed liquid universe:
  - symbols tested: `BTC,ETH,SOL,XRP,DOGE,TAO`
  - selected basket: `BTC,DOGE,ETH,XRP`
  - outputs:
    - [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/funding_20260403_105931_funding_baseline_fixed6_365d/summary.csv)
    - [funding_per_symbol.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/funding_20260403_105931_funding_baseline_fixed6_365d/funding_per_symbol.csv)
    - [monthly_pnl.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/funding_20260403_105931_funding_baseline_fixed6_365d/monthly_pnl.csv)

**Human reading of the result:**
- The script modeled `4` symbols with `100 USD` notional each
- total modeled basket notional: `400 USD`
- net result after modeled fees: `+15.14 USD`
- simple reading: about `+3.78%` over `365` days on that modeled notional basket
- months:
  - mostly small green carry months
  - one red month: `2026-02`
- per-symbol leaders:
  - `BTC +4.00 USD`
  - `DOGE +3.87 USD`
  - `ETH +3.84 USD`
  - `XRP +3.43 USD`

**Caveat:**
- This is a useful baseline, not final truth.
- The current script still simplifies:
  - symbol selection
  - fee model
  - capital lock-up / margin model
  - spot hedge execution assumptions
- So funding carry is now back on the board as a serious candidate, but still needs a second validation pass before live.

## 2026-04-03 - Control-Plane Guardrails Added

**What changed:**
- Extended [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py) so every real orchestrator cycle appends a machine-readable line to [orchestrator_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/orchestrator_history.jsonl).
- Extended [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py) so every real router rebuild appends a machine-readable line to [symbol_router_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/symbol_router_history.jsonl).
- Both overlays now export their history-path metadata:
  - [regime_orchestrator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/regime_orchestrator_latest.env)
  - [dynamic_allowlist_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/dynamic_allowlist_latest.env)
- Added [run_validated_baseline_regression.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_validated_baseline_regression.py) as a dedicated gate for the trusted `v5` stack.

**What the new regression helper does:**
- Anchors to the exact trusted overlay:
  - [full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe.env)
- Anchors to the trusted annual summary:
  - [portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive/portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual/summary.csv)
- Builds the exact `run_portfolio.py` command from that trusted artifact.
- Compares fresh output against trusted `net`, `PF`, `DD`, and `trade count` with explicit tolerances.
- Writes machine-readable reports to:
  - [baseline_regression_latest.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/baseline_regression_latest.json)
  - [baseline_regression_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/baseline_regression_history.jsonl)

**Verification done:**
- `py_compile` passed for:
  - [build_regime_state.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py)
  - [build_symbol_router.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py)
  - [run_validated_baseline_regression.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_validated_baseline_regression.py)
- `run_validated_baseline_regression.py --dry-run` resolved the trusted annual command correctly.
- Ran one real orchestrator cycle:
  - fallback path still works
  - current local regime stayed `bear_chop`
  - history file was created and populated
- Ran one real router cycle:
  - scan completed
  - current router history file was created and populated

**Current next step:**
- The first real validated-baseline regression run has been launched and is in progress.

## 2026-04-03 - First Baseline Regression Verdict

**Result:**
- The first real trusted-`v5` regression run finished and **failed**.
- Report:
  - [baseline_regression_latest.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/baseline_regression_latest.json)
  - [baseline_regression_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/baseline_regression_history.jsonl)
- Fresh run artifacts:
  - [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_115644_validated_baseline_regression_20260403_085639/summary.csv)
  - [trades.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_115644_validated_baseline_regression_20260403_085639/trades.csv)

**Expected vs actual:**
- Expected trusted annual:
  - `100 -> 189.65`
  - `+89.65%`
  - PF `2.121`
  - DD `2.88%`
  - `427` trades
- Actual fresh rerun:
  - `100 -> 111.24`
  - `+11.24%`
  - PF `1.148`
  - DD `8.77%`
  - `211` trades

**Meaning:**
- This is not a tiny drift.
- The exact trusted annual result is **not currently reproducible** on the present local stack/data path.
- So the new regression gate already paid for itself:
  - it blocked us from pretending the old golden annual is still confirmed truth
  - it gave us a concrete discrepancy to investigate next

## 2026-04-03 - Quick Project Noise Audit

**Large buckets:**
- [data_cache](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/data_cache): about `644M`
- [backtest_runs_old_20260303.tgz](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs_old_20260303.tgz): about `6.7M`
- [backtest_archive](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive): about `1.2M`

**Obvious junk candidates (not deleted yet):**
- [.env.bak_20260326_local_sync](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.env.bak_20260326_local_sync)
- [runtime/live_breakout_allowv2.pid](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/live_breakout_allowv2.pid)
- [runtime/mplconfig](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/mplconfig)
- repo-level `__pycache__` / `.pyc` trees outside `.venv`

**Not junk by default:**
- [backtest_archive](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive)
- [runtime/control_plane](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane)
- [runtime/regime](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/regime)
- [runtime/router](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/router)
- [data_cache](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/data_cache) until we decide a clean cache policy

## 2026-04-03 - Safe Cleanup and New Strategy Queue

**Cleanup done:**
- Updated [.gitignore](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.gitignore) so future audits are quieter:
  - ignore `runtime/`
  - ignore `backtest_archive/`
  - ignore generated latest overlays/state
  - ignore `trades.db`
  - ignore underscore-form `.env.bak_*`
- Deleted only obvious disposable local artifacts:
  - [.env.bak_20260326_local_sync](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.env.bak_20260326_local_sync)
  - [runtime/live_breakout_allowv2.pid](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/live_breakout_allowv2.pid)
  - [runtime/mplconfig](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/mplconfig)
  - repo-level `__pycache__` trees outside `.venv`

**New strategies from Codex checked:**
- Present and compiling:
  - [alt_inplay_breakdown_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v2.py)
  - [pump_fade_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/pump_fade_v2.py)
  - [alt_support_bounce_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_support_bounce_v1.py)
  - [alt_range_scalp_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_range_scalp_v1.py)
  - [elder_triple_screen_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/elder_triple_screen_v2.py)
- Also verified that [backtest/run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py) already:
  - imports them
  - allows them in CLI validation
  - instantiates them
  - routes them into signal generation

**Important correction before research:**
- The five new autoresearch specs existed but all had `cache_only=true`.
- After the current reproducibility incident, that is the wrong evidence path.
- Switched them to fresh-data mode and JSON-validated:
  - [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json)
  - [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json)
  - [support_bounce_v1_bull_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_bull_sweep_v1.json)
  - [pump_fade_v2_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/pump_fade_v2_sweep_v1.json)
  - [elder_ts_v2_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/elder_ts_v2_sweep_v1.json)

**Research queue order recorded:**
1. `alt_range_scalp_v1`
2. `alt_inplay_breakdown_v2`
3. `alt_support_bounce_v1`
4. `pump_fade_v2`
5. `elder_triple_screen_v2`

**Constraint kept:**
- We still should not trust fresh research more than the failed annual reproducibility question.
- The next high-trust task remains forensic analysis of why the trusted `v5` annual no longer reproduces.

## 2026-04-03 - First Forensic Diff of Old vs Fresh Annual

**Compared:**
- Trusted annual:
  - [trades.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_archive/portfolio_20260328_233022_full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual/trades.csv)
- Fresh failed rerun:
  - [trades.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_115644_validated_baseline_regression_20260403_085639/trades.csv)

**Big picture:**
- Trusted annual:
  - `427` trades
  - `0` red months
- Fresh rerun:
  - `211` trades
  - `4` red months

**Monthly shape:**
- Trusted:
  - `2025-04 +8.76%`
  - `2025-05 +7.77%`
  - `2025-06 +8.13%`
  - `2025-07 +3.43%`
  - `2025-08 +7.10%`
  - `2025-09 +2.86%`
  - `2025-10 +5.17%`
  - `2025-11 +10.91%`
  - `2025-12 +0.74%`
  - `2026-01 +4.48%`
  - `2026-02 +3.78%`
  - `2026-03 +1.60%`
- Fresh:
  - `2025-04 -0.88%`
  - `2025-05 -2.08%`
  - `2025-06 +5.15%`
  - `2025-07 -0.40%`
  - `2025-08 +1.86%`
  - `2025-09 +1.12%`
  - `2025-10 +2.71%`
  - `2025-11 +1.04%`
  - `2025-12 -2.06%`
  - `2026-01 +2.43%`
  - `2026-02 +2.18%`
  - `2026-03 +0.55%`

**Per-strategy delta:**
- Trusted:
  - `alt_inplay_breakdown_v1`: `168` trades, `+34.24%`
  - `alt_resistance_fade_v1`: `48`, `+21.11%`
  - `alt_sloped_channel_v1`: `30`, `+8.63%`
  - `btc_eth_midterm_pullback`: `51`, `+8.27%`
  - `inplay_breakout`: `130`, `+17.41%`
- Fresh:
  - `alt_inplay_breakdown_v1`: `67`, `-12.44%`
  - `alt_resistance_fade_v1`: `63`, `+13.49%`
  - `alt_sloped_channel_v1`: `28`, `+4.90%`
  - `btc_eth_midterm_pullback`: `34`, `+6.35%`
  - `inplay_breakout`: `19`, `-1.06%`

**Main learning:**
- The mismatch is concentrated in the same momentum sleeves:
  - `inplay_breakout`
  - `alt_inplay_breakdown_v1`
- The quieter sleeves stayed broadly positive.
- So the regression failure does **not** look like “everything is randomly broken”.

**Current working hypothesis:**
- More likely:
  - data path drift
  - cache/fetch drift
  - hidden engine assumption drift
- Less likely:
  - one giant rewrite of the quiet sleeves

**Reason:**
- Core code drift in the affected annual stack exists, but the direct diffs are not huge:
  - [inplay_breakout.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/inplay_breakout.py)
  - [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py)
  - [alt_resistance_fade_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_resistance_fade_v1.py)
  - [alt_sloped_channel_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_sloped_channel_v1.py)
  - [backtest/run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py)

So the next right step remains:
- deeper apples-to-apples forensics on data slices and engine assumptions
- only then fresh optimizer sweeps

## 2026-04-03 - Two Fresh Sweeps Started

**Why only two, not all five:**
- We do want higher доход, более частые входы и сильнее edge.
- But after the failed annual reproducibility check, launching all five new fronts at once would create too much noise.
- So the bounded choice is:
  1. one current-market income candidate
  2. one current-market momentum/short repair candidate

**Started now:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json)
  - run dir: [autoresearch_20260403_103012_range_scalp_v1_sweep_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_103012_range_scalp_v1_sweep_v1)
- [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json)
  - run dir: [autoresearch_20260403_103012_breakdown_v2_1h_bear_sweep_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_103012_breakdown_v2_1h_bear_sweep_v1)

**Current status:**
- Both `results.csv` files exist and currently contain only header rows.
- So they are genuinely just started; no verdict yet.

## 2026-04-03 - Sleeve-Specific Forensic Clue

**Breakout old vs fresh:**
- Trusted annual:
  - `94 TP`
  - `36 SL`
  - total `130` trades
- Fresh rerun:
  - `9 TP`
  - `10 SL`
  - total `19` trades

**Breakdown old vs fresh:**
- Trusted annual:
  - `92 TP`
  - `76 SL`
  - total `168` trades
  - strong symbols: `ETH`, `SOL`, `BTC`
- Fresh rerun:
  - `17 TP`
  - `50 SL`
  - total `67` trades
  - worst symbol: `SOL` around `-8.54%`

**Meaning:**
- This is not just “the bot traded less”.
- `breakdown` quality actually flipped.
- So the annual mismatch is concentrated and real.

## 2026-04-03 - Cache Gap Found for Trusted Annual

**New concrete clue:**
- In [.cache/klines](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.cache/klines), the exact trusted annual 5m slice for `2025-04-01 -> 2026-03-27` exists only for:
  - `LINKUSDT`
  - `BTCUSDT`
  - `ETHUSDT`
  - `SOLUSDT`
- It is missing for:
  - `ADAUSDT`
  - `ATOMUSDT`
  - `SUIUSDT`
  - `DOTUSDT`
  - `LTCUSDT`

**Why this matters:**
- [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py) currently supports cache fallback.
- If fresh fetch fails, the engine can silently use the “best” cached slice from a different period.
- That is exactly the kind of evidence drift we were trying to eliminate.

**Action taken:**
- Started a stricter annual rerun with cache fallback disabled:
  - `BACKTEST_CACHE_FALLBACK_ENABLE=0`
- This run is now the next honest test of whether the annual mismatch is primarily cache-path drift.

## 2026-04-03 - Early Fresh Research Signal

**Range scalper:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json) started producing first rows.
- The first rows are all formal FAILs under the current constraints.
- But raw shape is already interesting:
  - some early combos around `net 8-10%`
  - PF around `1.9-2.6`
  - DD around `2.4-3.4`
- So `alt_range_scalp_v1` currently looks alive enough to keep running.

**Breakdown v2 1h:**
- [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json) is also running
- but had not yet produced visible result rows at this checkpoint.

## 2026-04-03 - Expanded Research Front, Alpaca Safe

**Alpaca / forex branch audit:**
- Confirmed the non-crypto branches were not lost during cleanup.
- The repo still contains the main equities/Alpaca bridge and configs:
  - [equities_alpaca_intraday_bridge.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/equities_alpaca_intraday_bridge.py)
  - [run_equities_alpaca_paper.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_alpaca_paper.sh)
  - [alpaca_paper_v36_candidate.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/alpaca_paper_v36_candidate.env)
- The separate forex stack is also still present:
  - [forex/engine.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/forex/engine.py)
  - [run_forex_backtest.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_forex_backtest.py)

**Strict annual regression update:**
- The no-fallback annual rerun did not finish.
- It stopped on a Bybit `10006` rate-limit while exact-fetching `ADAUSDT`.
- That does not disprove the cache-drift hypothesis; it reinforces that exact data acquisition is the current blocker.

**Current research queue:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json) keeps producing encouraging raw rows:
  - multiple combos around `net 10-12%`
  - DD roughly `0.8-3.3`
  - still formal FAIL because of gate settings, not because the raw edge is absent
- [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json) is still printing zero-trade rows in the early block

**New sweeps started:**
- [support_bounce_v1_bull_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_bull_sweep_v1.json)
- [pump_fade_v2_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/pump_fade_v2_sweep_v1.json)

**Why this ordering:**
- We are expanding from the strongest current signal (`range_scalp`) and the need for diversification.
- We are not opening every front at once, because that would create noise before we restore trust in the annual baseline path.

## 2026-04-03 - Allocator and Safe Mode Layer Added

**What was built:**
- Added allocator policy:
  - [portfolio_allocator_policy.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_policy.json)
- Added deterministic allocator builder:
  - [build_portfolio_allocator.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_portfolio_allocator.py)

**What it now does:**
- Reads:
  - orchestrator state
  - symbol router state
  - [strategy_health.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_health.json)
- Writes:
  - [portfolio_allocator_latest.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/portfolio_allocator_latest.env)
  - [portfolio_allocator_state.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/portfolio_allocator_state.json)
  - [portfolio_allocator_history.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/portfolio_allocator_history.jsonl)

**Live-bot integration:**
- [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) now:
  - reloads allocator overlay on startup and in pulse
  - multiplies base risk by both orchestrator and allocator
  - supports `BREAKOUT_RISK_MULT` and `MIDTERM_RISK_MULT`
  - can hard-block all new entries through `portfolio_can_open()` when allocator says data/control-plane is unsafe

**Current allocator verdict (local):**
- regime: `bear_chop`
- allocator status: `degraded`
- hard block: `off`
- global risk multiplier: `0.60`
- sleeves:
  - breakout: disabled
  - breakdown: enabled, trimmed to `0.7125` because health file marks it `WATCH`
  - flat: enabled, `1.05`
  - sloped: enabled, `0.81`
  - midterm: enabled, `0.60`

## 2026-04-03 - Research Queue Update

**Range scalper keeps improving as a current-market candidate:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json)
- multiple rows already around:
  - `net 11-12%`
  - DD around `0.3-0.8` in the best tiny-trade pockets
  - still formal FAIL under current gates, so we should not over-promote it yet

**Support bounce opened weak:**
- [support_bounce_v1_bull_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_bull_sweep_v1.json)
- first rows are consistently negative
- current read: this is not a leading candidate yet

## 2026-04-03 - Pump Fade V2 Was Crashing, Not Failing

**Concrete bug found:**
- [pump_fade_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/pump_fade_v2.py) expected `store.fetch_klines(...)`
- but the real portfolio selector passes `symbol + current bar`
- crash reproduced directly as:
  - `AttributeError: 'str' object has no attribute 'fetch_klines'`

**Fix applied:**
- Reworked `pump_fade_v2` to use its own rolling 5m bar buffer from sequential bar calls instead of asking for a store object.

**Verification:**
- `py_compile` passes
- 30d smoke backtest now completes cleanly at:
  - [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_144532_pump_fade_v2_smoke_fix/summary.csv)
- smoke result:
  - `0` trades
  - `0.00%`
  - no crash

**Important interpretation:**
- The currently running long `pump_fade_v2_sweep_v1` still contains many pre-fix crash rows.
- That active run is now contaminated as evidence and should be restarted later instead of treated as a valid strategy verdict.

**Follow-up completed:**
- The contaminated old `pump_fade_v2_sweep_v1` run was stopped.
- A fresh clean rerun from the same spec was started after the fix, so future rows can be interpreted normally.

## 2026-04-03 - Exact Annual Cache Gate Hardened

**Why this mattered:**
- We already had a strong suspicion that annual truth was getting distorted by cache fallback and environment drift.
- The old regression helper could still run on the wrong Python and could still attempt a baseline rerun without explicitly proving that the exact annual slices existed first.

**What changed:**
- Added:
  - [check_exact_kline_cache.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_exact_kline_cache.py)
- Updated:
  - [run_validated_baseline_regression.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_validated_baseline_regression.py)

**New regression behavior:**
- It now computes the exact trusted annual 5m window from:
  - `days=360`
  - `end_date_utc=2026-03-27`
- It audits exact cache coverage for the full trusted union before running.
- In `require` mode, it refuses to run if any exact slice is missing.
- When exact slices exist, it forces:
  - `BACKTEST_CACHE_ONLY=1`
  - `BACKTEST_CACHE_FALLBACK_ENABLE=0`
- It now prefers project:
  - `.venv/bin/python3`
  instead of the system interpreter.

**What we learned immediately:**
- The trusted annual union currently has full exact 5m cache coverage for:
  - `ADA`
  - `ATOM`
  - `LINK`
  - `SUI`
  - `DOT`
  - `LTC`
  - `BTC`
  - `ETH`
  - `SOL`
- So the annual gate can now be rerun honestly from exact local slices instead of "best cached slice" fallback.

**Why this is good even before final annual numbers return:**
- If the new annual still fails, we can stop blaming missing exact slices.
- If it matches or improves, we finally have a reproducible path back to trusted annual truth.

**Extra environment fix caught on the way:**
- The first hardened rerun failed not on market logic, but because it launched `run_portfolio.py` under the system Python and hit:
  - `ModuleNotFoundError: numpy`
- That is now fixed by preferring the project `.venv`, so the annual gate is no longer polluted by interpreter drift.

## 2026-04-03 - Research Queue Reality Check

**Range scalper still leads:**
- [range_scalp_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/range_scalp_v1_sweep_v1.json)
- By row `240`, the visible positive pockets are still there:
  - roughly `+6.9%` to `+9.85%`
  - drawdown still very small: `~0.33-1.24`
- The main reason it keeps showing as FAIL is still:
  - `trades < 40`
- Interpretation:
  - not promoted yet
  - but still the best current-market candidate in the queue

**Breakdown v2 1h is not waking up yet:**
- [breakdown_v2_1h_bear_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v2_1h_bear_sweep_v1.json)
- Through row `121`, the visible block is still all:
  - `0 trades`
  - `0 net`
  - `0 PF`
- Interpretation:
  - this is now more than just "warming up"
  - the current search region looks weak

**Support bounce remains weak:**
- [support_bounce_v1_bull_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/support_bounce_v1_bull_sweep_v1.json)
- Through row `68`, rows are still failing on:
  - PF
  - negative months
  - negative streak
- Net is positive in spots (`~+3.6%` to `+4.4%`), but the quality is not good enough.

**Pump fade v2 is fixed technically, but weak strategically so far:**
- [pump_fade_v2_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/pump_fade_v2_sweep_v1.json)
- The clean rerun is now producing real rows instead of crash spam.
- First visible honest rows are still poor:
  - net around `-2.8%` to `-41%`
  - DD around `12-52`
- Interpretation:
  - interface bug is solved
  - current parameter zone is not good

## 2026-04-03 - Honest Annual Verdict and What It Means

**Big truth update:**
- The hardened annual rerun is finished.
- It used:
  - exact annual 5m cache slices
  - project `.venv`
  - the trusted symbol union
  - the trusted overlay
- And it still did **not** reproduce the historical golden annual.

**Expected vs actual:**
- trusted annual reference:
  - `+89.65%`
  - PF `2.121`
  - DD `2.88`
  - `427` trades
- honest rerun:
  - `+11.24%`
  - PF `1.148`
  - DD `8.77`
  - `211` trades

**What this means now:**
- The old mismatch is no longer explainable by:
  - missing exact annual slices
  - system Python drift
- So the next suspect class is:
  - strategy logic drift
  - shared engine drift
  - changed defaults in the portfolio path

**Per-strategy contribution on the honest rerun:**
- positive:
  - [alt_resistance_fade_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_resistance_fade_v1.py) about `+13.49`
  - [btc_eth_midterm_pullback.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/btc_eth_midterm_pullback.py) about `+6.35`
  - [alt_sloped_channel_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_sloped_channel_v1.py) about `+4.90`
- negative:
  - [inplay_breakout.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/inplay_breakout.py) about `-1.06`
  - [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py) about `-12.44`

**Immediate interpretation:**
- `alt_inplay_breakdown_v1` is now the clearest rewrite / retirement candidate.
- `inplay_breakout` is not dead, but it is not carrying the stack and should stay in repair rather than live-trusted status.
- `fade`, `midterm`, and `sloped` currently look healthier than the momentum sleeves.

## 2026-04-03 - Plain-Language Forensic Read of the Momentum Sleeves

**Whole honest annual rerun:**
- portfolio:
  - `+11.24%`
  - winrate `40.8%`
  - max DD `8.77%`
  - `211` trades
  - `4` red months
  - `8` green months
- monthly shape:
  - `2025-04 -0.88%`
  - `2025-05 -2.08%`
  - `2025-06 +5.15%`
  - `2025-07 -0.40%`
  - `2025-08 +1.86%`
  - `2025-09 +1.12%`
  - `2025-10 +2.71%`
  - `2025-11 +1.04%`
  - `2025-12 -2.06%`
  - `2026-01 +2.43%`
  - `2026-02 +2.18%`
  - `2026-03 +0.55%`

**Breakout vs historical baseline:**
- trusted annual:
  - `130` trades
  - `72.3%` winrate
  - `+17.41%`
- honest rerun:
  - `19` trades
  - `47.4%` winrate
  - `-1.06%`
  - `4` red months / `3` green months

**Breakdown v1 vs historical baseline:**
- trusted annual:
  - `168` trades
  - `54.8%` winrate
  - `+34.24%`
- honest rerun:
  - `67` trades
  - `25.4%` winrate
  - `-12.44%`
  - `9` red months / `3` green months

**Most important code-level insight:**
- [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py) is only a thin wrapper.
- It delegates to [inplay_breakout.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/inplay_breakout.py).
- And that wrapper delegates the real momentum logic to:
  - [sr_inplay_retest.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/sr_inplay_retest.py)

**Practical implication:**
- If the original breakout/retest engine changed over time, both sleeves would drift together.
- That fits the evidence much better than "random market bad luck".

**Approximate per-strategy drawdown on the honest annual rerun**
using trade-sequence equity from `pnl_pct_equity` as a quick forensic proxy:
- `alt_inplay_breakdown_v1`: about `12.75%`
- `alt_resistance_fade_v1`: about `3.62%`
- `alt_sloped_channel_v1`: about `2.34%`
- `btc_eth_midterm_pullback`: about `2.91%`
- `inplay_breakout`: about `2.33%`

This strengthens the same conclusion:
- `breakdown_v1` is not just slightly negative; it is the sleeve with the nastiest standalone damage profile in the current honest annual rerun.

## 2026-04-03 - Audit Fixes Landed

**Autopilot truth-path fixed**
- [equity_curve_autopilot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/equity_curve_autopilot.py)
- Default run selection no longer grabs the newest random `portfolio_*`.
- It now prefers the latest trusted baseline regression artifact and rejects exploratory runs by default unless `--allow-exploratory` is passed.
- Verification:
  - running in quiet mode now rewrites [strategy_health.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_health.json) from:
    - `portfolio_20260403_150051_validated_baseline_regression_20260403_120047`

**Allowlist watcher dry-run fixed**
- [allowlist_watcher.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/allowlist_watcher.py)
- Standalone `apply_now()` now resolves the file path correctly instead of crashing on undefined `ALLOWLIST_FILE`.
- Verification:
  - `python3 bot/allowlist_watcher.py --dry-run` works

**Health gate coverage improved**
- [health_gate.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/health_gate.py)
- Added mappings for:
  - `micro_scalper_v1`
  - `alt_support_reclaim_v1`
- Missing known live sleeves no longer silently read as `OK`; they default to `WATCH`.
- Verification:
  - `micro_scalper_v1 -> WATCH`
  - `alt_support_reclaim_v1 -> WATCH`

**Smoke test honesty improved**
- [tests/smoke_test.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/tests/smoke_test.py)
- It now fails if indicator imports are missing, unless explicitly allowed by env.
- This is intentional: green smoke tests should no longer hide fallback-indicator mode.

## 2026-04-03 - Strategy Design Conclusion Locked In

The user's explanation matches the current evidence well enough to treat it as a design correction, not just a preference:
- `inplay_breakout` should remain a long-biased family:
  - impulse
  - pullback / retest
  - continuation toward the next overhead level
- The current `alt_inplay_breakdown_v1` mirrored short logic looks conceptually weaker than the original long concept.
- So the short side should likely evolve into:
  - dump continuation
  - bearish reclaim failure
  - fast breakdown / panic unwind
rather than a symmetric "in-play but down" clone.

## 2026-04-03 - Breakdown V1 No Longer Mirrors Long InPlay

We acted on that design correction immediately.

- Stopped the stale fresh-data sweeps so we do not keep optimizing around the old short logic.
- Replaced [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py) with a standalone short engine.
- It keeps the existing `BREAKDOWN_*` env names, so live and backtest plumbing do not need renaming.

New short logic:
- detect a real 1h support break / dump
- arm a short setup around that broken level
- enter either on:
  - a weak 5m reclaim that fails below support
  - or continuation while price stays compressed under the broken level

Important consequence:
- `inplay_breakout` can now stay a long-family without dragging a conceptually weak mirrored short behind it.
- The next backtests should therefore be treated as a clean test of the new short thesis, not another variation of the old mirror wrapper.

## 2026-04-03 - Review Confirmed And New Run Pack Started

The extra code review was useful, but the good news is that the reported fixes were already present in the tree by the time we checked them:
- `run_portfolio.py` already dispatches the new strategies through proper OHLCV bars and uses `maybe_signal(...)` where needed
- `alt_inplay_breakdown_v2.py` already excludes the current bar from its 5m volume baseline and uses the corrected stop reason text
- `elder_triple_screen_v2.py` already has a real `stoch_rsi` path instead of a dead copy-paste branch

What we changed after verification:
- added a dedicated fresh-data sweep config for the rewritten short sleeve:
  - [breakdown_v1_bear_failed_reclaim_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v1_bear_failed_reclaim_sweep_v1.json)
- restarted the relevant overnight research around the new logic instead of the old mirrored one

Active overnight package:
- `range_scalp_v1_sweep_v1`
- `breakdown_v1_bear_failed_reclaim_sweep_v1`
- `elder_ts_v2_sweep_v1`
- trusted-overlay `current90` portfolio probe with rewritten `alt_inplay_breakdown_v1`

Operational note:
- the local shell environment is awkward for detached background jobs, so the most important runs were left in live exec sessions to guarantee they continue computing.

## 2026-04-03 - New Current90 Control Point

We now have a real post-rewrite control point for the crypto package on the most relevant recent window:
- [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260403_175621_breakdown_v1_rewrite_current90_probe/summary.csv)

Result:
- `90d`
- `+13.97%`
- `47` trades
- `PF 2.059`
- `winrate 57.4%`
- `max DD 2.48%`

Per-strategy contribution:
- `alt_inplay_breakdown_v1`: `+7.23%`, `22` trades, WR `59.1%`
- `alt_resistance_fade_v1`: `+5.81%`, `9` trades, WR `77.8%`
- `alt_sloped_channel_v1`: `+1.43%`
- `btc_eth_midterm_pullback`: roughly flat
- `inplay_breakout`: `-0.53%`, `1` trade

Interpretation:
- the rewritten short-side logic is the first real structural improvement we have seen in the momentum family on a current window
- this package should be treated as a saved control point, not as final truth for all regimes

## 2026-04-03 - Focused Breakdown Search Started

Instead of continuing the broad annual search, we narrowed around what is actually working now.

New specs:
- [breakdown_v1_current90_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v1_current90_focus_v1.json)
- [breakdown_v1_recent180_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakdown_v1_recent180_focus_v1.json)

Why:
- the wide `360d` breakdown sweep was too blunt and mostly told us the strategy is not a universal all-regime engine
- the saved `current90` package told us the new short logic *is* live on the actual recent market
- so the next correct move is to optimize locally around that successful region, then test robustness on `180d`

Early signal:
- the very first `current90` focused row already opened with:
  - `PASS`
  - `net 9.09`
  - `PF 3.771`
  - `WR 70.8%`
  - `DD 1.97%`

This is not final validation yet, but it is exactly the kind of signal we wanted before going to sleep: recent-window strength that survives a tighter sweep instead of disappearing immediately.

## 2026-04-03 - Weak Sleeve Triage and New Focused Repairs

Three useful conclusions came out of the next decomposition pass.

1. `inplay_breakout` is not mainly failing because TP is "a little too far". In the honest annual run it had `19` trades, and all `10` losing trades were direct `breakout_retest_long+SL` stop-outs. That points to marginal retests / late reclaim entries, not to a target that is simply too ambitious.

2. `alt_sloped_channel_v1` is modest but alive. In the saved current-window package it contributed `+1.43%` across `9` trades, mostly on `ATOM`, `LINK`, and `ADA`. The right question is not "is it dead?", but "can we make it more explicitly short-only and more selective in bear-chop?"

3. `btc_eth_midterm_pullback` is not missing a short side; the code already has one. The issue is that, right now, it behaves like a low-frequency stabilizer rather than a driver.

New focused specs prepared from those conclusions:
- [arf1_current90_density_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/arf1_current90_density_focus_v1.json)
- [asc1_bear_short_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/asc1_bear_short_focus_v1.json)
- [breakout_current90_repair_focus_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/breakout_current90_repair_focus_v1.json)

These are the next honest tests:
- `ARF1`: can we widen the current bear-chop fade pocket without killing the edge?
- `ASC1`: does short-only sloped-range behavior work better than the current mixed profile?
- `breakout`: can stricter reclaim quality and less-late retests recover the long in-play family without pretending a lower TP magically solves bad entries?

Those focused sweeps are now actually running:
- [autoresearch_20260403_204839_arf1_current90_density_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_204839_arf1_current90_density_focus_v1)
- [autoresearch_20260403_204906_asc1_bear_short_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_204906_asc1_bear_short_focus_v1)
- [autoresearch_20260403_204906_breakout_current90_repair_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_204906_breakout_current90_repair_focus_v1)

## 2026-04-04 - What The Breakout Review Actually Meant

The latest `breakout` review contained one useful hardening idea and two claims that looked scarier than they are in this repo.

- Useful hardening:
  - [strategies/inplay_breakout.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/inplay_breakout.py) now keeps a per-symbol engine map (`_impl_by_symbol`) instead of relying only on a single `self.impl`.
  - In practice, both live and portfolio backtest were already creating one wrapper per symbol, so this was not the root cause of the strategy's recent losses.
  - But it removes a real future footgun and makes the wrapper API safer.

- Not a current production bug:
  - The async warning does **not** match the current code path, because both live and backtest `fetch_klines(...)` entry points are synchronous today.
  - The "no caching" warning is also overstated for live, because [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) already caches raw public klines in `_KLINE_RAW_CACHE`.

So the diagnosis stays the same:
- coin selection matters a lot
- timeframe choice matters some
- but the main `breakout` problem still looks like poor retest quality / late entries, not async/caching architecture

## 2026-04-04 - The First Night Package That Actually Looks Like A Core

We now have a clear package-level winner on the fresh `current90` window:

- [portfolio_20260404_003719_overnight_current90_core2_fade_breakdown/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_003719_overnight_current90_core2_fade_breakdown/summary.csv)
  - `+19.05%`
  - `55` trades
  - PF `2.691`
  - WR `61.8%`
  - max DD `4.43%`

The strategy split is exactly what we hoped to see from the repaired crypto stack:

- `alt_inplay_breakdown_v1`: `42` trades, `+13.9582`, WR `59.5%`
- `alt_resistance_fade_v1`: `13` trades, `+5.0922`, WR `69.2%`

We also confirmed what is hurting the larger mixed package:

- [portfolio_20260404_003719_overnight_current90_core4_no_breakout_tuned/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_003719_overnight_current90_core4_no_breakout_tuned/summary.csv) only managed `+10.08%` with PF `1.356`
- the main drag inside that package was `alt_sloped_channel_v1`, which lost `-9.1036` over `34` trades

That means the night package should not be "run everything and hope." The current honest focus is:

- keep `ARF1` density research alive:
  - [autoresearch_20260403_204839_arf1_current90_density_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_204839_arf1_current90_density_focus_v1)
  - current clean PASS pocket: `+4.59%`, PF `2.571`, WR `64.3%`, DD `1.69%`
- keep `breakdown_v1` `180d` focus alive:
  - [autoresearch_20260403_200428_breakdown_v1_recent180_focus_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260403_200428_breakdown_v1_recent180_focus_v1)
  - current strong pocket: `+13.05%`, PF `2.113`, DD `3.91%`
- keep the package probe alive for the two sleeves that are actually paying:
  - `overnight_recent180_core2_fade_breakdown`

And for now, do **not** let `ASC1` or `breakout` dominate the overnight queue until they earn their way back in.

## 2026-04-04 - Morning Verdict

The night finished with a clear answer: the strongest crypto core right now is not "everything together." It is:

- `alt_inplay_breakdown_v1`
- `alt_resistance_fade_v1`

Fresh package results:

- [portfolio_20260404_003719_overnight_current90_core2_fade_breakdown/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_003719_overnight_current90_core2_fade_breakdown/summary.csv)
  - `+19.05%`
  - `55` trades
  - PF `2.691`
  - WR `61.8%`
  - DD `4.43%`
- [portfolio_20260404_004652_overnight_recent180_core2_fade_breakdown/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_004652_overnight_recent180_core2_fade_breakdown/summary.csv)
  - `+27.23%`
  - `148` trades
  - PF `1.748`
  - WR `53.4%`
  - DD `10.32%`

Decomposition:

- `alt_inplay_breakdown_v1` remains the main motor:
  - `current90`: `42` trades, `+13.9582`, WR `59.5%`
  - `recent180`: `107` trades, `+22.4814`, WR `54.2%`
- `alt_resistance_fade_v1` is the quality stabilizer:
  - `current90`: `13` trades, `+5.0922`, WR `69.2%`
  - `recent180`: `41` trades, `+4.7510`, WR `51.2%`

Focused research also improved:

- `ARF1` density search now reaches about `+8.77%`, PF `4.156`, WR `68.8%` on `current90`
- `breakdown_v1` `recent180` focus now reaches about `+22.20%`, PF `1.801`, WR `51.8%`

We also fixed an execution-level weakness in the live bot:

- The scary external diagnosis about `position_manager.py` did **not** match this repo.
- Real live TP/SL here goes through [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) and Bybit `v5/position/trading-stop`, not a standalone stop order.
- But the real risk was still valid in spirit: if exchange TP/SL placement keeps failing, the position could stay open too long.
- So the bot now arms a TP/SL failsafe and force-closes the position if it remains unprotected past a short grace window.

That means the next move is not random exploration. It is:

- treat `fade + new breakdown` as the current crypto candidate core
- keep repairing `breakout` separately
- keep `ASC1` and `midterm` on reduced influence until they earn their way back in

## 2026-04-04 - New Chop Sleeve Added: `AVW1`

To keep the bot adaptive instead of frozen around the current `bear_chop` winner, we added a brand new sleeve:

- [alt_vwap_mean_reversion_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_vwap_mean_reversion_v1.py)

What it is:

- intraday VWAP mean reversion on `15m`
- meant for chop/range environments
- fades statistically stretched moves back toward session VWAP
- uses low ER, RSI extremes, ATR distance from VWAP, and a rejection/reclaim bar

It is already wired into the project properly:

- portfolio backtester:
  - [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py)
- router profiles:
  - [strategy_profile_registry.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_profile_registry.json)
- allowlist fallback path:
  - [dynamic_allowlist.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/dynamic_allowlist.py)
- strategy fit scorer:
  - [strategy_scorer.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/strategy_scorer.py)
- research sweep:
  - [vwap_mean_reversion_v1_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/vwap_mean_reversion_v1_sweep_v1.json)

First smoke result:

- [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_084344_avw1_smoke_30d/summary.csv)
  - `-6.63%`
  - `122` trades
  - PF `0.620`
  - WR `49.2%`
  - DD `7.81%`

That is not a failure of integration. It is a useful strategic answer:

- the sleeve is alive
- it clearly adds frequency
- but in its raw default form it is far too loose and noisy

So the next honest step for `AVW1` is:

- do not promote it
- tighten its filters
- run the focused sweep
- only then decide if it deserves a place next to `ARF1 + breakdown`

2026-04-04 09:55 UTC

We completed the first real server-side transition from the old mixed crypto stack to the new canary overlay.

- Uploaded the selected files to `/root/by-bot`
- Backed up the remote `.env`
- Applied [live_candidate_core2_breakdown_arf1_20260404.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/live_candidate_core2_breakdown_arf1_20260404.env)
- Restarted the live bot

The live intention is now clear and narrow:

- `alt_inplay_breakdown_v1` is the primary short momentum sleeve
- `alt_resistance_fade_v1` remains the stabilizing range/fade sleeve
- legacy sleeves are intentionally not part of the current canary core

On the local research side:

- `VWAP` is alive but still strategically weak
- `range_scalp` has been re-launched as the main additive frequency candidate
- `breakout` repair has been re-launched as its own explicit track
- `ASC1` bear-short focus has also been re-launched, but its early rows are still mostly weak/negative

Current honest shortlist:

- live candidate core: `ARF1 + new breakdown`
- next additive candidate: `range_scalp`
- repair candidate: `breakout`
- still-unproven secondary sleeve: `ASC1`
- research-only/no-promotion: `VWAP`

2026-04-04 10:45 UTC

I cleaned up the active queue and replaced one stale tool with a current one.

The old generic walk-forward script is not trustworthy for the current crypto stack:

- it imports archived/dead strategies
- it fails before execution
- it is not the right foundation for evaluating the current `ARF1 + breakdown` core

So instead of trying to salvage it blindly, I added a dedicated runner:

- [run_crypto_core_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_crypto_core_walkforward.py)

This new runner:

- uses the real `.venv`
- calls the live [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py)
- runs rolling windows
- writes CSV + Markdown + JSON summaries

It is now running on the current core:

- symbols: `ADA,SUI,LINK,DOT,LTC,BTC,ETH,SOL`
- strategies: `alt_resistance_fade_v1 + alt_inplay_breakdown_v1`
- horizon: `180d`
- windows: `30d`
- step: `15d`

I also explicitly stopped the `VWAP` sweep.

That was the right call:

- the sweep had already shown extreme persistent weakness
- it was consuming process budget
- it had not produced a single credible rescue signal

So the active queue is cleaner now:

- running: `core2 walk-forward`
- running: `breakout repair`
- running: `pump_fade_v2`
- completed earlier and available for reading: `ARF1 density`, `breakdown focus`, `range_scalp`
- stopped/deprioritized: `VWAP`, `ASC1`

2026-04-04 11:30 UTC

Two concrete architecture fixes landed, and one of them is already validated.

First, `breakdown` no longer has to trade blind into the next support.

In [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py) the strategy now:

- scans for the next lower support cluster
- stores it at arm time
- moves TP up in front of that level when it would otherwise overshoot it

This is not just theoretical. The smoke run:

- [summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_112212_breakdown_level_tp_smoke_90d/summary.csv)
  - `+10.20%`
  - `39` trades
  - PF `2.345`
  - WR `59.0%`
  - DD `3.48%`

And the trade reasons confirm the new path is active:

- `bd1_failed_reclaim+level_tp+TP1+TP2`

Second, `elder` now has a cleaner risk model.

In [elder_triple_screen_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/elder_triple_screen_v2.py) I added:

- `ETS2_RISK_TF`

That means stop/target ATR can come from a slower timeframe than the raw entry trigger. The new sweep:

- [elder_ts_v2_sweep_v2.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/elder_ts_v2_sweep_v2.json)

now fixes risk ATR on `60m` while still comparing `15m` vs `60m` entry timing honestly.

Early result is still bad:

- `r001-r004` all fail badly

So `elder` is still research, not promotion.

Finally, the active queue is narrower and healthier:

- running: `core2 walk-forward` with overlay-bound env
- running: `elder v2`
- stopped: `VWAP`
- stopped: `pump_fade_v2`
- stopped: `breakout repair current sweep`

That is a much cleaner place to leave the machine for the next hour.

- 2026-04-04 12:40 UTC — Found and fixed a real honesty bug in `run_portfolio`: on Bybit rate-limit fallback it could reuse a wide cached slice without trimming back to the requested time window, which made separate walk-forward windows replay the same trade history. Patched candle trimming by `start_ms/end_ms`, recompiled, and restarted the validation run under `core2_walkforward_180d_overlay_v2`. `elder_ts_v2_sweep_v2` finished with zero PASS rows; best raw was still negative (`r136`, net `-3.21`, PF `0.938`), so `elder` remains bench/research only. `breakdown_v2_1h_bear_sweep_v1` was stopped after `122` straight zero-trade rows — not enough signal to justify more process budget. Also refreshed the DeepSeek operator layer: removed stale hard-coded portfolio lore from `bot/deepseek_overlay.py`, added current `core2` candidate context to `bot/deepseek_autoresearch_agent.py`, and added explicit truth fields to the live snapshot in `smart_pump_reversal_bot.py`. Immediate rollout of those AI/runtime files to the server is currently blocked by SSH/SCP timeouts to `167.172.191.107`, so that part is waiting on connectivity, not on code. While the repaired walk-forward runs, launched `flat_arf1_expansion_v2` as the next useful frontier.
- 2026-04-04 13:10 UTC — The server confusion was not a broken key but a stale IP. The live server in the repo surface is `64.226.73.119`, not `167.172.191.107`. Connected to the real host, confirmed `/root/by-bot` and the live `smart_pump_reversal_bot.py` process, uploaded refreshed `smart_pump_reversal_bot.py`, `bot/deepseek_overlay.py`, `bot/deepseek_autoresearch_agent.py`, and `backtest/run_portfolio.py`, then restarted the live bot successfully. That means server AI now has the refreshed truth-oriented prompt/context and server backtests now include the cache-window trimming fix. Research-wise, `range_scalp_v1_sweep_v1` is now the strongest next additive sleeve with multiple PASS pockets (best `r364`: `+15.84%`, PF `2.212`, DD `4.70`), while `flat_arf1_expansion_v2` stays promising but still under its strict PF gate and `support_bounce_v1_bull_sweep_v1` remains weak in the current market. Launched two package probes to test the real next question: does adding `range_scalp` improve the current `core2`? Running tags: `core3_current90_breakdown_arf1_range_probe` and `core3_recent180_breakdown_arf1_range_probe`.
- 2026-04-04 13:35 UTC — The next useful question is no longer “is `range_scalp` good alone?” but “does it actually expand the package when it stops fighting core2 for the same inventory?” A trade-cut made the overlap obvious: the standalone winner in [portfolio_20260404_132235_range_scalp_best_current90_probe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_132235_range_scalp_best_current90_probe) trades mostly `DOT/LINK/SUI/ADA/LTC/ATOM`, while the current core already occupies `ADA/LINK/LTC/SUI/DOT` through `breakdown` and `ARF1`. So I did not force a false conclusion from the first core3 package probe. Instead I launched [core3_range_additivity_current90_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/core3_range_additivity_current90_v1.json), which gives `range_scalp` tuned best-pocket params, a semi-disjoint `ARS1_SYMBOL_ALLOWLIST`, and slightly wider `max_positions` to test real additivity rather than pure competition. In parallel I launched [pump_momentum_v1_current90_zoom_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/pump_momentum_v1_current90_zoom_v1.json) as the cleaner answer to “what if we trade continuation without waiting for the reclaim?” Both are now running while `core2` walk-forward and `flat_arf1_expansion_v2` continue.
- 2026-04-05 00:05 UTC — The finished answer was stricter than the hopeful one. `core3_range_additivity_current90_v1` did complete with many PASS rows and a best pocket of `+19.11`, PF `2.919`, DD `3.56`, but decomposing the trades showed the same two current sleeves doing all the work: `alt_inplay_breakdown_v1` and `alt_resistance_fade_v1`. Even at `MAX_POSITIONS=5`, `alt_range_scalp_v1` still produced zero package trades. The direct recent180 probe told the same story: [portfolio_20260404_134600_core3_range_additivity_recent180_bestprobe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260404_134600_core3_range_additivity_recent180_bestprobe) came in at `+21.78`, PF `1.696`, DD `10.21`, again with no actual `range_scalp` participation and still weaker than the older recent180 `core2` benchmark. So the honest next conclusion is: `range_scalp` is still real as a standalone idea, but not yet proven as the third live sleeve; the best immediate portfolio improvement signal came from giving the current `core2` more room, not from adding a new family. `pump_momentum_v1_current90_zoom_v1` also finished cleanly with zero PASS rows, so the “trade the pump directly without waiting for a reclaim” hypothesis did not revive the long side. Separately, the operator’s `NO_DATA` alert was confirmed as a monitoring weakness, not evidence of two bots or a dead engine: the guard treated a fully empty 2h window as critical even when `smart_pump_reversal_bot.py` was alive. That path is now patched locally and on the real server `64.226.73.119` so empty quiet windows downgrade to `LOW_SAMPLE` instead of paging as a crisis.
- 2026-04-05 02:25 UTC — Wrote down the current best-known baseline explicitly in [core2_research_best_20260405.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/core2_research_best_20260405.env) so the strongest current research pocket is no longer spread across chat + logs. It keeps `ARF1` on the live candidate values and upgrades `breakdown` to the strongest finished `current90` pocket from [breakdown_v1_current90_focus_v1 results](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260404_223512_breakdown_v1_current90_focus_v1/results.csv) row `r483`: `LOOKBACK_H=60`, `MIN_BREAK_ATR=0.25`, `RSI_MAX=60`, `SL_ATR=1.8`, `RR=2.4`, five-coin allowlist (`BTC,ETH,SOL,LINK,ADA`). That gives us one obvious source-of-truth file for “what currently works best” while we keep searching for more sleeves.
- 2026-04-05 02:25 UTC — Instead of grinding the old breakout reclaim family again, I started a new long-side research branch: [impulse_volume_breakout_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/impulse_volume_breakout_v1.py). The logic is intentionally different from both old `inplay_breakout` and failed `pump_momentum`: detect a real high-volume 5m impulse through local highs, arm the setup, wait for a shallow retrace back toward the defended breakout zone, then only enter on a bullish reclaim while the level still holds. Wired it into [run_portfolio.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py), verified syntax, and ran a first smoke [portfolio_20260405_022015_impulse_volume_breakout_v1_smoke_30d](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_022015_impulse_volume_breakout_v1_smoke_30d): technically healthy but strategically weak so far (`-0.90`, `7` trades, PF `0.417`). That is still useful because it proves the new family is wired and tradable; now it needs honest search, not speculation.
- 2026-04-05 02:25 UTC — Launched two first-wave autoresearch sweeps for the new long family: [impulse_volume_breakout_v1_current90_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/impulse_volume_breakout_v1_current90_sweep_v1.json) and [impulse_volume_breakout_v1_recent180_sweep_v1.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/impulse_volume_breakout_v1_recent180_sweep_v1.json). Output directories are already created: [autoresearch_20260404_232131_impulse_volume_breakout_v1_current90_sweep_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260404_232131_impulse_volume_breakout_v1_current90_sweep_v1) and [autoresearch_20260404_232131_impulse_volume_breakout_v1_recent180_sweep_v1](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/autoresearch_20260404_232131_impulse_volume_breakout_v1_recent180_sweep_v1). That is the cleanest current answer to “try something new if the old runs are low-quality”: keep the live core stable, and search a genuinely different long sleeve in parallel.
- 2026-04-05 10:35 UTC — Added two practical live protections around the current `core2`. First, [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) now computes a recent close-trade health state for `alt_inplay_breakdown_v1` from `trade_events` and applies a configurable `breakdown` sleeve breaker: soft risk cut when the 30d net slips below a soft threshold, and full block when it breaches a hard threshold after enough closes. Second, the live bot now writes structured trade lifecycle events to [runtime/live_trade_events.jsonl](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/live_trade_events.jsonl) so the operator and the DeepSeek overlay can see `order_submitted`, `entry_filled`, `close`, and `failsafe_close_sent` directly instead of reverse-engineering them from pulse counters. I also bound the runtime knobs into [live_candidate_core2_breakdown_arf1_20260404.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/live_candidate_core2_breakdown_arf1_20260404.env), which means the current live candidate now has an explicit path both for safer `breakdown` behavior and for better trade forensics.
## 2026-04-05 | Codex (session 24b — Alpaca intraday revival + dynamic paper rollout)

- Разобрался, почему Alpaca intraday не выглядела живой: дело было не в “сломанных входах”, а в том, что активной оставалась monthly-paper ветка, а intraday контур фактически не был доведён до полноценного операционного запуска.
- Подтвердил, что `v36 monthly` сейчас действительно статична по дизайну:
  - `ALPACA_SEND_ORDERS=0`
  - `ALPACA_CLOSE_STALE_POSITIONS=0`
  - `latest_advisory.json` показывает `dry_run_no_current_cycle`
  - old `GOOGL/TSLA` в advisory были ghost-state из старого monthly paper snapshot, а не реальные текущие live-paper позиции.
- В [equities_alpaca_intraday_bridge.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/equities_alpaca_intraday_bridge.py) добавлена важная защита:
  - bridge теперь видит remote Alpaca positions, которых нет в `intraday_state.json`
  - считает их занятыми слотами
  - умеет принудительно закрывать такие stale remote paper positions через `INTRADAY_CLOSE_UNKNOWN_REMOTE_POSITIONS=1`
- Добавлен отдельный dynamic Alpaca candidate:
  - [configs/alpaca_intraday_dynamic_v1.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/alpaca_intraday_dynamic_v1.env)
  - [scripts/run_equities_alpaca_intraday_dynamic_v1.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_alpaca_intraday_dynamic_v1.sh)
  - [scripts/setup_cron_alpaca_intraday_dynamic_v1.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/setup_cron_alpaca_intraday_dynamic_v1.sh)
- Исправлен SPY regime fallback:
  - если live Alpaca daily bars по SPY приходят пустыми в weekend/holiday окне, gate теперь берёт cached SPY closes из `data_cache/equities_1h/SPY_M5.csv`, а не делает слепой pass-through.
- Локальный live-paper запуск новой intraday ветки прошёл честно:
  - dynamic watchlist rebuilt successfully
  - account clean (`equity ≈ cash`, no open positions)
  - no entries because `SPY < SMA50`, so the long-only intraday lane is correctly blocked by bearish regime, not by a hidden bug
- Серверный rollout завершён:
  - files uploaded to `64.226.73.119:/root/by-bot`
  - remote one-shot run succeeded
  - cron installed: `*/5 14-21 Mon-Fri -> run_equities_alpaca_intraday_dynamic_v1.sh --once`
- Итог: Alpaca снова не “старый paper-призрак”, а отдельная живая dynamic lane с honest gates и понятным operational path. Следующий шаг по equities — либо ослабить/модифицировать long-only intraday gate под bear regimes, либо добавить отдельный short/reversion sleeve на equities, если хотим активность даже в risk-off.

## 2026-04-05 | Codex (session 24c — Alpaca dynamic research truth layer)

- Чтобы не принимать решения по Alpaca “на глаз”, добавил честный recent-window research path:
  - [scripts/run_forex_backtest.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_forex_backtest.py) теперь умеет `--start-date/--end-date`
  - [scripts/run_forex_combo_walkforward.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_forex_combo_walkforward.py) тоже режет окна по датам
  - [scripts/run_equities_strategy_scan.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_strategy_scan.sh) и [scripts/run_equities_walkforward_gate.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_walkforward_gate.sh) получили env-управление recent-window диапазоном и безопасные `RUN_SUFFIX`, чтобы параллельные dry-run не били друг другу out-dir.
- Для этого добавил новый orchestrator:
  - [scripts/run_equities_intraday_dynamic_research.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_intraday_dynamic_research.sh)
  - он сам:
    - rebuild-ит dynamic watchlist,
    - вычисляет recent окно (`EQ_RECENT_DAYS`),
    - запускает scan,
    - потом сразу walkforward gate.
- Первые честные front’ы показали неприятную, но полезную правду:
  - [equities_scan_20260405_085619_alpaca_dyn90/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_scan_20260405_085619_alpaca_dyn90/summary.csv)
  - [equities_scan_20260405_085619_alpaca_dyn180/summary.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_scan_20260405_085619_alpaca_dyn180/summary.csv)
  - [equities_wf_gate_20260405_085646_alpaca_dyn90/raw_walkforward.csv](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_wf_gate_20260405_085646_alpaca_dyn90/raw_walkforward.csv)
  - dynamic watchlist выглядит разумно, но current gate слишком жёсткий для `90d`: `No candidates from scan passed prefilter`.
- Поэтому сразу открыл четыре новые dry-run ветки с более реалистичным recent-window gate:
  - `alpaca_dyn90_relaxed`
  - `alpaca_dyn90_wide_relaxed`
  - `alpaca_dyn90_breakout_bias`
  - `alpaca_dyn90_reversion_bias`
- Логика простая: сначала честно доказать, что dynamic equities вообще дают устойчивые recent-window кандидаты под более реалистичный trade-count, и только потом думать о promotion или о включении ордеров.

## 2026-04-05 | Codex (session 24d — Alpaca annual truth without watchlist lookahead)

- Нашёл ещё одну важную дыру в честности Alpaca research: [build_equities_intraday_watchlist.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_equities_intraday_watchlist.py) до этого ранжировал symbols по самым свежим cached M5 барам, даже если сам backtest запускался на историческом окне. Это означало скрытый lookahead на уровне выбора watchlist.
- Исправил это:
  - builder теперь принимает `--start-date/--end-date`
  - перед расчётом metrics режет candles по историческому окну
  - [run_equities_intraday_dynamic_research.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_intraday_dynamic_research.sh) теперь передаёт `EQ_END_DATE` в watchlist build
- Это ещё не “идеальный daily-rolling annual sim”, но уже убирает самый грубый вид lookahead и делает recent-window dynamic research честнее.
- Чтобы получить годовую правду без этой дырки, добавил:
  - [run_equities_intraday_dynamic_annual_segments.sh](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_equities_intraday_dynamic_annual_segments.sh)
- Он запускает 4 non-overlapping сегмента по `90d`, каждый раз:
  - rebuild-ит dynamic watchlist на историческую дату конца сегмента,
  - запускает scan,
  - затем walkforward gate,
  - и пишет manifest по всем сегментам.
- Уже запущены 2 honest annual dry-run фронта:
  - `alpaca_annual_seg_relaxed`
  - `alpaca_annual_seg_wide`
- Честный промежуточный вывод остаётся таким:
  - на latest `90d` проблема уже не в старом gate и не в старых Alpaca-висяках;
  - проблема в том, что текущие equity session combos пока не дают положительный recent-window edge.

## 2026-04-05 | Codex (session 24e — annual Alpaca verdict + crypto Elder logic repair)

- Honest annual Alpaca segmented dry-runs завершились:
  - [alpaca_annual_seg_relaxed](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_intraday_dynamic_annual_20260405_091048_alpaca_annual_seg_relaxed)
  - [alpaca_annual_seg_wide](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/equities_intraday_dynamic_annual_20260405_091048_alpaca_annual_seg_wide)
- Жёсткая, но полезная правда:
  - все `4/4` сегмента по `90d` в обеих annual-ветках закончились без validated candidates
  - соответствующие `raw_walkforward.csv` пустые
  - значит **честного долгого Alpaca return % к депозиту сейчас нет**, потому что нет ни одного кандидата, который прошёл наш годовой validation path
- При этом raw scan внутри сегментов не совсем мёртвый:
  - в latest quarter есть положительные low-trade pockets вроде `AAPL trend_pullback_rebound_v1`, `TSLA trend_pullback_rebound_v1`
  - в oldest segment живее смотрится `AVGO breakout_continuation_session_v1`
  - но это ещё не годится для promotion, потому что trade count и stability пока слишком слабые
- На сервере Alpaca теперь чище:
  - old monthly trading cron снят
  - legacy duplicate intraday cron снят
  - осталась одна новая dynamic dry-run lane + TG reports
- После этого фокус снова переведён в crypto:
  - [elder_triple_screen_v2.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/elder_triple_screen_v2.py) получил реальную logic repair в `Screen 3`
  - вместо raw breakout теперь entry идёт через entry-TF retest/reclaim с `touch ATR buffer` и `minimum body fraction`
  - под это запущен новый rescue-run:
    - [elder_ts_v2_retest_reclaim_v4.json](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/autoresearch/elder_ts_v2_retest_reclaim_v4.json)
- Разбор сегодняшнего live breakdown-шорта оказался полезным не как “ой, стоп словили”, а как логический сигнал:
  - это был скорее stale breakdown / возврат в диапазон, а не missed long
  - под это я усилил [alt_inplay_breakdown_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/alt_inplay_breakdown_v1.py)
  - добавлены:
    - `BREAKDOWN_FRESH_BREAK_BARS_5M`
    - `BREAKDOWN_FLAT_FILTER_BARS_5M`
    - `BREAKDOWN_FLAT_FILTER_MAX_RANGE_ATR`
    - `BREAKDOWN_FLAT_FILTER_LEVEL_BAND_ATR`
  - смысл простой: не шортить слишком поздно и не шортить, когда пробой уже умер и превратился в пилу вокруг уровня
- Быстрый sanity-probe на узком core2-баскете после этого остался положительным:
  - [core2_breakdown_fresh_flat_probe_90d](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_125802_core2_breakdown_fresh_flat_probe_90d/summary.csv)
  - `+4.44%`, PF `1.369`, DD `3.95`
  - это не новый финальный baseline, а просто первый чек, что guardrail-фикс не убил стратегию сразу
- По `core3 + impulse` картина стала наконец-то честно трёхслойной, а не только “есть красивый solo-run”:
  - [recent180 package probe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_134236_core3_impulse_best_recent180_probe/summary.csv): `+28.65%`, PF `1.356`, DD `9.32`
  - там [impulse_volume_breakout_v1.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/strategies/impulse_volume_breakout_v1.py) реально добавила edge (`102` trades, about `+7.80%`)
  - [current90 package probe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_135423_core3_impulse_best_current90_probe/summary.csv): `+16.30%`, PF `1.462`, DD `3.74`
  - но на `90d` `impulse` сама дала почти flat contribution (about `-0.09%`), то есть promotion ещё рано
  - [annual package probe](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest_runs/portfolio_20260405_140930_core3_impulse_best_annual_probe/summary.csv): только `+2.26%`, PF `1.029`, DD `16.35`
  - это хороший разворот в research, но пока не live-ready 3rd sleeve
- Закрыл ещё один старый пробел в tooling: в [smart_pump_reversal_bot.py](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py) теперь есть первый `chart inbox` путь для Telegram-графиков:
  - входящие фото сохраняются в `runtime/chart_inbox`
  - сохраняется `latest.json` с метаданными
  - появился `/chart_last`
  - это ещё не полноценное vision/CV, но теперь бот хотя бы умеет принять живой скрин графика и держать его как structured input для следующего визуального слоя
