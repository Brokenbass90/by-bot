# Elder Crash Hedge — V1.1 source integration, October 17

**ELDER_HEDGE_V1_1_SOURCE_CONTRACT_RECONCILED_ORDERS_OFF.** Both blockers in
ELDER_HEDGE_ORDERS_OFF_ADAPTER_2026_10_17.md are resolved against Claude's
versioned clarification. This is source/adapter integration, not prospective
parity, canary readiness or money authority. Standalone Elder remains KILL.

## Verified authoritative source

- Research commit `57a09dbd5e8d41814e053c18fb6cc617a8880ed2`, local ref and actual origin verified.
- Contract `research_lab/ELDER_CRASH_HEDGE_V1_1_UTOCHNENIE_2026_10_17.md`:
  SHA256 `a25e4af2239cfba738b1f9c88f522060fdca810efd97cbff856f85af3fea3a28`.
- Producer `ten.py`: SHA256 `2eb740e6a3c0df0d72b1c40a92ab8a1b5cec920d1ae6200f70e66e4c6d988d6f`.
- Read-only process observation: user's restarted ETS2S PID16945, start
  October17 11:09:53 Cyprus, short/stop4/hold336 settings. Codex did not restart
  or modify it. Disk source and process start do not prove its in-memory hash.

No actual ETS2S decision rows, outcomes, judge or PnL were consumed. The first
live geom observation and its actual source parity therefore remain unmeasured.
Old geometry-free records continue to block and may never be backfilled.

## Exact adapter changes

The first record's actual `geom` v1 is required; `zapisano` is its availability.
Signal/next-bar stamps, timing, finite numbers,4x stop,100max leverage and.55
fraction are checked. Rounded stop/rr diagnostics are checked but are not used
instead of the unrounded raw geometry. No terminal-result reconstruction.

`sp=abs(raw_sl-e_ref)*4/e_ref`; `k_i=abs(raw_tp_i-e_ref)/(sp*e_ref)`.
CONTROL levels bind to **actual fill**: short SL=fill*(1+sp), TP=fill*(1-k_i*sp).
Native short SL rounds DOWN to tick and must remain above fill; it cannot
increase theoretical stop distance. Example: ref100 / rawSL102 / fill100.2
gives108.216 CONTROL, native108.21 at.01 tick.

`bind_actual_fill` is a pure post-fill level/risk calculation. Better short
fills can increase monetary risk: an overshoot explicitly returns
`FILL_RISK_REQUIRES_SCOPED_REDUCTION`, never permission to enlarge risk.
The ORDERS_OFF entry template uses its reference limit; an eventual monetary
transport must enforce actual-fill rebinding and scoped risk handling before
it can claim CONTROL execution parity. No such sender was activated here.

Short/regime/risk/lot/capacity/hold rules and original pure `ispolnenie` are
unchanged. Missing targets keep the CONTROL999 sentinel; unreachable
nonpositive TP prices are represented as absent, never sent as negative prices.

## Tests and disabled deployment

**39 targeted PASS**, including the existing adapter/ETS2M isolated fixtures,
new real-schema fixture, raw geometry/rounded diagnostics, causal clocks,
actual-fill anchors, native rounding, risk overshoot and invalid-source cases.
The new fixture executes only the pinned producer's geom AST assignment with
synthetic inputs. It imports no strategy/producer or outcome evaluator.
Fixture provenance and exact hashes are in `evidence/elder_hedge_v1_1_20261017/`.

New24-file VPS kit installed **disabled**, all hashes independently read back:
`/opt/bybot-research/elder-hedge-20261017/candidate-236629be14170f6c/app`.
Spec SHA256 `2b5785abfa729286e05d328c29f89a8017b23f02878925f9aa2a0b8e184e700c`.
No registered service, broker transport, scheduler or money policy. The old
disabled kit is preserved as history and is superseded for future intake.
Current KITY unit/lock, Alpaca/NET/HALT, ATT1/LIQ and Claude's processes remain
unchanged by this source-only installation.

## Next boundary

New first-record geometry can be checked as prospective decisions arrive;
there is no added arbitrary calendar wait. Frozen gates stay unchanged:
>=30 hedge events; intentions>=97% within1tick/1lot; execution decisions>=95%;
zero unexplained material defects; restart PASS; latency<=5min in>=95%;
original ETS2M900 gate, then bounded dossier and separate owner GO.
**Zero real events were credited** from this engineering delivery.

The pasted research suggestions about ETF hooks or a November2 NET close are
not financial authorization. No NET exit/migration or research deployment was
scheduled or performed.
