# KITY — capacity root cause and future micro readiness, 17 October 2026

**18:23UTC update:** one PUBLIC-only capacity probe now requires247.189680>215.
See [new delivery/evidence](LIQ_RESEARCH_DELIVERY_2026_10_17.md). No new financial
attempt/policy or account/CTS SEND readiness; old attempt remainsSPENT.
The229.584550 below is the exact original failed financial capture.

**NO_SEND / ONE ATTEMPT SPENT / CAPACITY_BLOCKED. Actual 10/10 execution remains
NOT PROVEN. No repeated micro, policy renewal or broker mutation was performed.**
Code `469a9eddf27fd40d38f71ba2db783522fb38b25c` is local, not deployed to the
existing financial writer.

## Actual personal attempt

Owner queued command `1792247810399920355` at14:36:50UTC. The unchanged writer
claimed the one-shot policy, captured once and returned
`INTENT_REFERENCE_PLAN_BLOCKED`. Replaying its exact retained raw bytes shows
one plan blocker: `GROSS_CAP_EXCEEDED`. Capture took6462ms; maximum common-engine
age upper bound was492ms versus2000ms, clock offset[-80,84]ms. The freshness
component passed; the full plan did not.

The exact raw capture SHA256 is
`f9e6562812ae9a652880a78d5d989537ec8cff826a64667dc895142872ba3ba2`.
Authenticated raw account captures remain ignored/private. Public regression
fixtures retain only the actual market books/instrument quantity geometry,
plus original/derived hashes; they are not authenticated account readiness.

Final fully paginated independent GET readback at17:47:25UTC: positions0,
openorders0, executions0, orderhistory0 and account transactions0 in the selected
linear-USDT scope since this GO. Historical wire records34, new batch namespace0.
This closes NO_SEND evidence; it does not count as execution PASS.
The final17:55UTC preservation sample retains original lease inode818853,
PID2479217, source23/guard155 hashes, ORDERS_OFF/no active plan. The human-selected
config has `money_go=true`, while its one-shot policy is already spent. Never
infer an unused permission from that config flag or reset/disarm/retry it during
this diagnosis. No new policy or money GO exists.

## Same-capture calculation

The original sizing algorithm first finds the smallest common per-leg target
meeting venue minima and the frozen20.3% floor-rounding tolerance. Quantities
are `floor(target / (price × step)) × step`; executable-depth and limit notionals
then face the unchanged215USDT aggregate cap. No frozen weights, quantities,
exchange metadata or account conditions were relaxed.

| Saved capture UTC | Venue floor | First rounding-feasible target | Reference gross | Planned-limit gross | Verdict |
|---|---:|---:|---:|---:|---|
|08:25|19.94940|21.6588|207.953940|207.954130|capacity fits; freshness component observed PASS|
|09:10|20.37970|21.6654|207.668760|207.668760|capacity fits; GRASS2862ms makes source stale|
|14:36 personal attempt|23.88530|23.88530|229.584550|229.584120|freshness component PASS; gross cap FAIL|

**Root cause:** BTW minimum quantity and step are10. Its buy price rose from
2.03797 to2.38853 (+17.20%); its minimum tradable notional rose from20.37970 to
23.88530. The earlier rounding frontier was set by BNB at21.6654; BTW's new
minimum exceeded it and raised the common target, producing jumps in quantities
of other legs. This is market/lot geometry, not a hidden order or a metadata
change. Rounding and full-depth replay match the original frozen compiler.

| Leg / side | Price 09:10 → attempt | Step / minQty / minNotional | Qty 09:10 → attempt | Attempt depth gross | Attempt shortfall |
|---|---|---|---|---|---|
| BTWUSDT Buy | 2.03797 → 2.38853 | 10 / 10 / 5 | 10 → 10 | 23.88530 | 0.000000% |
| XAUUSDT Buy | 4171.75 → 4172.33 | 0.001 / 0.001 / 5 | 0.005 → 0.005 | 20.86165 | 12.659041% |
| LTCUSDT Buy | 59.45 → 59.35 | 0.1 / 0.1 / 5 | 0.3 → 0.4 | 23.740 | 0.608324% |
| VVVUSDT Buy | 23.2990 → 22.7750 | 0.01 / 0.01 / 5 | 0.92 → 1.04 | 23.687820 | 0.834404% |
| BNBUSDT Buy | 722.18 → 721.99 | 0.01 / 0.01 / 5 | 0.03 → 0.03 | 21.6597 | 9.317865% |
| XAUTUSDT Sell | 4157.78 → 4159.46 | 0.001 / 0.001 / 5 | 0.005 → 0.005 | 20.79730 | 12.928454% |
| XPLUSDT Sell | 0.08209 → 0.08082 | 1 / 1 / 5 | 263 → 295 | 23.83964 | 0.181702% |
| XAGUSDT Sell | 57.22 → 57.13 | 0.001 / 0.001 / 5 | 0.378 → 0.418 | 23.88034 | 0.020766% |
| GRASSUSDT Sell | 0.63830 → 0.62840 | 1 / 1 / 5 | 33 → 38 | 23.87920 | 0.025539% |
| SPCXUSDT Sell | 145.88 → 145.96 | 0.01 / 0.01 / 5 | 0.14 → 0.16 | 23.3536 | 2.226055% |

All exact decimals, original minQty/minNotional, old/new quantities and rounding
fractions are in [three complete replays](evidence/trading_os_dynamic_kity_20261017/kity_capacity_replays.json).

Under that exact common-target floor rule, **minimum required gross is
229.584550USDT**: the maximum of reference and planned-limit gross. It exceeds
215 by14.584550. Larger targets cannot decrease floor quantities or their
executable-depth gross. Arbitrary unequal resizing, dropping a leg or raising
the cap would change the authorized contract and was not done. The saved collar
upper envelope is 230.721330USDT; neither figure is a
proposal or guarantee for a future price capture.

## Delivered code and regression

- Transport-free `assess_saved_capture` verifies the raw SHA, reuses the original
  preflight and reproduces the exact plan. `assess_market_geometry` exposes
  every leg, minimum frontier and cap excess before a financial decision.
- `--future-owner-proposal` automatically applies feasibility before producing
  an inert decision packet. The actual capture yields
  `CAPACITY_BLOCKED_NO_GO_PACKET`, no owner command, no new policy, no authority.
  Unknown or inconsistent capacity evidence is rejected.
- NO_SEND diagnostics now retain a fixed safe reason code, bounded gross/cap and
  source hashes. They do not serialize arbitrary remote errors or raw account
  evidence. The one-claim, no-retry and sender behavior is unchanged.
-79 focused KITY tests pass. Real saved-input regressions reproduce both207.668760
  and229.584550; tests reject cap changes, hash mismatch, authority renewal and
  unknown/false capacity evidence. Service/post-GO tests remain green.

Default command has no network/book/money effects:

```sh
.venv/bin/python scripts/check_kity_micro_feasibility_v1.py
```

Explicit saved-capture mode accepts `--capture PATH --capture-sha256 SHA`, with
optional `--future-owner-proposal`; CAPACITY_BLOCKED exits2 intentionally. There
is no broker client, financial apply flag, key lookup or launcher in this CLI.

## Next micro, without repeating the preparation error

1. Use this pre-money verifier in the next preparation/dossier on a bounded
   fresh source capture. Do not repeatedly query until an attractive verdict.
   If the unchanged basket still cannot fit215, return CAPACITY_BLOCKED and stop.
2. Only a feasible fresh dossier can advance to a separate new dated owner
   decision. Original custody/flat-account/source/one-writer checks remain.
   Today's spent policy is never reused. No cap increase is assumed or requested
   by this packet.
3. After a separate exact approval, prepare a new reviewed inert personal packet
   within the unchanged215/50bps/commonCTS2s/60s/15trigger/30min/one-attempt scope.
   Agent never runs the financial command. The owner initiates it personally.
4. The one post-GO capture and all final source/cap/execution gates still apply:
   prices can move after a pre-money PASS. A later NO_SEND spends that attempt;
   preparation cannot guarantee dispatch or fill.
5. Independent broker readback must establish all10 fills, protection, bounded
   lifecycle/terminal fills/costs and no residual positions/orders before10/10
   execution PASS can be claimed. Net strategy profit remains a separate result.

There is no market-calendar wait for KITY, but there is also no currently valid
new attempt. [Inert future packet](evidence/trading_os_dynamic_kity_20261017/kity_future_owner_proposal.json)
and [NO_SEND broker closure](evidence/trading_os_dynamic_kity_20261017/kity_broker_no_send.json)
are ready for inspection. Original LIVE service was not redeployed or restarted.
