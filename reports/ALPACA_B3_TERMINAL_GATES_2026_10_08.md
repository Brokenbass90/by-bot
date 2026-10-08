# October 8 — terminal money/engineering gates

**Alpaca: BLOCKED_DATA_CURRENT_OPENING, no PAPER order. KITY October8:
BLOCKED_EXECUTION_CURRENT_SIGNAL. Frozen B3: B3_FAIL.**

This is the terminal record for this bounded cycle. Source closure does not claim
PAPER_EXECUTION_PASS or READY_FOR_LIVE_GO. Current LIVE remains flat and HALTED.

## Alpaca: old cash closed, new lifecycle still pending

Authenticated opening snapshot at **13:33:40.957 UTC**: selected LIVE cash,
equity and non-marginable buying power **$496.12**, pending regulatory/accrued
fees **$0**, positions/open orders **0**. Six known fills reconcile to exact gross
$8.754976679662; five published pooled fees total **$0.05**, exact net
$8.704976679662. Broker cash increased **$8.70**, matching cent-rounded net.
The former pending $0.02 is not another fee deduction. AMD was a native stop;
CRWD/META were actual MARKET emergency exits, not relabelled stop fills.
No pooled fee is arbitrarily allocated to a leg. This closes the known-old
cash/finality inventory, not a universal broker fee-publication guarantee.

Source61/23/21 manifests and both replacement books match existing pins;
one ranking/three inherited slots/**zero intents/exits**. LIVE binding/profile/
wrapper/HALT and production PIDs1648585/1623208/1584802, NRestarts0, unchanged
at that snapshot. Existing PAPER has five legacy positions, XOM flat and no
orders. Legacy exclusion SHA8171cd5e…122e3f remains. No runtime deployment,
service restart, account/mode change or broker order occurred in this cycle.

The original 13:30–13:35UTC opening elapsed without preparation/reservation or
PAPER entry. Do not enter later, backdate the owner's tariff answer or reuse this
quote as tomorrow's input. Captured IEX XOM bid158.36/ask169 has raw timestamp
13:33:31.216707017UTC; receive13:33:37.746UTC. SIP403. IEX is not NBBO; observed
width is not a newly approved spread filter. Current code correctly protects
actual fill price minus the frozen, cent-rounded plan risk distance.

The owner directly confirmed standard personal commission-free Alpaca. Archived
[official October1 brokerage schedule](https://files.alpaca.markets/disclosures/library/BrokFeeSched.pdf)
confirms SEC sell-value rate.0000206, TAF0, CAT.000003 per executed NMS share,
with each fee type aggregated daily per account and rounded upward to cents.
The PDF was hashed and independently extracted with pdftotext. The
[official BUY minimum](https://alpaca.markets/support/can-we-submit-orders-smaller-than-1-usd-in-notional-value)
is $1; [Trading API documentation](https://docs.alpaca.markets/us/docs/fractional-trading)
supports fractional DAY LIMIT/STOP and nine decimal quantity precision.
Source contract was independently reviewed **APPROVE_WITH_LIMITATIONS**.
1e-9 is the representable unit, not a fabricated asset-specific API minimum.
Actual fresh asset/account/quantity validity and PAPER acceptance remain gates.

`reports/evidence/alpaca_b3_gate_closure_20261008/fee_reserve_input.py` is a
source-only calculator, with no broker/network/order authority. On a fresh,
capped entry-quantity ceiling it maps commission0 and cent-ceiling CAT plus
actual unresolved liabilities into the **existing** snapshot liability reserve.
That reserve must reduce spendable funding before preparation: regression proves
cash100 -> funding99.99 + reserve.01. Quantity ceiling, contract hash and actual
liability inputs must be bound anew; the dated illustration is not a plan.
Account/day aggregation and possible different execution days remain explicit;
future exit fees use actual fills/prices, not an invented hard loss bound.

**Next action:** October9 13:30–13:35UTC /16:30–16:35Cyprus, fresh preflight and
at most one authorized XOM PAPER lifecycle using the unchanged sealed ranking,
inherited slot ordering, $487.42/.70 caps and original shared lock. Check all
writers, exact PAPER identity, legacy exclusions, cash/liabilities/fees, raw
quote time, asset, earnings, concentration and exact quantity before reservation.
Unknown/conflicting inputs => terminal BLOCKED, not repeated retries. Then
entry/full native protection/readback/restart, scoped partial/unwind/finality.
If first entered October9 and held overnight, actual DAY re-arm is first due
**October12**, not October9. This is an operational gate, not extra days for
statistical trade count. Preserve LIVE HALT until a complete dossier and separate
owner GO. Never rebuy CRWD/META or adopt/flatten legacy PAPER holdings.

The existing two-opening heartbeat prompt was corrected. Its original Oct8/9
schedule and count were not extended. Delete after the second check/terminal;
no automatic new retries or new recurring job was created.

## KITY: current signal closed

October8 is **BLOCKED_EXECUTION_CURRENT_SIGNAL**: exact 币安人生USDT is absent
on both preferred Bybit and Bitget. Binance has all8 but its current key/account
is not ready and owner deprioritizes it. Stop venue shopping for this signal;
no missing-leg substitution/drop. Prior read-only venue reports are retained,
not repeated. Strict GAIB/provenance/seal source blockers remain independently.
Future venue eligibility before ranking is a separate Claude research challenger,
not a reinterpretation of the current frozen strategy.

## B3: one frozen attempt, FAIL

Research cf904086, repaired A1 checkpoint881dde0. All22 execution/support/input
files match both refs and the sibling; all137 upstream 15m data pins match.
Frozen fixture tests **17 PASS**. No prior B3 receipt existed. An exclusive,
fsynced execution-spent claim was written before the judge. Run exactly once in
an isolated byte-identical copy with inherited broker/provider variables cleared,
no research code/config/criteria changes, no new trade regeneration.

| Frozen arm | Sum R | Judge drawdown R |
|---|---:|---:|
| A always on | +224.925 | 98.951 |
| B leg filter | -68.562 | 79.326 |
| C regime routed | -67.327 | 91.561 |

C fails to beat A; C>=B holds **2/4**, required>=3/4. Judge status is **B3_FAIL**,
regardless of process exit0. ConfigSHA9b65e28c…4f2256f, rawreceipt
SHA4f36a1c0…8a87e; execution13:53:01–13:53:04UTC. Raw logs, receipt, input
manifest and one-shot claim are retained under this cycle's evidence directory.
No SEALED_V2 run/repair/rescue/repetition. Judge R and entry-ordered closed-trade
drawdown are not actual dollars or mark-to-market portfolio risk. The FAIL is
terminal under the frozen criteria and gives this policy no forward/LIVE authority.

Existing OS2 SHADOW_WIRING_PASS remains an engineering result. Actual-source
adapter/parity can continue orders-OFF without a money policy. Policy promotion/
whole-system policy PAPER is blocked by B3_FAIL; do not install regime overrides.
Claude resumes research Sunday; no message or research-branch edit was made.

## Verification and boundaries

**114 targeted Alpaca PASS**, including three new counterexamples: wide captured
quote with improved fill/full fill-relative protection; accepted entry with lost
response/restart without second buy; commission0 still deducting CAT before
sizing. No production execution source changed. Frozen B3 fixtures17PASS.
One gpt-6-astra/high financial review plus targeted fee-resolution followup:
APPROVE_WITH_LIMITATIONS. Worker and gpt-5.6-luna/medium inventory model/effort
were verified from actual rollout turn_context, not self-report.

ATT1/ETS deadlines, gates, production and sealed evidence unchanged. No new
strategy, AI, UI, broad architecture, cleanup or Claude message. Foreign
`configs/allowlist_change_log.json` add587f1…f19a1 untouched and unstaged.
Full suite was not repeated for source evidence/three targeted regressions.

Minimal backlog: Alpaca actual PAPER -> exact LIVE GO; OS2 source/parity only;
Claude's separate future KITY venue-aware challenger handoff. No current-signal
rescue or new research policy is approved by this report.
