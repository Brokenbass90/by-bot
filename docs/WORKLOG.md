# Bybit bot (v28) — worklog / reminders

## Цель
Собрать набор из 3–4 стратегий, которые в портфельном бэктесте (5m, Bybit linear USDT) дают стабильный плюс, с понятным управлением риском и возможностью «тянуть» прибыль (runner-выход), а не брать микропрофит.

## Стратегии в коде
- **inplay (retest)** — breakout + retest на выбранном TF (по умолчанию 15m). Выход может быть «runner» (partials + trail + time-stop) или простой.
- **pump_fade** — вход против резкого импульса/«перегрева» (режимная стратегия).
- **bounce** — отскок от горизонтальных S/R уровней (пивоты 1h, кластеризация), подтверждение свечой на 5m.
- **range** — торговля диапазона 1h, подтверждение на 5m.

## Важные ограничения
- Бэктест использует **OHLC(V)** и индикаторы (ATR/EMA/RSI и т.п.). **Стакан/лента** в бэктесте не используются.
- Для L2/Order Book исторических данных честный бэктест без собственной записи невозможен.

## Что поменяно в v28_15
- Добавлен алиас **INPLAY_REGIME=1** (включает режимный фильтр inplay через EMA), чтобы не путаться с INPLAY_REGIME_MODE.
- Добавлен фильтр **INPLAY_MIN_STOP_PCT / INPLAY_MAX_STOP_PCT** (отрезает микростопы/слишком широкие стопы).
- Добавлены удобные скрипты:
  - `scripts/run_core_suite.sh` — портфельный прогон + baselines по тем же символам
  - `scripts/prune_backtest_runs.sh` — чистка старых прогонов (оставить N последних)
  - `scripts/run_baselines_30d.sh` теперь принимает и путь к `summary.csv`, и папку прогона

## Следующий шаг (практика)
1) Доводим **inplay runner**:
   - включаем режимный фильтр (bear: short-only)
   - уменьшаем количество входов (жёстче `INPLAY_IMPULSE_ATR_MULT`, `INPLAY_RETEST_MAX_AWAY_ATR`, `INPLAY_REGIME_MIN_GAP_ATR`)
   - делаем «тягу» менее нервной (увеличить `INPLAY_TRAIL_ATR_MULT`, пересобрать partials)
2) Держим **pump_fade** как режимный модуль (включать только при явных импульсах/перегреве).
3) **range** — ослабляем условия, добиваемся хотя бы стабильного количества сделок.
4) **bounce** — пока только под жёсткими фильтрами (или выключен), т.к. на «трендовом» рынке он обычно пилится.

---

## 2026-02-14 — Старт ревью (контекст + bounce)
- Прочитаны ключевые документы: `docs/CONTEXT.md`, `docs/WORKLOG.md`, `docs/INPLAY_RUNNER.md`, `docs/strategies_live.md`, `bybit_bot_context_summary.md`.
- Зафиксировано: в бою сейчас тест на 2 недели с риском **0.5%** на сделку (обновить live .env при необходимости).
- Старые бэктесты в `/Users/nikolay.bulgakov/Documents/Work/bot-new/old-tests`: всего 72 прогона, `summary.csv` есть в 62, `params.json` только в 4 (многие старые настройки восстановить нельзя).
- Просмотрены bounce-модули:
  - backtest: `strategies/bounce_bt.py` и `strategies/bounce_bt_v2.py`
  - live: `sr_bounce.py` + wiring в `smart_pump_reversal_bot.py`
- Следующий фокус: понять, какие фильтры/параметры в live bounce можно ужесточить/перестроить, и сравнить с backtest-аппроксимацией (bounce_bt_v2).
- Сводка по old-tests (портфельные summary.csv, 58 прогонов):
  - Лучшие net_pnl: `combo_inplay_breakout_180d`, `combo_inplay_breakout_360d`, `probe_combo_inplay_breakout_180d_clean8`, `probe_breakout_180d_clean8`, `probe_breakout_60d_clean8`.
  - Устойчивые кандидаты: `inplay_breakout` и комбо `inplay + inplay_breakout` (особенно на clean-universe).
  - Сильно отрицательные: `bounce` (60d), `retest_levels`, `trend_pullback`, `inplay_breakout` без фильтрации.

## 2026-02-14 — Live .env snapshot (последний использованный)
- `ENABLE_INPLAY_TRADING=0`
- `ENABLE_BREAKOUT_TRADING=1`
- `ENABLE_RETEST_TRADING=0`
- `ENABLE_RANGE_TRADING` не задан (по умолчанию выключен).
- `BREAKOUT_TOP_N=16`, `BREAKOUT_TRY_EVERY_SEC=30`
- `SYMBOL_FILTERS_PATH=/tmp/bybot_symbol_filters.json`
- `SYMBOL_ALLOWLIST` задан (16 тикеров), `SYMBOL_DENYLIST` пуст
- `RECO_ENABLE=1`, `RECO_PERIOD_SEC=604800`, `RECO_LOOKBACK_DAYS=60`, `RECO_WORST_N=3`, `RECO_MIN_TRADES=8`, `RECO_STRATEGIES=inplay_breakout`
- Risk: `risk_pct=0.005` (0.5%), `bot_capital_usd=100`, `max_positions=3`, `min_notional_usd=18.0`
- `bounce_execute_trades=false` (bounce выключен)

## 2026-02-14 — Динамический фильтр символов (начало)
- В `smart_pump_reversal_bot.py` добавлена поддержка per-strategy фильтров в `SYMBOL_FILTERS_PATH`:
  - Формат теперь поддерживает `per_strategy` с `allowlist/denylist` по стратегиям.
  - Применение: сначала базовый фильтр, затем конкретный для `breakout/inplay/retest/range/bounce`.
- Добавлен генератор фильтров: `scripts/build_symbol_filters.py`.
- Добавлены профили фильтров: `configs/symbol_filters_profiles.json` (пороговые значения — стартовые).
- Генератор поддерживает офлайн-режим через `--cache_dir data_cache` (без Bybit API).
- В Telegram будут добавлены команды `/filters` и `/filters_build`.

## 2026-02-14 — Сервер и git (фиксация)
- Сервер: DigitalOcean droplet `ubuntu-s-1vcpu-1gb-fra1-01`, IP `64.226.73.119`, Ubuntu 24.04 LTS.
- SSH попытка `root@64.226.73.119` дала `Permission denied (publickey)` — нужно проверить ключ/юзера.
- Git remote: `https://github.com/Brokenbass90/by-bot` (ветка `codex/dynamic-symbol-filters`).
- Локальные SSH-ключи: `~/.ssh/by-bot` и `~/.ssh/by-bot.pub`.
## 2026-02-16 — Сервер: выкладка ветки и инцидент
- SSH вход успешен: `ssh -i ~/.ssh/by-bot root@64.226.73.119`.
- На `main` были локальные изменения `smart_pump_reversal_bot.py` и `trades.db`, сделали `git stash push -m "server-local-changes-before-codex"`.
- Перешли на `codex/dynamic-symbol-filters`, фильтры сгенерированы на сервере (base_allow≈35).
- При рестарте сервис падает с `SyntaxError` в `smart_pump_reversal_bot.py` около строки ~737 — нужна проверка и исправление файла на сервере.
- `.env` на сервере несколько раз повреждался из-за некорректной вставки here-doc; нужно перезаписать аккуратно.
## 2026-02-16 — Breakout фильтры и спред
- В конфиге фильтров ужесточаем breakout: `min_turnover=50M`, `min_atr_pct=0.55`, `top_n=20`.
- Добавляем спред‑фильтр для breakout (по orderbook, % от mid), чтобы избегать сильного проскальзывания.
- Изменения пока не подтянуты на сервер (нужно push и pull).

## 2026-02-17 — Сервер после фиксов
- Ветка сервера: `codex/dynamic-symbol-filters`, head `b098249` (fix escaped f-string).
- Сервис `bybot` запущен стабильно (последние `SyntaxError` в `journalctl` были историческими до фикса).
- В `.env` включен `BREAKOUT_MAX_SPREAD_PCT=0.20`.
- Фильтры пересобраны: `base_allow=34`, `breakout_allow=18`, `inplay_allow=34`, `range_allow=34`, `bounce_allow=30`.
- Live PnL за 7 дней (`trade_events`, `event='CLOSE'`): `inplay_breakout` — 14 сделок, `sum_pnl=-2.353697`, winrate `35.71%`.
- Топ-убыточные символы за 7 дней: `SIRENUSDT (-1.305544)`, `BCHUSDT (-1.079424)`.
- Проверка лога после фикса: старые `SyntaxError` до 00:39 были в истории рестартов; после запуска в 00:45 бот работает, подключен к WS, принимает трейды.

## 2026-02-17 — План, этап 4 (фильтр)
- Добавлена команда `/health` (killers/winners + текущие критерии base/breakout).
- Добавлен фоновый `symbol_filters_loop`: периодическая пересборка фильтра (`FILTERS_AUTO_BUILD`) и refresh universe без ручного рестарта.

## 2026-02-17 — Журнал: политика свертывания
- Введено правило журнала: пока фича в работе — короткие шаги; после завершения — оставить одну итоговую строку в разделе "Готово".
- Это правило применяем ко всем следующим задачам (визуализация, range, наклонки, динамический фильтр).
- 2026-02-17 13:47 UTC | filter-audit | Проверена интеграция автообновления фильтров и /health в коде (поиск ключевых точек) | done
- 2026-02-17 13:53 UTC | viz | Добавлена авто-визуализация ENTRY/CLOSE (PNG, уровни entry/tp/sl/exit) и отправка в Telegram | done
- 2026-02-17 13:59 UTC | viz | Добавлена TG-команда /plotlast [SYM] для графика последней закрытой сделки | done
- 2026-02-17 14:10 UTC | deploy | Проверка: /plotlast есть в origin, диагностика сервера где команда еще Unknown | in_progress
- 2026-02-17 14:13 UTC | viz | /plotlast: добавлен fallback на Bybit 5m kline при пустом локальном буфере | done
- 2026-02-17 14:33 UTC | viz | /plotlast: добавлен второй fallback (latest bars без time range) + лог retCode | done
