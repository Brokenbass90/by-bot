# ATT1 — gap, funding and cash diagnosis, October 4

Continue `555e9e1`. Terminal diagnostic result **ROOT_CAUSE_FOUND+FIX_PROPOSAL**;
actual packet remains **BLOCKED_DATA / NEW ORDERS OFF**. Four preserved gaps
were reproduced using the exact captured deployed driver and original journals.
This delivery changes documentation and analysis only. Frozen strategy, risk,
hold, quantity rules, 2s threshold, coordinator and single journal remain unchanged.

The first real **96/96 quarantine** is now preserved and independently replayed.
Fresh authenticated selected-account snapshot **13:06:37 UTC**: flat/no open orders
before and after, OLD entry retirement active, main PID1648585/public PID1584802,
NRestarts0, core/guard/public source hashes unchanged. Public is now
**10 sessions / 68 records / 5 filled simulations / 4 gaps / 0 clean terminals**.
ADA simulated102 is held and protected102, no incident at capture, final net-Rnull.
It is public simulation; no broker fill or clean terminal is credited in advance.

## Four gaps: different triggers, bounded causal conclusions

| Symbol | Preserved trigger and measured evidence | Verdict |
|---|---|---|
| SEI | CTS age2485ms at receipt;2380ms at response server time;105ms server-to-local delta | Source age already over2s; source publication/cache/quiet-book cause NOT_PROVEN |
| SUI | CTS age2249ms at receipt;2168ms at response server time;81ms server-to-local delta | Same stale-source trigger; underlying cause NOT_PROVEN |
| ETH | Current book GET completed2442ms after prior received clock:1087ms tail+50ms next-request delay+1305ms request wall | Aggregate observation budget exceeded; pair/management/publish tail and HTTP variation measured |
| ETC | GET completed within1680ms of prior received clock; continuity marked at2399ms,719ms after GET completion | Receive/consume frontier conflation in sequential management; CTS freshness of that consumed snapshot NOT_PROVEN |

ETC timing source stores `public_get.finished_ms`, not the returned `rx` field.
Its receive-gap upper bound is1680ms and receive-to-mark lower bound719ms.
For both ETH and ETC, nested `request_io` and `public_get` completion timestamps
coincide and bracket returnedrx at that same millisecond, assuming no backwards
local wall-clock step within those nested operations. ETH's2442ms book-ready
frontier is captured; the exact receive inference and assumption remain explicit.
No restart, changed driver/coordinator/strategy source, or source replacement was
observed. The4 original RECOVERY_GAP receipts remain dirty and immutable.

The frozen implementation calls `_mark_observation_gap(session,self.clock())`
before consuming a prefetched observation. It also validates receipt and consumed
CTS age independently. ETC therefore demonstrates a misclassified continuity
frontier; removing the premature label alone would not prove timely management
or a fresh CTS snapshot. HTTP timings show that the October1 paired-fetch fix
can still exceed the aggregate budget; the evidence does not support blaming
only the1-second polling sleep or declaring all4 gaps unavoidable venue outages.
[Bybit distinguishes matching-engine CTS from server timestamp](https://bybit-exchange.github.io/docs/v5/market/orderbook).

## Proposed next local candidate — not installed

1. Distinguish immutable received-time continuity, CTS freshness at receipt/use,
   and processing deadline. Keep every2s gate. A delayed risk-management decision
   remains fail-closed with an accurate reason; it must not become clean by relabeling.
2. Prioritize held-book acquisition independently of sequential manage/publish
   tails, using bounded prefetch within current public concurrency/rate limits.
   Workers only fetch; decisions, exits and journal writing stay sequential.
   No unbounded buffer, hidden stale backlog, repaired old gaps, or copied fresh clocks.
   Overflow, missing ordering, restart and real continuity gaps fail closed.
3. For SEI/SUI, one bounded public REST/WS comparison must capture CTS, sequence,
   server/receive/use clocks and quiet-book behaviour. This is transport diagnosis,
   not authority to substitute outerts forCTS or install a new transport blindly.
4. Replay these exact captured triggers and synthetic contention/partial-exit/
   starvation/restart cases before public zero-risk deployment. Measure deadline
   feasibility under actual service quotas; local tests cannot guarantee HTTP tails.

## Funding study — historical dominance, policy unchanged

Frozen method was written before new data inspection in
`docs/superpowers/plans/2026-10-04-att1-gap-policy-diagnosis.md`. Public Bybit funding
history covers2023-01-01 through2026-10-04T00:00:00Z **exclusive**, or contract launch
if later.167 GET pages,46.804s collection; exact response wire bytes, hashes,
parameters and local receive clocks preserved privately. All retCode0.
32569 raw rows:8 endpoint-inclusive boundary rows explicitly excluded;32561 retained.
No duplicates or interior holes on the published8h grid. Seven symbols have
4116 settlements; SUI3749. SUI's launch-to-first19.74h segment is unverified/censored;
its initial14d windows are excluded. No unpublished-event or historical interval
metadata completeness guarantee is invented.
[Official funding-history endpoint](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate).

32225 overlapping14d windows at **constant unit stop-notional**; each `(end-14d,end]`
contains42 observed settlements. Adverse-only debit sums negative funding without
credit offset. Signed net debit is reported separately; negative values remain
funding income and never reduce the adverse reserve. p50/p95/p99, maxima and all
worst-window timestamps are in JSON. Overlapping windows are not independent.
Fixed2×/5× stresses were selected before outcomes. Supplementary43-consecutive
settlement maxima cover the current phase-count difference and leave the all8
5× comparison unchanged.

| Symbol | Worst observed14d adverse | Fixed2× stress | Fixed5× stress | Current43-limit envelope | Envelope/worst |
|---|---:|---:|---:|---:|---:|
| ADAUSDT | 0.636935% | 1.273870% | 3.184675% | 24.940000% | 39.16× |
| BTCUSDT | 0.355414% | 0.710828% | 1.777070% | 14.319000% | 40.29× |
| DOTUSDT | 1.698703% | 3.397406% | 8.493515% | 14.190000% | 8.35× |
| ETHUSDT | 0.275407% | 0.550814% | 1.377035% | 14.319000% | 51.99× |
| LINKUSDT | 0.865537% | 1.731074% | 4.327685% | 28.380000% | 32.79× |
| LTCUSDT | 0.284674% | 0.569348% | 1.423370% | 28.380000% | 99.69× |
| SOLUSDT | 3.909301% | 7.818602% | 19.546505% | 21.500000% | 5.50× |
| SUIUSDT | 0.588743% | 1.177486% | 2.943715% | 43.000000% | 73.04× |

All percentages apply to the same fixed notional; this is funding only, not total
fees/slippage or strategyPnL. Eight current lower funding limits and480-minute
intervals are bound to the dated09:29 instrument capture. The ex-ante criterion
passes all8: **POLICY_OVERCONSERVATIVE relative to observed history**. SOL is the
closest margin:5.50× actual worst,5.34× supplementary43-event worst.

This result justifies a separately preregistered reserve candidate, not immediate
policy reduction or a hard future-capital bound. Rates/intervals/limits and mark
notional can change; entry-time stop notional is not proved a pathwise price bound.
A future candidate must include adverse funding stress, changing notional,
funding/execution protection, liquidation risk and unresolved-reserve handling.
The current43-limit policy, R0.40/D0.80/N100 draft,14d hold and fees remain unchanged;
prior8/8 budgetREJECT persists. ETH/SUI archived frozen quantities remain0 even
if funding reserve is later revised. No upward min-quantity rescue is allowed.

## Cash frontier — honest provisional cutoff, finality still blocked

The prior74041ms delta was **our chosen60000ms cutoff plus14041ms collectiontime**.
It was not a measured Bybit publication lag. Earlier wording calling that a60s
publication lag is corrected here; the original captures remain preserved.

Two signed complete-pagination GETs used exactly the same economic cutoff
**10:07:20.342 UTC**. Their cash-query receipt clocks were10:07:20.716 and
10:07:41.388UTC:20672ms apart. Both have0 executions/0 cash, flat before+after.
The second pass is a causal overlap check; stable empty pages cannot establish
absence of unpublished fees/funding/fills or estimate latency. API identity and
credentials are not published; decoded signed envelopes are private0600, with
sourceSHA, params and clocks. No original signed wire-byte preservation claim.
[Bybit warns transaction-log data may be delayed, without a fixed74s SLA](https://bybit-exchange.github.io/docs/v5/account/transaction-log).

Proposed contract separates `economic_cutoff_ms`, `requested_end_ms`, `received_ms`,
`reconciled_asof_ms`, publication-finality status and unresolved command reserves.
Repeat fixed-cutoff and overlapping later queries, retain both hashes, reconcile
known fill/order/position/cash identities, apply late/corrected records idempotently,
and hold unknown reserves. Complete pagination means currently published rows,
not finality of all economic events. Entry retirement/flatness is a precondition,
not proof of all-history cash completeness. The existing validator is unchanged;
**CASH_CURRENT_FRONTIER remains BLOCKED**, handoff/drain is not manufactured.
Implementation of a new contract requires a separate reviewed plan before money.

## First real quarantine and verification

The observer automatically pinned completion **11:00:00UTC** and observed it at
**11:01:55.581UTC**. Exact capture SHA:
`b57706acf068d1eb16f167d951a9e013fb11f8a6feab9d87032ce0d4f0311cf1`;
observation SHA`c2a22f7ad0d8b15c04bc2bcd138f38eb4657072d12710bb324488c4b78732a55`.
Original bytes were copied without reset/update. All8 original M5 envelopes and
all pure quarantine fields/common-bar hashes reproduce96/96. This is the original
11:01 observation, not a freshly advanced clock; actual_handoff_ready remainsfalse.

- 4 frozen-driver trigger replays PASS;4sessions/48records byte-identical against
 captured heartbeat, stateSHA`9832b9f7a04c3d7c9ab31bc6f38e5d9e7462c6764fa70605a2adf0d4101c7b83`.
 Exact deployed30-file closure used. Initial local-profile replay correctly rejected
 differing implementation hashes; no header/hash bypass used. Source bytes unchanged.
- 54 current local targeted tests PASS,20.63s. Runtime code unchanged; full suite
 not rerun this docs/analysis cycle. Prior555e9e1 full3501PASS/57sameFAIL is historical,
 and the suite remains not green. No current VPS test-run claim.
- Independent exact-Fraction check of32225windows: all8 adverse/net maxima,
 signed medians and5× comparison PASS. Raw page and dated-limit bindings verified.
 Cash SHA/fixed cutoff/empty pagination and96 raw-source replay PASS.
- One bounded verified6-astra/high review found net-credit clipping and timing-label
 precision issues; both corrected and primary rechecked. Reviewer hit usage limit
 before final signoff; **independent final review incomplete**, no expensive retry.
 Mechanical funding worker actual5.6-luna/medium verified from rollout metadata.
- Initial private cash-check assertion expected integer params; signed client
 normalizes them to strings. Exact integer-value comparison passed without altering
 capture. No source failure was suppressed. Foreign allowlist SHA remains
 `add587f1bd7059c2c706f1f7c604e36c2fb7b36b258b127e01fcd2101d3f19a1`, unstaged.

Private reproducible sources/scripts/hashes: `.private/att1_gap_policy_20261004/`.
Local commands: `python3 .../analyze_funding.py`, `.venv/bin/python .../replay_gaps.py`;
those read saved data only. Complete receipt:
`ATT1_GAP_FUNDING_CASH_DIAGNOSIS_2026_10_04.json`.
No productioncode/service restart, brokerwrite, modewrite, routeDB change, paidAI
call, Claude checkout/message or research holdout consumption. Known50 OLD history
stays closed. LINK remains the prior terminal conflict; no further blind mode hunt.

## Next bounded order

Close the local observation candidate and transport diagnostic first; reserve and
cash need separate reviewed proposals with unchanged money authority. Then actual
packet,2–3 clean prospective filled terminals/net-R, fresh exclusive dossier and
separate ownerGO. Completed96 alone grants no money. Claude's KITY→LONG→RANGE queue
remains last verified; this cycle does not claim new research progress. Alpaca
October5 re-arm is the next operationalP0; Alpaca/AI were not changed or rechecked.
