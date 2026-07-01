# CODEX HANDOFF — 2026-07-01 (от Claude). Тёрнкей на деплой+прогон.

Claude собрал 11 новых модулей-технологий, ВСЕ под тестами (прогон ниже 100% зелёный).
Сервер/деньги — Codex/владелец. Порядок строгий.

## 1. ЗАКОММИТИТЬ (bot/ + tests/, всё зелёное)
range_filter, pump_exhaustion, retest_quality, elder_filter, breakout_confirm,
oos_selector, level_entry, position_sizing, exposure_gate, decision_bus,
cascade_reversal, wf_folds, news_session_filter (+ соответствующие tests/test_*.py). ИТОГО 12 модулей.
Прогон (общий `pytest tests/` падает на чужом scripts/alpaca_v3_event_backtest.py -> sys.exit(2),
ПРЕДСУЩЕСТВУЮЩИЙ баг, чинить отдельно; наши гоняются явным списком):
  pytest tests/test_range_filter.py tests/test_pump_exhaustion.py tests/test_retest_quality.py \
    tests/test_elder_filter.py tests/test_breakout_confirm.py tests/test_oos_selector.py \
    tests/test_level_entry.py tests/test_position_sizing.py tests/test_exposure_gate.py \
    tests/test_decision_bus.py tests/test_cascade_reversal.py tests/test_wf_folds.py \
    tests/test_news_session_filter.py

## 2. ЧИСТКА проекта (reports/CLEANUP_PLAN_2026_07_01.md) — «архив, не корзина»
git rm --cached кэши/tmp (.gitignore дополнен); 85 корневых .md -> docs/archive;
~71 FREEZE/ARCHIVE стратегий -> strategies/archive (после grep импортов + апдейт каталога);
reports старьё -> reports/archive. Активная поверхность ~15-20 стратегий.

## 3. WIRING технологий в ноги (сплит short/long везде)
range_filter/retest_quality/breakout_confirm/pump_exhaustion/elder_filter -> bounce/fade/breakout/pump ноги;
level_entry -> maker-вход У уровня (не по закрытию); position_sizing -> единый sizer;
exposure_gate -> risk-manager; decision_bus -> каждая нога пишет запись (контекст+plan+outcome).
Спеки: RANGE_FILTER_WIRING, INPLAY_V4_REWORK (реворк InPlay V4).

## 4. WF — ТОЛЬКО с технологиями и честно (иначе тест недействителен)
- Гонять РЕВОРКНУТЫЕ ноги (с хелперами), maker-fill через level_entry.simulate_fill.
- Фолды через bot/wf_folds.purge_embargo_folds (gap>=max-hold), отбор через bot/oos_selector
  (passes==True/robust_plateau, НЕ PF-пик). Свип: tp_rr{2,2.5,3}, require_all/require_with_tide, min_quality.
- Приоритет: ФОРЕКС (ranges чище) + символы с чистыми уровнями.

## 4b. ФОРЕКС news/session-гейт (bot/news_session_filter.py)
Подключить к форекс range/bounce ногам. В WF: PF новостных vs чистых дней; новостной PF<0.8 -> фильтр обязателен (DeepSeek H2). Избегать входа за 1ч до NFP/ставок + тонкой азиатской сессии.

## 5. H4 — честный тест каскадов (bot/cascade_reversal.py)
На MID-CAPS (SOL/AVAX/LINK/MATIC), НЕ BTC/ETH (переполнено), РЕАЛЬНЫЕ liq-данные коллектора.
Триггеры: funding z>=2, OI-drop>=5%/15м, liq>=95п/4ч, вход +2 бара, SL1/TP2 ATR. Гейт PF>1.3 -> canary $50.
Прошлый liquidation_cascade_entry_v1 FAIL был на BTC/ETH+proxy+неполные триггеры -> не опровержение.

## 6. МЕХАНИКА (деньги)
Carry: НЕ live; ре-гейт (CARRY_REGATE_SPEC) ИЛИ узкая ниша DeepSeek (negative-funding-side, hold 3-5 циклов).
Pair-arb: WF на длинной истории (research-хост). SpikeFadeV3: лестница SPIKEFADE_V3_PRECANARY_GATE.

## 7. ALPACA (владелец) — первый реальный плюс
$500: ключи в server-only configs/alpaca_live_v38.env, dry-run -> OK -> live.

## ИНФРА-ПРАВИЛО
Тяжёлые свипы — только research-хост/локально, НИКОГДА рядом с live на 1GB VPS.

## Вернуть утром (разберёт Claude по OOS)
WF-цифры реворкнутых ног (форекс+крипта), H4 PF по mid-caps, carry net-за-цикл, pair-arb WF, Alpaca dry-run лог.
Ключевые доки: ROADMAP_V4, DEEPSEEK_RESPONSE_ACTIONS, RESEARCH_IDEAS, PROJECT_STATE_LEDGER (все 2026-07-01).

## Codex update — 2026-07-01

- Focused verification passed: `109 passed` for helper, InPlay, SpikeFade and
  new P0/P1 modules.
- `scripts/spike_fade_robustness_gate.py` fixed: missing cache in cross-symbol
  sanity no longer crashes the whole gate; it records a skipped row.
- First full SpikeFade gate stopped on missing `NEARUSDT` cache. Restarted as
  `screen sfv3_robust_gate_20260701_v2` with cached cross-symbols:
  `SOLUSDT,SUIUSDT,DOGEUSDT,ADAUSDT`.
- Cleanup is not executed blindly. `.gitignore` and plan are safe; strategy
  archiving requires grep/import/catalog check first.
- Server safety: stopped stale `arf1_structured_short_repair_20260627`
  research on the 1GB live VPS (`~446MB RAM`, `~82% CPU`). Available RAM
  recovered from about `134MB` to about `561MB`. Live bot and liquidation
  collector were not touched.

## Codex update — 2026-07-01 mechanics wiring

- SpikeFadeV3 robust gate completed and FAILED:
  `29` OOS trades, `+0.93R`, PF `1.144`, bad fold `-1.10R`,
  fee-stress failed. Do not canary SpikeFadeV3 LINK short.
- `backtest/portfolio_engine.py` now supports pending limit-signal execution:
  `entry_order_type=limit`, fill only on touch, expiry by `limit_validity_bars`;
  ordinary next-open signals unchanged.
- `strategies/inplay_retest_v4.py` now supports `IRV4_USE_LEVEL_ENTRY`.
  Setup A/B build maker-limit plans via `bot.level_entry`; late-chase rejects
  preserve exact reason.
- Focused verification: `56 passed`.
- First end-to-end smoke:
  - InPlay V4 base, `ADA/DOGE/SUI`, 120d: `61 trades, -3.64R, PF 0.691, DD 6.75R`.
  - InPlay V4 + level-entry: `11 trades, +0.31R, PF 1.25, DD 0.33R`.
  - InPlay V4 + retest_quality + level-entry, 240d:
    `ADA/DOGE/SUI` `22 trades, +2.61R, PF 2.52, DD 0.60R`;
    `LINK/SOL/ADA` `14 trades, -0.19R, PF 0.908`.
- Not live-grade yet. Next required gate: rolling WF using the rewired chain
  (`retest_quality -> level_entry -> pending limit fill/expiry -> costs ->
  wf_folds -> oos_selector`). Details:
  `reports/MECHANICS_WIRING_STATUS_2026_07_01.md`.
- Added `scripts/inplay_v4_mechanics_gate.py` for that next gate. It runs
  rolling train/test on the rewired chain and writes markdown+CSV under
  `reports/research/`. Smoke verification completed; use a longer screen run
  for actual evidence.
