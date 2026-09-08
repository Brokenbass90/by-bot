# ATT1 public lifecycle — September 8

Status at this commit: IMPLEMENTED_AND_LOCAL_VERIFIED; target deployment pending.
Scope: frozen ATT1 only, no strategy changes. BE and ATR trailing remain disabled.

Implemented the existing planned profile/admission, coordinator, delayed funding,
durable journal and public runtime wiring. All runtime GETs are limited to public
Bybit market endpoints; no private API, credentials, broker or order authority.
The separate systemd unit permits writing only its new runtime and reads L1 cache.

## Verification

138 focused tests pass. Standalone verifier has 2 literal financial cases and
23 durable restart boundaries, plus the actual runtime on a synthetic HTTP tape
restarted at ENTRY / TP1 / TP2 / FINAL_COSTS. Fees363/20000, funding0 and final
net-R36637/20000 match the literal oracle. Separate delayed-funding test checks
historical exposure after exit. Dirty restart/polling gaps retain positions,
request simulated emergency exits and block clean final net-R.

Evidence: `research_lab/results/att1_full_lifecycle_20260908/`.
Astra/high found stale funding coverage on open valuation; root reproduced it,
added the failing regression, and fixed the existing coordinator horizon gate.
The reviewer then hit its usage limit, so there is no completed independent
Astra final approval. Root performed the final integration/security review.
Terra/high implemented the profile/input/transport parts; root completed runtime
wiring after the first helper-only delivery. Actual routing metadata is saved.

## Evidence boundaries

Execution model: PUBLIC_SNAPSHOT_IOC_SIMULATION. A short uses fresh post-submit
bid depth for entry and ask depth for exit, capped at5% of displayed level size.
The profile's scenario risk/notional caps are virtual, not money settings.
Fee assumption is0.001 per fill, not a verified account tier. Funding is settled
public history with historical held quantity and MARK_1M_PROXY candle-open mark;
publication and boundary uncertainty are explicit. Ordinary snapshot quotes are
not a continuous market path or broker execution parity proof. They do not
establish profitable net edge. Bybit source shapes:
[orderbook](https://bybit-exchange.github.io/docs/v5/market/orderbook),
[funding history](https://bybit-exchange.github.io/docs/v5/market/history-fund-rate).

The source-pinned L1 shadow has not been modified. Its final in-memory evaluator
returned PASS_OPERATIONAL_BURN_IN at2026-09-08T10:13:13.561Z:72/72 required slots,
0 missing, findings[],0 restarts. Whole journal7602 rows/36 raw signal rows
includes bootstrap and3 later cycles; those counts are not independent trades.
Final receipt:
`research_lab/results/att1_ets2s_burnin_20260908/onsite_final_20260908T101313Z.json`.

## Deployment contract and rollback

Application: `/opt/bybot-research/att1-lifecycle-zero-risk/app`.
Runtime: `/opt/bybot-research/att1-lifecycle-zero-risk/runtime/v1`.
Unit: `att1-lifecycle-zero-risk.service`; bybot-research,160MiB/30%CPU,
ProtectSystem=strict, no home/secrets, write access only to the new runtime.
Repository config remains default-off; package enables only public simulation.
Package manifest binds all file hashes and is verified before target smoke.
Rollback is stop/disable only this new unit, preserve all journals and release
files. No existing service/position is affected, no evidence cleanup or rewrite.

Target smoke/deploy/restart receipts will be appended after actual execution.
