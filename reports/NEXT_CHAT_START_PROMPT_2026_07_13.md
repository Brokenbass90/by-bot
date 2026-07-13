# NEXT CHAT START PROMPT — 2026-07-13 phase-1 checkpoint

Продолжай recovery multi-market trading station с текущей точки; общий аудит и уже закрытый event-long phase-1 заново не начинай.

Сначала полностью прочитай:

1. `reports/RECOVERY_CHECKPOINT_2026_07_13.md`
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_13.json`
3. `reports/EVENT_EXPANSION_RETEST_LONG_V1_PHASE1_FREEZE_2026_07_13.md`
4. `configs/preregistered/event_expansion_retest_long_v1_phase1_20260713.json`
5. `reports/PUMP_EXHAUSTION_STRICT_VERDICT_2026_07_13.md`
6. `reports/ALPACA_TRUTH_AND_NEXT_TEST_2026_07_13.md`
7. `reports/FX_CFD_DATA_AND_FIRST_FIGURES_AUDIT_2026_07_13.md`
8. tail `reports/PROJECT_STATE_LEDGER.md`
9. `configs/ai_operator_canonical_state.json`

Затем проверь direct truth: local/origin HEAD; tracked dirty files; VPS checkout/deployed manifests; Bybit positions/heartbeat/effective ATT1 contract; Alpaca broker positions/stops/SAFE-HOLD и scheduled report receipt. Не считай Git push VPS deploy.

## Не повторять уже выполненное

- Bybit partial-close PnL aggregator исправлен и pushed (`3f6278b`, `12a9abd`), но на VPS ещё не развёрнут. Existing ADA trade не reconciled.
- Strict pump gate завершён `NO_PROMOTION`: stress `N=39`, PF `1.234`, `+1.228%` за 720d, DD `3.015%`; holdout `N=6`. Frozen minimum-sample gates не ослаблять.
- Event-long phase-1 завершён и pushed. Current contract включает strengthened horizontal H1/H4 LevelSnapshot, exact closed M5 aggregation, H1 expansion, later M15 hold/first-retest/higher-low/later-BOS, exact next M5 execution, frozen stop, stop-first, 1R/2R, costs/funding policy, authenticated MTF->execution bridge и atomic `0600` single-writer state/outbox.
- Downtime bug закрыт commit `72c273d`: replay останавливается ровно на первом плане; pending outbox блокирует дальнейшие свечи до durable ACK; после ACK тот же tail доигрывается.
- Phase-1 preflight integrity PASS, exact suite `97 passed`, но `BLOCKED_RESEARCH_RUNNER_DATA / PERFORMANCE_FORBIDDEN / LIVE_FORBIDDEN`, девять blockers. Полный suite checkpoint: `1191 passed`.
- Phase-0 не переписывать: это исторический freeze старых hashes; текущий authority — phase-1.
- FX V3 level/news/cost contract hardened; старый Jul11 config исторический и блокируется до source gate. Alpaca exact four-arm parity preflight остаётся blocked; SAFE-HOLD не снимать.

## Live truth

- Единственный crypto money sleeve: ATT1 short-only risk `0.10`; edge не доказан, не масштабировать. Canary expiry `2026-07-20` требует explicit review. Bybit key expiry `2026-08-12`, безопасная ротация до `2026-08-05`.
- Последний verified Bybit snapshot 13 Jul 09:04 UTC был flat, heartbeat fresh, failed units zero. Ночная ADA прошла partial TP -> trailing profit, но старый учёт сохранил только residual row.
- Alpaca SAFE-HOLD: около `$486.93`, ABBV/ABNB/GE/SCHW, stops `4/4`; core restart не нужен. Report due 13 Jul 22:10 UTC, watchdog 23:00 UTC — проверить только после срока.
- FX/CFD: research-only, capital zero.
- VPS Git `f7ed011` stale/dirty; targeted deployed files новее. Blind pull/reset/cleanup запрещены.

## Первый порядок действий

1. Когда server access доступен и Bybit flat: targeted deploy partial-PnL package, без risk change; pre/post flat check; reconcile ADA broker rows. Не выдавать Git push за live deploy.
2. После 22:10/23:00 UTC проверить Alpaca report/watchdog receipt. Затем материализовать broker lifecycle, PIT universe/data, shared executable exit/conformance, costs/gaps, regimes/survivorship и sealed forward; outcome access только после PASS preflight.
3. После owner OANDA Practice/region/account-type/instruments/news-source inputs создать новый FX V3 prereg, refresh bid/ask data, и только затем считать первые figures. Secrets только локально.
4. Crypto phase-2: один single-owner runner на completed-bar engine store. Он обязан durable-сохранить bridge и trade receipts до atomic ACK, восстановить ambiguous writes без duplicate execution, доказать funding completeness, создать uniform dev13 manifest, fixed folds/embargo/LOSO/portfolio/additivity. До нового hash-pinned phase-2 freeze performance не запускать.
5. После phase-2 freeze materialize fixed external8 (`FIL/UNI/ETC/ICP/TRX/TON/MNT/IMX`) без замен. Только затем один dev gate и один external replication.
6. После event-long verdict — отдельные horizontal range rejection long и short. Sloped levels — отдельный versioned contract; Elder только как filter/ablation. ATT1 challenger до outcome фиксирует unbroken line, first retest, bounded overshoot и отдельный >=3-respect/two-pivot class.

Запрещено: включать pump как «почти PASS»; повышать ATT1 frequency/risk; возвращать ARS1/ASB2/Elder/InPlay по старым сеткам; запускать event-long/FX performance при blocked data; снимать Alpaca SAFE-HOLD; обещать доход или выдавать selected backtest за прогноз.

В конце обнови canonical index, AI state и ledger. Отдельно укажи: Git pushed, VPS deployed, service restarted, broker/live behavior changed, research-only artifacts и failed gates.
