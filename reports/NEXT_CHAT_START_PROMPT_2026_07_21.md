# Точка входа следующего чата — 2026-07-21

Работай из:

`/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`

Сначала полностью прочитай:

1. `reports/RECOVERY_CHECKPOINT_2026_07_21.md`
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_21.json`
3. последние July-21 секции `reports/PROJECT_STATE_LEDGER.md`
4. `reports/TSM_PROVISIONAL_DOWNGRADE_AUDIT_2026_07_21.md`
5. `reports/CROSS_EXCHANGE_FUNDING_V2_FORENSIC_VERDICT_2026_07_21.md`
6. `reports/EVENT_UNIVERSE_V2R2_LAUNCH_STATUS_2026_07_21.md`
7. `reports/SETTLEMENT_EXECUTION_V3_RESEARCH_MVP_2026_07_21.md`

Затем read-only проверь изменчивую truth: current local/upstream HEAD, tracked dirty ownership, оба service PID/start time, direct broker positions, ATT1 breaker/effective risk, Alpaca real positions/stops, active screen names и clock state. `d55fbc1` — pushed audited July-21 research/docs batch; metadata follow-up может быть новее.

## Текущая истина

- VPS checkout `f7ed011` намеренно stale с последними `349` status records; targeted deploy receipts важнее checkout SHA. Blind pull/reset/clean запрещены.
- `bybot.service` active, PID `1131772`, controlled broker-flat restart выполнен `2026-07-21T19:04:10Z`. Web active, PID `1046949`, перезапущен Jul21 только для `8f030e3`.
- `8f030e3` исправил chart epoch и настоящий rolling health; stale `range N21 PF0.487` удалён. Core/env/risk/orders не менялись.
- Map-only `72dc6c2` deployed с hashes, без restart/risk/orders. Новый July-21 canonical batch сначала проверь по resulting commit/receipt; не дублируй и не broad-deploy вслепую.
- ATT1 renewal полностью применён: `71e0857` pushed, exact override expiry Aug5/risk `0.10` short-only/IVB1 `0` установлен с совпавшим SHA и backup; 3 direct flat confirmations, controlled restart, heartbeat `19:06:21Z` expiry Aug5, breaker open/×1, broker positions 0. ATT1 активен. `N8`, WR `50%`, PF `1.27965`, net `+0.4992 USDT`, edge unproven. Никогда не повышай risk ради frequency.
- Alpaca real = `SAFE_HOLD`, equity `$484.01`, `ABBV/ABNB/SCHW`, stops `3/3`. Separate paper manager = `ABBV/CRWD/DDOG`; это не real live. Successor не auto-start/force-liquidate и blocked пятью authoritative inputs.
- Старый TSM PASS отозван: `RESEARCH_BLOCKED`, valid shadow weeks `0/8`; defects anchor/cost/funding/concentration/liquidation/parity/immutability. Не wire на VPS.
- Sloped/horizontal/sweep и level-DCA families провалены; final pump-fade тоже без survivor. Второго crypto money sleeve нет.
- V1 event labels blocked source revisions. Original V2 сохранён и invalidated из-за неверного prereg timestamp. Только V2r2 действителен: screen `event_universe_v2r2_20260721`, first `752/100/100/17/0`, public GET-only, deadline `2026-07-28T18:19:58Z`.
- Public cash-carry active до `2026-07-23T04:37:10Z`: snapshot `1557` observations, economics passes `0`, no capital. Старый `$5–15/month` forecast withdrawn.
- Cross-exchange funding v2 invalid: 228 cycles не evidence. Scanner P0 и v3 sequential/atomic research-only MVP локально реализованы; три independent-audit P1 закрыты, `11` focused tests PASS. Следующий gate — provenance-bound public collector и fresh cycles from zero. Не deploy cron и не добавляй капитал.
- Dukascopy M5 уже есть: ~728d, 6 symbols. `bot/fx_setups.py` repair committed in `1436f7b`, research-only. V3 ждёт PIT news, account/session costs и exact next-open. OANDA EU/MT5 demo даёт inputs, не REST deployment.
- Research Station v3 — immutable/resumable/fail-closed research frame; independent audit closed, `16` focused PASS, но production strategies пока `0` и edge authority нет.
- Local tape clocks active: ONDO L2 ~1.5GB, trades ~637–638MB; bytes не означают promotion-grade.
- Web exact signal horizontal/sloped geometry ещё не wired/rendered; `reports/GEOMETRY_SNAPSHOT_SPEC_2026_07_20.md` пока только spec.

## Строгий порядок 22–28 июля

1. `22 Jul`: read-only direct-truth receipt после финального root commit. Никаких широких изменений.
2. До Aug5: продолжать ATT1 broker-reconciled collection на `0.10`, контролировать breaker/heartbeat и не менять geometry/allowlist. Risk raise не обсуждать как способ получить больше сделок.
3. `23 Jul 04:37Z`: дать cash-carry clock завершиться. `23–24 Jul` выпустить immutable final evidence; при нуле economics passes — `NO_ENTRY`.
4. `22–25 Jul`: freeze audited local-only `settlement_execution_v3`, построить provenance-bound public collector и начать fresh public cycles from zero. Не менять VPS cron до отдельного approved migration.
5. Не раньше `23 Jul 18:19Z`: V2r2 48h source-finality/interim label pass без tuning. До `28 Jul 18:19Z` продолжать clock; final report реалистично 29 Jul. Любая revision = stop fail-closed.
6. `22–26 Jul`: исправить TSM contract/runner; first reviewed Station v3 adapter. Corrected rerun может FAIL; 8-week clock только после corrected PASS.
7. `24–28 Jul`: локально wire exact order-bound geometry -> Web overlays. Deploy только отдельным approval. Одновременно materialize FX/Alpaca inputs, но не считать performance на неполных данных.

FX figures реалистичны через `1–3 недели` **после** полного input freeze, не от текущей даты. Alpaca final untouched forward verdict остаётся не раньше `2026-11-04`. Никакой прибыли или `$100–300/month` не обещать.

## Не делать

- не использовать `git add -A` и не захватывать чужие dirty changes;
- не clean/pull/reset VPS;
- не auto-renew/scale ATT1 и не ослаблять фильтры ради частоты;
- не называть N8 edge;
- не возвращать TSM по старому PASS;
- не смешивать invalid V2 с V2r2 и не tune thresholds по clock;
- не путать Alpaca paper и real;
- не давать капитал carry/arbitrage;
- не выдавать MT5 demo за REST/live;
- не называть tape size доказательством;
- не утверждать, что Web уже рисует exact signal geometry;
- не обещать доход, PASS или дату money promotion.

## Главные exact sources

- `reports/releases/TRUTHFUL_WEB_HEALTH_TARGETED_DEPLOY_RECEIPT_8F030E3_2026_07_21.json`
- `reports/releases/CANONICAL_EVENT_ACTIVE_TARGETED_DEPLOY_RECEIPT_72DC6C2_2026_07_21.json`
- `reports/releases/ATT1_BOUNDED_RENEWAL_TARGETED_DEPLOY_RECEIPT_71E0857_2026_07_21.json`
- `runtime/live_mirror/bot_heartbeat.json`
- `runtime/live_mirror/alpaca_live_v38/account_state.json`
- `runtime/live_mirror/operator/operator_snapshot.json`
- `runtime/research/public_cashcarry_station_v1_20260716_public1/station_state.json`
- `runtime/research/event_universe_v2r2_20260721_public1/launch_receipt_v2.json`
- `research_lab/RESEARCH_STATION_V3.md`
- `configs/preregistered/settlement_execution_v3_research_v1.json`
- `tests/test_settlement_execution_v3_station.py`
- `reports/SETTLEMENT_EXECUTION_V3_RESEARCH_MVP_2026_07_21.md`
