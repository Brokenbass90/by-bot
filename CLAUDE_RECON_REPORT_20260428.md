# Claude — отчёт о разведке проекта и план действий
**Дата:** 2026-04-28
**Автор:** Claude (инженер качества)
**Задача:** изучить проект, найти точки утечки доходности, выставить приоритеты, предложить план без правок в прод.

---

## 1. Что я успел изучить

- `README.md`, `ROADMAP_SELF_IMPROVING.md`, `STRATEGY_STATUS_20260419.md`, `AUDIT_REPORT_20260427.md`
- `configs/portfolio_allocator_policy.json` (v7-v8 — 24 sleeve)
- `configs/regime_overlay_bear_chop.env`, `regime_overlay_bear_trend.env`
- `runtime/regime/orchestrator_state.json`, `runtime/live_mirror/regime/orchestrator_state.json`
- `.env` (только риск-параметры; ключи не выписываю)

Глубокого код-обзора `smart_pump_reversal_bot.py` (524 KB), аллокатора и оркестратора — пока не делал. Это отдельный пункт ниже.

---

## 2. Текущее состояние live (на 2026-04-28 13:00 UTC)

```
regime              = bear_chop
macro               = MACRO_BEAR  (-0.15 risk modifier)
global_risk_mult    = 0.55  (база 0.7 - macro 0.15)
base_risk_per_trade = 1.0% (BYBIT_ACCOUNTS_JSON.main.risk_pct=0.01)
leverage            = 3
max_positions       = 3
min_notional_usd    = 18
```

Депозит ~$100 (твои слова). При max_positions=3 одновременная экспозиция в худшем случае ≈$300 нотионала, риск-капитал на одну открытую = ~$0.55 в текущем режиме (1% × 0.55 × sleeve_mult).

---

## 3. Главная утечка — пять v7-рукавов без WF-22

ROADMAP пишет дословно: «may be losing money live right now with no evidence of edge». Я подтвердил, что они **реально активны** в текущем bear_chop оверлее:

| sleeve | overlay (bear_chop) | allocator mult | live risk на сделку |
|---|---|---|---|
| `funding_rev` | ON | 0.85 | **~0.47%** |
| `micro_scalp` | ON, longs+shorts | 0.80 | ~0.44% |
| `slope_choch` | ON, shorts | 0.75 | ~0.41% |
| `liq_cascade` | ON, longs+shorts | 0.60 | ~0.33% |
| `breakdown_v2` | OFF в bear_chop, ON в bear_trend (1.05) | 0.85 (ch)/1.05 (tr) | 0 сейчас |

`funding_rev` нагружен **сильнее `flat`** (0.7) и `sloped` (0.65) — то есть непроверенный рукав весит больше доказанных. Это не баг, это решение из allocator v7, но с учётом отсутствия WF-22 — рекомендую снизить.

---

## 4. Известные баги (сводно из STRATEGY_STATUS + AUDIT)

| стратегия | проблема | план |
|---|---|---|
| `alt_inplay_breakdown_v2` | 0 сделок в backtest (cache/signal bug) | диагностика — я |
| `flat_live_canary` | 0 сделок (gating bug, аудит 2026-04-27) | диагностика — я |
| `btc_eth_midterm_v3` | SL-баг исправлен, нужен param sweep | TZ → Codex |
| `elder_triple_screen_v3` | дефолты дают 0 сделок (фильтры строгие) | TZ → Codex |
| `inplay_breakout` | HTF SL ATR-scale fixed, нужен retune | TZ → Codex |
| weekly DeepSeek audit | сэндбокс блокирует SSH/DeepSeek/Telegram | вынести на серверный cron |

---

## 5. Свежие победители — кандидаты в продакшн

Из `AUDIT_REPORT_20260427.md`:

- `breakdown_v1_current90_focus_v1_r002` — PF=4.30, WR=0.74, DD=1.97%, score=41.90. **Только 23 сделки** — выборка маленькая, продвигать в портфель опасно. Сначала recent-180 → annual confirmation.
- `impulse_volume_breakout_v1_annual_repair_v1_r073` — PF=1.98, WR=0.64, DD=2.28%, **95 сделок**. Это самый чистый кандидат: годовой горизонт, нормальная выборка. Готов к WF-22.
- `att1_initial_sweep_v1_r424` (от 04-18) — PF=1.32, DD=7.27 на 1944 сетке. Уже в стадии portfolio-test.
- `bear_chop_core_repair_v1_r971` (от 04-11) — PF=2.17, DD=3.01, score=44.75. Самый высокий score на диске, но sweep уже 16 дней; нужен свежий прогон.

---

## 6. Что я предлагаю сделать (ничего ещё не применено)

### 6.1. v7 risk cut — гибрид (бэктест → совещание → push)

Логика: разделяю v7 на два класса.

**Bybit-уникальные edge'ы — режу до 0.3, оставляю торговать для накопления статистики:**
- `funding_rev` (8h funding mean reversion — реальный perp-edge)
- `liq_cascade` (liquidation engine overshoot — bidirectional)

**Дубль/шум — выключаю в 0.0 до WF-22:**
- `breakdown_v2` (есть рабочий v1, v2 пока даёт 0 сделок в backtest)
- `slope_choch` (логика частично перекрывается с sloped_channel_v1)
- `micro_scalp` (5m скальпер — без валидации опасен по частоте)

Diff (предлагаемый, **не применённый**):

```diff
# configs/portfolio_allocator_policy.json
  "name": "breakdown_v2", ...
- "base_risk_mult_by_regime": { "bull_trend": 0.0, "bull_chop": 0.0, "bear_chop": 0.85, "bear_trend": 1.05 }
+ "base_risk_mult_by_regime": { "bull_trend": 0.0, "bull_chop": 0.0, "bear_chop": 0.0,  "bear_trend": 0.0  }

  "name": "slope_choch", ...
- "base_risk_mult_by_regime": { "bull_trend": 0.0, "bull_chop": 0.2, "bear_chop": 0.75, "bear_trend": 1.0 }
+ "base_risk_mult_by_regime": { "bull_trend": 0.0, "bull_chop": 0.0, "bear_chop": 0.0,  "bear_trend": 0.0 }

  "name": "liq_cascade", ...
- "base_risk_mult_by_regime": { "bull_trend": 0.75, "bull_chop": 0.6, "bear_chop": 0.6, "bear_trend": 0.8 }
+ "base_risk_mult_by_regime": { "bull_trend": 0.30, "bull_chop": 0.30, "bear_chop": 0.30, "bear_trend": 0.30 }

  "name": "funding_rev", ...
- "base_risk_mult_by_regime": { "bull_trend": 0.65, "bull_chop": 0.85, "bear_chop": 0.85, "bear_trend": 0.65 }
+ "base_risk_mult_by_regime": { "bull_trend": 0.30, "bull_chop": 0.30, "bear_chop": 0.30, "bear_trend": 0.30 }

  "name": "micro_scalp", ...
- "base_risk_mult_by_regime": { "bull_trend": 0.7, "bull_chop": 0.8, "bear_chop": 0.8, "bear_trend": 0.7 }
+ "base_risk_mult_by_regime": { "bull_trend": 0.0, "bull_chop": 0.0, "bear_chop": 0.0, "bear_trend": 0.0 }
```

### 6.2. Перед применением — парный backtest

- 365d portfolio replay со старой политикой (v7-default) и с новой (v7-cut)
- Сравнить: `net_pnl`, `PF`, `max_dd`, `trades_total`, `trades_per_month`, `negative_months`, `max_negative_streak`
- Принимаем **только если** новая ≥ старой по PF и DD, и не теряет более 30% сделок
- Если режем сделки сильно — предусмотреть, что компенсируем сразу промоушеном `impulse_volume_breakout_r073`

### 6.3. WF-22 для двух свежих победителей

Готовлю CODEX_TASK файл в стиле существующих, с командами и acceptance criteria. Параллельно с (6.1)-(6.2).

### 6.4. Диагностика 4 сломанных стратегий

Делаю сам (не Codex):
- `breakdown_v2` 0-trades — чтение strategies/alt_inplay_breakdown_v2.py + smoke-run на тестовых данных
- `flat_live_canary` 0-trades — поиск gating bug в overlay/health_gate
- `elder_v3` over-constrained — анализ фильтров, предложить relax
- `midterm_v3` — проверка SL fix (commit 3fd801f) что действительно правильно встал

### 6.5. Phase 3 — спроектировать (пока без кода)

Контракты для:
- `auto_apply_research_winner.py` — защита: ≥3 одинаковых run + тихое окно 02-04 UTC + dry-run mode
- `live_vs_backtest_monitor.py` — rolling 30d live PF vs backtest PF, порог 0.6, действие = pause + reopt queue
- `params_history.jsonl` — append-only лог с P&L attribution

Пишу архитектурный документ (1 страница), смотрим втроём, потом реализация.

### 6.6. Weekly audit fix

Перенести SSH+DeepSeek+TG часть в серверный cron (там сеть открыта), а в Claude VM scheduled-task оставить только локальный сканер `backtest_runs/`. Готовлю патч для скрипта + cron entry.

---

## 7. Чего я НЕ делаю в эту сессию

- Не правлю код в репозитории
- Не делаю git commit, не пушу
- Не трогаю боевой сервер (SSH из VM всё равно заблокирован, как показал аудит)
- Не предлагаю менять `base_risk_per_trade` — он уже выставлен в 1%, как ты хочешь

---

## 8. Безопасность — отдельный звонок

В `/Users/.../bybit-bot-clean-v28/.env` строка 17 содержит **Bybit API key + secret в открытом виде** (`BYBIT_ACCOUNTS_JSON`).

`.gitignore` это покрывает (`.env` обычно ignored), но проверять надо: сделай `git log -p -- .env` и убедись, что эти ключи никогда не попадали в коммиты. Если попадали — ротировать на Bybit немедленно. Депозит маленький, но прецедент опасный.

---

## 9. Список приоритетов для совещания «втроём»

| # | Что | Кто делает | Срок | Риск |
|---|---|---|---|---|
| 1 | v7 risk cut (см. 6.1) + парный backtest | я | 1 сессия | низкий — только конфиг |
| 2 | WF-22 TZ для impulse_r073 + breakdown_v1_current90_r002 | я пишу TZ, Codex прогоняет | 2-3 дня | нулевой |
| 3 | Диагностика breakdown_v2 / flat_canary / elder_v3 | я | 1-2 сессии | нулевой (пока не правим код) |
| 4 | Param sweep midterm_v3, inplay_breakout retune | TZ → Codex | 2-3 дня | нулевой |
| 5 | Код-обзор smart_pump_reversal_bot.py | я | 2-3 сессии | нулевой |
| 6 | Phase 3 архитектура (auto-apply, degradation monitor) | я (доку), потом ревью | 1 сессия на доку | средний — спроектировать защиты |
| 7 | Weekly audit pipeline fix | я | 1 сессия | низкий |
| 8 | Bybit ключи: проверить git history, при необходимости ротейтнуть | ты на droplet | срочно | критический если утекли |

---

## 10. Вопросы для совещания с GPT/Codex

1. Согласны ли с гибридом v7 (funding_rev/liq_cascade=0.3, остальные=0.0)? Или жёстче — все в 0.0 до WF-22?
2. Готов ли Codex взять WF-22 двух кандидатов прямо с этого репо, или нужна отдельная подготовка данных?
3. Какие KPI считаем достаточными для промоушена `impulse_r073` в портфель: WF-22 ≥13/22 windows как у att1, или жёстче?
4. По Phase 3 auto-apply — какой минимум одинаковых runs допустим (ROADMAP пишет ≥3, может стоит 5)?
5. По gating bug `flat_live_canary` — это известная Codex'у проблема, или диагностика с нуля?

---

*Конец отчёта. Готов разбирать по пунктам.*
