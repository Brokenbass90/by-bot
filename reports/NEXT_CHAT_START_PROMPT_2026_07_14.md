# NEXT CHAT START PROMPT — 2026-07-14

Продолжай recovery multi-market trading station с текущей точки. Не начинай общий аудит заново и не повторяй закрытые grids.

Сначала полностью прочитай:

1. `reports/RECOVERY_CHECKPOINT_2026_07_14.md`
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_14.json`
3. tail `reports/PROJECT_STATE_LEDGER.md`
4. `configs/ai_operator_canonical_state.json`
5. `reports/RECOVERY_CHECKPOINT_2026_07_13.md`
6. `reports/EVENT_EXPANSION_RETEST_LONG_V1_PHASE1_FREEZE_2026_07_13.md`
7. `reports/ALPACA_TRUTH_AND_NEXT_TEST_2026_07_13.md`
8. `reports/FX_CFD_DATA_AND_FIRST_FIGURES_AUDIT_2026_07_13.md`
9. `reports/PUMP_EXHAUSTION_STRICT_VERDICT_2026_07_13.md`

Затем заново проверь только изменчивую direct truth: local/origin HEAD и tracked dirty; targeted deploy receipts/SHA; VPS service PIDs/start time; Bybit positions/heartbeat/effective ATT1 contract; Alpaca broker positions/open stops/SAFE_HOLD/latest manager receipt; web `/ping` и live API payload. Git push не равен VPS deploy.

## Уже выполнено — не повторять

- Bybit partial-close aggregation (`3f6278b`, `12a9abd`) targeted deployed; core был контролируемо restarted flat, risk не менялся. Старую ADA history не считать reconciled без broker rows.
- Alpaca P0 stale-holding protection (`cc3ef8a`) и quantity-aware truth/web package (`66ffa02`) pushed/targeted deployed. SAFE_HOLD `ABBV/ABNB/GE/SCHW`, exact stop quantity coverage `4/4`, under/over-protection none, новых buys/stale closes не было. Scheduled TG report delivered; manual core restart для monthly manager не нужен.
- Единственный crypto money sleeve — ATT1 short-only `risk_mult=0.10`; edge unproven. Review `2026-07-20`; Bybit key rotate до `2026-08-05`, expiry `2026-08-12`.
- Pump strict verdict — `NO_PROMOTION`; min-sample gates не ослаблять и grid не повторять.
- FX M5 Dukascopy уже есть примерно за 728 дней. V2 все шесть side-specific sleeves отрицательны; не загружать M5 «с нуля» и не повторять V2 grid.
- Event-long phase-1 mechanics/closed bars/levels/MTF/execution/bridge/atomic outbox закрыты. Uniform dev13 freeze `5801cc6` deep-validated `13 x 207241` rows and lowered blockers `9 -> 8`; performance/live forbidden.
- AI mission `41da86d` pushed: feed-bound one-shot shadow only, AI may SELECT frozen card or ABSTAIN; promotion authority false, no live/TG/broker wiring.
- Replayable tape code `4db0f4d` pushed. Local screens `l2_ondo_v1_20260714` and `trades_micro_v1_20260714` are running with disk fail-stops. First ONDO replay PASS, gaps `0`.
- Full regression at published HEAD `4db0f4d`: `1283 passed`; local/origin matched. Активного nightly performance/autoresearch нет.

## Pending/blocked work

1. Owner password/TOTP replay after `Unauthorized` remains unproven. Web service was restarted at PID `2863782` and `/ping` works; friendly errors do not fix a wrong password.
2. Event-long still lacks single-owner performance runner, durable receipt-before-ACK runner, funding completeness and external8 inputs/reference: 8 blockers, no outcomes.
3. AI mission lacks parity screener/model batch/prereg OOS comparison; never connect directly to money from a single replay.
4. Tape processes run locally only. Check `screen -ls`, heartbeats, daily validation, bytes/day and compression after the first UTC day.
5. Alpaca exact parity remains blocked on nine artifacts; SAFE_HOLD stays on.
6. `bot/fx_setups.py` and `tests/test_fx_setups.py` are foreign pre-existing dirty edits; do not include silently.

## Первый порядок действий

1. Event-long: построить single-owner completed-bar runner, который durable пишет bridge/trade receipts до ACK, восстанавливает ambiguous writes без duplicate execution и доказывает funding completeness. До нового hash-pinned authorization outcomes не открывать.
2. Tape: после первого полного UTC дня валидировать ONDO book/trades и 6-symbol trades; зафиксировать gaps, coverage, duplicate IDs, bytes/day и zstd ratio. Не называть это edge.
3. Alpaca: materialize nine exact-parity artifacts, then four-arm monthly/adaptive/daily-control replay. SAFE_HOLD unchanged until verdict.
4. FX V3: использовать существующие M5. Сначала новый prereg + data repair/refresh + pinned macro-news + account-specific costs; затем failed-break short, horizontal range long/short и range-edge expansion/retest long/short.
5. ATT1: 20 июля explicit canary review по logical broker-reconciled trades. Geometry challenger отдельно preregister: unbroken line, first retest, bounded overshoot, >=3-respect/two-pivot split.
6. AI: wire deterministic screener into mission shadow, freeze prereg, compare model SELECT against mechanical baseline across a batch. No broker/live.
7. После честного event-long verdict строить два физических horizontal range sleeves. Elder — только filter/ablation; InPlay — only event/tape successor.

## AI/web/screener truth

- AI сейчас observer/proposal-only; не владеет risk/orders.
- Standalone screener, monolith `/coins` и web setup cards не parity-equivalent; web card не является strategy signal.
- Successful owner password/TOTP replay после `Unauthorized` ещё не доказан. User/TOTP config существует; секреты/пароль в чат не выводить.
- Web truth patch is live, but owner login success is not proven.

Запрещено: повышать risk; включать второй money sleeve по local backtest; снимать SAFE_HOLD; ослаблять gates после результата; запускать blocked event/FX performance; выдавать AI opinion за order; blind pull/reset/cleanup VPS; смешивать long/short identity; обещать доход.

В конце каждого пакета обновляй canonical index, AI state и ledger. Отдельно перечисляй: tested; committed; pushed; targeted deployed; service restarted; broker/live behavior changed; research-only; failed/blocked gates.
