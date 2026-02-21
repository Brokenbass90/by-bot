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
- 2026-02-17 14:40 UTC | viz | FIX: /plotlast Bybit fallback использовал undefined BYBIT_BASE; переключено на TRADE_CLIENT.base/BYBIT_BASE_DEFAULT | done
- 2026-02-17 14:57 UTC | viz | Улучшен стиль графика: dark candlesticks, entry/exit markers, TP/SL линии, контекстные уровни, инфоблок | done
- 2026-02-17 15:07 UTC | analysis | Добавлен scripts/analyze_entry_quality.py (late-entry/adverse/favorable move audit по CLOSE/ENTRY) | done
- 2026-02-17 15:16 UTC | breakout | Добавлены: retest-confirm, max-chase guard, ATR-floor для SL, cooldown после SL, killer-guard skip | done
- 2026-02-17 15:24 UTC | range | FIX: confirm_limit вынесен в env (default 40) + ATR/RR/reclaim/wick/sl-width параметры для live RangeStrategy | done
- 2026-02-18 10:05 UTC | range | FIX backtest wrapper: range TTL>0 (иначе диапазон тух сразу) + корректный reason + мягче дефолты; v4 дал 262 trades, net -36.05 (отклонено) | done
- 2026-02-18 10:33 UTC | range | Перепил: scan_tf/confirm_tf вынесены в env; RANGE_MIN_RR поднят до 3.0 (TP >= 3x risk) | done
- 2026-02-18 11:27 UTC | range | v7: добавлены anti-chop фильтры в wrapper (allow/deny, regime gate, cooldown bars, max signals/day) | done
- 2026-02-18 11:27 UTC | range | bugfix: восстановлен _env_float в strategies/range_wrapper.py (иначе RANGE_MIN_RR становился None) | done
- 2026-02-18 11:27 UTC | range | backtest 60d range_v7_antichop_60d: trades=7 net=-1.58 PF=0.461 DD=1.58 (существенно лучше по риску, но still <0) | done
- 2026-02-18 19:58 UTC | range | backtest 60d range_v9_tf15_box_60d: trades=0 net=0.00 (слишком жестко) | done
- 2026-02-18 20:12 UTC | range | backtest 180d range_v9_tf15_box_180d: trades=0 net=0.00 | done
- 2026-02-18 20:13 UTC | range | backtest 60d range_v10_tf5_tight_rr3_60d: trades=0 net=0.00 | done
- 2026-02-18 20:24 UTC | range | backtest 180d range_v8_tf15_strict_180d_rerun: trades=1 net=+0.49 PF=inf (стат. недостаточно) | done
- 2026-02-18 20:30 UTC | range | backtest 180d range_v13_tf15_relaxed_180d: trades=60 net=-6.59 PF=0.698 DD=9.47 | done
- 2026-02-18 20:33 UTC | range | backtest 180d range_v14_tf15_relaxed_rr12_180d: trades=87 net=-11.47 PF=0.640 DD=14.63 | done
- 2026-02-18 20:38 UTC | range | backtest 60d range_v13_tf15_relaxed_60d: trades=17 net=-3.93 PF=0.419 DD=4.83 | done
- 2026-02-18 20:44 UTC | tg | Добавлена команда /stats (алиас /report) с периодами 1/7/30/90/365 и отправкой text+csv+png отчёта | done
- 2026-02-18 21:08 UTC | range | Перепил логики входа: require_prev_sweep + фильтр импульсной свечи (body<=ATR*mult), прокинуты env RANGE_REQUIRE_PREV_SWEEP и RANGE_IMPULSE_BODY_ATR_MAX | done
- 2026-02-18 21:14 UTC | range | backtest 60d range_v15_reentry_impulse_60d: trades=20 net=-5.14 PF=0.357 DD=7.20 | done
- 2026-02-18 21:14 UTC | range | backtest 180d range_v15_reentry_impulse_180d: trades=50 net=+2.95 PF=1.184 DD=3.56 (месяцы: 4/6 в плюс) | done
- 2026-02-18 22:07 UTC | range | v16 adaptive: добавлены режимы волатильности (adaptive RR + adaptive impulse filter) через env-параметры | done
- 2026-02-18 22:07 UTC | range | backtest 60d range_v16_adaptive_60d: trades=20 net=-3.58 PF=0.523 DD=6.73 (лучше v15, но <0) | done
- 2026-02-18 22:07 UTC | range | backtest 180d range_v16_adaptive_180d: trades=39 net=+4.05 PF=1.342 DD=4.38 (лучше v15 по PF и net) | done
- 2026-02-18 23:16 UTC | range | v17 adaptive TP (tp_mode=frac + tp_frac by regime): 60d net=-4.17 PF=0.500; 180d net=-0.94 PF=0.945 — хуже v16, не брать в прод | done
- 2026-02-18 23:28 UTC | audit | quick audit inplay_breakout 7/30d: trades=17 net=-2.3075 winrate=41.18%; reason SL=10 trades net=-3.3905; top losers SIRENUSDT (-1.3055) и BCHUSDT (-1.0794) | done
- 2026-02-18 23:29 UTC | plan | range-направление не закрыто: вернуться после блока "наклонки"; дополнительно исследовать отскоки вне классического флэта и пробойные сценарии на базе range-структур | todo
- 2026-02-18 23:32 UTC | slope | первичный бэктест trend_pullback: 60d net=+2.36 PF=1.263 DD=3.45; 180d net=-3.03 PF=0.916 DD=17.34 (нестабильно) | done
- 2026-02-19 01:40 UTC | slope | v2 trend_pullback: усилены фильтры тренда/наклона, подтверждение reclaim через пересечение EMA, лимит сделок/день, ATR-режим и denylist символов | in_progress
- 2026-02-19 02:12 UTC | slope | диагностика v2: перефильтрация (часто 0 сделок); контрольный ultra-relaxed даёт сигналы, значит проблема в жёстких gate, а не в пайплайне исполнения | done
- 2026-02-19 02:13 UTC | slope | v4 тесты (60d): v4a trades=0; v4b_notouch trades=1 net=-0.45; v4c_freq trades=27 net=-5.87 PF=0.414 — нужен промежуточный режим между v4b и v4c | in_progress
- 2026-02-19 09:20 UTC | viz | улучшен trade chart: явные подписи линий ENTRY/TP/SL/EXIT, подписи entry/exit вертикалей; добавлена команда /plotts SYMBOL CLOSE_TS для точечного разбора конкретной сделки | done
- 2026-02-19 09:46 UTC | viz | trade chart v2: добавлены entry/exit треугольники (buy/sell), легенда линий, и BRK_REF (опорный уровень prior 20-bar) для inplay_breakout | done
- 2026-02-19 09:58 UTC | viz | trade chart v3: фиксация рассинхрона marker/line (маркеры теперь на фактических entry/exit ценах), добавлены MFE/MAE(1h) и Late vs BRK_REF в инфоблок для быстрой диагностики качества входа | done
- 2026-02-19 10:20 UTC | breakout | inplay_breakout: добавлены anti-late/anti-fomo guards (late_vs_ref + min pullback), включен runner-режим выходов для breakout (partials+trail), добавлен timing-лог (sig→send, send→fill, fill→close) в ENTRY/CLOSE уведомления | done
- 2026-02-19 10:28 UTC | analytics | добавлен scripts/monthly_pnl.py для помесячного среза trades.csv (trades/winrate/net/PF + overall max_dd_usdt) | done
- 2026-02-20 16:20 UTC | filters | добавлен scripts/update_filters_from_trades.py: strategy-aware denylist из trades.csv (min-trades/max-net, dry-run), для обновления per_strategy фильтров | done

## 2026-02-18 — Стратегический план (долгий горизонт)
- Цель проекта: дотянуть систему до самообучаемого торгового контура с контролем риска и регулярной переоценкой качества сигналов.
- Архитектурная цель: не “один бот”, а модульная платформа (сбор данных, бэктест, ранжирование стратегий, риск-менеджер, live-исполнение, отчётность).
- Рынки развития после стабилизации в крипте: Forex/валютные пары, золото, акции; отдельно исследовать арбитражные сценарии.
- Экономическая модель: допускается высокий бюджет инфраструктуры/разработки при условии устойчивого положительного матожидания и контролируемой просадки.
- Операционный принцип: часть прибыли системно реинвестируется в поддержку, развитие и улучшение инфраструктуры.

## 2026-02-20 — Inplay v10 stabilization
- 2026-02-20 18:50 UTC | inplay | v7 (inplay universe=40): v7a 360d net=+23.39 PF=5.18 DD=2.15%; v7b net=+19.52 PF=4.40 DD=2.28% | done
- 2026-02-20 18:59 UTC | filters | smart deny (single-run) на inplay: удалён HYPEUSDT, v8 360d net=+24.47 PF=6.43 DD=1.26% | done
- 2026-02-20 19:06 UTC | filters | combo deny (v7a+v8+v9): deny BCH/ESP/FARTCOIN/INJ/RAVE; v10 360d net=+26.79 PF=20.37 DD=0.52% | done
- 2026-02-20 23:58 UTC | robustness | v10 окна: 120d +6.69, 180d +7.27, 240d +8.76, 300d +8.18; есть убыточные месяцы в отдельных окнах, но net>0 на всех | done
- 2026-02-20 23:59 UTC | baseline | зафиксирован baseline inplay_v10_combo_deny_360d в baselines/ + snapshot filters + commit e6d6e28 | done
- 2026-02-21 00:20 UTC | range-short | старт блока adaptive_range_short: добавлен новый модуль стратегии и интеграция в run_portfolio CLI/selector | in_progress
