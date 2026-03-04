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
- 2026-02-22 12:15 UTC | pump_fade | добавлены env-overrides (PF_*) для быстрого тюнинга без правок кода | done
- 2026-02-22 18:30 UTC | pump_fade | v6 logicfix: added level/reversal gates (entry min/max drop, bearish body confirms), runner exits (partials+ATR trail+time-stop) via PF_* envs | done
- 2026-02-22 18:58 UTC | pump_fade | baseline fixed: pf_v4c_240d (net=+7.81, PF=1.883, DD=3.77, ~+0.98%%/month over 240d) | done
- 2026-02-22 19:10 UTC | pump_fade | v7 spike-only mode added (PF_SPIKE_ONLY + spike thresholds/last-leg gate); fixed scripts/plot_trade_bybit.py base URL bug for backtest trade visualization | done
- 2026-02-22 19:25 UTC | live | anti-spam fix: BREAKOUT killer-guard skip notifications throttled per-symbol (KILLER_GUARD_LOG_EVERY_SEC, default 300s) | done
- 2026-02-24 00:00 UTC | smart_grid | added new range mean-reversion grid-like strategy (long/short, zone-based entries, ATR SL, 2 partial TPs), integrated into backtest/run_portfolio.py via --strategies smart_grid | done
- 2026-02-24 00:00 UTC | range_bounce | added new level-bounce strategy (touch-count + volume context + rejection candle, long/short) and integrated into backtest/run_portfolio.py via --strategies range_bounce | done
- 2026-02-24 00:00 UTC | roadmap | accepted next R&D queue: (1) HTF trend pullback 4h/1h (BTC/ETH/SOL), (2) Donchian 20/55 breakout, (3) volatility expansion (ATR/BB squeeze->breakout), (4) funding/OI filter module, (5) BTC regime master-filter for alts; news layer planned as optional toggleable module after price-action stack | planned
- 2026-02-24 00:00 UTC | trend_pullback/trend_breakout | screened as R&D candidates: trend_pullback strongly negative; trend_breakout proxy produced 0 trades on BTC/ETH/SOL for 180d/360d at current defaults | done\n
- 2026-02-24 00:00 UTC | donchian_breakout | added new HTF Donchian breakout candidate (55 channel + EMA filter + ATR SL + RR target), integrated into backtest/run_portfolio.py via --strategies donchian_breakout | done\n
- 2026-02-24 00:00 UTC | strategy-screen | range_bounce v1/v2 screened on 180d/360d: persistent negative PF (<1), rejected for live; donchian_breakout v1 screened on 180d/360d(+stress): negative PF, rejected for live; inplay vs inplay_breakout head-to-head: breakout strongly superior and remains core | done\n
- 2026-02-24 00:00 UTC | roadmap-priority | priorities updated: P1 BTC regime master-filter (portfolio gate), P2 volatility expansion candidate (vol_breakout tuning/screen), P3 session/seasonality filters, P4 liquidation-event setup, P5 funding/OI module (optional), P6 pairs/stat-arb R&D, P7 optional news layer (toggleable) | planned\n
- 2026-02-24 00:00 UTC | core-improvements | queued implementation items for live core: session filter, spread/liquidity filters, soft BTC-regime as position-size multiplier (not hard gate), and slippage control guards | planned\n
- 2026-02-24 00:00 UTC | midterm-screen | donchian_breakout 4h v1 screen on BTC/ETH/SOL (360d): base +3.48 USDT, stress +2.38 USDT, 66 trades/year, max DD ~3-3.5 USDT; weak but resilient candidate for further tuning | done\n
- 2026-02-24 00:00 UTC | donchian_breakout v2 | upgraded medium-term candidate: one-signal-per-new-HTF-bar, ATR%% and volume breakout filters, EMA-distance/slope guard, TP1/TP2 partials + ATR trailing + time stop, cooldown interpreted in HTF bars | done
- 2026-02-24 00:00 UTC | donchian_breakout v2 | screen result: fail (360d base/stress both negative, 28 trades, 0% winrate), archived as R&D with potential revisit later | done\n
- 2026-02-24 00:00 UTC | session-filter | added session gating to backtest/run_portfolio.py (SESSION_FILTER_ENABLE, SESSION_FILTER_ALLOWED, SESSION_ALLOWED_<STRATEGY>) with UTC windows: asia/europe/us | done\n

- 2026-02-25 06:20 UTC | context | Product snapshot recorded for handoff/new chat continuity.
  Product: Bybit futures trading bot (`smart_pump_reversal_bot.py`) with live execution, Telegram notifications, dynamic symbol filters, and backtest framework (`backtest/run_portfolio.py`).
  Current live mode: breakout enabled, pump_fade disabled temporarily, inplay/retest/range disabled. Dynamic filter auto-build/auto-refresh enabled every 1800s.
  Current known status: `inplay_breakout` shows strong base backtests but degrades under stress-cost assumptions; `pump_fade` currently underperforming / low signal frequency and moved to R&D.
  Infra: Bybit WS stability tuning in progress (TOP_N/SHARD/BATCH/PING params via `.env`), monitored via journalctl counts for keepalive timeouts and ENTRY/CLOSED events.

- 2026-02-25 06:20 UTC | roadmap | Mandatory cleanup TODO added.
  TODO (project hygiene):
  1) inventory and remove/archive obsolete backtest runs (keep baselines only),
  2) clean stale cache artifacts (`data_cache`, `.cache/klines`) by retention policy,
  3) normalize env templates and remove dead vars,
  4) consolidate strategy docs + decision log,
  5) prune unused scripts/modules after PF v2 and core baseline are finalized.
- 2026-02-25 06:35 UTC | pump_fade v2 | added exhaustion gates to strategy (`PF_USE_EXHAUSTION_FILTER`, `PF_EXHAUSTION_BODY_TO_WICK_MAX`, `PF_EXHAUSTION_VOL_DROP_RATIO`), wired volume stream into signal logic, kept compatibility via maybe_signal() pass-through | done
- 2026-02-25 06:55 UTC | handoff summary | Consolidated status for next-chat continuity.
  Bot product: automated Bybit USDT-perp trading system with live execution (`smart_pump_reversal_bot.py`), strategy toggles via `.env`, dynamic symbol filtering, Telegram reporting, and portfolio backtesting (`backtest/run_portfolio.py`).
  Live config now: breakout ON, pump_fade OFF (temporary), inplay/retest/range OFF; dynamic filter auto build+refresh every 1800s; WS shard/batch tuning applied for stability.
  Proven by recent tests: `inplay_breakout` remains the only currently robust alpha source in base-cost runs; legacy `inplay` underperforms; `pump_fade` v1/v2 currently non-viable (low trade count and negative 180/360d).
  Key risk observed: severe degradation under stress execution assumptions (high fee+slippage), indicating execution-cost sensitivity.
  Decision: keep live conservative (breakout-only) while running PF v3 redesign in R&D and preparing a second non-correlated strategy candidate.
  Immediate next tasks: (1) breakout execution hardening (spread/liquidity/slippage guards), (2) PF v3 new hypothesis with explicit skip-reason diagnostics, (3) project cleanup pass (archive old runs, cache retention, env/doc normalization).
- 2026-02-25 07:30 UTC | pump_fade v3 diagnostics | added explicit skip_reason counters in strategies/pump_fade.py and aggregated export in backtest/run_portfolio.py (pump_fade_skip_reasons.csv with per-symbol and TOTAL breakdown + signals_emitted) for PF hypothesis debugging | done
- 2026-02-25 07:57 UTC | live/ws hardening | bybit WS reconnect loop hardened in smart_pump_reversal_bot.py: first-connect stagger only, fast reconnect path for ConnectionClosed/Reset/OSError, env-configurable reconnect/open/close timeouts (BYBIT_WS_RECONNECT_* / BYBIT_WS_OPEN_TIMEOUT / BYBIT_WS_CLOSE_TIMEOUT), reduced traceback noise for transient disconnects | done
- 2026-02-25 08:03 UTC | breakout yield-upgrade | added quality-based dynamic sizing for inplay_breakout entries in smart_pump_reversal_bot.py (BREAKOUT_SIZEUP_ENABLE, BREAKOUT_SIZEUP_MAX_MULT, BREAKOUT_SIZEUP_MIN_SCORE). Size multiplier uses chase/late/spread/pullback quality and applies only within existing risk/cap model; entry message now shows size_mult | done
- 2026-02-25 08:14 UTC | breakout hardening | added liquidity guard for live inplay_breakout entries: BREAKOUT_MIN_QUOTE_5M_USD (default 70000). Entry now skipped on thin 5m tape to reduce slippage/noise fills; works alongside spread/chase/late/pullback gates and quality size-up. | done
- 2026-02-25 08:22 UTC | pf_v3 diagnostics | fresh 120d base/stress with skip_reason export: dominant skips NO_PUMP_DETECTED, RSI_NOT_OVERBOUGHT, ENTRY_TOO_EARLY. PF v3a (adaptive min_drop + RSI override) had near-zero impact (2 trades, unchanged pnl). PF v3b (pump detection by window highs) increased frequency (2->4 trades) but worsened pnl (base -0.37, stress -0.55), rejected for live and kept in R&D only | done
- 2026-02-25 08:22 UTC | portfolio screen | inplay_breakout + smart_grid (fixed 10-symbol universe, 120d): combo collapsed (base net -48.79, stress -95.66, DD up to 95.8%). Strategy attribution: smart_grid strongly negative (base -100.18; stress -94.43) while inplay_breakout alone remained strong (base +82.58; stress +9.60). smart_grid rejected as diversification candidate in current form | done
- 2026-02-25 08:25 UTC | breakout session filter R&D | added live env-gated session filter for breakout (`BREAKOUT_SESSION_FILTER_ENABLE`, `BREAKOUT_SESSION_ALLOWED`) and tested in backtest via SESSION_ALLOWED_INPLAY_BREAKOUT=europe,us on fixed 10-symbol universe (120d): base net +51.66 vs +82.58 (lower return), but stress improved +15.12 vs +9.60 with better PF (1.27 vs 1.095) and lower DD (7.11 vs 9.66); candidate as robustness mode for live if we prioritize stress resilience | done
- 2026-02-25 09:32 UTC | midterm R&D | added new strategy module strategies/btc_eth_midterm_pullback.py (BTC/ETH only): 4h trend regime (EMA50/EMA200 + slope) with 1h pullback/reclaim entries, ATR+swing SL, RR target, cooldown and daily signal cap; integrated into backtest/run_portfolio.py as btc_eth_midterm_pullback | done
- 2026-02-25 09:32 UTC | midterm screen | mtpb_v1 on BTC/ETH 360d: base +24.50 PF=1.281 DD=7.46, stress -3.57 PF=0.961 DD=11.99; session eu/us variant underperformed stress. Tuned conservative v2c (slope/reclaim/cooldown): base +23.43 PF=1.462 DD=5.22, stress +5.87 PF=1.106 DD=6.76 (improved robustness, stress turned positive) | done
- 2026-02-25 09:46 UTC | midterm tuning | tested mtpb_v3 (runner exits + extra filters): overtrading/regression (base -6.64, stress -44.94), rejected. Set strategy defaults to conservative profile (v2c-like): slope=0.40, reclaim=0.12, max_pullback=1.00, cooldown=72, runner disabled by default. New default results on BTC/ETH 360d: base +24.08 PF=1.480 DD=5.22, stress +6.46 PF=1.118 DD=6.76 | done
- 2026-02-25 09:46 UTC | sizing scenarios | mtpb default with 2000 USDT / 3x: r=0.5% -> base +481.58, stress +129.13; r=1.0% -> base +963.39, stress +246.55; drawdown increases materially with higher risk (about 5.22%->9.84% base and 6.76%->12.83% stress) | done
- 2026-02-25 10:00 UTC | midterm v2d sweep | evaluated 4 conservative parameter sets (a/b/c/d) for btc_eth_midterm_pullback on BTC/ETH 360d base+stress. Best profile: v2d-a (slope=0.45, reclaim=0.15, max_pullback=0.90, cooldown=84) with base +23.69 PF=1.686 DD=4.00 and stress +11.06 PF=1.288 DD=5.40; 106 trades, 3 negative months in base and 4 in stress | done
- 2026-02-25 10:00 UTC | midterm defaults updated | set btc_eth_midterm_pullback defaults to v2d-a profile and re-validated 360d: base +23.69, stress +11.06. Scenario sizing (2000 USDT, 3x): risk 0.5%% -> base +473.83, stress +221.15; risk 1.0%% -> base +1004.83, stress +472.15 with higher DD (~7.53 base / ~10.35 stress) | done
- 2026-02-25 10:12 UTC | live integration | integrated BTC/ETH midterm strategy into live bot: added MidtermLiveEngine (midterm_live.py), new env toggles (ENABLE_MIDTERM_TRADING, MIDTERM_TRY_EVERY_SEC, MIDTERM_NOTIONAL_MULT, MIDTERM_SYMBOLS), dedicated entry path try_midterm_entry_async with risk-sized notional * alloc multiplier, universe alignment (MIDTERM_ACTIVE_SYMBOLS), and startup/status reporting updates; default remains OFF until env enable | done
- 2026-02-25 18:36 UTC | ml-dataset | upgraded ml_samples close logging: merge close-time features into feature_json (close_reason/close_session/close_hour_utc + entry_to_close_sec/fill_to_close_sec/send_to_fill_sec), preserving entry features for training exports | done
- 2026-02-25 18:37 UTC | btc_eth screen | 360d BTC/ETH scan (base fee/slip 6/2, stress 10/10): midterm_pullback remained positive (base +12.46, stress +5.64), trend_breakout/range_bounce produced 0 trades, donchian_breakout negative in both; midterm retained as active R&D/live candidate | done
- 2026-02-25 18:38 UTC | vol_expansion R&D | btc_eth_vol_expansion v1 rejected: 360d base -73.44, stress -95.98, deep DD; archived as failed hypothesis | done
- 2026-02-25 18:39 UTC | new strategy R&D | added btc_eth_trend_rsi_reentry (trend + RSI pullback reclaim, long/short) and integrated into backtest/run_portfolio.py; 360d results negative in v1 (base -3.58, stress -17.67) and stricter v1b (base -5.06, stress -7.70), rejected for live | done
- 2026-02-25 18:51 UTC | pump_fade v3 redesign | implemented PF_V3 mode in strategies/pump_fade.py (peak-recent pump detection, RSI peak->reentry transition, EMA bearish gate, configurable reversal body/confirm bars, volume climax->fade checks, separate v3 RR/SL params, full skip_reason diagnostics retained) | done
- 2026-02-25 18:52 UTC | pump_fade v3 sweep | 360d PF-only universe (10 symbols) quick grid A..F: best base profile = B (PF_V3_PUMP_THRESHOLD_PCT=0.07, MIN_DROP=0.003, MAX_DROP=0.12, RSI_PEAK_MIN=70, RSI_REENTRY_MAX=65, REVERSAL_BARS=1, BODY_MIN_FRAC=0.20, RR=1.4) => base +2.10 (121 trades, PF 1.208, DD 2.34) | done
- 2026-02-25 18:53 UTC | pump_fade v3 stress check | profile B on stress costs: +0.01 (121 trades, PF 1.001, DD 3.14), materially better than prior PF v2/v3 defaults (negative), but still near-flat and not yet strong enough for live capital increase | done
- 2026-02-25 19:05 UTC | pump_fade v3.1 | added regime filters to PF v3: session gate (PF_V3_SESSIONS_ALLOWED) + ATR%% band (PF_V3_MIN_ATR_PCT/PF_V3_MAX_ATR_PCT); maybe_signal now passes ts_ms into strategy for UTC session filtering | done
- 2026-02-25 19:06 UTC | pump_fade v3.1 sweep | profiles G/H/I/J tested on 360d PF universe: session-heavy filters reduced trades too much and did not improve stress robustness materially | done
- 2026-02-25 19:07 UTC | pump_fade v3.1 candidate K | soft ATR-band profile achieved positive base+stress on 360d (66 trades): base +1.86 PF=1.356 DD=1.45; stress +0.50 PF=1.083 DD=1.67. Still modest edge, but first profile with stable >0 in both cost regimes at non-trivial trade count since PF degradation | done
- 2026-02-25 19:09 UTC | pump_fade v3.2 R&D | tested long-pump detector + adaptive RR boost (profiles M/N) to capture extended pumps; both underperformed v3.1-K in stress (M heavily negative, N slightly negative). Decision: keep v3.1-K as best current PF profile, park v3.2 branch as rejected for now | done
- 2026-02-25 19:41 UTC | smart_grid v2 R&D | implemented anti-trend protections (EMA slope + ATR band regime filter, breakout kill-switch pause, range maturity/touch-count gate). Backtest on BTC/ETH/SOL 360d: conservative profile produced too few trades (base +0.11, stress -0.18 on 4 trades), relaxed profile v2b failed hard (base -8.81, stress -22.36). Decision: grid remains non-viable for current portfolio and stays R&D-only | done
- 2026-02-25 19:42 UTC | trendline_break_retest v1 R&D | added new strategy module (extrema-based trendline with multi-touch validation and breakout-after-consolidation logic). Initial profile overtraded and failed (BTC/ETH/SOL 360d base -78.87, stress -99.38); stricter profile v1b eliminated overtrading but produced 0 trades. Decision: hypothesis needs redesign before any live consideration | done
- 2026-02-25 20:08 UTC | trend sanity check | existing trend_pullback on BTC/ETH 360d remains near-flat (base +0.28, stress -0.08, only 5 trades), unsuitable as main trend arm | done
- 2026-02-25 20:09 UTC | btc_eth_trend_follow v1 R&D | added new trend-follow strategy (4h regime + 1h pullback resume + breakout + runner/trailing) and integrated into run_portfolio. 360d BTC/ETH result failed hard: base -36.32 (530 trades), stress -50.28 (533 trades), very low winrate => rejected | done
- 2026-02-25 20:16 UTC | grid regime filter | added flat-symbol prefilter in backtest/run_portfolio.py for mean-reversion arms (smart_grid/range_bounce): FLAT_SYMBOL_FILTER_ENABLE, FLAT_SYMBOL_MIN_SCORE, FLAT_SYMBOL_KEEP_TOP_N with symbol ranking by EMA-gap/slope, ATR regime, and local range score. If no symbol passes threshold, engine now keeps top-ranked subset instead of disabling filter silently | done
- 2026-02-25 20:32 UTC | flat-filter calibration | fixed flat-score horizon bug (insufficient sample caused zero scores), switched scoring to smooth functions, added keep_top_n fallback and symbol score debug output. On BTC/ETH/SOL 360d filter selected ETH/BTC as relatively flatter symbols (scores ~0.515/0.510 vs SOL 0.486) | done
- 2026-02-25 20:33 UTC | flat-regime backtests | smart_grid + range_bounce with flat-filtered ETH/BTC (360d): range_bounce produced 0 trades; smart_grid produced 2 trades only (base +0.29, stress +0.15). Conclusion: regime filter works directionally, but entry logic remains too restrictive for useful frequency | done
- 2026-02-25 20:46 UTC | regime router | added bar-level regime router in backtest/run_portfolio.py: REGIME_ROUTER_ENABLE with strategy routing sets (REGIME_FLAT_STRATEGIES / REGIME_TREND_STRATEGIES). Regime is derived from EMA gap/slope + ATR band at each bar to switch between flat and trend strategy groups in one combined run. Verification runs blocked by Bybit API rate limit (10006) during this window; code compiles and is ready for delayed rerun | done
- 2026-02-25 21:06 UTC | roadmap fx | deferred goal recorded: after crypto core reaches stable multi-strategy profitability (base+stress), start phase-2 expansion to FX/metals (EURUSD/GBPUSD/XAUUSD first). Requirements: broker/API onboarding (Oanda preferred), execution adapter, costs model (spread/commission/swap), risk profile per market, and same backtest discipline (base/stress + monthly) before any live deployment | planned
- 2026-02-25 13:49 UTC | v2-strategy iteration | revised trendline_break_retest_v2 (break->retest state machine), flat_bounce_v2 (RSI+sweep+range-width filters), btc_eth_trend_follow_v2 (signal EMA alignment + pullback depth bounds + lower RR) and re-ran 180d base/stress | done
- 2026-02-25 13:49 UTC | v2-strategy results | trendline_v2 rev2: base +0.08 / stress -0.28 (5 trades); flat_bounce_v2 rev2: base -0.15 / stress -0.37 (3 trades); trend_follow_v2 rev2: base -1.75 / stress -2.33 (20 trades). Only trendline near-flat; others rejected for live | done
- 2026-02-25 13:49 UTC | trendline sweep | parameter sweep on 180d found local combo (RR=2.2, MIN_BREAKOUT_EXT_ATR=0.40) with base +0.47 / stress +0.19 (4 trades), but 360d validation failed (base -0.27 / stress -0.71, 6 trades). Decision: keep as research branch, not production candidate yet | done
- 2026-02-25 14:01 UTC | trendline v3 R&D | added strategies/trendline_break_retest_v3.py (trendline break + BOS + volume + retest state machine) and integrated into backtest/run_portfolio.py as trendline_break_retest_v3 | done
- 2026-02-25 14:01 UTC | trendline v3 results | default strict profile on BTC/ETH/SOL 360d produced 0 trades (base/stress), relaxed sweeps increased frequency but remained negative; best strict-relaxed checks still negative in stress | done
- 2026-02-25 14:01 UTC | trendline v3 session filter | Europe/US session-gated variant (180d) remained negative: base -2.06, stress -3.40 (20 trades). Decision: reject v3 for production, keep branch as failed hypothesis | done
- 2026-02-25 14:14 UTC | structure_shift v1 | added strategies/structure_shift_v1.py (CHOCH/BOS + pullback continuation) and integrated into backtest/run_portfolio.py as structure_shift_v1 | done
- 2026-02-25 14:14 UTC | structure_shift results | first 360d run failed hard on BTC/ETH/SOL: base -20.58 (688 trades), stress -69.53 (791 trades). Tightened filters (BOS/trend/cooldown) still negative on 180d. Decision: reject current hypothesis, requires redesign before next test | done
- 2026-02-25 14:14 UTC | funding/basis R&D bootstrap | added scripts/scan_funding_basis.py to scan Bybit linear tickers for funding annualization and mark-index basis watchlists (delta-neutral/cash-and-carry candidate discovery). Local run blocked by DNS/network in current environment; script ready for server run | done
- 2026-02-25 14:24 UTC | breakout quality gating | added algorithmic setup quality scoring for live breakout entries (breakout_quality_score from spread/chase/late/pullback), optional hard skip by BREAKOUT_QUALITY_MIN_SCORE, and tiered quality boost multipliers (BREAKOUT_QUALITY_BOOST_*) applied to notional risk. Telegram entry now prints quality/size/boost; ml_features now include quality_score/risk_mult | done
- 2026-02-25 14:38 UTC | backtest quality A/B | added breakout quality-gate to backtest/run_portfolio.py for inplay_breakout (BT_BREAKOUT_QUALITY_ENABLE + BT_BREAKOUT_QUALITY_MIN_SCORE) using live-consistent score from chase/late/spread/pullback; run summary now prints checked/skipped/pass_rate when enabled | done
- 2026-02-25 14:38 UTC | overnight runner | added scripts/run_breakout_quality_overnight.sh to execute 8 A/B runs (baseline vs quality-gated, 180d+360d, base+stress) and auto-build consolidated report with summary.csv + monthly_pnl per run | done
- 2026-02-25 14:38 UTC | note | local smoke runs were blocked by Bybit REST rate limit (10006) in this environment; overnight script intended to run from user side/server where connectivity limits are manageable | note
- 2026-03-01 17:45 UTC | tv-like atr contour | added strategies/tv_atr_trend_v1.py (trend+breakout with SL=2ATR, TP=9ATR, trailing ATR) and integrated into backtest/run_portfolio.py as tv_atr_trend_v1 for isolated R&D
- 2026-03-01 17:45 UTC | tvatr_v1 results | 360d BTC/ETH: base -10.09 (360 trades, PF 0.583), stress -32.17 (372 trades, PF 0.216), many negative months => rejected in current form
- 2026-03-01 17:45 UTC | ops note | increased MIDTERM_NOTIONAL_MULT to 0.50 and tuned WS ping/reconnect env on server; need post-change diagnostics window (since restart time) to validate impact on keepalive timeout frequency
- 2026-03-01 17:52 UTC | tvatr v2 | added stricter strategies/tv_atr_trend_v2.py (HTF slope+gap filter, pullback+breakout+volume, lower frequency, multi-TP + ATR trailing) and integrated in run_portfolio
- 2026-03-01 17:52 UTC | tvatr_v2 results | 360d BTC/ETH: base -3.43 (82 trades, PF 0.524), stress -8.70 (83 trades, PF 0.232). Better than v1 but still negative => rejected for production
- 2026-03-01 18:12 UTC | live allocator prep | implemented live allocator hooks in smart_pump_reversal_bot.py (LIVE_ALLOCATOR_ENABLE with per-strategy/per-regime multipliers). Applied to breakout and midterm risk/notional path; default OFF for safe rollout
- 2026-03-01 18:12 UTC | midterm execution | added MIDTERM min-qty fallback logic (MIDTERM_ALLOW_MINQTY_FALLBACK + MIDTERM_MINQTY_FALLBACK_MAX_MULT) to reduce BELOW_MIN_QTY skips on small balances while capping oversize vs calculated notional
- 2026-03-01 18:45 UTC | allocator soft A/B | tested softer allocator profile on breakout+midterm (BTC/ETH/SOL/ADA/LINK/DOGE/LTC/BCH/ATOM/AVAX, 360d): base improved +33.49 -> +35.69, PF 1.820 -> 2.001, DD 2.40 -> 2.23; stress net near-flat +15.43 -> +15.33 but PF improved 1.294 -> 1.304 and DD improved 4.27 -> 4.17, with fewer trades
- 2026-03-01 19:15 UTC | live stack overnight A/B | added scripts/run_live_stack_overnight.sh for breakout+midterm profiles (baseline/quality/allocator_soft/combo) across 360d base+stress with monthly breakdown and compact lines in report.txt | done
- 2026-03-02 07:30 UTC | live stack overnight A/B results | 360d breakout+midterm on 10 symbols: best balanced profile = quality-only (base +32.90 PF 1.857 DD 2.54; stress +16.97 PF 1.349 DD 4.17; only 2 negative stress months). combo had highest base PF but larger stress DD; decision: keep allocator OFF in live for now, keep quality gate ON, continue live observation window for trade-count/ops stability | done
- 2026-03-02 08:05 UTC | live diagnostics v1 | added runtime diag counters to smart_pump_reversal_bot.py (ws_connect/ws_disconnect/handshake_timeout + breakout/midterm try/no_signal/entry/skip reasons). Pulse and strategy stats now include compact diag snapshot to explain no-trade periods without changing trading logic | done
- 2026-03-02 13:35 UTC | structure_shift_v2 R&D | added strategies/structure_shift_v2.py + run_portfolio integration; 180d results on 10-symbol universe: base -8.86 PF=0.921 (372 trades), stress -30.02 PF=0.742; rejected
- 2026-03-02 13:35 UTC | trendline_break_retest_v4 R&D | added strategies/trendline_break_retest_v4.py + run_portfolio integration. Strict profile: 0 trades (base/stress). Relaxed smoke: 5 trades, base -0.08 PF=0.948, stress -0.42 PF=0.744; rejected for production
- 2026-03-02 13:45 UTC | flat_bounce_v3 R&D | added strategies/flat_bounce_v3.py + run_portfolio integration. Strict profile produced 0 trades on 180d. Relaxed profile (FB3_MAX_EMA_GAP_PCT=0.70, FB3_MAX_EMA_SLOPE_PCT=0.80, FB3_MIN_RANGE_WIDTH_ATR=2.2, FB3_ZONE_ATR_MULT=0.60, FB3_MIN_TOUCHES=2, FB3_VOL_MULT_MIN=0.90, FB3_MIN_REJECT_WICK_FRAC=0.30, FB3_MIN_REJECT_BODY_FRAC=0.14, RSI 38/62) gave 180d base +2.69 PF=2.414 and stress +1.77 PF=1.789 on 13 trades; 360d base +3.72 PF=1.786 and stress +1.51 PF=1.264 on 31 trades. Candidate kept in R&D (low frequency / uneven monthly profile)
- 2026-03-02 13:45 UTC | funding/basis scan | ran scripts/scan_funding_basis.py --top 20 successfully; produced live watchlists for positive/negative funding and abs-basis candidates (e.g., ZETA/KAVA/PHA/YGG in high abs basis). Next step: separate delta-neutral contour with liquidity/turnover floor and borrow/execution constraints
- 2026-03-02 13:52 UTC | funding capture prototype | added scripts/backtest_funding_capture.py: historical funding-mode backtest with liquidity filters, auto symbol selection, per-symbol/monthly/summary exports, and two realism modes (hold vs flip with flip fees). Smoke 30d run (top8, notional 100): hold net +50.76, flip net +52.47 after fees; strong concentration in SAHARA/ATH/YGG/ALICE
- 2026-03-02 14:15 UTC | funding capture hardening | upgraded scripts/backtest_funding_capture.py with outlier controls and robustness filters: max_abs_funding_8h_pct, min_events_per_symbol, clip_abs_rate, exclude_symbols, hold/flip mode metadata, top_symbol_share_net in summary, and median funding interval filter (min_interval_hours/max_interval_hours). This enables filtering out 1h high-noise contracts and tracking concentration risk explicitly
- 2026-03-02 14:16 UTC | funding smoke v2 | 30d auto(top8) with realism filters (turnover>=20m, OI>=5m, abs funding >=0.01%, cap 2.0%, min_events>=20, clip 0.8%): hold net +9.07 (top_symbol_share 0.727), flip net -1.33 after flip fees; concentration still high due to PIPPIN
- 2026-03-02 14:16 UTC | funding stable-universe check | 30d major8 (BTC/ETH/SOL/ADA/LINK/DOGE/LTC/BCH, interval 6-10h): hold net +0.25 with low concentration (top share 0.345), flip net -13.04 (flip fees dominate). Conclusion: edge in stable 8h universe is weak; flip mode is not viable at 6 bps flip cost
- 2026-03-02 14:38 UTC | funding profile v1 (hold, interval-filtered) | 90d auto-buffered top8 (selection_buffer_mult=10, min_interval 6h, max_interval 10h, clip 0.8%): net +5.51, top_symbol_share 0.206. 180d same profile: net +17.18, top_symbol_share 0.340. Symbols converged to DOT/1000PEPE/HYPE/BCH/AVAX/SUI/ZEC/ARB with 8h median interval
- 2026-03-02 14:38 UTC | funding profile v1 stress-fee | on same 8-symbol set with higher total entry/exit fees (30 bps): 90d net +4.39, 180d net +16.06; edge remains positive, concentration within acceptable R&D range (<0.36)
- 2026-03-02 15:02 UTC | funding_hold_v1 strategy split | added separate strategy module strategies/funding_hold_v1.py (concentration-aware selector with max_top_symbol_share + min_symbol_net filters). Updated scripts/backtest_funding_capture.py to use this strategy class and report new selection controls in summary
- 2026-03-02 15:02 UTC | funding_hold_v1 validation | 90d profile with selector guardrails: net +5.95, top_symbol_share 0.191, symbols diversified (ZEC/BCH/1000PEPE/SUI/HYPE/DOT/AAVE/ARB)
- 2026-03-02 15:30 UTC | triple screen import test | added strategies/triple_screen_v132.py and integrated into backtest/run_portfolio.py as triple_screen_v132 (approximation of TradingView Triple Screen with trend+oscillator+ATR exits, trade mode/cooldown, execution mode adjustment)
- 2026-03-02 15:30 UTC | triple screen results | 180d on BTC/ETH/SOL/ADA/LINK/DOGE/LTC/BCH: active profile collapsed (base -99.45, stress -100.00 due to overtrading). Added eval timeframe gating and conservative profile; still negative (base -5.33, stress -23.53). Strategy rejected in current form
- 2026-03-02 16:56 UTC | ts132 A-scan tooling | added scripts/run_ts132_a_scan.sh to scan friend A-list symbols in base/stress with retry/backoff for Bybit 10006 rate-limit; fixed script to not depend on rg and to output correct symbol values
- 2026-03-02 17:50 UTC | triple screen v132b | added strategies/triple_screen_v132b.py (stricter HTF trend+slope, long-only default, lower frequency, RSI cross only, stronger volatility/volume gates) and integrated into run_portfolio
- 2026-03-02 17:50 UTC | triple screen v132b results | A-list 180d long-only: base -5.48 (42 trades, PF 0.221), stress -9.29 (51 trades, PF 0.104). Still negative => rejected, likely no robust edge under realistic costs
- 2026-03-02 18:10 UTC | strategy symbol gate | added scripts/strategy_symbol_gate.py with two modes: trade (base/stress scan CSV -> robust symbol gating) and funding (per_symbol funding CSV -> concentration-aware selection via FundingHoldV1Strategy). Includes normalization for malformed legacy scan rows
- 2026-03-02 18:10 UTC | gate results | trade gate on ts132 A-scan: strict criteria selected 0 symbols; relaxed criteria selected only KSMUSDT (base +2.05, stress -0.58) => still not production-ready. funding gate selected 8-symbol basket: ZEC,HYPE,SUI,DOT,1000PEPE,ARB,LTC,BCH
- 2026-03-02 18:28 UTC | funding nightly pipeline | added scripts/run_funding_gate_overnight.sh: automated funding hold A/B (base+stress fee profiles), runs strategy_symbol_gate funding selection, and writes consolidated report.txt with summary/monthly/gated symbols/compact lines for morning review
- 2026-03-02 18:35 UTC | funding | added scripts/run_funding_leverage_sweep.sh for leverage/notional sweep (1.0x/1.5x/2.0x/3.0x by default) over strict funding gate profile; outputs summary CSV with base/stress net and top-share | done
- 2026-03-02 18:59 UTC | structure_shift | added scripts/run_structure_shift_suite.sh (base+stress sequential runner with summary/monthly output for structure_shift_v2) | done
- 2026-03-02 19:16 UTC | structure_shift_v2 | 360d suite on 10 symbols: base net -33.90 (PF 0.846, DD 41.46), stress net -64.96 (PF 0.671, DD 66.72), 804 trades, many negative months => rejected for live; move to next R&D candidate | done
- 2026-03-02 19:30 UTC | structure_shift_v2 | hardened BOS logic: fresh-cross BOS, minimum BOS body filter (SS2_BOS_MIN_BODY_FRAC), prevent pending setup overwrite; added scripts/run_trendline_v4_suite.sh for next candidate base/stress+monthly suite | done
- 2026-03-02 19:54 UTC | structure_shift_v2 + trendline_v4 | 360d results: ss_v2 still deeply negative after hardening (base -41.61 / stress -68.07, 789 trades); tlv4 produced 0 trades in base/stress (too strict). Decision: reject ss_v2 for now, tune tlv4 thresholds to obtain controlled trade count and re-evaluate PF/DD | done
- 2026-03-02 20:22 UTC | flat_bounce_v3 | added scripts/run_flat_bounce_v3_suite.sh (base+stress sequential runner with summary/monthly output) as next R&D candidate | done
- 2026-03-03 10:27 UTC | trend_follow_v2 | added scripts/run_trend_follow_v2_suite.sh (BTC/ETH default, base+stress sequential runner with summary/monthly output) as next high-priority resilient candidate | done
- 2026-03-03 11:35 UTC | trend_follow_v2 audit | 360d base/stress both negative (base -3.14/-3.41 tuned, stress -4.15/-4.52 tuned, ~36-39 trades); concluded no hard blocker bug found, trading frequency constrained mainly by stacked breakout/midterm filters, minQty/cap universe gate, and killer-guard bans | done
- 2026-03-03 11:42 UTC | breakout audit/tuning | added scripts/run_breakout_filter_sweep.sh (strict/balanced/active/open profiles; base+stress with summary ranking) to retune live filters and pick canary profile | done
- 2026-03-03 10:50 UTC | live canary | applied balanced breakout profile on server (.env) + restarted bybot; updated chase/late/pullback/impulse/reclaim/max_dist/buffer, liq floor=50k, killer-guard relaxed (min_trades=5, max_net=-1.20), risk unchanged
- 2026-03-03 13:16 UTC | R&D tooling | added scripts/run_candidate_scan.sh (multi-candidate base/stress ranking scan) and scripts/run_live_diagnostics.sh (journal diag delta parser: entry/no-signal/skip/ws ratios) for faster iteration without manual parsing
- 2026-03-03 11:45 UTC | ops diagnostics | fixed scripts/run_live_diagnostics.sh delta math across bot restarts (counter reset-safe, pid switch info) to remove false negative try/no_signal/ws values | done
- 2026-03-03 12:05 UTC | breakout diagnostics v2 | added no-signal reason tracing inside InPlayBreakoutStrategy/Wrapper + live counters (no_break/regime/retest/hold/dist/impulse) and extended scripts/run_live_diagnostics.sh breakdown to identify why breakout returns no signal in live | done
- 2026-03-03 13:55 UTC | candidate scan v2 | scanned untested strategies (momentum/trend_pullback/trend_breakout/adaptive_range_short/smart_grid/inplay_pullback) on 360d base+stress; no new robust winners: trend_breakout=0 trades, smart_grid near-flat low freq, trend_pullback stress negative, others collapse to ~-100 via overtrading | done
- 2026-03-03 15:39 UTC | trend_pullback_be_trail R&D | added strategies/trend_pullback_be_trail.py (trend pullback entry + BE trigger + ATR trailing + partial TP runner), extended backtest signal/engine/portfolio_engine with be_trigger_rr/be_lock_rr, integrated strategy into run_portfolio + added scripts/run_trend_pullback_be_trail_suite.sh | done
- 2026-03-03 15:44 UTC | trend_pullback_be_trail + ts132 A-list checks | 180d results negative: tpbt base -8.11 / stress -18.03; hard-filter stress sweep best -1.11 (still negative). Triple screen on A-list also negative (v132 base -56.83, v132b base -5.48). Rejected for live
- 2026-03-03 16:22 UTC | live diag granularity | expanded breakout no-signal counters: entry_timing, invalid_risk, history, symbol, stop (in addition to no_break/regime/retest/hold/dist/impulse/other); updated scripts/run_live_diagnostics.sh breakdown accordingly for sharper live tuning decisions
- 2026-03-03 16:48 UTC | forex pilot scaffold | added isolated module `forex/` (data loader, backtest engine with spread/swap, strategy `trend_retest_session_v1`, CLI runner `scripts/run_forex_backtest.py`, smoke launcher `scripts/run_forex_pilot_smoke.sh`, docs in forex/README.md). No integration with crypto live paths
- 2026-03-03 16:49 UTC | rd cleanup prep | added docs/RD_CLEANUP_PLAN.md and scripts/rd_cleanup_candidates.py; generated docs/rd_cleanup_candidates.csv (keep_active=4, archive_candidate=34) to support safe archive-first cleanup
- 2026-03-03 16:55 UTC | forex_pilot | Added isolated batch runner for EURUSD/GBPUSD/USDJPY and session args in runner; updated forex README with batch launch instructions | done
- 2026-03-03 17:02 UTC | rd governance | Added docs/RD_FOCUS_RULES.md with fixed split: crypto R&D only 2 directions, forex parallel pilot, 10-14 day no-pass switch rule (50% R&D to forex), and capital isolation policy | done
- 2026-03-03 17:22 UTC | forex_pilot | Fixed run_forex_pilot_batch.sh for macOS bash 3.2 (removed associative arrays); batch now runs and skips missing CSV gracefully | done
- 2026-03-03 17:22 UTC | cleanup tooling | Added scripts/index_backtest_runs.py and generated docs/backtest_runs_catalog.csv from backtest_runs/old (489 rows) to preserve experiment history before potential deletion | done
- 2026-03-03 17:35 UTC | tracking | Added docs/OPEN_TASKS.md (done/in-progress/next/blocked) and docs/CLEANUP_LOG.md (archive-first cleanup ledger with reason/effect/reversibility) to avoid losing unfinished work across sessions | done
- 2026-03-03 17:37 UTC | cleanup tooling | Added scripts/archive_rejected_strategies.sh (dry-run by default) to archive rejected strategy files with manifest trail under archive/rejected_manifest_*.csv; validated with dry-run list | done
- 2026-03-03 17:53 UTC | breakout canary R&D | Added scripts/run_breakout_impulse_sweep.sh (targeted sweep for BREAKOUT_IMPULSE_ATR_MULT with other live-like filters fixed) and ran 180d sweep: 0.80->stress +3.60, 0.75->+3.96, 0.70->+3.96; base improved slightly from +18.88 to +19.09 | done
- 2026-03-03 17:53 UTC | live diagnostics v3 | Expanded breakout no-signal taxonomy in smart_pump_reversal_bot.py and scripts/run_live_diagnostics.sh with explicit atr/range/post_filters counters to reduce opaque other-bucket | done
- 2026-03-03 17:57 UTC | task tracking | Updated docs/OPEN_TASKS.md with latest 2h live diagnostics metrics and impulse-only sweep results (0.80/0.75/0.70) plus canary recommendation
- 2026-03-03 17:59 UTC | cleanup guard | Documented prerequisite in docs/OPEN_TASKS.md: do not move rejected strategy files before pruning static imports/allowed-list in backtest/run_portfolio.py to avoid breakage
- 2026-03-03 18:08 UTC | cleanup tooling | Added scripts/cleanup_gap_report.py and generated docs/cleanup_gap_report.csv (33 archive candidates still imported in run_portfolio; import-prune required before archive move)
- 2026-03-03 18:08 UTC | forex tooling | Added scripts/forex_data_check.py + scripts/run_forex_data_check.sh; generated docs/forex_data_status.csv (ready=0/3, EURUSD/GBPUSD/USDJPY CSV missing)
- 2026-03-04 05:50 UTC | live diagnostics v4 | Split breakout impulse no-signal reasons into dedicated counters (`breakout_ns_impulse_weak`, `breakout_ns_impulse_body`, `breakout_ns_impulse_vol`) in bot runtime snapshot and diagnostics parser for cleaner canary decisions
- 2026-03-04 05:51 UTC | forex pilot check | Re-validated `scripts/run_forex_pilot_batch.sh` launch path on local machine: batch executes correctly and gracefully skips missing CSV inputs (no parser/unbound crash)
- 2026-03-04 05:52 UTC | breakout canary guardrail | 180d stress check for relaxed impulse body filter (`BREAKOUT_IMPULSE_BODY_MIN_FRAC=0.20`, `IMPULSE_ATR=0.75`) degraded to net `-3.16`, `DD 7.18` -> rejected for live deployment
- 2026-03-04 05:53 UTC | breakout canary guardrail | 180d stress check for `BREAKOUT_IMPULSE_BODY_MIN_FRAC=0.30` (`IMPULSE_ATR=0.75`) ended near-flat but still negative (`-0.14`, `DD 6.07`) vs baseline positive stress -> rejected for live deployment
