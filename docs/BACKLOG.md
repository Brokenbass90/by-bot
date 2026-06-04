# Backlog — приоритезированный список действий

**Last updated:** 2026-06-04
**Формат:** P0 (этой недели, блокирующее) → P1 (этого месяца) → P2 (когда выйдем в плюс)
**Правило:** один пункт = 1 строка. Подробности — в спеках, не здесь.

## P0 — этой недели (блокирует первые trades)

| # | Задача | Кто | Где спека | Acceptance |
|---|---|---|---|---|
| P0-PROTECT | **Restored-position broker protection repair. Done/deployed 2026-06-04.** A restored BTC bootstrap position had SL but no TP and was incorrectly treated as manually locked. Partial bootstrap protection now remains repairable; existing protection is preserved and the missing side is filled. | Codex | `bot/tpsl_policy.py`, `smart_pump_reversal_bot.py`, `tests/test_tpsl_policy.py` | Any future restored position with only TP or only SL is repaired or hard-failed/alerted; never silently left partial |
| P0-BASELINE | **Strict crypto static-v1 baseline established.** A newly downloaded exact no-gap 365d Bybit dataset gives `+65.89% / PF 1.462 / DD 7.49% / 486 trades / 3` negative months. All four sleeves changed trade counts versus the older `+73.96%` artifact, so the old result remains a cache-provenance reference rather than the promotion gate. | Codex | `backtest/run_portfolio.py`, `scripts/check_exact_kline_cache.py`, `scripts/run_crypto_income_static_v1_candidate.sh` | Done: future package candidates must beat the reproducible strict result on the same exact cache |
| P0-ARB-EVIDENCE | **Cross-exchange arb closed-cycle evidence.** Open shadow PnL is not earned return. Honest report currently has `0` closed current-model cycles and refuses ROI projection. | Codex | `scripts/arb_roi_calculator.py`, `runtime/arb_roi_estimate.json` | At least 10 closed `settlement_execution_v2` cycles, fee/slippage/depth included, before tiny live canary proposal |
| P0-ALPACA38 | **Prepare v38 `$500` real canary.** QCOM high-water trailing close filled in paper, cash/re-entry state updated, and no cleanup conflict remained. The monthly bridge now fails closed on live accounts unless the role/confirmation/capital-cap guard is explicit. | Codex | `scripts/equities_alpaca_paper_bridge.py`, `tests/test_alpaca_live_order_guard.py`, Alpaca account isolation config | Create a monthly-v38-only live credential profile, run read-only preflight, then request explicit approval for the bounded `$500` start |
| P0-HEALTH | **Publish a trusted strategy-health baseline.** `strategy_health_review.py` is active and safely refuses demotion on tiny samples, but `equity_curve_autopilot.py` cannot find a trusted baseline and therefore leaves `configs/strategy_health.json` historical. Do not fake freshness or promote exploratory sweep output. | Codex | `scripts/strategy_health_review.py`, `scripts/equity_curve_autopilot.py`, `configs/strategy_health.json` | A provenance-tagged strict baseline is accepted explicitly; health freshness distinguishes historical backtest age from live observation age |
| P0-RESEARCH-PARITY | **Additive package parity guard. Done 2026-06-04.** Package specs had silently omitted two strict-baseline ARF1 values, and autoresearch resume reused old runs by tag after specs changed. Specs now declare a baseline env, validation rejects missing/mismatched baseline keys, and resume requires a full candidate fingerprint. | Codex | `scripts/validate_sweep_configs.py`, `scripts/run_strategy_autoresearch.py`, `tests/test_sweep_baseline_parity.py`, `tests/test_autoresearch_resume_fingerprint.py` | Any changed base env, command, or overrides must rerun; additive package rows must reproduce the strict baseline when the candidate makes zero trades |
| P0-NEW | **Crypto strict live-vs-static_v1 parity.** Fixed diagnostic returns `FAIL`: live adds `sloped,asm1` and expands static symbols. Runtime account check shows actual live concurrency is `MAX_POSITIONS=3` (`leverage=3`, effective risk `0.44%`). Matching strict-three-slot ARF1 `r002` replay is validated: `+67.11% / PF 1.530 / DD 4.82% / 2` red months versus baseline `+62.79% / PF 1.478 / DD 5.36% / 3`; five-slot ceiling remains research-only. Live process currently has no explicit total-portfolio or same-direction risk caps. | Codex | `scripts/compare_static_v1_live_parity_inputs.py`, `configs/crypto_income_arf1_r002_strict3_shadow_candidate.env` | Request explicit approval for a capped strict-three-slot canary: keep leverage/slots unchanged, remove live drift, apply fixed symbols + aggregate/direction caps, then observe 24-48h |
| P0-1 | **Same-bar guard fix.** Задеплоено 2026-05-19 11:13 UTC: ATT1/ASM1/FLAT планируются раз в 55m, MIDTERM раз в 235m. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §3.1 | Monitor 2-24h: `att1_ns_same_bar / att1_try ≤ 20 %` |
| P0-2 | **Midterm grouped no-signal counters.** Deployed 2026-05-19 11:43 UTC: `midterm_ns_*`. | Codex | `docs/MIDTERM_GROUPED_COUNTERS_SPEC_20260519.md` | Monitor fresh sample |
| P0-3 | **Skip-portfolio split.** Deployed 2026-05-19 11:43 UTC for active sleeves: max_positions / overlap / global_risk / other. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §3.2 | Monitor fresh sample |
| P0-11 | **Per-decision crypto trace for final parity diagnosis.** Deployed 2026-05-25 16:35 UTC with `open_trades=0`: bounded diagnostics-only JSONL for `midterm/att1/flat/breakdown`, exposed in `crypto_blocker`/operator AI context. No trade/filter/risk changes. | Codex | `smart_pump_reversal_bot.py`, `scripts/build_crypto_setup_blocker_report.py` | After 2-24h, identify the exact live filters that reject expected static-v1 decisions; file stays bounded at 2 MB |
| P0-SEC | **Rotate Alpaca paper credentials before any real deposit.** 2026-05-25 audit found credential literals in legacy tracked `docs/HANDOFF_20260311_SESH3.md` and historical tracking of `configs/alpaca_paper_local.env`; current HEAD document redacted, local runtime env is ignored. | Owner + Codex | `docs/HANDOFF_20260311_SESH3.md`, `.gitignore` | Create new Alpaca paper keys, revoke old pair, verify `ALPACA_API_KEY_ID=present`/`ALPACA_API_SECRET_KEY=present` only; decide separately whether to rewrite Git history |
| P0-4 | **AI full-context + extras cron.** Done on server: `full_context.json` + `extras.json` every 5 min. | Codex | `scripts/build_ai_full_context.py`, `scripts/build_ai_extras.py` | Monitor freshness |
| P0-5 | **DeepSeek/web prompt подключить runtime packs.** Deployed: setup cards, crypto blocker, deeper trade history, errors, indicators, top OHLC, memory lines. | Codex | `AI_CONTEXT_BRIDGE_SPEC_20260517.md` (ORACLE stage) | Ask AI: must cite setup cards / blocker counters / AI extras |
| P0-6 | **Scheduler allowlist parity for active sleeves.** Done 2026-05-21: `ATT1`, `ASM1`, `sloped` scheduler now reads fresh env allowlists before scheduling. Added `sloped_ns_*` grouped counters. | Codex | `smart_pump_reversal_bot.py`, `strategies/alt_sloped_channel_v1.py`, `bot/diagnostics.py` | 30-60m sample: no `*_ns_symbol` domination from scheduler drift |
| P0-7 | **Breakdown router geometry force-keep for validated ADA/ONDO.** Done 2026-05-22: `breakdown_bear_core` was selecting ADA/ONDO before geometry, then geometry removed them; now validated ADA/ONDO survive geometry only if already selected by router. | Codex | `scripts/build_symbol_router.py`, `configs/strategy_profile_registry.json` | 1-3h sample: ADA/ONDO no longer `blocked_by_symbol_allowlist`; next blocker must be real strategy filter (`support/rsi`) or entry |
| P0-8 | **Sloped live 5m confirmation parity.** Done 2026-05-22: pending sloped setup now confirms against real closed 5m OHLC instead of zero OHLC from the live scheduler call. | Codex | `strategies/sloped_channel_live.py` | 1-3h sample: if sloped reaches pending state, no false invalidation from zero OHLC; next blockers must be real channel/filter reasons |
| P0-9 | **Remove unreviewed live autoresearch override.** Done 2026-05-25: stale auto-apply ATT1 parameters were overriding `static_v1`; bot now loads reviewed `approved_strategy_params.env`, while autoresearch is proposal-only unless explicitly approved. | Codex | `smart_pump_reversal_bot.py`, `scripts/auto_apply_research_winner.py`, `configs/approved_strategy_params.env` | After restart: `open_trades=0`, approved ATT1 values loaded; monitor ATT1 signals/entries for 24h |
| P0-10 | **Alpaca paper ownership isolation.** Done 2026-05-25: monthly bridge now preserves intraday positions while their close order is pending; before fix `META/PANW` were wrongly classified as stale after intraday submitted a close. | Codex | `scripts/equities_alpaca_paper_bridge.py`, commit `f36b2c7` | Observe one complete intraday close cycle: no monthly duplicate close / `held_for_orders` conflict |
| P0-12 | **Alpaca monthly software trailing arming. Done in paper.** Fixed/deployed to v38 paper bridge 2026-05-26 in `89c6f8d`: fractional `GOOGL` reached HWM `+6.40%`, then gave back `5.78%`; run `14:00 UTC` issued trail close and re-entry block, run `14:30 UTC` no longer contained GOOGL and showed no cleanup conflict. | Codex | `scripts/equities_alpaca_paper_bridge.py`, `tests/test_alpaca_monthly_trailing.py` | Reconcile filled ledger, rotate paper credentials and finish cycle review before any `$500` deposit |

## P0.5 — параллельно (read-only research)

| # | Задача | Кто | Где |
|---|---|---|---|
| P0.5-1 | Done 2026-05-19: `scripts/alpaca_dynamic_v2_backtest.py`; winner by script score = STATIC_BH, dynamic_v2 not promoted. | Codex | `runtime/alpaca_v2_backtest_report_20260519.json` |
| P0.5-2 | Done 2026-05-20: `scripts/crypto_strategies_backtest.py` ASB1/ATT1/IVB1/RANGE_SCALP × 365d × 5 монет. Only IVB1_static was weak-positive (PF≈1.18); ASB1 not enough evidence for live. | Codex | `runtime/crypto_backtest_report_20260519.json` |
| P0.5-NEXT | **Next additive package candidates:** IVB1 v2 risk-fixed `r010` is the first candidate to pass annual, live-style strict3, and segmented replays. Five-slot annual: `+74.51 / PF 1.528 / DD 5.52 / 493 trades / 1` red month versus strict baseline `+65.89 / PF 1.462 / DD 7.49 / 3`. Strict3: `+64.90 / PF 1.452 / DD 5.22 / 2` red months versus `+59.31 / PF 1.409 / DD 10.08 / 4`. It improved both half-year segments, although the strong segment added one small red month. PFS1 funding-aware sweep made zero additive trades in all 12 variants and is rejected pending redesign. MTPB/GS1 are also rejected. IVB1 telemetry-only shadow was deployed `2026-06-04 17:29 UTC` with `IVB1_RISK_MULT=0.0`; the code returns before all order submission paths and exposes separate signal/shadow counters. | Codex | `configs/autoresearch/package_ivb1_impulse_additive_v2_riskfix.json`, `configs/ivb1_r010_telemetry_shadow.env`, `tests/test_ivb1_shadow_guard.py`, strict3/segment run artifacts | Compare IVB1 live signals/blocks for 7-14 days before proposing any capital |
| P0.5-3 | Подождать завершения ASB1 repair queue. Если все варианты FAIL — ASB1 → «redesign», не live. | Codex | runtime/research_nightly/ |
| P0.5-4 | Done/rejected 2026-05-26: `att1_density_v3_more_pivots_v1` standalone best `r259` (`+38.48%`, PF `1.384`, DD `3.97%`) failed full-package replay: `+58.50%`, PF `1.386`, DD `15.18%`, 3 red months versus static-v1 `+70.17%`, PF `1.545`, DD `6.23%`, 2 red months. No promotion. | Codex | `configs/crypto_income_static_v1_att1_r259_replay.env`, `backtest_runs/portfolio_20260526_085609_codex_static_v1_att1_r259_replay_20260526/` |
| P0.5-9 | `att1_short_slope_v1` finished `18/18` and failed gate: best `+15.44%`, PF `1.097`, DD `9.96%`; reject. Elder Revived diagnostic on 360d/6 symbols with 6bps fee + 2bps slippage remains the next bounded strategy diagnostic. Claude drafts for ARF1/BRC1/MTPB/Elder remain local challengers only until replay. | Codex | `docs/CODEX_HANDOFF_20260525.md`, `configs/autoresearch/`, `logs/att1_short_slope_after_v3_20260525.nohup.log` |
| P0.5-10 | **BRC1 bear-continuation candidate.** Clean server-mirror 90d sweep completed `64/64`: best `r005` `+6.15%`, PF `4.800`, WR `67.7%`, DD `0.40%`, 31 trades, 0 red months. This targets the current bear market but is not annual evidence yet. | Codex | `backtest_runs/autoresearch_20260526_160528_bear_regime_continuation_v1_fast_90d_v1/` | Run 365d validation with fees/slippage; only if pass, add to strict-three-slot package replay as a challenger |
| P0.5-11 | **Elder canonical bounded probe.** Clean mirror `--limit 256` research started after BRC1; first 16 rows are catastrophic fails (`PF ~0.28-0.32`, DD >83%). | Codex | `logs/elder_canonical_probe_clean_20260526.log` | Let bounded probe finish; reject branch unless a passing pocket emerges, do not spend live capital |
| P0.5-5 | Run 2026-05-20: `compare_live_pulse_vs_backtest.py` shows open_trades=0, flat true no-signal/range, breakdown symbol/no-setup, ATT1/midterm no attempts. Use symbol-aware blocker before touching filters. | Codex | `runtime/bot_heartbeat.json` |
| P0.5-6 | Done 2026-05-19 17:24 UTC: approved breakdown router/profile patch applied for ADA+ONDO only; ENA excluded. Active router includes ADA now; ONDO staged but geometry-filtered until setup quality improves. | Codex | `backtest_runs/portfolio_20260519_170243_breakdown_new_symbols_180d_20260519/summary.csv` |
| P0.5-7 | Done 2026-05-25: `flat_live_frequency_v3` standalone PASS (`+9.66%`, PF `2.232`, DD `1.76%`), but replacing ARF1 params in full `crypto_income_static_v1` worsened it to `+64.24%`, PF `1.491`, DD `7.31%`. Do not promote this flat override. | Codex | `backtest_runs/autoresearch_20260525_072703_flat_live_frequency_v3/`, `backtest_runs/portfolio_20260525_102913_codex_static_v1_arf1_r033_replay_20260525/` |
| P0.5-8 | Rejected quick probe 2026-05-25: resistance-zone attempt for `flat_ns_touch` failed its first bounded variants (`PF 1.130-1.137`, `DD 7.26-7.65%`). No live/code promotion and no full grid spend. | Codex | `backtest_runs/autoresearch_20260525_104946_flat_resistance_zone_v1/results.csv` |

## P0.9 — менеджерская чистка (low risk, high signal)

| # | Задача | Кто | Acceptance |
|---|---|---|---|
| P0.9-1 | Удалить definite trash: `%s`, `.DS_Store`. | owner / любой | git clean |
| P0.9-2 | Done 2026-05-25: 32 tracked legacy `AUDIT_REPORT` / `CLAUDE_*` / `CODEX_TASK_*` documents побайтно перенесены в `docs/archive/` (`git rename`, история сохранена). Удалённую `alt_liquidity_sweep_reversal_v1.py` не смешивать с cleanup до отдельного ревью. | Codex | commit `71fc5ca` |
| P0.9-3 | Перенести 22 спеки от 17 мая в `docs/specs/` подпапку. | Codex | `ls docs/specs/*_20260517.md` |
| P0.9-4 | Disk hygiene: rotate `backtest_runs/` (оставить 30 дней + best-of), архивировать остальное. | Codex | `du -sh backtest_runs/` ≤ 200 MB |
| P0.9-5 | Подтвердить что Alpaca configs v35/v36/dynamic_v1/v2_broad/1000usd/small_cap не используются → удалить. | Codex (grep) | `grep -r alpaca_paper_v35` empty |
| P0.9-6 | Done 2026-05-20: rotate noisy `runtime/allocator_decisions.jsonl` (~473 MB) and disable allocator decision trace by default. | Codex | `runtime/archive/allocator_decisions_20260520_0515.jsonl` |
| P0.9-7 | Done 2026-05-20: deleted archived allocator trace on server and fixed cleanup fallout: `run_portfolio.py` no longer crashes when retired `alt_liquidity_sweep_reversal_v1` is absent. | Codex | `py_compile` local + server OK |
| P0.9-8 | Done 2026-05-25: preserved compressed tail and truncated runaway server `runtime/live.out` (~202 MB); add persistent `logrotate` guard (`maxsize 20M`, compressed history). | Codex | `scripts/setup_systemd_bot.sh`, `/etc/logrotate.d/bybot-live` |

## P1 — этого месяца (после P0)

| # | Задача | Кто | Где спека |
|---|---|---|---|
| P1-1 | **Monitor approved bear router update.** Breakdown ADA+ONDO profile patch deployed; next decision after 24-72h counters/trades. Не включать ASB1. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §3.3 |
| P1-1a | **Done 2026-05-20: restore proven crypto package via shadow/replay, not blind live.** Static rerun: +70.17%/365d, PF 1.545. Control-plane replay: +42.31%/360d, PF 1.383, DD 5.87, 536 trades, 1 red month. Current live approximation: +17.45%/365d, PF 1.211, DD 13.25. | Codex | `backtest_runs/dynamic_annual_20260520_100256_codex_p1_1a_static_v1_control_plane_replay_20260520/summary.json` |
| P1-1b | **Done 2026-05-20: prepare static-v1 live parity/shadow, no live env edits.** Synced missing static-v1 policy/health/env artifacts to server. Dry-run shows static-v1 policy in current `bear_trend` enables `flat+breakdown` only; ATT1/midterm are blocked by orchestrator, not allocator policy. | Codex | Acceptance: no live restart/env edit |
| P1-1c | **Done/monitor: backtest-driven symbol/router expansion for static core.** Owner-approved live deployment active; after adequate sample, allowlist mismatch is no longer dominant. Internal blockers now dominate: `breakdown_support`, `ATT1_trendline`, `flat_touch`. | Codex | Acceptance met for routing diagnosis; continue with targeted filter replay, no blind expansion |
| P1-1d | **Targeted live-filter replay.** Fresh 2026-05-25 counters after `100%` input parity: `breakdown` 419/419 no-signal (`rsi=320`, `support=80`), `flat` 32/32 (`touch=20`), `ATT1` 56/57 (`trendline=24`, one signal then rounding skip). Reproduce these filters over a tradeful window and test one bounded repair per sleeve. | Codex | Promote only if PF≥1.25, DD≤8%, trades≥30 and negative months do not worsen |
| P1-1e | **Signal/timestamp parity after router fix.** Dead-zone audit done: latest 9 replay entries were outside UTC 0/1/2. Report now labels retrospective-config replay correctly; next compare must use a stable post-fix live window. | Codex | Must explain post-fix replay entries vs live before any filter relaxation |
| P1-1f | **Done/observe: signal-to-order funnel counters.** Instrumented active sleeves and blocker report with `signal` plus post-signal sizing/risk/submit skip reasons; deployed diagnostics-only at `open_trades=0`. Initial sample has zero generated signals, so order path is not yet implicated. | Codex | Next generated signal must be classified as `entry` or exact post-signal skip |
| P1-1g | **Fixed-dataset static-v1 reconciliation.** Done for current recovery benchmark: server candle-cache mirrored into isolated local shadow; identical annual protocol now reproduces server `+73.96%`, PF `1.591`, DD `5.16%`, 436 trades and 2 red months. Keep dataset provenance attached to package decisions; do not compare promotion candidates to old local-cache `+70.17%`. | Codex | Package sweeps use mirrored server cache only; no blind clean redeploy |
| P1-1h | **Full-package internal-filter sweep. Done/replay passed.** `package_breakdown_rsi_v1` best accepted `+74.43%`, PF `1.596`, DD `5.16%`, 1 red month. `package_arf1_flat_touch_v1` winner `r002` is confirmed at five slots (`+77.57%`, PF `1.646`, DD `5.16%`, 419 trades, 2 red months) and at current three slots (`+67.11%`, PF `1.530`, DD `4.82%`, 432 trades, 2 red months). | Codex | Conservative promotion path is the strict-three-slot candidate only after owner approval and live safety caps |
| P1-2 | **Broker-side TP/SL hardening audit.** Existing bot already calls Bybit trading-stop with retry/ensure/hard-fail-close; remaining work is to audit the narrow entry-to-protection interval and add a smoke assertion before larger deposits. | Codex | `smart_pump_reversal_bot.py`, `SAFETY_PATCHES_20260517.md` |
| P1-3 | **SAFETY Patch 2 — TRADES race fix.** `threading.RLock` + persistent snapshot. | Codex | `SAFETY_PATCHES_20260517.md` |
| P1-4 | **Funding carry code audit + DRY_RUN only.** Current executor is one-legged perp exposure, not market-neutral carry; do not schedule real execution until hedge leg and broker-side protection exist. | Codex | `scripts/funding_carry_executor.py`, `FUNDING_CARRY_ACTIVATION_20260517.md` Phase 1 |
| P1-5 | **direction-aware `global_risk_mult`.** Разделить на `long_risk_mult` / `short_risk_mult` в orchestrator. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §3.4 |
| P1-6 | После P1-1 + P1-2: **активация 2-3 strategies** через acceptance gate (BRC1, alt_bear_breakdown_v1, alt_squeeze_breakout_v1). `base_mult=0.5` start. | Codex | `docs/STRATEGY_SET_PER_REGIME_20260519.md` §2 |
| P1-7 | **DeepSeek reporting integrity.** Done 2026-05-25: weekly audit attributes metrics from each sleeve's own trades; universe proposals are backtest-only and evidence-bound. | Codex | `scripts/deepseek_weekly_cron.py --dry-run --phases audit,research,report --skip-universe` |
| P1-7a | **Budgeted read-only AI analyst.** Feed cited/cached macro, earnings, sector/news headlines, Bybit liquidity/funding snapshots to `ai_context`; use a stronger analyst model only for queued stock/strategy reviews, DeepSeek for routine summaries. Elder may be an analysis candidate only after its diagnostic/WF gate, never a source of direct live decisions. | Codex | No direct config/order writes; freshness + source URL + token/request budget required in every analyst run |
| P1-8 | Alpaca v39 (если backtest v2 пройдёт): paper 14 дней с `ALPACA_DYN_V2_ENABLED=1`. | Codex | результаты P0.5-1 |
| P1-8a | **Alpaca market data freshness fix. Deployed 2026-05-25 16:53 UTC.** Root cause: Alpaca bars request without `start` returned zero recent bars; v3 shadow remained on `2026-05-18 19:30 UTC`. Paper-only patch adds bounded recent-window API requests for M5 and daily/SPY data; v3 remains DRY_RUN. | Codex | `scripts/equities_alpaca_intraday_bridge.py` | Server dry-run confirmed last available market bar `2026-05-22 19:55 UTC`; verify again after US open on 2026-05-26 |
| P1-8b | **Alpaca filled-PnL safeguard. Deployed 2026-05-25 16:57 UTC in paper bridge.** `v3_shadow` defaults to dry-run; monthly bridge protects pending intraday closes. Manager-close positions now stay `close_pending`, repeat closes are avoided, and realized P&L is booked only after a filled exit is found. Pre-patch `PANW/META` accepted orders still require manual fill reconciliation and ledger cleanup. | Codex | `scripts/equities_alpaca_paper_bridge.py`, `scripts/equities_alpaca_intraday_bridge.py`, `logs/alpaca_intraday_dynamic_v1.log` | Observe one complete post-patch filled close before deposit |
| P1-8c | **Alpaca v39 event-based rebalance.** Fee-stressed validation: 24m `+70.37%`, PF `1.850`, DD `13.29%`, red months `6/24`; OOS 12m `+26.15%`, PF `1.895`, DD `9.51%`; bear-2022 `-23.47%`, PF `0.415`, DD `27.66%`. Still research-only; repair downside/regime protection before paper shadow. | Codex | `scripts/alpaca_v3_event_backtest.py`, `strategies/alpaca_dynamic_v3_event.py`, `configs/alpaca_v39_event_best_research.env` |
| P1-8d | **Web operator visibility.** Done/deployed 2026-05-26: `API Keys` page exposes safe expiry/configured status and credential rotation form; Setup Scanner cards open a full Bybit candlestick modal with level, invalidation and timeframe switching. | Codex | `web/routes/admin_routes.py`, `web/routes/data_routes.py`, `web/static/index.html` |
| P1-8e | **Alpaca reporting ownership truth. Done/deployed 2026-05-26.** Daily station digest, web and AI context distinguish monthly-owned positions, intraday tracked positions, pending close fills and unverified journal P&L; crypto periodic report is explicitly crypto-only. | Codex | `trade_reporting.py`, `scripts/tg_daily_digest.py`, `bot/operator_snapshot.py`, `web/routes/data_routes.py`, `web/routes/ai_routes.py`, `web/static/index.html` |
| P1-8f | **Alpaca profit-lock OHLC/high-water research. Done/reject quick promotion.** New runner models conservative OHLC stop-first exits. Simple v39 trail worsened 24m to `+55.54%`, PF `1.611`, DD `16.27%`; best 24m SPY-gated variant (`+72.24%`, PF `1.931`, DD `8.86%`) collapsed on OOS (`+6.07%`) and bear variants remained negative after warm-up/risk-off exit. | Codex | `scripts/alpaca_v39_ohlc_trailing_backtest.py` | Keep v38 monthly paper as deposit candidate; redesign v39 defensive/cash sleeve before any paper shadow |
| P1-8g | **Alpaca active defensive redesign.** Develop an additive active sleeve around v38, not a replacement: risk-off cash/defensive universe, intraperiod profit-lock, and event re-entry tested on 24m + OOS + bear windows with OHLC and fees. | Codex | Use `scripts/alpaca_v39_ohlc_trailing_backtest.py` as validation harness | Paper-shadow only when positive OOS, bear loss bounded, and current v38 return/DD not materially harmed |
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
- 2026-05-26: Deployed Alpaca reporting ownership truth: daily digest/web/AI no longer present `GOOGL` monthly ownership or `META/PANW` pending close fills as clean intraday performance. Full-package replay rejected ATT1 density `r259` despite its standalone result; ATT1 slope failed; Alpaca v39 remains research-only after bear stress failure.
- 2026-05-26: Deployed Setup Scanner candlestick chart and honest read-only monitor. Exact static-v1 server rerun produced `+73.96%`, PF `1.591`, DD `5.16%`, 436 trades. Reconciliation identified different candle-cache as the result drift; mirrored server cache reproduces the server benchmark locally. Package breakdown/flat sweeps now run locally in `screen` to keep the live VPS free.
- 2026-05-26: Deployed strict parity diagnostic (`e339ee2`). It corrected a false `PASS`: static-v1 required inputs are covered, but current live has extra sleeves `sloped,asm1` and extra router symbols. Follow-up runtime check corrected the initial slot inference: running account uses `MAX_POSITIONS=3`, `leverage=3`, effective risk `0.44%`; fixed-cache three-slot baseline is `+62.79% / PF 1.478` versus `+73.96% / PF 1.591` at five. No trade settings changed.
- 2026-05-26: Fixed and deployed Alpaca monthly software-trailing arming bug (`89c6f8d`). Saved paper evidence showed `GOOGL` peak `+6.40%`; the `14:00 UTC` v38 paper run triggered trailing close/re-entry block, and `14:30 UTC` confirmed GOOGL no longer present with no cleanup conflict. Added OHLC/high-water v39 research requirement; Claude v40 close-only draft is rejected.
- 2026-05-26: Built and ran OHLC/high-water `v39` research. A trailing/SPY-gate shortcut cannot be promoted: the tempting 24m score does not survive OOS/bear stress. Near-term Alpaca remains `v38` paper with the fixed software trail; active v39 becomes a defensive-sleeve redesign task.
- 2026-05-26: Finished ARF1 full-package sweep and independent replay on the server-mirrored fixed dataset. Five-slot `r002` is the first confirmed package improvement (`+77.57%`, PF `1.646`, DD `5.16%`, 2 red months); four slots adds a red month. Next crypto change is strict shadow parity and total-risk sizing, not a blind live toggle.
- 2026-05-26: Verified the ARF1 `r002` candidate at current live concurrency of three positions: `+67.11%`, PF `1.530`, DD `4.82%`, 2 red months, improving three-slot baseline. Proposed config is inert/review-only until explicit approval because current live has real funds and no configured aggregate/same-direction caps.
- 2026-05-26: Clean next-sleeve queue started after ARF1: BRC1 fast 90d produced a strong bear-continuation candidate (`PF 4.800`, 31 trades, no red months); it advances to annual/additivity validation only. Elder bounded probe is running and currently fails hard.
- 2026-05-25: Fixed Alpaca paper ownership isolation: monthly bridge now treats intraday pending-close positions as protected, preventing duplicate stale cleanup while orders are in flight. First scheduled post-patch monthly run preserved `META/PANW` and issued no duplicate close. ATT1 v3 remains running; no winner/deploy before package replay.
- 2026-05-25: Deployed Alpaca paper-only freshness and filled-PnL safeguards. v3 dry-run now reads the last available market bar (`2026-05-22 19:55 UTC` while the US market is closed); realized intraday P&L is no longer booked at close submission. Reconcile pre-patch `PANW/META` fills after the next US open.
- 2026-05-25: Corrected DeepSeek weekly attribution bug and gated universe proposals as backtest-only. Added P1-1e signal/timestamp/no-entry-hours parity and P1-7a read-only external market context; live settings unchanged.
- 2026-05-25: Dead-zone did not explain the latest live/replay gap (`0/9` replay entries in UTC 0/1/2). Hardened weekly interpretation: current-config replay over pre-deployment days is counterfactual; require a stable post-fix window.
- 2026-05-25: Deployed entry-funnel diagnostics for all active crypto sleeves and extended crypto blocker report with post-signal skip classification. New live sample shows `signal=0`, focusing the next work on targeted filter replay rather than allocator/order edits.
- 2026-05-25: Tested a promising ARF1/flat frequency variant in isolation and in the full proven package; it harms package return/DD, so it is rejected for promotion. Next candidate repair stays `ATT1`, while BRC1 annual research continues.
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
