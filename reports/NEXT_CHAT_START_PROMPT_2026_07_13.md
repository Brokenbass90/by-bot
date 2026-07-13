# NEXT CHAT START PROMPT — 2026-07-13

Продолжай recovery multi-market trading station с текущей точки; общий аудит заново не начинай.

Сначала прочитай полностью:

1. `reports/RECOVERY_CHECKPOINT_2026_07_13.md`
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_13.json`
3. `reports/PUMP_EXHAUSTION_STRICT_VERDICT_2026_07_13.md`
4. `reports/ALPACA_TRUTH_AND_NEXT_TEST_2026_07_13.md`
5. `reports/FX_CFD_DATA_AND_FIRST_FIGURES_AUDIT_2026_07_13.md`
6. `reports/EVENT_EXPANSION_RETEST_LONG_V1_PREREG_2026_07_13.md`
7. tail `reports/PROJECT_STATE_LEDGER.md`
8. `configs/ai_operator_canonical_state.json`

Затем проверь direct truth: local/origin HEAD; dirty tracked files; VPS checkout/deployed manifests; Bybit positions/heartbeat/effective ATT1 contract; Alpaca broker positions/stops/SAFE-HOLD и scheduled report receipt. Не считай Git push VPS deploy.

## Не повторять уже выполненное

- Bybit partial-close PnL aggregator исправлен и pushed (`3f6278b`, `12a9abd`), но на VPS ещё не развёрнут из-за server-tool quota. Existing ADA trade не reconciled.
- Immutable pump M5 data `13/13` PASS.
- Strict pump runner и authorization были committed до outcome. Итог `NO_PROMOTION`: stress `N=39`, PF `1.234`, `+1.228%` за 720d, conservative DD `3.015%`; holdout `N=6`, PF `6.30`. Failed только `min_trades 39<40` и `holdout 6<10`, но ворота после outcome не ослаблять.
- Causal horizontal `LevelSnapshot v1`, restart-safe long-only event mechanics and deterministic closed M5 -> M15/H1/H4 aggregation are implemented and pushed (`a98b640`, `f07dd01`). Финальный full suite после phase-0: `1127 passed`.
- Event-long phase-0 prereg/preflight is pushed (`526492a`): `integrity_pass=true`, focused `57 passed`, but verdict stays `BLOCKED_RESEARCH_MECHANICS / PERFORMANCE_FORBIDDEN` with nine declared blockers. It has no performance/live authority.
- FX V3 respect теперь fail-closed, H1 explicit; news/cost validators строгие. Jul11 config исторический и специально останавливается до source gate с недостающими contract fields. Нужен новый versioned prereg после owner inputs.
- Alpaca exact four-arm parity prereg frozen; preflight `BLOCKED_FAIL_CLOSED`, outcome access false, SAFE-HOLD unchanged. Не запускать performance до девяти pinned artifacts.

## Live truth

- Единственный crypto money sleeve: ATT1 short-only risk `0.10`; не масштабировать. Canary expiry `2026-07-20` требует explicit review. Bybit key expiry `2026-08-12`, ротация до начала августа.
- Последний verified Bybit snapshot 13 Jul 09:04 UTC был flat, heartbeat fresh, failed units zero. Ночная ADA прошла partial TP -> trailing profit, но старый учёт сохранил только residual close row.
- Alpaca SAFE-HOLD: около `$486.93`, ABBV/ABNB/GE/SCHW, stops `4/4`; core restart не нужен. Отчёт due 22:10 UTC, watchdog 23:00 UTC 13 Jul — проверить после срока.
- FX/CFD: research-only, capital zero.
- VPS Git `f7ed011` stale/dirty; targeted deployed files новее. Blind pull/reset/cleanup запрещены.

## Первый порядок действий

1. Когда server access вернётся и Bybit flat: targeted deploy partial-PnL package, без risk change; restart только bot после pre/post flat check; reconcile ADA broker rows.
2. После 22:10/23:00 UTC проверить Alpaca report/watchdog. Затем материализовать Jul6–9 broker lifecycle, PIT universe/data, shared executable exit+conformance, cost/gap, regimes/survivorship и sealed forward; повторить только preflight.
3. От владельца получить OANDA Practice/region/account type/instruments/news-source context; secrets только локально. Создать новый FX V3 prereg с fresh source/artifact hashes; старый Jul11 не редактировать.
4. Crypto: не повторять phase-0. Следующий кодовый шаг — один hash-pinned orchestrator closed H1 expansion -> later M15 hold/first retest/HL/BOS -> exact next M5 open, затем frozen exits/cost/funding runner и conformance. Только после нового runnable freeze можно materialize fixed external8 (`FIL/UNI/ETC/ICP/TRX/TON/MNT/IMX`) и запускать один dev gate; performance сейчас запрещён. Short pump можно расширять только point-in-time universe-additivity без выбора symbols по просмотренному PnL. После этого — отдельные horizontal range long/short; sloped levels отдельным versioned contract.
5. ATT1 live не переписывать после одной удачной сделки. Для challenger до outcome зафиксировать unbroken line, first retest, bounded overshoot и отдельный >=3-respect/two-pivot class.

Запрещено: включать pump как «почти PASS»; повышать ATT1 frequency/risk; возвращать ARS1/ASB2/Elder/InPlay по старым сеткам; запускать FX performance при blocked data; снимать Alpaca SAFE-HOLD; обещать доход или выдавать selected backtest за прогноз.

В конце обязательно обнови canonical index, AI state и ledger; отдельно укажи: Git pushed, VPS deployed, service restarted, broker/live behavior changed, research-only artifacts и failed gates.
