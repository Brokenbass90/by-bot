# Recovery checkpoint — 2026-07-21

Каноническая точка продолжения после corrective-аудита live, TSM, event-universe, cash-carry, cross-exchange funding, FX и локальной Research Station v3. Снимок обновлён около `2026-07-21T18:55Z`.

Приоритет истины: broker/exchange -> свежий runtime receipt -> targeted deploy receipt + SHA -> immutable prereg research -> этот checkpoint/index -> интерпретация ИИ. Git push, VPS checkout и фактически установленные на VPS файлы — разные слои истины.

## Короткий вердикт

Оба live-сервиса работают, но доказанного нового денежного рукава нет. Владелец явно одобрил bounded-renewal ATT1: commit `71e0857` pushed, exact override с expiry `2026-08-05`, short-only risk `0.10` и IVB1 risk `0` установлен на VPS. Однако свежий heartbeat `2026-07-21T18:49:56Z` всё ещё показывает старый process env (`2026-07-20`, breaker blocked, **effective risk `0.0`**), поэтому ATT1 пока нельзя называть активным до reload/restart postcheck. Его маленькая выборка `N8`, WR `50%`, PF `1.27965`, net `+0.4992 USDT` не доказывает edge. Alpaca real live безопасно удерживает три позиции со стопами `3/3` в `SAFE_HOLD`. Старый TSM PASS отозван. Intraday sloped/horizontal/sweep, pump-fade final gate и три level-DCA ветки не дали второго crypto sleeve.

Положительный прогресс сейчас инфраструктурный: truthful Web/health patch развернут, event-universe V2r2 корректно preregistered и собирает public data, public cash-carry clock дошёл до 1557 observations, а Research Station v3 получила immutable/resumable/fail-closed каркас. Это не обещание прибыли.

Финальная локальная проверка после corrective batch: `1507` tests PASS; JSON maps валидны; `git diff --check` чист.

## Git и targeted live

- Branch: `codex/dynamic-symbol-filters`.
- До July-21 docs/research batch local HEAD и upstream совпадали на `71e0857`; сам audited batch committed и pushed как `d55fbc1`. Небольшой metadata follow-up может быть новее; следующая сессия обязана заново получить HEAD/upstream.
- VPS checkout намеренно остаётся `f7ed011` stale; последняя direct проверка насчитала `349` status records. Blind pull/reset/clean запрещены. Runtime truth задают exact-file deploy receipts и postchecks.
- Map-only release `72dc6c2` завершён: два AI/capability map файла установлены с совпадающими hashes, без restart, risk, orders или checkout advance. Receipt: `reports/releases/CANONICAL_EVENT_ACTIVE_TARGETED_DEPLOY_RECEIPT_72DC6C2_2026_07_21.json`.
- Commit `8f030e3` адресно развернут только для Web chart timestamps и rolling health. `bybot.service` остался active, PID `2931263` не менялся с 15 июля; `trading-journal-web.service` active и был перезапущен 21 июля, новый PID `1046949`. Core/env/risk/orders не менялись. Receipt: `reports/releases/TRUTHFUL_WEB_HEALTH_TARGETED_DEPLOY_RECEIPT_8F030E3_2026_07_21.json`.
- Canonical configs локально обновлены, но их новый July-21 batch ещё не targeted-deployed на VPS: onboard AI остаётся на предыдущем map receipt до отдельной установки exact files и rebuild context.
- ATT1 renewal receipt: `reports/releases/ATT1_BOUNDED_RENEWAL_TARGETED_DEPLOY_RECEIPT_71E0857_2026_07_21.json`. Exact override SHA `956af19f...` совпал после установки; backup существует; core не перезапускался, риск/геометрия/allowlist не повышались.

## Bybit и ATT1

- Direct/mirrored runtime: core active, `trade_on=true`, `dry_run=false`, broker flat, `bull_chop`.
- Installed ATT1 override содержит expiry `2026-08-05`, configured `risk_mult=0.10`, short-only; IVB1 остаётся `0`. Last observed runtime всё ещё содержит expiry `2026-07-20`; breaker показывает `expired=true`, `blocked=true`, поэтому effective risk пока `0.0`.
- Последний честный малый cohort: `N8`, wins/losses `4/4`, WR `50%`, PF `1.27965`, net `+0.4992 USDT`; verdict `insufficient`, edge unproven.
- Решение владельца уже получено и exact override установлен. Следующий gate — один свежий heartbeat с expiry `2026-08-05`, `blocked=false`, `expired=false`, breaker multiplier `1.0`; если standalone reload не происходит, нужен один controlled broker-flat restart. Будущие автопродления запрещены.
- Риск нельзя повышать ради частоты: `risk_mult` меняет размер позиции, но не создаёт сигналов. Повышение выше `0.10` требует отдельной evidence ladder и достаточной broker-reconciled выборки, которой сейчас нет.
- Source: `runtime/live_mirror/bot_heartbeat.json`, `reports/ATT1_CANARY_ACTIVATION_2026_06_29.md`, deploy receipt `8f030e3` выше.

## Alpaca: не смешивать real и paper

Latest real broker mirror (`2026-07-21T08:00:13Z`):

- real account equity `$484.01`, cash/buying power `$358.11`;
- real positions `ABBV`, `ABNB`, `SCHW`;
- exact open protective stop quantity coverage `3/3`;
- режим остаётся `SAFE_HOLD`: никаких новых buys, forced stale closes или принудительной liquidation/rotation.

Это не тот же контур, что отдельный paper adaptive/intraday manager. Paper runtime `LIVE_PAPER` имеет условный paper equity и позиции `ABBV`, `CRWD`, `DDOG`; его нельзя показывать как реальные Alpaca holdings или live income.

Successor не auto-activates и не force-liquidates текущие real holdings. Он остаётся fail-closed из-за пяти отсутствующих authoritative inputs: XNYS calendar ledger, PIT universe, PIT adjusted market manifest, corporate-actions/delistings и broker lifecycle + real cost calibration. Real source: `runtime/live_mirror/alpaca_live_v38/account_state.json`; separation source: `runtime/live_mirror/operator/operator_snapshot.json`; gate: `reports/ALPACA_BAKEOFF_V2_AND_SAFE_HOLD_AUDIT_2026_07_16.md`.

## TSM и crypto research verdicts

Предыдущий `tsm4 long_short PASS` заменён на `RESEARCH_BLOCKED`; valid prospective shadow weeks остаются `0/8`. Причины:

- symbol-dependent weekday anchor не совпадал с заявленным Monday execution;
- списывалась одна сторона заявленных round-trip costs, funding не был PIT;
- результат anchor/2021-sensitive и концентрирован;
- отсутствовали mark, maintenance, liquidation и survival semantics;
- local shadow ledger допускал две разные записи за день без as-of/hash/idempotency;
- code/data/output не были immutable evidence на момент PASS.

TSM не доказан мёртвым, но серверный wiring/capital запрещены до corrected immutable rerun. Source: `reports/TSM_PROVISIONAL_DOWNGRADE_AUDIT_2026_07_21.md`.

Остальные итоги:

- unique sloped run: `64/64` FAIL;
- wide sloped/horizontal + sweep: `160/160` без survivor и без положительного IS net;
- final pump-fade station: `36/36`, включая 19 positive-IS rows, но `0` IS-pass и `0` survivor;
- level-DCA v1/v2/v3 закрыты тремя отрицательными preregistered verdicts;
- следовательно второго crypto money sleeve нет; старые families не перебирать повторно на тех же данных/majors.

Sources: `research_lab/results/sloped_v1.jsonl`, `research_lab/results/wide_v1.jsonl`, `research_lab/results/sweep_v1.jsonl`, `research_lab/results/pumpfade_v1.jsonl`, `reports/LEVEL_DCA_V1_VERDICT_2026_07_20.md`, `reports/LEVEL_DCA_V2_MIDTERM_VERDICT_2026_07_20.md`, `reports/LEVEL_DCA_V3_FINAL_VERDICT_2026_07_20.md`, `reports/PROJECT_STATE_LEDGER.md`.

## Event universe: V1 blocked, V2 invalidated, V2r2 active

- Frozen V1 label scorer остановился fail-closed на cross-snapshot revisions одного BANKUSDT M5 bar. Returns/performance не считались; статус `BLOCKED_BY_SOURCE_FINALITY`, а не strategy FAIL. Source: `reports/EVENT_UNIVERSE_LABEL_SCORER_FIRST_PASS_2026_07_21.md`.
- Первый V2 запуск имел declared preregistration timestamp после первого observation. Screen остановлен; root и один snapshot сохранены, явно invalidated и не могут смешиваться с replacement. Receipt: `reports/releases/EVENT_UNIVERSE_V2_INVALIDATED_TIMESTAMP_RECEIPT_2026_07_21.json`.
- Corrected prereg `event_universe_v2r2_20260721` frozen до launch/observation. Active local screen: `event_universe_v2r2_20260721`; hard deadline `2026-07-28T18:19:58Z`.
- Первый corrected snapshot: universe/prefetch/scored/candidates/errors = `752/100/100/17/0`.
- Collector public `GET` only, no keys/private calls/orders/risk, terminal fail-closed on any later revision. Никакого threshold tuning или promotion по текущему clock.
- Sources: `configs/preregistered/event_universe_v2r2_20260721.json`, `reports/EVENT_UNIVERSE_V2R2_SOURCE_FINALITY_PREREG_2026_07_21.md`, `reports/EVENT_UNIVERSE_V2R2_LAUNCH_STATUS_2026_07_21.md`, `runtime/research/event_universe_v2r2_20260721_public1/launch_receipt_v2.json`.

## Cash-carry и cross-exchange funding

Public single-venue cash-carry station остаётся active до `2026-07-23T04:37:10Z`. Snapshot около `2026-07-21T18:03Z`:

- `1557` durable observations на шести символах;
- economics passes `0`; все последние действия `observe`;
- public GET-only, no keys/private calls/broker calls/orders/capital;
- старый прогноз `$5–15/month per $1000` остаётся отозван; при нулевых passes капитал не добавлять.

Sources: `configs/preregistered/public_cashcarry_station_v1_20260716.json`, `runtime/research/public_cashcarry_station_v1_20260716_public1/station_state.json`, `reports/BYBIT_ACCOUNT_FEE_RECEIPT_2026_07_18.md`.

Отдельная cross-exchange funding v2 invalidated как модель. Её `228` closed cycles не доказывают ни доходность, ни убыток: неверные per-venue funding intervals, отсутствующая asset taxonomy, не-authoritative settlements, parallel cron без lineage/atomic handoff и execution/exit defects. Все старые `$5–15` forecasts withdrawn. Исправленный scanner P0 и отдельный `settlement_execution_v3` sequential/atomic research-only MVP реализованы локально. Независимый аудит нашёл и закрыл три P1: funding теперь считается `quantity × exact settlement mark × actual rate`; причинная цепочка `predicted -> validation -> entry -> settlement` fail-closed; manifest хеширует весь runner/package. Итог `11/11` focused PASS, P0/P1 внутри declared model не осталось. Никаких cron/deploy/capital/orders. Ограничения: только pre-normalized public bundles, комиссии assumptions, без authenticated fills, margin, transfers, liquidation и real legging; ROI descriptive only. Source: `reports/CROSS_EXCHANGE_FUNDING_V2_FORENSIC_VERDICT_2026_07_21.md`, `scripts/cross_exchange_funding_scan.py`, `scripts/settlement_execution_v3/`, `tests/test_settlement_execution_v3_station.py`.

## FX/CFD

- Реальные Dukascopy M5 уже существуют примерно за `728` дней по `6` symbols; повторно объявлять, что M5 отсутствует, нельзя.
- Legacy causal repair `bot/fx_setups.py` + `tests/test_fx_setups.py` сохранён в pushed commit `1436f7b`, но это research-only, не VPS/live.
- FX V3 остаётся blocked до трёх authoritative вещей: PIT historical macro-news, target account/session-specific costs (spread p50/p95, commission, swap/financing, slippage) и exact signal-close -> next tradable open execution parity.
- OANDA EU/MT5 demo observations полезны для instrument/cost inputs, но не дают OANDA v20 REST deployment, broker automation или live authority. Demo orders допустимы только после strict PASS; real — после минимум 30 clean demo closes и отдельного owner approval.
- Sources: `reports/FX_CFD_DATA_AND_FIRST_FIGURES_AUDIT_2026_07_13.md`, `reports/FX_COST_CONTRACT_OANDA_DEMO_2026_07_13.md`, `configs/research/fx_v3_preflight_20260711.json`, `bot/fx_setups.py`.

## Research Station v3 и local collectors

`research_lab/station_v3.py` — новый research-only immutable/resumable/fail-closed orchestrator: explicit paths and hashes, input continuity/calendar validation, hash-chained trial evidence, atomic receipts/checkpoints, idempotent resume и credential-free/network-blocked worker. Независимый integrity-аудит закрыт: исправлены checkpoint/resume/finality/isolation P1, `16` focused tests PASS, оставшихся P0/P1 внутри documented frame model нет. Это всё ещё только frame: production strategy adapter не подключён и performance authority отсутствует. Sources: `research_lab/RESEARCH_STATION_V3.md`, `research_lab/station_v3.py`, `research_lab/station_v3_worker.py`, `tests/test_research_station_v3.py`.

Local public tape clocks активны и растут:

- ONDO L2 tree около `1.5 GB`;
- six-symbol public trades tree около `637–638 MB`;
- это сырые local data, не promotion-grade evidence: нужен immutable data-quality/coverage receipt, stable-host continuity, clock/skew/drop/reconnect analysis и preregistered consumer.

Sources: `reports/L2_TAPE_COLLECTOR_SPEC_2026_07_13.md`, `reports/L2_TAPE_COLLECTION_START_2026_07_14.md`, `runtime/tape/bybit_l2_ondo_v1/heartbeat.json`, `runtime/tape/bybit_trades_micro_v1/heartbeat.json`.

## Web/TG truth и незакрытая geometry

- `8f030e3` исправил seconds-vs-milliseconds epoch в trade chart и ограничил health настоящим rolling 30-day window; stale historical `range N21 PF0.487` удалён из текущего TG health, который теперь показывает только ATT1 и `insufficient`.
- Web пока рисует candles и простые entry/SL/TP horizontals. Exact signal-generating horizontal/sloped levels, ATT1 pivots/line/projection и order-bound geometry snapshot **не wired и не rendered**.
- `reports/GEOMETRY_SNAPSHOT_SPEC_2026_07_20.md` — только spec. До реализации нельзя утверждать, что chart объясняет геометрию фактического сигнала.

## Строгая очередь на 7 дней: 22–28 июля

| Приоритет и срок | Работа | Жёсткий выход/ворота |
|---|---|---|
| P0, 22 Jul | После финального root config/docs commit заново проверить HEAD/upstream, tracked dirty ownership, оба service PID, broker flat, ATT1 breaker и Alpaca stops. | Только read-only receipt. VPS checkout не чистить. |
| P0, сейчас | Подтвердить применение уже установленного owner-approved ATT1 renewal. Если heartbeat остаётся stale — один controlled restart только после broker-flat check. | Postcheck: expiry Aug5, blocked/expired false, breaker×1, ATT1 `0.10` short-only, IVB1 `0`, позиции не изменились. |
| P0, 23 Jul 04:37Z; report 23–24 Jul | Дать public cash-carry clock закончиться, затем заморозить final counts/distribution/reasons. | При `0` stressed economics passes: `NO_ENTRY`, no capital; не «лечить» рискованием. |
| P0, target 22–25 Jul | Freeze audited local-only `settlement_execution_v3`, построить provenance-bound public collector и начать fresh cycles from zero. | Никакого cron/deploy/capital на этой неделе; descriptive ROI не превращать в доходность. |
| P1, earliest interim 23 Jul 18:19Z; hard end 28 Jul 18:19Z | Не трогать V2r2 thresholds; после 48h только source-finality/interim labels, после deadline — final evidence freeze. | Любая revision => terminal fail-closed. Final report реалистично 29 Jul, не в минуту deadline. |
| P1, target 22–26 Jul | Переписать TSM contract и runner под fixed UTC anchor, exact next-open, обе стороны fees, PIT/stressed funding, mark/maintenance/liquidation, immutable hashes и idempotent weekly receipt; первым real adapter подключить к Station v3 только после review. | Corrected rerun может остаться FAIL. Новый 8-week parity clock начинается только после corrected PASS, не задним числом. |
| P1, target 24–28 Jul | Локально wire order-bound geometry snapshot -> Web exact horizontal/sloped overlays; параллельно материализовать, но не подменять, FX/Alpaca authoritative inputs. | Geometry deploy — отдельное approval. FX figures не раньше 1–3 недель после полного input freeze; Alpaca остаётся SAFE_HOLD. |

## Решения владельца

1. Если runtime не перечитает override сам, нужен отдельный controlled broker-flat restart и postcheck; renewal и риск уже одобрены, повторное решение не требуется.
2. Не force-sell Alpaca и не путать paper `ABBV/CRWD/DDOG` с real `ABBV/ABNB/SCHW`.
3. Для FX предоставить/подтвердить account-specific commission/swap/session spread evidence и PIT macro-news source; secrets не присылать в чат.
4. Не добавлять капитал в carry/arbitrage и не ждать фиксированную доходность от текущих research clocks.

## Запрещено без новых ворот

- автоматически продлевать ATT1, повышать его risk или ослаблять фильтры ради сделок;
- называть `N8` доказанным edge;
- включать TSM по старому PASS или засчитывать две July-21 строки как недели shadow;
- повторять закрытые sloped/horizontal/sweep/DCA grids и выдавать selection за discovery;
- анализировать invalidated V2 вместе с V2r2;
- считать 1557 cash-carry observations или 228 invalid v2 cycles денежным edge;
- выдавать MT5 demo за OANDA REST/live deployment;
- называть local tape bytes promotion-grade dataset;
- утверждать, что Web уже рисует exact signal geometry;
- blind pull/reset/clean dirty VPS, `git add -A`, broad deploy без exact hashes/backup/postcheck;
- обещать прибыль, `$100–300/month` или календарную дату money promotion.

## Канонические evidence-файлы

- `reports/PROJECT_CANONICAL_INDEX_2026_07_21.json`
- `reports/NEXT_CHAT_START_PROMPT_2026_07_21.md`
- `reports/PROJECT_STATE_LEDGER.md`
- `reports/releases/TRUTHFUL_WEB_HEALTH_TARGETED_DEPLOY_RECEIPT_8F030E3_2026_07_21.json`
- `reports/releases/CANONICAL_EVENT_ACTIVE_TARGETED_DEPLOY_RECEIPT_72DC6C2_2026_07_21.json`
- `reports/releases/ATT1_BOUNDED_RENEWAL_TARGETED_DEPLOY_RECEIPT_71E0857_2026_07_21.json`
- `reports/TSM_PROVISIONAL_DOWNGRADE_AUDIT_2026_07_21.md`
- `reports/EVENT_UNIVERSE_LABEL_SCORER_FIRST_PASS_2026_07_21.md`
- `reports/EVENT_UNIVERSE_V2R2_LAUNCH_STATUS_2026_07_21.md`
- `reports/releases/EVENT_UNIVERSE_V2_INVALIDATED_TIMESTAMP_RECEIPT_2026_07_21.json`
- `reports/CROSS_EXCHANGE_FUNDING_V2_FORENSIC_VERDICT_2026_07_21.md`
- `reports/SETTLEMENT_EXECUTION_V3_RESEARCH_MVP_2026_07_21.md`
- `reports/FX_CFD_DATA_AND_FIRST_FIGURES_AUDIT_2026_07_13.md`
- `research_lab/RESEARCH_STATION_V3.md`
- `configs/preregistered/settlement_execution_v3_research_v1.json`
- `tests/test_settlement_execution_v3_station.py`
