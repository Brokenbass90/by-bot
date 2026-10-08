# KITY source contract and Binance account intake — October 8

**Terminal: BLOCKED_DATA. Current Binance key: BLOCKED_EXECUTION.**
The frozen basket and research remain unchanged. A source-compatibility contract
is defined below; it is not installed and creates no accepted signal seal.
Authenticated account fields are now captured, rather than marked universally
unknown. They do not establish money readiness. No sender or KITY credentials
were added. The adjacent JSON binds actual receipts, source pins and diagnostics.

## Source compatibility V1

The pinned research ref remains `d6ed8126c041969de0bc6191e39fefe4a1272d5b`.
Its forward `instrumenty()` (lines56–65) applies the literal TRADING filter.
Current assessor lines119–130 instead includes an already-onboard relevant row
and rejects it if non-TRADING. GAIB's original cutoff row is PENDING_TRADING
with past onboardDate and empty OI. The frozen selector excludes it before OI.

The minimal bounded correction, before any later implementation:

1. Keep the complete original census capture and raw SHA; never project, rewrite
   or replace the cutoff response. Validate symbol uniqueness across all relevant
   rows, listing identity/dates, body shape, source clock and current2s cutoff.
2. Admit TRADING rows through the unchanged exact OI/history gates. Positively
   known PENDING_TRADING at the captured cutoff is explicitly ineligible, with
   a retained exclusion receipt binding symbol/status/reason/census hash. This
   first compatibility version does not silently accept other status strings.
   Missing, unknown, conflicting or malformed status remains BLOCKED_DATA.
3. Every eligible row must have one valid exact23:55 OI response. The retained
   GAIB response remains preserved, hash/query/identity/clock validated and pinned
   as evidence for a noncandidate; its absence from ranking is explicit. Its
   receive time must be at/after cutoff and at/before evaluation and participates
   in overall source-availability accounting. Extra OI
   keys without a classified census row block. No fallback23:50 or ranking over
   successful requests alone. All candidate completeness failures still block.
4. Top50, feature/history logic, tie order, n//10, sides, seven-day hold and12bps
   research cost remain unchanged. All251 existing signal vectors and actual
   eight-leg diagnostic parity must remain exact after implementation. Unknown
   status, duplicate excluded identity, TRADING with missing OI, unrelated OI,
   altered raw/hash, stale census and late availability are refusal cases.
5. Provenance authority stays independent. Our raw census/OI/candle captures bind
   an independent reconstructed signal. Claude's original files and hashes are
   immutable external comparison evidence; no added field may claim that Claude
   retained our raw responses. A new sidecar may pin the original external signal
   hash, exact source-code/ref identity and independent source-manifest hashes,
   but is labelled **created now**. Missing external raw evidence remains a
   separate strict comparison blocker; it is not backfilled from our archive.
6. Publication must validate the **complete** receipt/envelope against existing
   2MiB limits. Original compact input2087545bytes has only9607bytes headroom.
   Offline canonical serialization of just mandatory source_bundle/source_pins
   inside receipt.signal is **2134621bytes**, already37469 above2097152, before
   other signal/receipt/seal fields. This is a size lower bound, not an accepted
   receipt: the existing inline format is infeasible for this complete capture.
   No truncation, larger limit, silent split/alternate schema or accepted seal is
   authorized by this document. Oversize becomes an explicit publication blocker.
If a detached-source schema is needed, it requires its own reviewed amendment.
7. A prospective seal must measure actual creation before October9 00:00UTC;
   replay never supplies an earlier sealing time. Failed or late acceptance stays
   diagnostic, not an admitted October8 entry. No historical judge rerun.

This formalizes the source question without changing canonical assessor behavior
in this cycle. It is not GAIB acceptance, strict forward PASS or proof of edge.

## Actual existing Binance account — 08:43:49–08:43:52 UTC

One bounded SSH operation issued24 allowlisted GETs: two clocks, key restrictions,
account/config, position risk, normal/algo open orders, eight symbol configs and
eight commission rates. All returned HTTP200; raw replies are retained privately
with hashes/timestamps. No POST, order test, mode/leverage write or remote write.

| Field | Captured truth |
|---|---|
| Current key | enableReading=true, **enableFutures=false**; no withdrawal/transfer permissions |
| Position mode | dualSidePosition=true (Hedge) |
| Account collateral mode | multiAssetsMargin=true |
| All8 exact legs | marginType=CROSSED, leverage2, isAutoAddMargin=false |
| Actual per-leg commission | maker0.000200, taker0.000500 on all8 |
| Current positions / normal orders / algo orders | separate GET replies empty |
| Aggregate available/wallet/margin | 11.70137565; multi-assets USD-account representation |
| Nonzero wallet asset | **BNFCR11.70137565** |
| USDT wallet/available | **0 / 0** |

This corrects the preceding receipt's unqualified "11.70USDT" wording.
Do not sum asset `availableBalance` rows: in multi-assets they are alternative
representations of available credit, not independent cash pots. The source is
consistent with [Binance Futures Credits](https://www.binance.com/en/support/faq/detail/0e857c392a2d47cebde0af762d9255ae),
whose margin/PnL/fees use BNFCR. No conversion, transfer, top-up, leverage increase
or automatic key permission change is proposed here. API enableFutures=false is
an exact blocker for the current key even though account canTrade=true.

GET definitions: [Binance account/config/commission](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/account)
and [key permissions](https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/account#get-api-key-permission).
The accountConfig's updateTime is a configuration timestamp, not cash finality.
Empty snapshots prove no observed exposure at these reads, not exclusive ownership.

## Sizing, fees and funding: facts versus policy

Use only the previously captured eight-leg diagnostic quantities, not a new entry
plan. Their43.73889gross/common-reference5.5412 are bound to morning public books;
those books are stale for any present dispatch. Equal-notional flooring leaves
per-leg residuals that require an explicit approved tolerance, never padding.

At captured2× leverage, gross/2 gives **21.869445** illustrative initial margin
before fees/reserves. This simplified arithmetic is not the authenticated venue
margin/credit/haircut requirement, and exceeds the captured11.70137565 aggregate
credit. Round-trip taker/taker at unchanged notionals is10bps/0.04373889; true exit
prices/notionals are unknown. Maker execution, fee discounts and future rates are
not promised. Actual costs do not replace the historical12bps benchmark.

Funding histories/current intervals/caps are retained for all8 legs. The JSON
reports observed seven-day series diagnostics using actual captured settlement
marks and the proposed constant quantities, plus a separate current-cap scenario.
Neither is a future hard bound or an adopted reserve policy: marks/notionals and
settlement intervals can change, histories are finite, and future liabilities and
BNFCR accounting need a reviewed policy. No reserve is lowered to make cash fit.

Owner per-leg/portfolio/daily capital and loss caps, approved equal-weight rounding
tolerance, funded collateral contract, and source-bound funding/liability policy
remain **unset**, not inferred from $100/$1000 examples or ATT1. Historical~24%
basket DD and severe short tail are not guaranteed loss bounds. Neutral weights
do not establish zero risk. No new directional short stop or early strategy exit.

## Partial basket, ownership, restart, finality and kill contract

These are required rules for a later runner, **not installed account integration**:

- One exclusive KITY entry owner must reserve the complete basket's approved
  resources once. Identity binds week/ref/accepted signal/account/venue/quantities/
  fee/funding/cap/profile pins. Duplicate/restart cannot create a second intent.
- All2k exact legs and current metadata must pass one common2s assessment before
  preparation; recheck before dispatch. One missing leg means no entry.
- Rejection, partial basket, timeout or uncertain acknowledgement blocks further
  entry. Query the exact owned client/order IDs and fills before any retry; never
  treat no local event as no broker order. Unknown fill/position state stays
  RECOVERY_BLOCKED with retained reservation and liability, not silently flat.
- Unwind only confirmed owned filled quantities, with separate deterministic exit
  IDs and explicit account positionSide/close semantics. The actual Hedge mode
  requires positionSide and forbids a reduceOnly parameter; closePosition is
  whole-side conditional closing, not proof of a quantity-scoped owned exit.
  [Official trade contract](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade).
  It cannot inherit an unvalidated one-way reduce-only adapter. No whole-account
  flatten, foreign position close, symbol replacement or speculative duplicate.
- Terminal requires all owned orders terminal/no late-fill ambiguity, exact owned
  positions reconciled, fees/funding/cash/liabilities reconciled with a source
  cutoff and later finality check. Flat snapshots alone do not release reservations.
- Kill first disables new entries; management/reconciliation continues. Scoped
  unwind authority, absolute limits, observation/acknowledgement timeouts and
  rollback to entry-disabled state must be fixed and validated before money GO.
  Current pure synthetic replay is not authenticated lifecycle validation.

Exact sender/timeout/kill policy and account ownership approval are still absent;
this dossier cannot claim READY_FOR_CANARY_DOSSIER, actual unwind/finality PASS or
money authority. Current strict source/caps/collateral contract are BLOCKED_DATA;
the current Binance key and the missing exact Bybit leg are BLOCKED_EXECUTION.

One bounded6-astra/high review accepted the source proposal for later orders-OFF
implementation, validated all24 GET replies and the funding arithmetic/544 sampled
seven-day windows. Counterexamples above retain excluded-first duplicate detection,
excluded OI availability/pins, and Hedge close-side/foreign-ownership guards.
This is neither implementation acceptance nor money GO. The primary separately
verified the full-publication size lower bound; no serializer limit was changed.

## Next handoff

First implement/test the reviewed source compatibility within orders-OFF scope,
preserving original artifacts and251-vector parity; measure full publication size
before any timely seal. Then close the selected-account/collateral/caps and
validated ownership/unwind/finality contract. No new money or source bypass.

At16:25Cyprus the existing Alpaca heartbeat preempts: fresh quote/cash/finality/
fees/minimum/ownership → one conditional XOM PAPER at16:30–16:35. This cycle did
not query Alpaca, alter HALT/heartbeat or retry its old window. October9 DAYrearm
remains required if held overnight. ATT1/ETS/Claude/OS2 remain untouched.

Operator source copies are under `reports/evidence/kity_execution_intake_20261008`;
raw signed replies remain local/private at
`.private/kity_intake_20261008/binance_account_raw_archive.json`, SHA
`fdc2f6e4f148d0dd4c03daa21f2e2a0c448f510e690e0a3419756f140ae8a2b4`.
Source copies are evidence, not installed workers or a repeat-capture instruction.
Offline arithmetic checks all eight raw funding series, window/sign/quantity
facts and source hashes; no product test rerun is claimed because product code
is unchanged. Canonical checkpoint and entrypoints carry the current blockers.
