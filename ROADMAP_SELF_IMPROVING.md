# Roadmap: Self-Improving Algobot

**Цель:** Контролируемая самообучающаяся система, которая сама обнаруживает
возможности, проверяет их и адаптируется к рынку через воспроизводимые gates.
Автоматическая генерация не даёт права на деньги: AI/Ollama/DeepSeek работают
в режиме `proposal-only`, а promotion, риск и ордера требуют hash-bound
доказательств и явного owner-approved release.

**Дата создания:** 2026-04-10  
**Обновлено:** 2026-08-24
**Статус:** архитектура и исследовательский pipeline частично готовы; closed-loop
самооптимизация НЕ считается завершённой до live/research parity, shadow
control и paper lifecycle gates.

## Канонический жизненный цикл идеи

Для каждой ноги порядок неизменен:

`propose → preregister → parity → shadow + random control → paper lifecycle → tiny canary → scale`

Исследовательская вселенная должна быть шире денежной: evidence-shadow и
контроль собирают статистику на заранее зафиксированной широкой universe,
тогда как live money sleeve остаётся узким до отдельного parity и
exposure/correlation gate. AI только предлагает finding/experiment и не может
сам продвигать кандидата, менять конфиг, риск или включать торговлю.

## Фактическая граница текущей автономности

Оркестратор, router, allocator, watchdogs и исследовательская очередь существуют
как компоненты, но наличие компонента не означает, что он подключён к каждому
денежному caller. Для ATT1/SBR1 это проверяется caller receipt и fixed-universe
ON/OFF replay. Самоисправление означает безопасное обнаружение → reproduction →
patch → tests → deploy receipt; не бесконтрольное изменение live.

---

## Фаза 1 — Инфраструктура (ЗАВЕРШЕНА ✅)

- **4-режимный оркестратор**: bull_trend / bull_chop / bear_chop / bear_trend (BTC 4H EMA21/55 + ER)
- **Symbol Router**: динамический подбор монет per-strategy, retry + degrade
- **Portfolio Allocator v8**: sleeve multipliers per-regime, 24 рукавов зарегистрировано
- **Самовосстанавливающиеся watchdogs**: health_watchdog (2 мин), control_plane (30 мин)
- **Nightly autoresearch queue**: автоматические backtest-запуски ночью
- **DeepSeek оператор в Telegram**: `/ai`, `/ai_tune`, `/ai_results`
- **Alpaca monthly rotation**: v37 sweep pending, текущий PF=4.68, +130% compound (paper)
- **BTC Dominance Regime Filter**: `build_btc_dominance_state.py` → alt_bias overlay (4H cron)

---

## Фаза 2 — Портфель стратегий (ФИНАЛ 🔄)

Цель: 8-10 рабочих стратегий с WF-22 подтверждением, покрывающих все режимы.

### ✅ Продакшн (WF-22 прошли)

| Стратегия | Sleeve | Режим | PF | Сделок/год |
|---|---|---|---|---|
| alt_resistance_fade_v1 | flat | bear_chop (primary) | 1.4+ | ~150 |
| alt_sloped_channel_v1 | sloped | все | 1.3+ | ~120 |
| alt_support_bounce_v1 | bounce1 | bull_trend | 1.3+ | ~80 |
| alt_range_scalp_v1 | range_scalp | все | 1.2+ | ~200 |
| impulse_volume_breakout_v1 | impulse | bull | 1.48 | ~40 |
| alt_inplay_breakdown_v1 | breakdown | bear (disabled — re-WF pending) | 4.3 sweep | ~60 |

### 🟡 Ожидают WF-22 (параметры найдены, на сервере сейчас)

| Стратегия | Sleeve | Лучшие параметры | Статус |
|---|---|---|---|
| alt_inplay_breakdown_v1 | breakdown | LOOKBACK_H=36, SL_ATR=1.4, RR=2.0 → sweep PF=4.3 | **Запущен WF-22 на сервере** |
| elder_triple_screen_v3 | elder_ts_v3 | 96-combo macro-relax sweep | **Запущен sweep на сервере** |
| alt_trendline_touch_v1 | att1 | PIVOT_LEFT=2, R=2.0, TOUCH_ATR=0.25 → PF=1.295 | **Запущен WF-22 на сервере** |
| alt_horizontal_break_v1 | hzbo1 | sweep не запускался | Ждёт очереди |
| inplay_breakout | breakout | HTF-scale SL fix (96cf4fd), нужен retune sweep | Ждёт sweep |

### 🆕 Новые стратегии (написаны, нужен backtest)

| Стратегия | Sleeve | Идея | Статус |
|---|---|---|---|
| session_open_breakout_v1 | sob1 | London 08:00 / NY 13:30 — первая импульсная 15m свеча | ✅ Написана, зарегистрирована, **нужен WF-22** |
| funding_rate_reversion_v1 | funding_rev | Bybit 8H funding extremes → reversion | Зарегистрирована, нужен backtest |
| liquidation_cascade_entry_v1 | liq_cascade | Liquidation spike fade | Зарегистрирована, нужен backtest |
| sloped_resistance_choch_v1 | slope_choch | CHOCH at sloped resistance | Зарегистрирована, нужен backtest |
| micro_scalper_v1 | micro_scalp | 5m EMA pullback scalper | Зарегистрирована, нужен backtest |

### 🔴 Требуют фикса

| Стратегия | Проблема |
|---|---|
| alt_inplay_breakdown_v2 | 0 сделок в backtest — баг в коде (диагноз в Codex Task 3.4) |
| btc_eth_midterm_v3 | SL-баг исправлен, нужен param sweep |
| elder_triple_screen_v3 | 0 сделок при дефолтных параметрах — слишком строгие фильтры |

---

## Фаза 3 — Самооптимизация (СЛЕДУЮЩАЯ 🎯)

### 3.1 Auto-Apply Winners (ПРИОРИТЕТ #1)
```python
# scripts/auto_apply_research_winner.py
# Research winner может только сформировать проверяемый apply proposal.
# Применение требует независимого receipt, hash/config parity, owner approval
# и тихого окна; отсутствие любого условия = fail-closed, без изменения live.
```

### 3.2 Performance Degradation Detector (ПРИОРИТЕТ #2)
```python
# scripts/live_vs_backtest_monitor.py
# rolling_pf_live_30d < backtest_pf × 0.6 → пауза стратегии + добавить в reopt queue
# TG: "⚠️ ARF1 деградирует: live PF=0.9 vs backtest PF=1.4"
```

### 3.3 Regime-Triggered Reoptimization (ПРИОРИТЕТ #3)
```python
# В control_plane_watchdog.py — хук на смену applied_regime
# При смене режима → добавить в queue параметры под новый режим
```

### 3.4 Live Params Drift Tracker (ПРИОРИТЕТ #4)
```
runtime/params_history.jsonl — лог всех applied параметров с P&L атрибуцией
```

### 3.5 Stack Comparison Gate (ПРИОРИТЕТ #5)
```bash
python3 scripts/run_stack_comparison_queue.py --config configs/stack_comparison_queue_20260423.json
```

Задача: больше не принимать красивые strategy-only цифры без проверки всего стека. Каждый кандидат сравнивается в двух режимах:

- без control-plane: стратегия сама по себе;
- с control-plane: orchestrator + router + allocator + health gate.

Правило ремонта: если полный стек сильно режет сделки/доходность и не даёт сравнимого снижения просадки, чинить или ослаблять именно control-plane для этого рукава, а не списывать стратегию как "сломалась".

---

## Фаза 4 — Strategy Factory (БУДУЩЕЕ 🔮)

- **Strategy Genome Engine**: мутации параметров от рабочих стратегий
- **DeepSeek Research Proposals**: AI предлагает идеи на основе рыночной статистики
- **A/B Testing Framework**: параллельный запуск 2 версий, автовыбор победителя
- **Cross-Regime Learning**: выученные паттерны из реальных данных

---

## Фаза 5 — Масштабирование (БУДУЩЕЕ 🔮)

- Multi-account: aggressive / conservative risk profiles
- Cross-exchange: Bybit + Binance + OKX
- Crypto + Equities: единый оркестратор Bybit + Alpaca
- Volatility-adjusted sizing: адаптация к BVIV/ATR percentile
- Correlation-aware portfolio: лимит одновременных коррелированных позиций

---

## Текущий стек

```
LIVE BOT
├── smart_pump_reversal_bot.py        — главный loop
├── bot/deepseek_overlay.py           — TG оператор с AI
├── bot/operator_snapshot.py          — snapshot для AI
│
ORCHESTRATION
├── scripts/build_regime_state.py     — 4-режимный детектор
├── scripts/build_btc_dominance_state.py  — alt_bias overlay (NEW)
├── scripts/build_symbol_router.py    — динамический роутер
├── scripts/build_portfolio_allocator.py  — риск-распределение
│
SELF-HEALING
├── scripts/bot_health_watchdog.sh    — каждые 2 мин
├── scripts/control_plane_watchdog.py — каждые 30 мин
├── scripts/setup_server_crons.sh     — мастер-инсталлер
│
SELF-RESEARCH
├── backtest/run_portfolio.py         — портфельный backtest
├── scripts/run_nightly_research_queue.py — ночная очередь
├── bot/deepseek_autoresearch_agent.py    — AI анализ
│
SELF-OPTIMIZE (НЕТ — ФАЗА 3)
├── scripts/auto_apply_research_winner.py   — fail-closed proposal/apply gate
├── scripts/live_vs_backtest_monitor.py     — TODO
└── runtime/params_history.jsonl           — TODO
```

---

## Приоритеты прямо сейчас (август 2026)

1. Закрыть live-native caller parity ATT1/SBR1 и доказать фактическое
   подключение режима/аллокатора, не меняя деньги до PASS.
2. Расширить SBR1/ATT1 evidence-shadow и random control на заранее записанную
   universe, оставив money universe узкой.
3. Завершить Alpaca paper lifecycle и protection health auditor; SAFE_HOLD
   снимать только отдельным promotion receipt.
4. Провести XAU/Forex и Polymarket только как data/paper research, с exact
   costs, settlement и no-order authority.
5. Вести 30/90-дневные gates и receipts вместо календарных обещаний доходности.

---

## KPI прогресса

| Метрика | Сейчас (апр 2026) | Цель Фаза 2 | Цель Фаза 3 |
|---|---|---|---|
| Стратегий с WF-22 | 5 | 8-10 | 10+ |
| Сделок в день | 1-3 | 3-8 | 5-12 |
| Ручного вмешательства | много | редко | почти нет |
| Auto-reopt coverage | 0% | 0% | 80% |
| Конвейер стратегий | 5 в разработке | стабильный | автоматический |
