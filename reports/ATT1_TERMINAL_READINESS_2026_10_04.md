# ATT1 terminal readiness — October4, orders OFF

Terminal result: **BLOCKED_DATA**. Authenticated broker collection08:47:58UTC;
public/observer snapshot08:56:42UTC. Continue662d322 and completed Tasks1–4.
Machine receipt: `ATT1_TERMINAL_READINESS_2026_10_04.json`.

## Delivered

The existing inert command-budget binder now optionally accepts exact captured
instrument/fee sources. It re-runs frozen admission, retains its quantity and
matches instrument filters/hash, account fingerprint, actual fees and the full
14-day funding reserve against OLD evidence. Daily spent debits reduce available
budget. Infeasible quantities reject before reservation. Source attachment is
forwarded by `prepare_new_att1_entry` and replayed during budget revalidation;
restart returns lookup-only and cannot reprice or issue another command.
The legacy synthetic interface remains inert; an actual dossier must explicitly
attach sources. No money runner, production binding or route DB was installed.

Explicit reviewed rule `FLAT_IDX0_HISTORICAL_PLUS_ZERO_TEMPLATE_V1` accepts only
two complete one-row pages, bothidx0/size0/empty side: historical Normal row plus
exact uninitialized template. It requires fresh same-account flat broker evidence
and preserves both row/page hashes and discarded_rows=0. The strict default is
unchanged. Six actual sources pass this explicit rule; SUI passes the ordinary
validator. **LINK1/2/0 still rejects.** This is a declared compatibility
interpretation, not venue permission to discard rows or a mode guarantee.
Bybit documents0/1/2 mode identities and pagination; no switch-mode request was
made. [Position API](https://bybit-exchange.github.io/docs/v5/position).

## Finite OLD cash/finality inventory

**50 known identities now have broker terminal cash coverage**:47 submitted
identities plus3 earlier entry-filled identities already in the same pinned
current event file. Five close records without entry IDs map uniquely to the
previously reconciled terminal broker quantities/time. No local label changed.

The new collection covered38 known missing entry-to-close windows and the3
additional known windows. Each exact-joins execution and cash IDs/order/side/
quantity/fees, checks cash arithmetic, funding settlements and a unique size
chain from the known entry to0. Three recent lifecycles and the six previously
reconciled islands were verified from their preserved sources. Initial19 windows
missed entries because local fill-observation clocks lagged broker fills; only
those windows were recollected from saved submit clocks. Original captures and
initial rejection details remain preserved. No broad archive search was opened.

Known identity terminal/cost coverage is complete within that source scope.
This is not all-history completeness or net-edge evidence. Mixed ADA islands
and older attribution remain contaminated; early LONG records do not establish
the present frozen SHORT strategy. ADA86 ML label remainsOPEN; no DB write.
Decoded authenticated HTTPS envelopes and source hashes are private; this new
collector does not claim byte-for-byte original HTTP-body preservation.

Current UTC-day executions/cash0 through08:46:48.394UTC with60s publication lag.
That finite frontier is not complete coverage to the later current clock and
has not been promoted into a validated actual cash/handoff declaration.

## Risk and exact quantity economics

Fresh dated OLD reference uses signed wallet equity, runtime risk0.44%, ATT1
multiplier0.10, breaker1/not blocked, volatility multiplier1, selected-account
trade settings and deployed source/config hashes. Reference risk ceiling:
**0.4493950071116USDT**. This is a sizing comparison; OLD entry authority is
retired. DraftR0.4/D0.8/N100 remains unapproved and uninstalled.

The last public ETH START has entry2690.93 and frozen rounded stop2728.78.
Under draftR0.4, unchanged sizing floors toqty0, below the venue0.01 minimum.
At minimumqty0.01 the adverse-risk reserve is0.41635USDT; captured14-day funding
limits plus two taker fees require3.937356662USDT in the conditional stop-price
scenario. The observed publicqty0.02 also cannot fit that draft. These are dated
price/quantity diagnostics of an archived signal, not a fresh actionable signal
or historical authenticated broker truth. No upward sizing/cap/hold/cost change.
The scenario still cannot guarantee future fee/funding limits or gap prices.
[Instrument fields](https://bybit-exchange.github.io/docs/v5/market/instrument).

## Runtime and verification

MainPID1648585 remains retired; authenticated account-wide positions0/orders0
before+after. Core/retirement guard hashes unchanged. PublicPID1584802 and its
driver/coordinator/strategy hashes unchanged, broker/ordercalls0,2s gate/one
journal unchanged. Cohort7sessions/39records/3filled simulations/2gaps/**0clean**;
ETH simulated0.02 held/protected without incident. It is not a broker position.

Cold observer **71/96**, current=true at08:56:42UTC, first completionnull.
Earliest96th close11:00UTC/14:00Cyprus remains conditional on uninterrupted bars.
The existing observer pins its first completion automatically; no restart,
backdating, synthetic bars or modification of an old receipt occurred.

- **223 targeted localPASS /223 isolated VPSPASS**, Python3.12.26 new tests.
  Initial VPS attempts exposed3 missing AST test seams, then1 missing helper;
  the final guarded seven-node AST fixture passes all223. No executable money
  monolith, credential file or production state was copied into the candidate.
- One bounded6-astra/high review:83PASS/no must-fix; targeted forwarding check
 14PASS closes the end-to-end inert preparation limitation.5.6-luna/medium
 performed mechanical source inventory. Actual rollout model/effort verified.
- Full suite **3490PASS/57FAIL**, exact previous57 nodeids, no added failures.
  All failed names/logSHA are in the JSON receipt. The full suite is not green.
  Foreign allowlistSHA preserved and remains untracked/unstaged.

## Next gate and rollback

1. Preserve first valid96/96 raw capture/clock when emitted. Use fresh broker,
   retirement and a contemporaneous cash/source packet; never backdate drain.
2. Resolve LINK against fixedidx0 binding via authoritative evidence or a
   separately approved broker-mode/handoff decision. No mode write or silent
   LINK removal is authorized in this cycle. Another blind archive scan will
   not resolve a current broker-mode conflict.
3. Map the published cash frontier and exact cost attachment into one actual
   inert handoff/budget declaration; retain any unresolved coverage as BLOCKED.
   Re-run exact quantity rejection on future fresh signals; draft caps are not
   a promise that every frozen signal can trade on this account.
4. Money still requires2–3 clean prospective filled terminals/net-R, fresh
   exclusive dossier/OLD absolute-risk comparison and separate owner GO.

Rollback is candidate-only: preserve OLD retirement/management and existing
public observer/collector. Never restore OLD entries automatically. Alpaca/AI,
Claude/Factory, sealed research and foreign diff were not changed or freshly
re-evaluated. Alpaca Oct5 re-armP0 remains its separate existing gate.
