# PUMP4 — actual-source/account component, 23 October 2026

**Later23Oct NET safety override:** the old personal NET launcher mentioned below
is now TECHNICAL HOLD; use the [R4 owner-review result](MONEY_REVIEW_NET_RECOVERY_2026_10_23.md).
PUMP source evidence here remains valid. No actual exit or LIVE activation occurred.

**COMPONENT_PASS_TINY_BLOCKED. Code `f5a517ff013b2c0299ee8e67241293d48a24d283`.**
151 tests locally and the **same151** on VPS, no failures/errors/skips. Network
was denied; VPS additionally used `unshare --net`. 83 packaged files,37 imported
candidate modules,0 checkout fallbacks. Material:
`c8fb58823efd7a8cb5ff11b1777d69b8a183b5d56e3448f67a39595b8cc7f110`.
[Receipt](evidence/pump4_sources_20261023/receipt.json),
[local](evidence/pump4_sources_20261023/local-acceptance.json),
[VPS](evidence/pump4_sources_20261023/vps-acceptance.json).

## DONE / TESTED

- Existing GET-only transport, frozen producer/intake, durable lifecycle,
  immutable publication and account lease reused. No new trading framework.
- Frozen137 list pinned to `935880315e2450e03e1df0beb43a8598a9e5440d86036a5469e436f76f6bd71a`.
  275 public GETs:136 instruments each have1000 historical seed hours, latest
  closed H1 and actual next-open price. Forming-bar close never feeds producer.
  HFT unavailable, retained explicitly in137 with QA; no substitute/universe rewrite.
  Contract§4 allows unavailable-data skips; this is not a new global veto.
- All136 passed actual-capture→existing producer→restart/duplicate parity.
  **0 signals** on the checked06:00UTC bootstrap boundary. Captured about29min
  after that boundary: historical initialization only, **0 prospective credits**,
  no executable entry. Restart parity is engineering evidence, not economic edge.
- Selected existing Bybit account:9 account-reader GETs (8 authenticated +1 public quote),
  1458ms bracket at06:40:06–06:40:08UTC. Flat, no open orders, REGULAR_MARGIN,
  no reported borrowing.942 actual fee rows; rates differ by instrument:
  2.75/5.5/11bps per side. No fixed blanket5.5bps assumption.
- Bound every private capture to expected reader identity; verify raw JSON/hash,
  endpoint/query/cursor chain, complete history windows, timestamps, known CIDs,
  fills, actual fees, native LastPrice stop and signed funding amounts. Same-symbol
  foreign executions/orders fail closed. Metadata and active risk are distinct.
- Actual `/account/info` lacks a response-level server timestamp: updatedTime is
  configuration-change time. Only this metadata endpoint uses the authenticated
  request/receive bracket; market/account-risk records retain API-time checks.
  [Official response semantics](https://bybit-exchange.github.io/docs/v5/account/account-info).
- Normalizer→existing lifecycle/restart tested with API-shaped fixtures. Duplicate
  fills deduplicated by exact identity; conflicting duplicates rejected. Native
  stop/partial/funding/lost-response tests retained. Empty activities never mean
  final zero costs; `costs_complete=False` remains explicit.
- Proposed sizing uses exact frozen stop, quantity step and40/60 representability,
  actual per-symbol fee/funding fields, cash reserve and current quote. It is a
  diagnostic, **not executable admission or a signed permit**. Static-stop price
  quantization remains exact-or-reject, floor/ceil candidates are not selected.

[Actual source receipt](evidence/pump4_sources_20261023/public-bootstrap.json),
[136 restart checks](evidence/pump4_sources_20261023/source-intake-restart.json),
[account validation](evidence/pump4_sources_20261023/account-readonly-validation.json).
Raw account evidence/credentials remain private. Response hashes prove recorded
byte integrity, not a broker signature or atomic/exhaustive market observation.

## Real sizing limits discovered

At proposed gross30USDT,124 symbols satisfy **lot/minimum40/60 constraints only**;
12 exceed this amount and HFT is unavailable. For example BTC minimum408.91150,
ETH120.1835, SOL52.1850USDT at the dated diagnostic quote. This is not a request
for increased capital, a new allowlist, or proof that124 trades meet R1/stop/costs.

Funding can dominate tiny R. Across the dated instruments, a constant30USDT
notional held168h at the **current published rate cap** produces a scenario as
high as50.40USDT. It is neither a forecast nor a guaranteed bound: price, rates,
caps and intervals may change. V1 hold168H is unchanged. A future financial risk
policy must account for funding/fees/slippage and gap loss; a1USDT stop-distance
proposal does not cap total realized loss at1USDT.
[Per-symbol diagnostics](evidence/pump4_sources_20261023/instrument-lot-diagnostic.json).

## Independent review

One bounded fresh `gpt-6-astra/high` review, runtime turn_context verified.
P2 reproduced: current quote90/reference100/stop104 could hide3.5USDT distance
risk under a nominal1USDT quantity. Fixed denominator uses larger reference/adverse
current-price stop distance; wrong-side quote rejected, stop unchanged. Original
case now CAPACITY_BLOCKED at exchange minimum5; minimum3 allowsqty.05/risk.7045.
RED→GREEN regressions; targeted follow-up28PASS, no remaining reviewed finding.
[Review receipt](evidence/pump4_sources_20261023/review.json).

## NET / Monthly today

Fresh NET GET at06:20UTC/09:20Cyprus: original position open; **no accepted active
DAY stop before regular session**, yesterday's stop expired. Manager waiting
regular session. This is a dated premarket gap, not confirmed protection today.
Regular opening13:30UTC/16:30Cyprus requires a fresh accepted-stop receipt.
[Sanitized GET](evidence/pump4_sources_20261023/net-morning.json).

Exact personal NET exit already approved:23Oct14:00–14:05UTC/17:00–17:05Cyprus,
market actual remainder<=0.325167779 regardlessPnL. No repeated GO required.
Human-only launcher unchanged (`bd437caf…28ca03`); agent did not execute/schedule
it. [Approved packet](ALPACA_MONTHLY_EARLY_NET_EXIT_2026_10_22.md). Initiation once;
uncertain result→GET reconciliation, no retry/resetclaim. Owned recovery may
finish after the5min initiation window. After actual human launch: prove original
NET flat/terminal orders, cost/cash seal, then separately authorized retirement/
Monthly activation. Do not remove protection while exposure/uncertainty remains.

All53 accepted Monthly source hashes and9VPS financial pins unchanged. No personal
GOfile/claim, broker write, unit/risk/NET/SHOP change. Private foreign allowlist
untouched. Monthly financial241 acceptance remains separate; this cycle did not
rerun or inflate it. First frozen Monthly rotation2November remains conditional
on handoff, exact authority/config, future source and account truth; CASH possible.

## REMAINING / next exact code gate

1. Integrate account-wide financial owner/send-once gateway and durable day/week/
   drawdown latches with existing global custody. Isolated observation adapter is
   implemented; **selected financial owner is not**. No native real stop was sent.
2. Finish fully source-bound fee/funding/risk admission under an exact TINY policy.
   50allocation/30gross/R1/max1/day2/week3/DD6 remain **unapproved proposals**.
3. If exact reference stop is off tick: obtain a versioned execution quantization
   rule or reject that opportunity; never alter frozen stop/hold/targets silently.
4. Future timely causal signal + separate precise owner execution packet. Actual
   fills/native acceptance and realized costs require that future approved pilot.

These are technical/authority gates, not a new waiting period or promise of profit.
Next engineering is financial owner/gateway/latches, not another general audit.
KITY stays original SPENT/ORDERS_OFF; no new money gate passed. Polymarket follows
current Money work; no research merge, judge/outcomes or Claude messaging occurred.

## Status delta for Claude

| Component | Status / SHA | Evidence | Blocker / next gate |
|---|---|---|---|
| PUMP4 source/account | COMPONENT_PASS / `f5a517f` |151local/same151VPS;136 actual H1 restart checks;9 accountGET | Financial owner/latches + fully bound TINY admission; no LIVE |
| NET23Oct | Premarket protection NOT_CONFIRMED; existing owner exit accepted |06:20UTC6GET; private raw retained | Fresh stop receipt at opening, personal17:00 exit, independent terminal/cost GET |
| Monthly | Prior engineering PASS unchanged |53 source hashes/9VPS pins unchanged | Actual NET handoff + exact financial scope/config + scheduled source |

Canonical priorities remain in `ROADMAP_SELF_IMPROVING.md`. Claude owns research
KARTA/passports, Codex owns canonical roadmap/derived execution board.
