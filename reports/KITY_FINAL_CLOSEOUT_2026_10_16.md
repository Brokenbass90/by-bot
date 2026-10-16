# KITY final execution closeout — October 16

CURRENT: **KITY_10_OF_10_READY — ENGINEERING / ORDERS_OFF**.
This is readiness for ONE new owner-authorized execution test, **not an actual
10/10 fill, strategy PASS, standing trading authority or C1–C3 evidence**.
The previous9/10 policy98ae…8f3ee remains SPENT/FAILED_SAFE_FLAT/net−0.38780112.

## Actual evidence and narrow correction

Only the actual9/10 run supplied replay latency inputs. In
[evidence/kity_closeout_20261016](evidence/kity_closeout_20261016/),
`actual_stage_timings.json` records every actual preflight, POST, fill and native
confirmation. `actual_timing_profile.json` retains648 GET durations before
unwind, nine POST acknowledgements and intent→wire delays.

| Actual9/10 stage | From GO |
| --- | ---: |
| Durable claim | 2.624s |
| Capture/compilation saved | 10.929s |
| Owner authorization completed | 11.349s |
| First entry intent | 13.237s |
| Ninth entry intent | 56.104s |
| Ninth native confirmation | 59.613s |
| Unwind | 60.930s |

Before initial unwind714 GETs included181 reads of known native-stop IDs and116
cursor continuations. The former per-order warming repeatedly reread stops from
previous legs. Maximum actual adjacent entry interval6.705s gives an estimated
tenth intent62.809s; that is extrapolation, **not an actual SPCX execution**.

`research_lab/kity_micro_account_readbacks_v2.py` replaces those duplicate owned
lookups with four complete account groups **within one ENTERING cycle**: open
and recent-closed realtime, history and executions since first durable entry.
Actual raw pages and actual request parameters stay intact. Consumer selection
requires the exact durable ID/link and symbol. Wrong symbol/category/method/
endpoint/parameters or incomplete pagination blocks. Unknown IDs use the original
exact query. Positions, native discovery and executable books keep fresh calls;
there is no cross-cycle cache. Sender, Full stops, unwind, unknown-send and
recovery remain unchanged. Non-ENTERING phases use the existing read path.

Official source contracts:
[realtime open/recent-closed orders](https://bybit-exchange.github.io/docs/v5/order/open-order),
[order history](https://bybit-exchange.github.io/docs/v5/order/order-list),
[execution list](https://bybit-exchange.github.io/docs/v5/order/execution).
All cursors are consumed. Closed realtime cache is not treated as sole truth;
history and executions remain separate actual sources.

Actual authenticated GET-only comparison of27 historical owned orders matched
81/81 endpoint selections. Latest strict-origin consumer replayed the same raw
pages OFFLINE:81/81,0 mismatch. Actual pages:1 open,2 closed,2 history,2 execution.
A proposed risk→entry book reuse was rejected because it hit the existing
COMMON_2S_BASKET_UNKNOWN. It is absent from this kit; CTS gates are unchanged.

## Authorized70s version and verification

Human explicitly replied **“Да, 70 секунд для одной новой policy”**. This changes
only the total GO→new-entry deadline for ONE closeout policy. It is not MONEY GO.
Old V1 policies retain60s and their original identity. New schema
`KITY_EXECUTION_MICRO_POST_GO_POLICY_V2_70S` requires the separate closeout scope,
ACCOUNT_READBACK_V2 profile and exact70000ms config. Arbitrary windows and
changing a V1 policy's window by rehashing are rejected. The new runtime refuses
a second PREPARE. All spent claims, selections, policies and journals stay spent.

**138 targeted tests PASS.** The same actual-latency replay includes real
account-instrument checks, cursor-tail pages, initial11.349s and191ms custody
call allowance. It does not charge pacing twice: actual request→receive timing
already includes it. Results:

| Replay | Tenth POST start | All native confirmations | Result |
| --- | ---: | ---: | --- |
| Same inputs,60s | — | — | Expected deadline refusal |
| Authorized70s | 63.130s | 67.407s | Ten entries/protection, restart,30min exit/accounting/flat PASS |

Margins are6.870s for the last entry and2.593s for all native confirmations.
**This deterministic replay is not a network worst-case bound or actual fills.**
A real delay may still cause safe unwind. Future endpoint samples reuse observed
latencies, and the unobserved tenth acknowledgement uses the maximum observed.
Old optimistic180/300ms fixtures remain historical tests, not this readiness's
timing basis. The prior full suite was5116PASS/60 existingFAIL, NOT_GREEN; no
broad suite rerun was used to justify this narrow closeout.

## Physical installation and fresh GET rehearsal

Separate20-file app `/opt/bybot-research/kity-micro-owner-20261015/app-closeout-v2`;
new namespace `runtime/post-go-closeout-20261016`. Existing KITY service was
replaced only after fresh flat/no-orders; original818853 lock retained. No
second writer. Flat/open0 proved before, under quiescent lock and after install.
Old kits and88 pinned predecessor/wire artifacts plus all old-namespace bytes
are intact.33 old financial send barriers; **0 new broker writes**. Oldbybot/web
remain inhibited; ATT1/LIQ/cron/Alpaca/Claude were not changed.

- Config: `ba23a26fa81e8440882a9bccca2ecbf643853ac82742c1ac111afb6eee5eee9b`.
- Unit: `99d091e10cde0103fa6177f5700b6dd2e18fc7f5ae4dd5522d432561a3973290`.
- Writer PID2311456, NRestarts0, HEALTHY/ORDERS_OFF/NO_ACTIVE_PLAN.
- Installed fresh capture6.989s,10/10 GET-only entry preflights PASS in9.178s,
  including SPCX; account flat/open0. Reference gross174.526790USDT.
- Actual selection/journal/owner GO absent. Full policy and sanitized receipts
  live in the evidence directory; raw account sources remain private.

The rehearsal prices are **not approved future prices**. A personal GO causes
exactly one new capture and quantities/limits from that capture. Fresh CTS≤2s,
margin/permissions/account eligibility/caps/collar/ownership remain mandatory.

## One owner packet

Policy:
`3ca9ca2321a704f8f8a4ade2156d519dbace1401e86fc5f679a913896f74c5c5`.
Expires **October16 21:00UTC = October17 00:00Cyprus**, no date transfer.

Unchanged: frozen5long/5short basket; quantity rule/rounding shortfall≤20.3%;
gross≤215USDT;±0.5% from one post-GO capture; immediate all-in15USDT exit trigger
with accepted gap/slippage/exchange-refusal overshoot; native Full stops;
30min from first durable entry intent; one attempt/no averaging/scaling/reentry;
execution-only journal excluded from strategy/C1–C3 evidence.70s is the sole
owner-approved timing amendment. Final flat/accounting still required.

STATIC blockers: **none found in this bounded closeout**. FRESH_ONLY: the existing
post-GO account/quote/CTS/margin/eligibility/caps/protection checks. OWNER_GO:
**not yet given for this policy**. Agent must not execute or schedule financial
authority, including after chat approval. The human personally chooses to run:

```bash
bash /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/kity_closeout_20261016/owner-micro-once.sh
```

Launcher is syntax-checked, not executed. Local create-exclusive claim and
runtime one-selection semantics prevent blind repeat. On COMMAND_QUEUED, observe
read-only through protected basket/owned exit/accounting or failed-safe-flat.
Never reset/retry a spent launcher or produce a replacement policy automatically.
After expiry, remain ORDERS_OFF. No extra approval/report/rehearsal is inserted
between the personal queued GO and actual runtime transport.

After actual10/10 success only: design standing bounded authorization without
granted money/research/scaling authority. Elder HEDGE_V1 ordersOFF and Reporting
remain next; they did not preempt this closeout.
