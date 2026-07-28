# Недельная research-очередь: 27 июля — 2 августа 2026

Статус: активна. Все задачи, кроме явно указанного targeted deploy, работают
без реальных ордеров.

| ID | Задача | Состояние | Trigger / gate | Выход |
|---|---|---|---|---|
| OPS-1 | Funding duplicate quarantine | выполнено | оставить один screen supervisor | incident receipt + post-cutover cohort |
| LIVE-1 | Equity fail-closed + ATT1 source telemetry | готовится | direct flat, py_compile, focused tests | targeted deploy receipt |
| EVT-1 | Event V2r2 collection | running | deadline `2026-07-28 18:19:58 UTC` | coverage/hash receipt |
| EVT-2 | Frozen event scorer | waiting | EVT-1 terminal | PASS/FAIL/BLOCKED_DATA |
| XSEC-1 | XSEC risk-zero decisions | running, N3 | immutable daily ledger; first markout expected 29 Jul | interim at N10–15 |
| XSEC-2 | PIT/execution repair spec | queued | no ledger rewrite | V5 prereg, not live |
| ARB-1 | Funding post-cutover paper | running low-priority, N7 | 7 losses; N20/N30 clean cycles | bounded economics decision |
| ALP-1 | Massive Basic PIT materializer/parity repair | connector 3/3, implementation queued | API env available locally; close 9 unpinned artifacts | coverage/corporate-actions receipt |
| ALP-2 | Exact broker-parity shadow | collection running, N5 unique decisions; performance blocked by ALP-1 | same picks/exits as future broker path | shadow ledger |
| FX-1 | Preserve current FX negative baseline | completed FAIL | 9-family 0 PASS; H4 stress 16/16 negative | no unchanged rerun |
| FX-2 | D1 carry+trend prereg | queued | Dukascopy data + conservative costs | sealed OOS receipt |
| FX-3 | H4 breakout/retest prereg | queued after FX-2 | WIP control | sealed OOS receipt |
| ATT-1 | ATT1 seasonality/filter | completed FAIL | discovery hour 21 UTC failed validation and holdout | no live filter change |
| ATT-2 | ATT1 A3/3R exact replay | completed FAIL | worse expectancy/red months/DD than champion | preserve champion; no forward shadow |
| VOL-1 | Full owner volume setup | queued after Package A | causal dynamic universe | integrated smoke then OOS |
| CLAUDE-A | Strategy/module/claim package | audited BLOCKED/PARTIAL | ASB1 name collision, overlapping evidence, no virtual shadow lifecycle | independent audit receipt |
| BNC-1 | BOUNCE1/support-bounce rehabilitation | queued next | canonical rename + virtual decision/fill/exit ledger + untouched prereg | risk-zero shadow-ready receipt |
| LEVEL-1 | LevelSnapshotV2 provenance design | queued | do not change ATT1 | parity/visual contract |
| PORT-1 | Three-slot portfolio combiner | queued | only authoritative trade ledgers | OOS portfolio metrics |

## Operating rules

- Не запускать второй экземпляр уже активного collector/supervisor.
- Не переписывать append-only ledgers; дефектные интервалы получают quarantine.
- Одновременно допускается один новый тяжёлый CPU backtest и один Claude
  package. Collectors продолжают работу параллельно.
- После каждого terminal job: exact command, input hashes, costs, sample,
  side/regime split, red months и PASS/FAIL/BLOCKED_DATA.
- Автовосстановление разрешено только для risk-zero research processes.
- Live ATT1 risk, side, universe и geometry не меняются этой очередью.

## Проверка каждые 12 часов

1. service/screens/PID uniqueness;
2. freshness и рост ledger;
3. disk/load;
4. terminal receipts и blockers;
5. promotion gate без автоматического promotion;
6. exact-file commit/push только новых доказательств.

## Ожидаемые контрольные точки

- 28 июля: event collector terminal;
- 29–30 июля: frozen event verdict либо coverage blocker;
- 30 июля–2 августа: Massive Basic audit, текущие FX receipts, ATT1 sealed
  filter/replay;
- фактическая funding скорость определяет N20; календарная дата не подменяет
  sample gate;
- XSEC interim ожидается позже недели, если daily frequency сохранится.

## Checkpoint 28 июля 11:09 UTC

- Direct live truth: Bybit service/heartbeat healthy, equity `1020.01 USDT`,
  open positions `0`; ATT1 remains short-only `x0.10`, no live mutation.
- Event V2r2 sequence reached `1418`; collector and the single postrun watcher
  remain alive. Terminal coverage/scoring stays bound to the deadline.
- XSEC has `3` immutable daily decisions; Alpaca adaptive shadow has `5` unique
  decisions. Neither sample is a performance verdict.
- Funding ROI receipt now excludes every cycle opened before the single-writer
  cutover. Truthful cohort is `N7`, `0` wins, median `-0.1930%`, p25
  `-0.2308%`; capital remains forbidden. A hidden pre-lock orphan that briefly
  rewrote the report as mixed `N17` was terminated and that receipt quarantined.
- ATT1 seasonality study is terminal `FAIL`: discovery selected hour 21 UTC,
  but removal worsened both validation and sealed holdout. `NO_ENTRY_HOURS_UTC`
  remains unchanged.
- ATT1 A3/3R exact replay is terminal `FAIL`. At 11 bps the champion produced
  `+41.70%` simulated 360d return, PF `1.475`, 4/4 positive folds, 1 red month
  and `6.65%` DD; the combined challenger produced `+17.52%`, PF `1.196`,
  3/4 folds, 4 red months and `17.46%` DD. Champion stays unchanged; the
  combined A3/fixed-3R hypothesis does not enter forward shadow.
- Claude support-bounce arithmetic reproduced, but promotion claims did not:
  “ASB1 long” was actually `BOUNCE1`, 292 rows contained 278 unique trades,
  the 46-trade power claim failed, and zero live risk cannot create virtual
  closures. Archive moves remain uncommitted. Next implementation WIP is a
  separate virtual BOUNCE1 lifecycle plus untouched prereg.
