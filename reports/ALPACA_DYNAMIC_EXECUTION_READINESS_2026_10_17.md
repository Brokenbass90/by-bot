# Alpaca Dynamic — restored scope and execution readiness, 17 October 2026

**Status: DATA/BROKER_ELIGIBILITY_PASS; event reselection is an isolated
ORDERS_OFF research candidate, not an approved profitable strategy or LIVE runner.**
Code: `469a9eddf27fd40d38f71ba2db783522fb38b25c`.
Monthly is separate and does not replace this P0.

## What existed, and what broke

Original implementation `a9cf3b68806279822ac12455924d4a12e1000477` and
`ALPACA_DYNAMIC_V1_POLICY_2026_10_06.json` define weekly first-XNYS-session
ranking, one confirmed full owned exit releasing one replacement slot, and at
most one replacement at a regular-session opening. That replacement behavior
was implemented and tested. It reused the weekly ranking; continuous fresh
whole-universe reselection after each stop was not implemented by that contract.
`daily_refresh_enabled=false`; a free fourth slot was never an extra funding token.

Commit `05d77bfdd6b45730aa346e1fa62b40d0cc7e4df1` added strict next-session
source admission through `ranking_matches_entry_window`. It intentionally
rejects a ranking from another opening with `NO_SEND/STALE_SIGNAL_RESELECT_FAIL`,
but ranking creation remained weekly-only. The changed test explicitly replaced
next-day `RESERVED_ORDERS_OFF` with `NO_SEND`. Therefore the current combination
cannot perform non-weekly replacement. This is a real functional gap; silently
reverting the freshness check would restore stale-source entry authority.

## Delivered repair candidate

`EventReselectionBook` reuses `DynamicBook` transaction, ownership lineage,
quantity, cash/fee reserve, original slot notional/stop-risk caps, reservation and
restart rules. Base Weekly's only edit extracts its existing weekly refresh
condition into an overridable method; its default condition and frozen policy
are unchanged. Monthly code/policy are unchanged.

A confirmed full owned exit before the current opening requests a fresh ranking
from the immediately previous completed session. Held, blocked and 21-day
cooldown names are removed before the unchanged v38/SPY200 selector. A candidate
may reserve at most one entry in the opening five minutes. An intraday stop does
not cause an immediate intraday purchase; its earliest candidate window is the
next regular opening. Gates, available cash and original slot risk still apply.

The candidate requires its own SQLite book and refuses an existing original
book before writes. Its runtime kind is `EVENT_RESELECTION_RESEARCH_ORDERS_OFF`;
the existing LIVE custody validator requires `LIVE_DYNAMIC_SEPARATE` and cannot
adopt it. Restart keeps the exact reservation, with no reprice or duplicate
intent. There is no broker/credential/financial execution path in the candidate
or CLI. Input-provided snapshots are not authenticated broker truth.

Reproduce without network or financial side effects:

```sh
.venv/bin/python scripts/run_alpaca_dynamic_reselection_v1.py
.venv/bin/python -m pytest -q tests/test_alpaca_dynamic_reselection_v1.py tests/test_alpaca_dynamic_v1.py
```

## Actual source and account evidence

- Monthly's existing 58 names comprise its 57 tickers plus SPY. Original Dynamic
  needs 59 names: the only missing name was QQQ. QQQ was obtained with the same
  existing hourly, RTH, unadjusted loader; 200 sessions match the actual broker
  calendar through 16 October. No synthetic bars or forward prices were added.
- All 59 broker assets were read with `writes_enabled=False`: exact symbols,
  active US equities, tradable and fractionable; errors0/ineligible0. The bound
  account was ACTIVE/USD with no account/trading block.
- Actual unchanged-selector preview on 16 October closed bars for 19 October is
  gate PASS, SHOP/ABBV/ADSK/MSFT. **This unfiltered preview is not an admitted
  portfolio, an order or a recommendation.** Live exclusions, owned slots,
  event history, fresh quotes and final cash/risk admission remain necessary.
- The separate one-off Dynamic59 capture is ready. The active Monthly58 timer
  does not automatically provide QQQ: continuing Dynamic59 refresh is not deployed.
- Current account has NET, HALT and no open orders at the recorded GET. NET is
  the existing manager's position, not an automatically adopted Dynamic slot.
  Original account lock inode813893 and95 protected source pins were verified.

Evidence: [source59](evidence/trading_os_dynamic_kity_20261017/dynamic_source59.json),
[broker59](evidence/trading_os_dynamic_kity_20261017/dynamic_broker59.json),
[versioned candidate semantics](evidence/trading_os_dynamic_kity_20261017/dynamic_candidate_contract.json).

## Exact remaining gates

| Gate | Current state / concrete next action |
|---|---|
| Original Dynamic versus new behavior | Proven distinction above; Claude should version/review the candidate's next-opening fresh-reselection semantics. Do not relabel it original V1. |
| Economic evidence | No verified like-for-like net-performance comparison of original Weekly, this candidate and accepted Monthly was found or run in this cycle. Existing `alpaca_dynamic_full_backtest.py` and V2 grid use different universes/exit rules and do not prove this contract. Compare fixed rules on the same source/costs/opportunities; no tuning or new waiting period is implied. |
| Continuous source59 | Extend the existing source operation through a separate explicit Dynamic59 contract; preserve Monthly58 identity and its frozen strategy. |
| Current account/slot ownership | Authenticate the original exit/slot ledger and NET ownership under the existing shared lock. No second manager, no synthetic free slot, no NET adoption. |
| Stop/restart lifecycle | Reuse existing native stop, daily ratchet and recovery components; candidate has contract/restart tests, but no actual financial binding or complete authenticated end-to-end admission receipt. DAY re-arm must be observed during RTH. |
| Transport and exact owner packet | Prepare disabled one-owner binding after semantic admission; fixed entry/capital/stop/cost/window/rollback and actual fresh GETs. There is no new activated policy, runner or financial timer. |
| Financial initiation | Separate exact OWNER GO and personal initiation after the reviewable packet. October6 prospective research permission is not automatic LIVE authority. |

**Earliest technical opening:** 19 October 13:30–13:35 UTC /16:30–16:35 Cyprus,
on 16 October closed bars. This is conditional, not a promise of a Monday
trade. An event candidate also needs a real eligible full-exit vacancy. There
is no month-end restriction in the restored Dynamic lane. If a deterministic
condition fails, report that condition; do not invent a calendar waiting gate.

250 focused Alpaca tests pass across the candidate, original Dynamic,
intake/first-intent/PAPER/LIVE-runtime and Monthly/native interfaces. They prove
specified software behavior, not strategy returns or broker execution. Final
review is root-only under the existing reviewer allowance restriction; no
independent financial/research signoff is claimed.
