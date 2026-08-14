# Recovery session checkpoint — 2026-08-14

## Answer first

The project made a real step forward: ATT1 now has a clean positive forward cohort, both the TP2 concern and a causal momentum-stall exit were tested rather than guessed, a distinct sloped-break V2 was implemented and rejected in one frozen historical run, Inplay silence was explained by evidence rather than a stale allowlist verdict, XAU download was repaired to resume daily, and a cross-collector compression race was removed. No second money sleeve is promoted by this checkpoint.

## Direct live truth at the checkpoint

- Bybit broker: flat, zero open positions at the read-only check.
- Bybit service: active; fresh heartbeat; trading enabled; WebSocket guard inactive at the check.
- ATT1 clean cohort: 5/20 closes, +2.950R, PF(R) 3.289, max clean drawdown 1.289R, zero rejected conflict evidence.
- ATT1 gates already passing: net R, PF, drawdown, and conflict checks. Remaining scale gate: N20 plus a fresh exact risk/runtime/broker reconciliation.
- Alpaca: live broker equity approximately $487.52, two protected legacy holdings at the check. New entries remain SAFE_HOLD.
- Bitget signed read-only futures balance: 0 USDT. Credentials are configured by presence, but no audited multi-exchange execution sleeve exists.

No order was submitted, changed, cancelled, or manually closed in this session. No risk was changed and no live monolith was deployed or restarted.

## ATT1: what is true now

The old +30.20R/308-trade narrow anchor is not a clean proof. Corrected Geometry V2 on the fixed eight-major pre-holdout window produced -2.468R over 393 trades. That historical correction does not make the currently running tiny canary automatically invalid: its first five clean forward closes total +2.950R, but N=5 is not enough to scale.

The user concern that TP2=2.5R might be too far was tested with a passported binary experiment. Moving TP2 to 1.8R worsened net result by 1.522R and did not materially improve drawdown. The 1.8R challenger is rejected.

The separate BE-gated momentum-stall experiment also completed. It changed 14/393 exits and improved the corrected pre-holdout result by +0.391R, from -2.468R to -2.077R; PF(R) moved from 0.9877 to 0.9897 and portfolio-dollar drawdown from 13.510 to 13.254. The direction is useful, but the arm remains negative, BTC/ETH were unchanged, and ADA/AVAX worsened. Verdict: validation candidate only, no live change.

Sources:

- `reports/evidence/ATT1_LIVE_LIFECYCLE_20260814.json`
- `reports/evidence/ATT1_TP2_DISTANCE_PREHOLDOUT_20260814.json`
- `reports/evidence/ATT1_MOMENTUM_STALL_EXIT_PREHOLDOUT_20260814.json`
- `research_lab/results/att1_tp2_distance_preholdout_v1_20260814/run_passport.json`
- `research_lab/results/att1_momentum_stall_exit_preholdout_v1_20260814/run_passport.json`

## Why the three silent shadow sleeves are silent

- Inplay prospective: zero current signals, but current hashes exactly match the historical reference. Four previous 35-day slices emitted 0.91–2.31 raw signals/day. Current regime fails mainly on impulse strength and breakout-side conditions. This is not an allowlist bug.
- Bounce1: runtime diagnostics show most attempts blocked by symbol routing, then same-bar suppression. This requires a strategy-specific scheduler/allowlist plumbing audit; it is not safe to call it simply a quiet market.
- IVB1: most rejects fall into an unhelpful `other` bucket. Instrumentation is insufficient and must be repaired before loosening filters.
- Midterm: very few attempts and all failed the trend filter on its BTC/ETH scope. It has a different trigger cadence and should not be expected to trade like ATT1.

## Research lanes

| Lane | Stage | Evidence now | Next gate |
|---|---|---|---|
| ATT1 | tiny live canary | N5, +2.950R; corrected historical net not robust | N20 and exact runtime/broker/risk reconciliation |
| Inplay ETH 24h | prospective shadow | N0 current; historical frequency parity passes; edge windows mixed | accumulate actual events; do not relax contract midstream |
| Sloped break/retest V2 | frozen development contract rejected | 18 trades, -2.739R, PF(R) 0.704; funnel: 131 breaks -> 35 held first retests -> 20 signals | V3 may change only the retest contract; no grid or live promotion |
| XSEC | research/shadow candidate | promising old research, but same-close/PIT/funding concerns | exact next-open, funding-adjusted, closed-contract PIT replay |
| Funding/carry | data repair | 137-symbol funding complete; only 74 exact spot pairs | exact spot/perp mapping, real fee tiers, PIT universe |
| Alpaca V38 | protected SAFE_HOLD pilot | clean proxy +11.14% annualized but DD 23.71% and not exact live contract | deploy isolated GTC protection fix only through safe gate; exact live replay |
| XAU intraday | data acquisition | repaired daily resumable collector; first market day persisted | finish/quarantine repair, then session sweep/retest preregistration |
| Bitget | read-only integration audit | futures balance 0; no order-parity/reconciliation layer | transfer by owner if desired, then read-only proof and dry-run contract |

## XAU status

The old downloader could lose a full month when one hourly request failed. It now writes daily atomic chunks, records empty-market and quarantined days, enforces disk/quarantine guards, and leaves the sealed holdout unread. At this checkpoint progress is 6/1734 calendar days: 2021-01-04 and 2021-01-06 are persisted, 2021-01-07 is in progress, weekend days are recorded as empty, and 2021-01-01 plus a partially downloaded 2021-01-05 are quarantined after provider failures. Promotion remains fail-closed until gaps are repaired.

## Research system and project inventory

- Strategy inventory: 90 strategy files; 20 live entry handlers; 22 enable flags; five unreferenced archive candidates.
- Adapter census: 31 signal-emitting, 29 zero-signal, 29 no-class, one crashing, two not probed. Liveness is not edge.
- Idea intake: four complete cards accepted, zero rejected: ATT1 stall exit, sloped break/retest V2, XAU session sweep/retest, and strategy-specific causal universe selection.
- External model execution was deliberately not given fresh private/live telemetry. A sanitized audit packet was produced instead.
- The onboard AI context now labels `live_positions.json` as a runner-local export instead of silently treating it as direct broker truth. Until a fresh signed GET snapshot is included, position authority is `NOT_CONFIRMED` even when heartbeat and runner counts agree.
- Public L2/tape collection is fresh and order-incapable. The parent BTC/ETH collector no longer recursively owns nested ONDO/micro collector roots, eliminating the observed background-compression race. It was safely restarted; at 2026-08-14T13:42:51Z both books were synced, frame lag was 6 ms, storage had about 78 GiB free, and no compression warning or current-process coverage alert was present. Historical ONDO/micro coverage alerts remain evidence and are not erased by this restart.
- The isolated server collector was separately found blocked since 2026-08-12 because 2,147,714,319 tape bytes exceeded its 2 GiB cap. The guard was not overridden. Four completed partitions were compressed by the existing verify-by-decompression/SHA path, reducing tape usage to 280,871,694 bytes. A no-network preflight passed with config SHA `1d8943b7968054d6cde41ccf42b08031df91102aa40b450d1e21c56176b24810`; at 2026-08-14T13:49:48Z the collector was again `collecting`, both books were synced, and frame lag was 2 ms.

Sources:

- `reports/evidence/STRATEGY_INVENTORY_20260814.json`
- `reports/evidence/RESEARCH_IDEA_BATCH_20260814.jsonl`
- `reports/evidence/SLOPED_BREAK_RETEST_V2_PREHOLDOUT_20260814.json`
- `reports/evidence/SLOPED_BREAK_RETEST_V2_FUNNEL_20260814.json`
- `reports/evidence/SERVER_L2_COLLECTOR_RECOVERY_20260814.json`
- `reports/EXTERNAL_AUDIT_PACKET_20260814.md`

### Sloped break/retest V2 failure localization

The frozen V2 contract did not fail because the scanner found no sloped breaks. Across eight majors and the pre-holdout window it evaluated 27,792 completed 4h states and found 131 qualifying breaks. Only 35 first retests held the broken line (26.7% of breaks); 20 then produced a later 15m BOS signal. The portfolio accepted 18 trades after overlap/slot handling. The dominant funnel loss is therefore break -> valid first retest, while the accepted trades still had negative expectancy. A V3 is justified only as one preregistered retest-definition challenger; loosening every threshold or choosing favorable symbols would be a new selection-bias error.

## Timing, conditionally

- ATT1 0.10 → 0.25: earliest after 15 more clean closes. At the first five-close cadence this is roughly 1–3 weeks, but the market controls signal frequency. It is a gate, not a calendar promise.
- Second crypto leg: engineering/shadow candidate in days; a tiny capital canary is more honestly 3–6 weeks if one candidate survives causal replay and forward evidence.
- Three to four crypto money legs: 6–12 weeks is an aggressive conditional range, not a guarantee.
- Alpaca new selection: exact replay and GTC protection are engineering work measured in days; capital expansion requires forward evidence measured in weeks.
- XAU/FX first honest numbers: after materialization and a frozen replay. Data is now moving, but not yet complete enough to quote a return.

## Next session, exact order

1. Validate the ATT1 stall mechanism on a disjoint non-sealed window or prospective shadow; keep TP2 2.5R and live runner unchanged.
2. Design one Sloped Break/Retest V3 retest-definition challenger from the measured 131 -> 35 funnel; do not parameter-sweep the rejected V2 or select winners by symbol.
3. Repair Bounce1 routing telemetry and IVB1 `other` diagnostics; do not loosen filters before cause counts are trustworthy.
4. Complete exact spot/perp mapping and funding-cost replay for the 74 currently hedgeable pairs, while PIT reconstruction continues.
5. Package the isolated Alpaca GTC protection deployment and verify it outside the live directory; do not re-enable selection until overnight persistence is proven.
6. Feed a fresh signed-GET broker snapshot into the onboard AI state compositor; runner-local position state is now explicitly labelled and cannot impersonate broker truth.
7. Keep XAU and public L2/tape collection running behind disk and heartbeat guards.

## Things explicitly not authorized by this checkpoint

- no manual close or order mutation;
- no risk increase;
- no Bitget capital movement or trading;
- no live promotion of Inplay, XSEC, funding, sloped V2, or XAU;
- no destructive cleanup of the dirty worktree;
- no conclusion that a strategy has edge merely because the adapter emits signals.
