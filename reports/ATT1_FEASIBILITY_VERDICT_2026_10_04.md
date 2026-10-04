# ATT1 actual feasibility verdict — October4, orders OFF

Terminal **BLOCKED_DATA**. Continue e33e253; completed Tasks1–4 and the50 known
OLD cash/finality inventory remain closed. No OLD historical window queried.
Authenticated selected-account GET snapshot09:29:30UTC; public09:35:45UTC.
Machine receipt: `ATT1_FEASIBILITY_VERDICT_2026_10_04.json`.

## Result that changes the next step

**All eight admitted symbols fail frozen sizing budget at the captured bids**
under draftR0.40/D0.80/N100 and the unchanged14-day policy. This is conditional
reserve-policy infeasibility, not a strategy profitability or future-price verdict.
The draft remains unapproved/uninstalled. Current dated signed equity1021.3349235,
OLD reference risk ceiling0.44938736634; OLD entry authority is retired, not usable
permission. R0.40 remains within that comparison ceiling. No risk/cap/hold/cost
change or upward size correction was made.

The table uses captured bids and the **nearest possible tick stop**, purely an
optimistic minimum-lot diagnostic. It is **NOT_A_SIGNAL** and does not substitute
for the frozen strategy stop. Qmin rounds UP only for this diagnostic; actual
frozen admission continues to floor and reject without resizing.

| Symbol | Captured bid | Valid Qmin | Optimistic stop-risk | 14d reserve | Optimistic total | Every-branch lower bound | Frozen sizing |
|---|---:|---:|---:|---:|---:|---:|---|
| ADAUSDT | 0.2448 | 21 | 0.00231 | 1.28829645 | 1.29060645 | 1.4877704 | REJECT |
| BTCUSDT | 85241.6 | 0.001 | 0.00011 | 12.299524893 | 12.299634893 | 7.2145 | REJECT |
| DOTUSDT | 1.1932 | 4.2 | 0.000462 | 0.71669598 | 0.71715798 | 0.91663592 | REJECT |
| ETHUSDT | 2702.2 | 0.01 | 0.00011 | 3.899018809 | 3.899128809 | 4.09900438 | REJECT |
| LINKUSDT | 14.097 | 0.4 | 0.00044 | 1.60660808 | 1.60704808 | 1.80649412 | REJECT |
| LTCUSDT | 70.36 | 0.1 | 0.0011 | 2.0048413 | 2.0059413 | 2.2045564 | REJECT |
| SOLUSDT | 121.24 | 0.1 | 0.0011 | 2.6202125 | 2.6213125 | 2.8199964 | REJECT |
| SUIUSDT | 1.176 | 10 | 0.0011 | 5.0701671 | 5.0712671 | 5.269736 | REJECT |

Risk/reserve/total/bounds are USDT; Qmin is in base units. Reserve includes two actual taker fees and43 adverse
funding settlements at captured lower limits, valued at the original stop;
hold20160minutes/4032M5 and adverse-risk expansion0.10 stay frozen.
Captured intervals/limits/fee tier/price-envelope persistence remain assumptions,
not guaranteed future ceilings; gaps and changed venue conditions can exceed them.

DOT's minimum-lot optimistic total0.71715798 fitsD0.80. **That quantity is not what
frozen risk-driven sizing selects**. A positive risk-limited floor retains more
thanR/2 risk, and every admitted quantity meets venue minimum notional. Its
minimum combined bound is0.91663592. Notional-limited sizes retain more thanN/2
stop notional; market-limit sizes use the exact floored market maximum. Taking
the minimum of these three bounds covers every frozen branch, including ties.
All eight bounds exceedD0.80 at their respective captured entry price.
This is why a manual minimum-quantity workaround would change the strategy.

Exact unchanged public START intents exist for ETH and SUI in this epoch; both
size to0 atR0.40 with frozen stop rounding/sizing. All other rows explicitly lack
an actual frozen signal. Current dated costs applied to archived intents are not
historical authenticated broker truth or fresh broker admission. Frequency of
future feasible signals and net edge are not measured by this matrix.

## LINK and contemporaneous cash/handoff

Fresh complete signed LINK pages again contain idx1/2 followed by an idx0
uninitialized template. Flat0/0 does not establish one-way mode; all three rows
and page/source hashes remain preserved. Terminal **BLOCKED_DATA: LINK_MODE_CONFLICT**.
No row dropped, symbol removed, hedge route inferred or broker mode written.
Six duplicatedidx0 sources pass the existing explicit retained-template rule;
SUI passes strict ordinary validation. These input-subset results do not authorize
money. [Bybit position identities/pagination](https://bybit-exchange.github.io/docs/v5/position).

The contemporaneous declaration records0executions/0cash only through
**09:28:15.085UTC**. Final broker observation09:29:29.126UTC leaves74041ms without
published current coverage. The existing contract requirescoverage_end==observed_ms
and fresh complete cash. Settingcomplete=true, advancing the frontier, backdating
a drain, or weakening freshness would manufacture evidence. Declaration status
is **BLOCKED_DATA: CASH_CURRENT_FRONTIER**, handoff_validated=false/drained_at=null.
Known50 inventory remains scoped complete; all-history completeness is unproven.
Raw decoded GET envelopes are private0600; public receipt carries hashes and safe
projections. No claim of original wire-byte preservation or published UID/key.

## Cold observation and public cohort

Observer **78/96**, current=true at09:35:45UTC, first completionnull. Existing
observer/timer continues and pins the first valid96/96 raw capture automatically.
Earliest96th close remains11:00UTC/14:00Cyprus conditional on continuity. This
bounded cycle does not wait idle, create bars, reset the epoch or claim completion.
When it emits96, preserve its original capture/hash/first clock and use fresh
broker/cash/handoff evidence. Maturity alone does not grant money authority.

Public now **9sessions/63records/4filled simulations/4gaps/0clean terminals**,
0simulated held positions. **ETH and ETC acquired RECOVERY_GAP** at09:01:31/32UTC;
both receipts retain reason“public polling continuity gap”. ETH is no longer a
candidate clean terminal. Event/journal hashes are preserved. Exact causal latency
is not proved by that generic reason; next work must diagnose the specific gap
source before another timing change. No reset, cleaned receipt or collector fix
was made. Driver/coordinator/strategy hashes, 2s gate and one journal unchanged.

## Verification and delivery boundaries

- RED11 expected missing-feature failures, GREEN11PASS. Local234targetedPASS;
  isolated target-Python VPS234PASS. Both machines produce the same pure matrix
  SHA59ece0b405617883d895364fb95ad44f552ebc1bcfd1ed564e5c4cf5b9063ac0.
- One bounded6-astra/high financial review: no must-fix,11PASS and217 additional
  exact-Fraction cases. Mechanical5.6-luna/medium research inventory. Actual
  rollout model/effort verified, not inferred from requested settings.
- Full **3501PASS/57FAIL**, exact previous57 nodeids, no added/removed failures.
  Names and log hash in machine receipt. Full suite is not green.
- Initial collector attempt refused a non-allowlisted ticker; public HTTPS GET
  used separately, signed allowlist unchanged. Second capture placed flat evidence
  after the declared symbol clock and was correctly rejected; both captures stay
  preserved. Final snapshot uses genuine before-source ordering and revalidates.
  Initial VPS test manifest counted support fixtures as target tests; corrected
  explicit11-file command passed. No failure suppressed or reported as PASS.
- MainPID1648585 remains process-pinned retired; signed selectedaccountpositions0/
  orders0 before+after; publicPID1584802/core/guard unchanged. Isolated candidates
  only; no production code install, routeDB change, service restart, broker write
  or paidAI call. Foreign allowlist originalSHA preserved/untracked/unstaged.

## Exact remaining gates / next bounded work

1. Existing observer's first96 receipt, with honest cash/drain provenance.
2. LINK requires authoritative compatible mode evidence or a separately reviewed
   account/mode decision. This cycle terminatesBLOCKED; no repeated blind GET hunt.
3. A source-backed cash-frontier/finality design is required; lagged empty pages
   alone cannot make a current declaration complete.
4. Current draft economics needs a separate reviewed policy/budget decision.
   This delivery changes nothing. Waiting for more signals cannot repair the
   measured reserve-policy mismatch at these prices. No money-ready promise.
5. Diagnose the newly preserved ETH/ETC public continuity gaps in a bounded replay/
   timing cycle, preservefrozen2s/strategy/risk/journal. Clean gate remains2–3
   prospective filled terminals with terminalnet-R, fresh exclusive dossier and
   **separate owner GO**. No strategy net-edge proof is claimed.

## LONG / RANGE research queue

Actual originresearch/fabrika-v1 verified at0505f9d564cf042f2a160a33a458aa7d28c76d1a;
current published KARTA updateOctober3. KITY isprereg/data pending, not terminal.
No accepted LONG/RANGE sleeve was found. Registry is a published claim, not a
fresh unpublished Claude progress check. No judges/holdouts executed, sibling
checkout changed, research merged or Claude message sent.

After KITYterminal and its bounded rescue, give Claude's one Factory slot one
independent **crypto LONG** mechanism; after itsPASS/KILL, one **RANGE/mean-reversion**.
Preregister before outcomes: causal/PIT inputs, exact costs and venue minimums,
baseline/random control, walk-forward/sealed holdout, objectivePASS/KILL and bounded
rescue. Screen actual quantity/cost feasibility early. Do not revive negativeBull/
SBR1 families or mirrorATT1 direction as evidence; mechanism independence must be
shown. Frequency alone is notnetedge. Elder/regime remains a separate auxiliary
experiment, no silentLIVE filter. Queue is written; these experiments are not
claimed running while KITYoccupies the slot.
