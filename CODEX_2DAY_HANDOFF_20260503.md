# Codex — handoff на возврат через 2 дня
**Дата:** 2026-05-03 вечер
**Размер:** короткий, чтобы не есть твои токены

## TL;DR

Я нашёл и задокументировал **главный bug «0 trades за 5 дней»**: смена режима bear_chop→bull_chop ~30 апр + отсутствие `regime_overlay_bull_chop.env` + мой ARF1 guard. Закоммитил `8447d00` (1 commit, 21 файл, 2078 строк) на твою ветку `codex/dynamic-symbol-filters`. Не запушил — твоё решение.

## Что в коммите 8447d00

### Critical fix (готов к live deploy после твоего acceptance test)
- `configs/regime_overlay_bull_chop.env` — НОВЫЙ overlay
- `configs/portfolio_allocator_policy_canary_v2_1.json` — flat.bull_chop=0.65, bounce1.bull_chop=0.85, impulse.bull_chop=0.6
- `configs/crypto_income_live_canary_v2_1.env` — REGIME_OVERLAY_ENABLE=1, ASB1+IVB1+breakout enable

### Web UX (бекенд+фронт)
- `web/routes/data_routes.py` — /api/status теперь возвращает last_trade_age_sec, today_pnl, abnormal_no_trades flag
- `web/static/index.html` — top-bar pills: "Today $X +Nt" + "last: Xh" (красный+blink если >24h)

### Tier-1 idempotency primitives (для будущего push)
- `bot/order_link.py` — pure helpers
- `tests/test_order_link_id.py` — 10 unit tests, all passing
- `smart_pump_reversal_bot.py` wiring **НЕ в этом коммите** (есть в моих uncommitted changes от прошлой сессии — реши сам, мерджишь или нет)

### Стратегические spec'и (готовы к ночному run)
- 5 autoresearch JSONs в `configs/autoresearch/`: asb1_bull_chop_repair, att1_density_v3_more_pivots, liquidity_sweep_reversal_v2_param_sweep, elder_v3_macro_off_full_relax, pump_fade_v5_bear_window
- + 4 spec'а Pair 1/Pair 2 (range/sloped split)
- Итого 2106 backtest combinations

### Documents (для контекста)
- `CLAUDE_MORNING_REPORT_20260503.md` — отчёт пользователю (на 8 разделов)
- `LIQUIDITY_HUNTER_V1_REVIEW_20260503.md` — review твоего liquidity sweep strategy (6 замечаний)
- `ALPACA_500_DEPLOY_PLAN_20260503.md` — главное: bracket orders уже работают, не блокер

## Что прошу тебя сделать когда вернёшься

### 1. Acceptance test для canary v2.1 (КРИТИЧНО)
Backtest старого canary v2 vs нового v2.1 на 60d окне с bull_chop dominantly. Если v2.1 даёт net ≥ +5 при PF ≥ 1.4 в bull_chop window И не деградирует bear_chop window > 1.5pp DD → push в live.

### 2. Если acceptance OK — deploy на сервер
- swap canary v2 → v2.1 env
- swap policy → policy_canary_v2_1.json
- restart bybot.service
- 24h monitor: должны быть сделки (сейчас регим bull_chop, ASB1 и ATT1 longs должны срабатывать)

### 3. 5 ночных autoresearch (если есть 1-2 часа CPU)
Запустить параллельно по 2 jobs:
```bash
for s in configs/autoresearch/{asb1_bull_chop_repair,att1_density_v3_more_pivots,liquidity_sweep_reversal_v2_param_sweep,elder_v3_macro_off_full_relax,pump_fade_v5_bear_window}_v1.json; do
  nohup .venv/bin/python3 scripts/run_strategy_autoresearch.py --spec "$s" --jobs 2 > "logs/$(basename $s .json).log" 2>&1 &
done
```

### 4. Решить про Tier-1 patch
Я применил orderLinkId+retry locally 5 дней назад и сделал unit-tests (10 pass). Они в коммите 8447d00. Но wiring в monolith мог быть в твоих uncommitted modified files (smart_pump_reversal_bot.py если ты его трогал). Сверь с моим патчем `PATCH_TIER1_orderLinkId_RETRY_20260429.md` и реши: применять, мерджить, или дропать.

## Что я НЕ делал

- Не push'ил в origin
- Не трогал твои modified files (portfolio_engine.py, run_portfolio.py, alt_inplay_breakdown_v1.py, и т.п.)
- Не deploy'ил v2.1 в live
- Не запускал autoresearch — spec'и готовы, сам запусти

## Кратко по приоритетам пользователя

Он спросил: «можно ли запустить ALPACA $500 уже сейчас?». Мой ответ — **да, через 1-2 недели**. Bracket orders уже работают на стороне брокера (`alpaca_paper_bridge.py:418-431` ставит `order_class=bracket` с TP+SL). Это базовая защита капитала. Trailing — улучшение, не блокер. См. `ALPACA_500_DEPLOY_PLAN_20260503.md` за полным roadmap.

Пользователь спал когда я работал, скоро увидит `CLAUDE_MORNING_REPORT_20260503.md`.
