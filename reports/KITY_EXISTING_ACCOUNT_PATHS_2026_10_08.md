# KITY existing account paths — October 8, 08:03 UTC

**Terminal: BLOCKED_DATA. Bybit exact basket remains BLOCKED_EXECUTION.**
One bounded read-only SSH operation checked the established Binance/Bitget
account readers. It made two signed GETs, no order calls, no remote writes,
credential additions, deployments or service restarts. The adjacent JSON retains
the redacted operator receipt; it is not a complete raw account response or a
money-admission packet. Alpaca was not queried in this cycle.

## What the existing paths establish

| Path | Fresh evidence | What remains unproved |
|---|---|---|
| Binance USDT-M | Existing key pair; GET `/fapi/v2/account` returned HTTP200 at08:03:18.638UTC. Wallet/margin/available11.70137565USDT, feeTier0, account canTrade=true. | Key trade scope, selected-account ownership/eligibility, actual per-symbol fees, margin/mode/leverage, caps, funding liability, partial-basket unwind, restart/finality and ownerGO. |
| Bitget USDT futures | Existing key triple; GET `/api/v2/mix/account/accounts?productType=USDT-FUTURES` returned HTTP200/code00000 at08:03:18.953UTC. Available/equity0. | KITY supports only Binance/Bybit. Existing Bitget adapter is public normalization only, without approved KITY execution/account lifecycle or exact-basket feasibility. |
| Bybit | Morning complete public census lacks exact `币安人生USDT`; seven of eight legs exist. | No exact approved mapping. Neither drop/substitution nor a partial cross-venue basket is allowed. No new Bybit account read was made. |

The Binance reply contains1848 position **rows**, not proof of1848 held positions;
active quantities/open orders were not captured here. `canTrade` is an account
flag, not verification of this API key's trading permissions. The inventory's
Bybit/MEXC key absence applies only to the named fields in `/root/by-bot/.env`,
not every configuration or the existing Bybit trading account.

The prior source-only Binance snapshot supports all eight exact diagnostic legs.
Its **43.73889USDT gross** is before fees/funding/buffers. It is neither an
authenticated capital requirement nor permission to use leverage. The11.70
available balance alone cannot establish feasibility; do not request a top-up,
raise risk or infer a funded canary from this comparison.

## Result and smallest next work

No already-approved complete KITY money path is demonstrated. Binance is the
existing account worth assessing next because its exact symbols are available;
switching the assessment venue need not replace a frozen signal leg. Do not
connect credentials or an order sender to the isolated KITY candidate.

Strict signal intake still rejects the526-row cutoff census with
`PIT_STATUS_AMBIGUOUS` on GAIB. The explicit frozen-research TRADING projection
has diagnostic parity only. Non-TRADING source compatibility, external raw/ref
provenance and accepted packet/seal bounds need a reviewed engineering contract;
no exclusion or accepted seal is created by this account inventory. Then an
orders-OFF selected-account dossier can bind actual fees/mode/cash/caps/funding,
equal-notional rounding, ownership, unwind/finality and rollback. Money remains
behind a complete dossier and separate ownerGO.

Prepared question for Claude when available, **not sent and not run**:
If the owner retains Bybit as the venue, preregister a separate execution-policy
challenger with point-in-time venue eligibility fixed before ranking, against
unchanged KITY as its benchmark. Measure lost opportunities, basket differences
and net economics using independent evidence. Do not retrospectively remove the
missing October8 leg or adopt the challenger as the current frozen strategy.
This question is unnecessary for an exact Binance basket if its own gates pass.

## Alpaca and OS2 clarification

Today16:30–16:35Cyprus remains a **conditional** one-XOM PAPER window. Morning
pendingfees0.02/cash-finality=false and stale IEX quote are not cleared by this
cycle. Fresh quote, cash/finality/fees/minimum, slot and exclusive-writer checks
must pass before any reservation or PAPER dispatch. If held overnight, actual
DAY expiry/re-arm is first observable October9 opening; no same-evening claim of
that gate. Current LIVE HALT remains in force.

OS2 already wires decision bus and edge diagnostics in its **local fixture**
bridge. Actual-source parity/B3 policy acceptance and separate policyGO remain;
it is not a LIVE regime authority. No OS2/Claude/ATT1/ETS work occurred here.

Sources: `MONEY_MORNING_KITY_ALPACA_2026_10_08.md/JSON`, current
`bot/kity_m3_orders_off.py`, `scripts/check_exchange_readonly_keys.py`,
`scripts/exchange_account_status.py`, `KITY_M3_VENUE_INVENTORY_2026_10_05.json`,
`BITGET_CASHCARRY_PUBLIC_ADAPTER_V1_2026_07_16.md` and
`OS2_SHADOW_BRIDGE_DELIVERY_2026_10_07.md`. Product code/strategy, sealed sources,
Alpaca runtime and native PAPER heartbeat were untouched. No product test rerun
is claimed for this evidence/documentation-only change.
