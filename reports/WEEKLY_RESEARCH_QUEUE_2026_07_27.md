# Недельная research-очередь: 27 июля — 2 августа 2026

Статус: активна. Все задачи, кроме явно указанного targeted deploy, работают
без реальных ордеров.

| ID | Задача | Состояние | Trigger / gate | Выход |
|---|---|---|---|---|
| OPS-1 | Funding duplicate quarantine | выполнено | оставить один screen supervisor | incident receipt + post-cutover cohort |
| LIVE-1 | Equity fail-closed + ATT1 source telemetry | готовится | direct flat, py_compile, focused tests | targeted deploy receipt |
| EVT-1 | Event V2r2 collection | completed N1504 | immutable collector receipt | terminal |
| EVT-2 | Frozen event scorer | completed: 1h/4h FAIL, 24h BLOCKED_DATA | aggregate unchanged; short discovery needs new prereg | no money |
| XSEC-1 | XSEC risk-zero decisions | running, N4 | immutable daily ledger; first phase gross markout -0.44% | interim at N10–15 |
| XSEC-2 | PIT/execution repair spec | family gate PASS, PIT queued | 36/36 neighbouring V4 variants positive; no ledger rewrite | V5 PIT prereg, not live |
| ARB-1 | Funding post-cutover paper | running low-priority, N12 | 2 wins, median -0.1671%, p25 -0.2238%; N20/N30 | bounded economics decision |
| FPOS-1 | Funding positioning V4 maker audit | completed PASS to shadow | 5bps fill 92.95%, realized +13.49bps/submitted, 8/8 symbols | prospective only |
| FPOS-2 | Funding positioning V4 public shadow | first 72h FAIL economics; continuing to prereg N20 | N11, mean −7.45 bps, median −6.29 bps, fill 85.7%; no keys/orders | N20 bounded decision |
| FPOS-3 | Dynamic Funding universe challenger | BLOCKED_DATA audit, N12 | only COTI/BANK closes; 62.96% concentration; price continuity audit required | audited N20 frozen-vs-dynamic comparison |
| ALP-1 | Massive Basic PIT materializer/parity repair | exit defect localized; PIT queued | shared exit -5.19% combined vs calendar-hold +53.91% survivor proxy; calendar arm lacks catastrophe stop | distant-stop prereg + PIT/corporate-actions receipt |
| ALP-2 | Exact broker-parity shadow | collection running, N6 unique decisions; performance blocked by ALP-1 | same picks/exits as future broker path | shadow ledger |
| FX-1 | Preserve current FX negative baseline | completed FAIL | 9-family 0 PASS; H4 stress 16/16 negative | no unchanged rerun |
| FX-2 | D1 carry+trend prereg | public OANDA side-specific swap contract ready | wire long/short swap + base/stress commission | sealed OOS receipt |
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

## Checkpoint 29 июля 08:55 UTC

- Five risk-zero screens are active: cross-exchange arbitrage, Alpaca adaptive,
  XSEC, frozen Funding V4 and dynamic Funding V4.
- Dynamic Funding selector built a 16-symbol public-data universe without using
  signal or PnL. The shadow started after the latest funding event, so N0 is
  expected until the next event; frozen N8 remains the control.
- Cross-exchange paper is N12, 2 wins/10 losses, median `-0.1671%`, with five
  open cycles. N20 is approximately 2–3 days away if discovery cadence holds.
- FX harness now supports signed long/short swap and the public OANDA contract.
  FX-2 moves from data-blocked to implementation-ready; KYC/deposit is not
  needed.
- AI technology inventory and read-only web Book Status are implemented and
  covered by focused tests. The inventory explicitly refuses to treat static
  test references as readiness.
- ATT1 live is healthy but quiet: last entry 24 July; latest attempts are
  cooldown/no-signal, not execution failures. Live risk/universe/signals remain
  unchanged.

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
- XSEC cheap family falsification completed from a preregistered 36-variant
  grid. All `36/36` variants were positive after the fixed 15 bps cost contract;
  median compounded return was `+35.86%`, and the published champion sat at
  the 75th percentile rather than on an isolated island. This justifies the
  PIT rebuild, but capital remains blocked by survivor-only data, absent
  independent OOS, funding, slippage and execution parity.
- Alpaca Adaptive V1 causal historical proxy is terminal `REPAIR`, not a
  delayed forward PASS. At 5 bps/side the gated model returned `-1.61%` in the
  2022 proxy and `-3.58%` in the recent proxy, but beat its ungated controls
  (`-8.70%` and `-7.28%`). The SPY gate is retained; selector-versus-exit
  attribution and Massive PIT materialization are next. SAFE_HOLD is unchanged.
- Alpaca exit attribution localized the main defect: unchanged gated selector
  with the shared stop/target exit was `-5.19%` across the two proxy windows,
  versus `+53.91%` arithmetic for a 22-session hold. The latter is not a
  forecast or live candidate: it is survivor-only and lacks a broker
  catastrophe stop. Two stricter causal SMA gates failed to remove the small
  2022 loss, so that tuning branch is stopped without post-hoc optimization.

## Checkpoint 30 июля — новая очередь

- Live ATT1 incident repaired and targeted-deployed; statistics do not restart.
- Five risk-zero screens are active and their ledgers are fresh. WIP is full.
- XSEC has five immutable daily decisions.
- Frozen Funding V4 has 40 trials, 9 submissions, 6 modeled fills and 5
  closed lifecycles. Dynamic challenger has 111 trials and 3 closes; its very
  large early mean is not interpreted before N20.
- New long-running work is sequenced rather than started as a sixth competing
  process.

Next launch triggers:

| Free resource | Next job | Required output |
|---|---|---|
| first WIP slot | FX D1 carry+trend | sealed base/stress OOS receipt |
| second WIP slot | BOUNCE1 virtual lifecycle | exact SHA, immutable decisions/fills/exits |
| short-strategy slot | BREAKDOWN regime V2 | bear OOS plus untouched bull control |
| FX harness after D1 | H4 break/retest | side/pair/cost attribution |
| measurement harness | BTC/ETH midterm V4 | standalone chronological ledger |

Canonical queue:
`configs/research/strategy_promotion_queue_20260730.json`.
