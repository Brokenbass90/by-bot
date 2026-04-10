# Roadmap: Self-Improving Algobot

**Цель:** Полностью автономная система, которая сама обнаруживает возможности, оптимизирует стратегии, адаптируется к рынку и масштабирует прибыльные идеи — без ручного вмешательства.

**Дата создания:** 2026-04-10  
**Статус:** Фаза 2 → переход к Фазе 3

---

## Фаза 1 — Инфраструктура (ЗАВЕРШЕНА ✅)

Всё что нужно для стабильной работы и самовосстановления.

- **4-режимный оркестратор**: bull_trend / bull_chop / bear_chop / bear_trend
  - BTC 4H EMA21/EMA55 + Efficiency Ratio (порог 0.28) 
- **Symbol Router**: динамический подбор монет per-strategy
  - Retry-логика (3 попытки), деградация с авторесторингом
- **Portfolio Allocator**: sleeve multipliers per-regime
  - Критический фикс: breakdown=0.0 в bull-режимах
- **Самовосстанавливающиеся watchdogs**:
  - `bot_health_watchdog.sh` — каждые 2 мин, авторестарт через systemd
  - `control_plane_watchdog.py` — каждые 30 мин, ребилд chain
  - `setup_server_crons.sh` — мастер-инсталлер всех 10 cron-задач
- **Nightly autoresearch queue**: автоматические backtest-запуски ночью
- **DeepSeek оператор в Telegram**: `/ai`, `/ai_tune`, `/ai_results`
- **Alpaca monthly rotation**: v36, PF=4.68, +130% compound

---

## Фаза 2 — Портфель стратегий (В ПРОЦЕССЕ 🔄)

Цель: 5-10 рабочих стратегий, покрывающих все режимы рынка.

### Активные (работают в продакшне)
| Стратегия | Режим | Trades/год | PF | Статус |
|---|---|---|---|---|
| alt_inplay_breakdown_v1 | все | ~157 | 1.3+ | ✅ Live |
| alt_resistance_fade_v1 (ARF1) | chop | ~99→150+ | 1.4+ | ✅ Live (расширен) |
| impulse_volume_breakout_v1 (IVB1) | bull | ~14→40+ | 1.48 | ✅ Live (расширен) |

### Исправляются
| Стратегия | Проблема | Фикс | Статус |
|---|---|---|---|
| elder_triple_screen_v2 | Screen2 RSI временное смещение | wave_lookback=3 | 🔄 Backtest pending |
| alt_range_scalp_v1 | 2 trades/year в портфеле | Требует standalone redesign | ⏳ Следующий приоритет |

### В разработке (spec готов)
| Стратегия | Тип | Режим | Статус |
|---|---|---|---|
| alt_volume_exhaust_fade_v1 (VEF) | Fade volume spike | все | 📋 Codex task написан |
| inplay_breakout_v2 | Breakout improvement | bull_trend | 📋 Codex task написан |

### Планируются (следующие)
| Идея | Тип | Режим |
|---|---|---|
| Crypto momentum rotation | Midterm 7-10d hold | bull_trend |
| Funding rate arbitrage | Market-neutral | любой |
| Micro scalper (1m) | High-frequency | высокий ATR |
| Support reclaim v2 | Bounce | bear_chop дно |
| Opening range breakout | Session-based | лондон/нью-йорк открытие |

**Цель Фазы 2:** 8-10 стратегий × 5-10 монет каждая = 3-8 сделок в день по портфелю.

---

## Фаза 3 — Самооптимизация (СЛЕДУЮЩАЯ 🎯)

Система сама улучшает параметры стратегий. Нужно дописать ~4 модуля.

### 3.1 Auto-Apply Winners (ПРИОРИТЕТ #1)
**Что:** Когда autoresearch находит конфиг с PF > порога и DD < лимита — автоматически применяет его в live без ручного approve.

**Как реализовать:**
```python
# scripts/auto_apply_research_winner.py
# Запускается после каждого autoresearch run
# Проверяет: passed=True, score > AUTOAPPLY_MIN_SCORE (env), neg_months <= 3
# Если всё ок → патчит dynamic_allowlist_latest.env + перезагружает allocator
# Уведомляет в TG: "Авто-апдейт: ARF1 LOOKBACK 48→60, score=36.1"
```

**Защиты:**
- Применяет только если ≥ 3 разных run с похожими параметрами прошли
- Не применяет в боевых условиях между 02:00-04:00 UTC (тихое окно)
- Хранит историю применений в `runtime/auto_apply_log.jsonl`

### 3.2 Performance Degradation Detector (ПРИОРИТЕТ #2)
**Что:** Отслеживает расхождение live P&L vs backtest-ожидания. Если стратегия "сдулась" — ставит её на паузу и запускает реоптимизацию.

**Как реализовать:**
```python
# scripts/live_vs_backtest_monitor.py  
# Каждый день: считает rolling_pf_live_30d для каждой стратегии
# Если rolling_pf < backtest_pf * DEGRADE_THRESHOLD (0.6):
#   → SET STRATEGY_X_RISK_MULT=0.0 (пауза)
#   → Добавляет strategy_x_reopt в research_nightly_queue.json
#   → TG: "⚠️ ARF1 деградирует: live PF=0.9 vs backtest PF=1.4. Пауза + реопт."
```

### 3.3 Regime-Triggered Reoptimization (ПРИОРИТЕТ #3)
**Что:** При смене рыночного режима автоматически запускает оптимизацию параметров под новый режим.

**Как реализовать:**
```python
# В control_plane_watchdog.py — добавить хук на смену applied_regime
# При bull_trend → bear_chop: добавить в queue задачи для "chop-friendly" стратегий
# При bear_chop → bull_trend: добавить задачи для "trend-following" стратегий
```

### 3.4 Live Params Drift Tracker (ПРИОРИТЕТ #4)
**Что:** Лог всех когда-либо применявшихся параметров с P&L-атрибуцией. Помогает DeepSeek-у видеть что работало исторически.

**Как реализовать:**
```
runtime/params_history.jsonl
{
  "ts": 1744200000,
  "strategy": "arf1",
  "params": {"ARF1_SIGNAL_LOOKBACK": 60, "ARF1_MIN_RSI": 54},
  "source": "auto_apply",
  "regime_at_apply": "bear_chop",
  "live_pf_30d_after": null  # заполняется через 30 дней
}
```

---

## Фаза 4 — Strategy Factory (БУДУЩЕЕ 🔮)

Система сама порождает и тестирует новые идеи стратегий.

### 4.1 Strategy Genome Engine
Каждая стратегия = набор "генов": entry_condition + filter_set + exit_logic.
При хороших результатах — "размножить" с мутациями:
```
ARF1 (fade от сопротивления) 
  → мутация 1: fade от поддержки (support_bounce)
  → мутация 2: fade от BB-верхней полосы (ARF2)
  → мутация 3: ARF1 + volume filter (ARF1+VEF hybrid)
```

### 4.2 DeepSeek Research Proposals
DeepSeek получает текущую рыночную статистику и предлагает:
- "В последние 30 дней BTC показывает высокую внутридневную волатильность 06:00-10:00 UTC → предлагаю протестировать Opening Range Breakout"
- Кодирует идею в spec.json → отправляет в autoresearch queue

### 4.3 A/B Testing Framework
Параллельный запуск 2 версий одной стратегии в live:
- Версия A: текущий live (50% капитала)
- Версия B: новый candidate (50% капитала)
- Через 30 дней: автовыбор победителя

### 4.4 Cross-Regime Learning
Метастратегия: какие стратегии/параметры работают лучше в каком режиме — выученные из реальных данных, а не из backtest.

---

## Фаза 5 — Масштабирование (БУДУЩЕЕ 🔮)

Когда система стабильно прибыльна и самооптимизируется.

- **Multi-account**: разные риск-профили (aggressive / conservative)
- **Cross-exchange**: Bybit + Binance + OKX арбитраж возможностей
- **Crypto + Equities**: единый оркестратор для Bybit + Alpaca
- **Volatility-adjusted sizing**: позиции адаптируются к текущему VIX/BVIV
- **Correlation-aware portfolio**: ограничение одновременных коррелированных позиций

---

## Текущий стек технологий

```
LIVE BOT
├── smart_pump_reversal_bot.py        — главный loop
├── bot/deepseek_overlay.py           — TG оператор с AI
├── bot/operator_snapshot.py          — сбор snapshot для AI
│
ORCHESTRATION
├── scripts/build_regime_state.py     — 4-режимный детектор
├── scripts/build_symbol_router.py    — динамический роутер монет
├── scripts/build_portfolio_allocator.py — распределение рисков
│
SELF-HEALING
├── scripts/bot_health_watchdog.sh    — каждые 2 мин
├── scripts/control_plane_watchdog.py — каждые 30 мин
├── scripts/setup_server_crons.sh     — мастер-инсталлер
│
SELF-RESEARCH (ЕСТЬ)
├── backtest/run_portfolio.py         — портфельный backtest
├── scripts/run_nightly_research_queue.py — ночная очередь
├── bot/deepseek_autoresearch_agent.py — AI анализ результатов
│
SELF-OPTIMIZE (НЕТ — ФАЗА 3)
├── scripts/auto_apply_research_winner.py   — TODO
├── scripts/live_vs_backtest_monitor.py     — TODO
├── scripts/regime_triggered_reopt.py       — TODO
└── runtime/params_history.jsonl           — TODO
```

---

## Приоритеты прямо сейчас

1. **Elder backtest** — запустить `CODEX_TASK_elder_wave_lookback_backtest.md`
2. **ARF1 wider universe** — уже в live конфиге (v2 обновление)
3. **IVB1 wider universe** — добавлены LINKUSDT, DOGEUSDT в live конфиге
4. **VEF стратегия** — Codex task написан, нужна реализация
5. **auto_apply_research_winner.py** — первый модуль Фазы 3 (самооптимизация)
6. **Range scalp redesign** — standalone backtest, переработка логики

---

## KPI для оценки прогресса

| Метрика | Сейчас | Цель Фаза 2 | Цель Фаза 3 |
|---|---|---|---|
| Активных стратегий в live | 3 | 6-8 | 10+ |
| Сделок в день | 0.5-1 | 3-5 | 5-10 |
| Ручного вмешательства | много | редко | почти нет |
| Auto-reopt coverage | 0% | 0% | 80% стратегий |
| Стратегий в разработке | 2 | 5 | постоянный конвейер |
