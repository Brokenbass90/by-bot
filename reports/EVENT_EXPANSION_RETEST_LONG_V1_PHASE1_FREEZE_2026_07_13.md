# Event Expansion Retest Long v1 — phase-1 causal freeze

Дата фиксации: 2026-07-13
Статус: **BLOCKED_RESEARCH_RUNNER_DATA**
Performance: **PERFORMANCE_FORBIDDEN**
Live/broker/risk: **LIVE_FORBIDDEN**, `risk_pct=0`

Phase-1 preflight прошёл identity-проверку: `integrity_pass=true`. Это означает,
что causal mechanics, тесты и их SHA256 совпадают с новым frozen contract. Это
не бэктест, не оценка edge и не разрешение на shadow/live.

Машинный контракт:
`configs/preregistered/event_expansion_retest_long_v1_phase1_20260713.json`.
Fingerprint:
`4d1dcf764c2f183945c01919ab8e52796f72ccc2d00ad945a950745e9c1ce993`.

## Что теперь действительно закрыто кодом

Phase 1 hash-pin фиксирует единый long-only путь:

1. только exact contiguous closed M5 prefix с явным `as_of` и provider
   fingerprint;
2. детерминированная агрегация M5 -> M15/H1/H4 без partial bucket и
   заполнения дыр;
3. immutable горизонтальный H1/H4 resistance level с доказанными respects,
   approach-from-below, реакцией и unbroken-history;
4. closed H1 expansion;
5. более поздний M15 hold;
6. первый более поздний M15 retest, который потребляется один раз;
7. отдельный подтверждённый M15 higher-low pivot;
8. строго более поздний M15 BOS;
9. решение известно на close BOS-бара, а допустимый fill — exact M5 open на
   этой же временной границе;
10. stop ниже `min(retest low, zone low)` с ATR-buffer;
11. actual next-open reanchors 1R/2R targets, stop остаётся замороженным;
12. stop-first при intrabar ambiguity, gap handling, 96 M5 max-hold, base и
   stress costs, exact funding-event policy;
13. MTF plan -> execution plan проходит через отдельный authenticated bridge,
   который связывает M5/H1/M15, level, event, state, provider и config;
14. FSM state и pending outbox сохраняются одним `0600` файлом через temp
   `fsync` -> replace -> directory `fsync`; ACK атомарно переносит plan из
   outbox в acknowledged ledger и проверяет повторную загрузку.

Важное downtime-исправление вошло в commit
`72c273d05cc93b945bea8709e25275a8e9f51b25`: если один replay доходит до
готового plan, он теперь останавливается точно на decision boundary. Он не
может продолжить прокрутку и сделать свежий plan уже просроченным для bridge.
Пока pending outbox не обработан и durable ACK не выполнен, новый replay и
движение watermark запрещены.

## Что перешло из phase 0

Phase 0 сохранён неизменным как историческая фиксация:

- path: `configs/preregistered/event_expansion_retest_long_v1_20260713.json`;
- SHA256:
  `8660ae7718951a9acfb510df0549d38ebef265c5dd67e1a692029bd9d7dc88de`;
- contract fingerprint:
  `317a3a63d437a2ce0aad06bee7dcea61a12e333fd1306ac7236719729fe40c7d`.

Старый phase-0 preflight теперь ожидаемо может показывать hash mismatch: он
фиксировал более ранний `LevelSnapshot`, а active source после этого был
усилен. Старый contract не переписан задним числом. Для текущей ветки
авторитетен phase-1 preflight.

Три phase-0 blockers закрыты только как code contracts:

- `MULTITIMEFRAME_ORCHESTRATOR_ABSENT`;
- `EXIT_MODEL_ABSENT`;
- `COST_FUNDING_MODEL_ABSENT`.

Последний пункт означает наличие точной cost/funding логики, но не наличие
полных исторических funding data. Полнота данных остаётся отдельным blocker.

Все численные будущие ворота phase 0 наследуются по точному SHA/fingerprint
без смягчения. Даже их будущий полный PASS не разрешает live автоматически.

## Data-quality blocker dev13

Существующий immutable manifest совпадает с закреплённым SHA и годится как
development input identity. Но он пока не performance-authoritative:

- 11 символов доходят до `2026-07-05T00:00:00Z`;
- BTCUSDT и ETHUSDT заканчиваются на 119 M5 bars раньше;
- общий безопасный end-exclusive сейчас только
  `2026-07-04T14:05:00Z`.

До доступа к результатам нужен новый immutable manifest: либо честно
дозагрузить BTC/ETH, либо прозрачно обрезать все 13 символов до единого общего
окна. Выбор и новый hash должны быть зафиксированы до performance-run.

External8 остаётся заранее запечатанным и непрочитанным:
`FIL, UNI, ETC, ICP, TRX, TON, MNT, IMX`. Prospective-период не начат.

## Девять оставшихся blockers

1. `PERFORMANCE_RUNNER_ABSENT`: нужен hash-pinned runner на completed-bar
   engine store с canonical snapshot loader, fixed folds/embargo, LOSO,
   portfolio sizing и additivity.
2. `DURABLE_EXECUTION_RECEIPT_AND_ACK_RUNNER_ABSENT`: bridge сам ничего не
   сохраняет и не ACK-ает. Runner обязан сначала durable-записать bridge и
   execution/trade receipts, затем atomic ACK; ambiguous write outcome должен
   восстанавливаться без duplicate execution.
3. `FUNDING_COMPLETENESS_PROOF_ABSENT`: нужны exact funding events и
   машинное доказательство полного покрытия каждого holding window.
4. `DEV13_UNIFORM_WINDOW_MANIFEST_ABSENT`.
5. `EXTERNAL8_MARKET_DATA_ABSENT`.
6. `EXTERNAL8_METADATA_ABSENT`.
7. `EXTERNAL8_LIQUIDITY_ABSENT`.
8. `EXTERNAL8_FUNDING_ABSENT`.
9. `ATT1_REFERENCE_ABSENT`: same-window returns, trades, occupancy и equity
   для обеих очередностей allocator.

Durable store намеренно single-writer и не имеет interprocess lock. Это
приемлемо только при одном явно назначенном research owner. Phase-2 runner
должен обеспечить это ограничение и fail closed при конкурирующем владельце.

## Что запрещено до следующего freeze

- запускать performance на dev13 или external8;
- смотреть outcome metrics и потом менять параметры/cohort/window;
- объявлять external8 или старые данные prospective;
- ACK-ать plan до durable bridge/execution receipt;
- добавлять sleeve в registry, shadow или live;
- делать broker call, назначать risk или деплоить эту стратегию на VPS.

## Воспроизводимая проверка

```bash
.venv/bin/python scripts/preflight_event_expansion_retest_long_v1_phase1.py
.venv/bin/python -m pytest -q \
  tests/test_closed_bar_aggregation_v1.py \
  tests/test_level_snapshot_v1.py \
  tests/test_event_expansion_retest_long_mtf_v1.py \
  tests/test_event_long_execution_v1.py \
  tests/test_event_long_mtf_execution_bridge_v1.py \
  tests/test_event_expansion_retest_long_mtf_state_store.py \
  tests/test_preflight_event_expansion_retest_long_v1_phase1.py
```

Фактический результат при freeze: `97 passed`; phase-1 preflight вернул
`integrity_pass=true` одновременно с
`PERFORMANCE_FORBIDDEN / LIVE_FORBIDDEN` и всеми девятью blockers.

Следующий допустимый этап — закрыть runner/receipt journal и data manifests,
создать отдельный phase-2 runnable freeze, commit + push, и только после этого
впервые открыть performance outputs.
