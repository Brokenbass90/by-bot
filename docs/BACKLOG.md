# Backlog — приоритезированный список действий

**Last updated:** 2026-05-25
**Формат:** P0 (этой недели, блокирующее) → P1 (этого месяца) → P2 (когда выйдем в плюс)
**Правило:** один пункт = 1 строка. Подробности — в спеках, не здесь.

## P0 — этой недели (блокирует первые trades)

| # | Задача | Кто | Где спека | Acceptance |
|---|---|---|---|---|
| P0-NEW | **Crypto live-vs-static_v1 parity fix.** `crypto_income_static_v1` доказан в backtest, но текущий live-effective состав другой. Сравнить static_v1 vs live-effective на tradeful окнах, затем точечно чинить: symbol mismatch → router/allowlist, strategy mismatch → enable flags, allocator mismatch → policy. | Codex | `scripts/run_crypto_income_static_v1_candidate.sh`, `scripts/run_live_effective_parity.py`, `scripts/weekly_live_vs_backtest_report.py` | Live/test effective stack воспроизводит ≥80% decisions static_v1 на 7-30d tradeful окне; до этого новые стратегии не promoted |
| P0-1 | **Same-bar guard fix.** Задеплоено 2026-05-19 11:13 UTC: ATT1/ASM1/FLAT планируются раз в 55m, MIDTERM раз в 235m. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §3.1 | Monitor 2-24h: `att1_ns_same_bar / att1_try ≤ 20 %` |
| P0-2 | **Midterm grouped no-signal counters.** Deployed 2026-05-19 11:43 UTC: `midterm_ns_*`. | Codex | `docs/MIDTERM_GROUPED_COUNTERS_SPEC_20260519.md` | Monitor fresh sample |
| P0-3 | **Skip-portfolio split.** Deployed 2026-05-19 11:43 UTC for active sleeves: max_positions / overlap / global_risk / other. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §3.2 | Monitor fresh sample |
| P0-4 | **AI full-context + extras cron.** Done on server: `full_context.json` + `extras.json` every 5 min. | Codex | `scripts/build_ai_full_context.py`, `scripts/build_ai_extras.py` | Monitor freshness |
| P0-5 | **DeepSeek/web prompt подключить runtime packs.** Deployed: setup cards, crypto blocker, deeper trade history, errors, indicators, top OHLC, memory lines. | Codex | `AI_CONTEXT_BRIDGE_SPEC_20260517.md` (ORACLE stage) | Ask AI: must cite setup cards / blocker counters / AI extras |
| P0-6 | **Scheduler allowlist parity for active sleeves.** Done 2026-05-21: `ATT1`, `ASM1`, `sloped` scheduler now reads fresh env allowlists before scheduling. Added `sloped_ns_*` grouped counters. | Codex | `smart_pump_reversal_bot.py`, `strategies/alt_sloped_channel_v1.py`, `bot/diagnostics.py` | 30-60m sample: no `*_ns_symbol` domination from scheduler drift |
| P0-7 | **Breakdown router geometry force-keep for validated ADA/ONDO.** Done 2026-05-22: `breakdown_bear_core` was selecting ADA/ONDO before geometry, then geometry removed them; now validated ADA/ONDO survive geometry only if already selected by router. | Codex | `scripts/build_symbol_router.py`, `configs/strategy_profile_registry.json` | 1-3h sample: ADA/ONDO no longer `blocked_by_symbol_allowlist`; next blocker must be real strategy filter (`support/rsi`) or entry |
| P0-8 | **Sloped live 5m confirmation parity.** Done 2026-05-22: pending sloped setup now confirms against real closed 5m OHLC instead of zero OHLC from the live scheduler call. | Codex | `strategies/sloped_channel_live.py` | 1-3h sample: if sloped reaches pending state, no false invalidation from zero OHLC; next blockers must be real channel/filter reasons |

## P0.5 — параллельно (read-only research)

| # | Задача | Кто | Где |
|---|---|---|---|
| P0.5-1 | Done 2026-05-19: `scripts/alpaca_dynamic_v2_backtest.py`; winner by script score = STATIC_BH, dynamic_v2 not promoted. | Codex | `runtime/alpaca_v2_backtest_report_20260519.json` |
| P0.5-2 | Done 2026-05-20: `scripts/crypto_strategies_backtest.py` ASB1/ATT1/IVB1/RANGE_SCALP × 365d × 5 монет. Only IVB1_static was weak-positive (PF≈1.18); ASB1 not enough evidence for live. | Codex | `runtime/crypto_backtest_report_20260519.json` |
| P0.5-3 | Подождать завершения ASB1 repair queue. Если все варианты FAIL — ASB1 → «redesign», не live. | Codex | runtime/research_nightly/ |
| P0.5-4 | Current running 2026-05-20: `elder_v3_macro_off_full_relax_v1` autoresearch. После него — `att1_density_more_pivots`. | Codex | runtime/research_nightly/ |
| P0.5-5 | Run 2026-05-20: `compare_live_pulse_vs_backtest.py` shows open_trades=0, flat true no-signal/range, breakdown symbol/no-setup, ATT1/midterm no attempts. Use symbol-aware blocker before touching filters. | Codex | `runtime/bot_heartbeat.json` |
| P0.5-6 | Done 2026-05-19 17:24 UTC: approved breakdown router/profile patch applied for ADA+ONDO only; ENA excluded. Active router includes ADA now; ONDO staged but geometry-filtered until setup quality improves. | Codex | `backtest_runs/portfolio_20260519_170243_breakdown_new_symbols_180d_20260519/summary.csv` |

## P0.9 — менеджерская чистка (low risk, high signal)

| # | Задача | Кто | Acceptance |
|---|---|---|---|
| P0.9-1 | Удалить definite trash: `%s`, `.DS_Store`. | owner / любой | git clean |
| P0.9-2 | Удалить с согласия owner'а: 27 старых `CODEX_TASK_*.md`, 3 `AUDIT_REPORT_2026040*.md`, 5 morning/night/status/recon docs, `alt_liquidity_sweep_reversal_v1.py`. ~36 файлов из корня. | owner→Codex | `git diff --stat` показывает только deletions |
| P0.9-3 | Перенести 22 спеки от 17 мая в `docs/specs/` подпапку. | Codex | `ls docs/specs/*_20260517.md` |
| P0.9-4 | Disk hygiene: rotate `backtest_runs/` (оставить 30 дней + best-of), архивировать остальное. | Codex | `du -sh backtest_runs/` ≤ 200 MB |
| P0.9-5 | Подтвердить что Alpaca configs v35/v36/dynamic_v1/v2_broad/1000usd/small_cap не используются → удалить. | Codex (grep) | `grep -r alpaca_paper_v35` empty |
| P0.9-6 | Done 2026-05-20: rotate noisy `runtime/allocator_decisions.jsonl` (~473 MB) and disable allocator decision trace by default. | Codex | `runtime/archive/allocator_decisions_20260520_0515.jsonl` |
| P0.9-7 | Done 2026-05-20: deleted archived allocator trace on server and fixed cleanup fallout: `run_portfolio.py` no longer crashes when retired `alt_liquidity_sweep_reversal_v1` is absent. | Codex | `py_compile` local + server OK |

## P1 — этого месяца (после P0)

| # | Задача | Кто | Где спека |
|---|---|---|---|
| P1-1 | **Monitor approved bear router update.** Breakdown ADA+ONDO profile patch deployed; next decision after 24-72h counters/trades. Не включать ASB1. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §3.3 |
| P1-1a | **Done 2026-05-20: restore proven crypto package via shadow/replay, not blind live.** Static rerun: +70.17%/365d, PF 1.545. Control-plane replay: +42.31%/360d, PF 1.383, DD 5.87, 536 trades, 1 red month. Current live approximation: +17.45%/365d, PF 1.211, DD 13.25. | Codex | `backtest_runs/dynamic_annual_20260520_100256_codex_p1_1a_static_v1_control_plane_replay_20260520/summary.json` |
| P1-1b | **Done 2026-05-20: prepare static-v1 live parity/shadow, no live env edits.** Synced missing static-v1 policy/health/env artifacts to server. Dry-run shows static-v1 policy in current `bear_trend` enables `flat+breakdown` only; ATT1/midterm are blocked by orchestrator, not allocator policy. | Codex | Acceptance: no live restart/env edit |
| P1-1c | **Done/monitor: backtest-driven symbol/router expansion for static core.** Owner-approved live deployment active; after adequate sample, allowlist mismatch is no longer dominant. Internal blockers now dominate: `breakdown_support`, `ATT1_trendline`, `flat_touch`. | Codex | Acceptance met for routing diagnosis; continue with targeted filter replay, no blind expansion |
| P1-1d | **Targeted live-filter replay.** Reproduce current `breakdown_ns_support`, `att1_ns_trendline`, `flat_ns_touch` over a tradeful window and test one bounded relaxation/logic repair per sleeve. | Codex | Promote only if PF≥1.25, DD≤8%, trades≥30 and negative months do not worsen |
| P1-1e | **Signal/timestamp parity after router fix.** Dead-zone audit done: latest 9 replay entries were outside UTC 0/1/2. Report now labels retrospective-config replay correctly; next compare must use a stable post-fix live window. | Codex | Must explain post-fix replay entries vs live before any filter relaxation |
| P1-2 | **SAFETY Patch 1 — SL/TP на брокере.** Bybit V5 `stopLoss`/`takeProfit` params в `place_market()`. Критично для защиты от flash crash. | Codex | `SAFETY_PATCHES_20260517.md` |
| P1-3 | **SAFETY Patch 2 — TRADES race fix.** `threading.RLock` + persistent snapshot. | Codex | `SAFETY_PATCHES_20260517.md` |
| P1-4 | **Funding carry DRY_RUN** через cron `*/30 * * * *` на неделю. | Codex | `FUNDING_CARRY_ACTIVATION_20260517.md` Phase 1 |
| P1-5 | **direction-aware `global_risk_mult`.** Разделить на `long_risk_mult` / `short_risk_mult` в orchestrator. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §3.4 |
| P1-6 | После P1-1 + P1-2: **активация 2-3 strategies** через acceptance gate (BRC1, alt_bear_breakdown_v1, alt_squeeze_breakout_v1). `base_mult=0.5` start. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §2 |
| P1-7 | **DeepSeek reporting integrity.** Done 2026-05-25: weekly audit attributes metrics from each sleeve's own trades; universe proposals are backtest-only and evidence-bound. | Codex | `scripts/deepseek_weekly_cron.py --dry-run --phases audit,research,report --skip-universe` |
| P1-7a | **Read-only market context for AI.** Feed cited/cached macro, earnings, sector/news headlines, Bybit liquidity/funding snapshots to `ai_context`; AI may propose research only. | Codex | No direct config/order writes; freshness + source URL required in every snapshot |
| P1-8 | Alpaca v39 (если backtest v2 пройдёт): paper 14 дней с `ALPACA_DYN_V2_ENABLED=1`. | Codex | результаты P0.5-1 |
| P1-8a | Alpaca market data freshness check: intraday dry-run 2026-05-19 видел last bar 2026-05-18 19:30 UTC. Проверить feed/cache перед active paper switch. | Codex | `scripts/equities_alpaca_intraday_bridge.py` |
| P1-8b | Done 2026-05-20: `v3_shadow` defaults to dry-run; stale SCHW pending paper orders cancelled; no more shared-account order conflict expected. Next: verify today during US session. | Codex | `logs/alpaca_intraday_dynamic_v3_shadow.log` |
| P1-8c | **Alpaca v39 event-based rebalance.** 24m best saved: `+88.05%`, PF `1.987`, WR `62.0%`, DD `12.90%`, red months `6/24`. 4y focused stress: `+140.20%`, PF `1.624`, DD `26.47%`, red months `16/52`; return beats static, quality gate does not. Still research-only; next refine exits/regime before paper shadow. | Codex | `scripts/alpaca_v3_event_backtest.py`, `strategies/alpaca_dynamic_v3_event.py` |
| P1-9 | **Депозит Фаза 1: $500 → Bybit** (если P0-1..P0-3 done + ≥ 10 trades + PnL ≥ −5 % 7 дней). | owner | `docs/PROJECT_STATUS.md` Финансовая фаза |
| P1-10 | Champion-challenger v1 на одной sleeve (ASB1) — shadow only. | Codex | `CHAMPION_CHALLENGER_FRAMEWORK_20260517.md` |

## P2 — после первого положительного месяца

| # | Задача | Когда триггерится |
|---|---|---|
| P2-1 | **Депозит Фаза 2: $500 → Alpaca real.** | 14 дней stable Bybit |
| P2-2 | Alpaca sector rotation 2+2 (paper 30 дней). | После P1-8 |
| P2-3 | Multi-timeframe confirmation для 7 sleeve. | После P1-6 success |
| P2-4 | Volatility-targeted sizing (ATR-normalized). | После P1-3 |
| P2-5 | **Депозит Фаза 3: +$700 Bybit + $300 Alpaca.** | 30 дней PF≥1.1, DD≤10% |
| P2-6 | DeepSeek weekly review cron (вс 21:00). | После P0-5 stable 14 days |
| P2-7 | AI ADVISOR stage — `/api/ai/suggest` + approve flow. | После 14d ORACLE stable |
| P2-8 | **Depozit Фаза 4: funding-carry sub-account $50.** | После P1-4 success |
| P2-9 | Bybit sub-account separation. | После P2-8 |
| P2-10 | Cross-asset hedge `panic_mode_detector.py` shadow. | После P1-2 |

## P3 — long-term (3-6+ месяцев)

| # | Задача | Когда |
|---|---|---|
| P3-1 | OANDA forex live. | Когда придёт API ключ |
| P3-2 | AI EXECUTOR stage (auto-apply whitelisted). | После 90d ADVISOR >65% accuracy |
| P3-3 | Live retraining pipeline. | После 3 мес champion-challenger |
| P3-4 | Genetic algorithm strategy evolution. | После 3 мес champion-challenger |
| P3-5 | Phase 2 monolith refactoring (12k строк → модули). | После 60 дней stable работы |
| P3-6 | HF scalping layer. | После $5k+ equity |

## ❌ Заморожено / отменено

| Что | Почему |
|---|---|
| `crypto_income_live_canary_v2_3_bear.env` (мой предыдущий план) | Нарушает non-negotiable rule «do not increase strategy set based on single backtest». Сначала P0. |
| Активация 11 alt_*_v1 strategies без backtest | Acceptance gate не пройден ни одной |
| Alpaca dynamic_v1 в production | Backtest проиграл buy-and-hold |
| Alpaca v38 more-active research → live | Хуже hybrid top4 по risk-adjusted |
| `alt_liquidity_sweep_reversal_v1.py` | Superseded by v2 |
| OANDA scope | Заморожен до конца лета |

## Acceptance gate (универсальный для P1-6, P1-8 и т.д.)
- PF (на 60+ дней backtest) ≥ 1.25
- MaxDD ≤ 8 %
- Net return ≥ 8 %
- Negative months ≤ 3
- Negative streak ≤ 2
- Trades count ≥ 30 (статистическая значимость)
- Fees + slippage учтены явно

## Стандарт TG-отчёта Codex'а после каждого P0/P1
```
🟢 [P0-1] DONE
Что: same-bar fix in ATT1/ASM1/Flat
Метрики:
  att1_ns_same_bar/try: было 96% → стало 14%
  att1 first signals за 24h: 3
  bot first live trade 2026-05-21 14:32 UTC, PnL +0.42$
Verdict: DEPLOY
Next: P0-2
```

## Изменения в backlog
- 2026-05-25: Corrected DeepSeek weekly attribution bug and gated universe proposals as backtest-only. Added P1-1e signal/timestamp/no-entry-hours parity and P1-7a read-only external market context; live settings unchanged.
- 2026-05-25: Dead-zone did not explain the latest live/replay gap (`0/9` replay entries in UTC 0/1/2). Hardened weekly interpretation: current-config replay over pre-deployment days is counterfactual; require a stable post-fix window.
- 2026-05-25: Router/static-core live sample now shows internal strategy filters as the blocker; added P1-1d targeted filter replay. Fixed broken breakdown bear research TF; its 36 variants failed. ATT1 focused 360d sweep produced a challenger (`+23.97%`, PF `1.278`, DD `9.82%`) that needs DD repair. Alpaca v39 4y stress retained for research only.
- 2026-05-24: Added P1-1c router static-core pins and saved Alpaca v39 best research config. Started local detached candidate matrix `candidate180_bear_flat_20260524` for BRC1/range/breakdown_v2/bear_breakdown on proven symbols.
- 2026-05-22: P0-7 done. Rebuilt server router/allocator: `BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,ADAUSDT,ONDOUSDT`, breakdown count 4, no hard block. Fresh compare after restart: stream alive, no portfolio/global block; sample too small, next check after 1-3h.
- 2026-05-21 evening: P0-6 done. Found `sloped_ns_symbol=116/119` after grouped diagnostics; patched sloped scheduler allowlist. Earlier same session patched ATT1/ASM1 scheduler allowlist drift. Server stream fresh after controlled restart.
- 2026-05-21: Добавлен P0-NEW live-vs-static_v1 parity fix. Главный recovery путь: не искать новые sleeves, а заставить live-effective stack повторить proven `crypto_income_static_v1` decisions ≥80% на торговом окне.
- 2026-05-19: первая редакция. Все 22 спеки от 17 мая распределены по P1/P2/P3.
- 2026-05-19: Codex update — AI extras pack deployed; flat fresh blocker пока internal no-signal; Alpaca fractional bracket 422 patched via simple-order fallback for fractional paper entries.
- 2026-05-19: Codex applied approved breakdown ADA+ONDO router fix; ADA active, ONDO staged by registry but filtered by geometry at current market snapshot.
- 2026-05-19: Codex hardened `build_ai_ohlc_and_logs.py` with public Bybit live-fetch fallback and filtered log tail; started crypto strategies backtest in background.
- 2026-05-20: Morning check — no Bybit trades overnight; compare shows portfolio/global-risk skips still dominate. Alpaca v3 shadow changed to dry-run, stale SCHW pending orders cancelled, DeepSeek evidence gate tightened, allocator trace bloat disabled.
- 2026-05-20: Control rerun confirmed `crypto_income_static_v1` still reproduces +70.17%/365d; current live mismatch is allocator/regime path disabling ATT1/midterm, not disappearance of the edge.
- 2026-05-20: P1-1a control-plane replay finished: +42.31%/360d, PF 1.383, MaxDD 5.87, 536 trades, 1 red month. Next is P1-1b live parity/shadow, not live activation.
- 2026-05-20: P1-1b dry-run finished; static-v1 artifacts synced to server. `build_crypto_setup_blocker_report.py` is now symbol-aware and shows current blocker is mostly allowlist/router mismatch, not only strategy filters.
