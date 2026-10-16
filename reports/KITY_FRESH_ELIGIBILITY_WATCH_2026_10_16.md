# KITY exact-policy eligibility watcher — October16

CURRENT: **KITY_FRESH_COMPATIBLE_READY**, terminal observed on VPS
2026-10-16 **13:05:56.306 UTC /16:05:56 Cyprus**. Independently read back
16:04:11 UTC; service exited successfully, MainPID0/NRestarts0. This is a dated
eligibility observation, not current price readiness or actual ten-leg execution.

Exact policy `9051edb3b7b69c87a81dd73a7ab0a1075ad841b6d88ad70889f96e71ec515155`.
Six successive incompatible captures retained gross331–334; seventh passed:
**gross206.694000USDT, ten account-instrument checks and ten existing fresh
entry preflights PASS**. Immutable terminal ID
`222e5e03adf9cfd354d2e8622077c83658a6448bc904eba75a4394ced0944ac7`.
Native one-shot Telegram delivered HTTP200/message15203, no repeat notification.

[Terminal and readback](evidence/kity_eligibility_watch_20261016/terminal_v11.json).
Original writer2314960/ORDERS_OFF/NO_ACTIVE_PLAN/original lock818853,
34 financial send barriers unchanged. Watcher never claimed the policy,
created a GO/journal/reservation or issued a financial POST. No standing money
approval exists. Original expiry remains October16 21UTC/October17 00Cyprus;
no extension/restart/new policy is authorized by watcher readiness.

## Actual installation and isolation

V1.1 root `/opt/bybot-research/kity-fresh-eligibility-watch-v11-20261016`;
unit `kity-fresh-eligibility-watch-oct16.service`,120s cadence until terminal.
Source SHA `bdbf7d951b8134312f114eb33667ca7f1556c43a0a34f484fb348b7c03da8ce3`;
spec SHA `bd3362cee3a077326503414b759ba13e8313e24af32b92add1de6433e4d0551f`;
unit SHA `883b9b278faaf330d2862a43f1c3e32c1cc7c86d330c5aaa4d89d882bec65d96`.
Its strict systemd filesystem sandbox permits writes only inside its own
runtime. Existing writer/policy/20source files/unit/wire baseline pinned.
Transport is GET-only; existing compiler and all ten preflights reused.

V1 first run is preserved terminally BLOCKED: the older health CLI's
`--no-notify` still opened an account-health lock for append. The read-only
sandbox denied that write before market capture. V1.1 calls only the pinned
pure health observer, never its locking CLI. V1 terminal/message15202 was not
reset or overwritten. First V1.1 readback was delayed by automatic-review usage
quota; after reset the actual terminal above was verified, not inferred.

Verification: **60 targeted PASS** (watcher/post-GO pricing/low-latency suites).
Includes repeated incompatible captures→one READY, expiry/race with human GO,
terminal integrity/restart/single-instance, POST refusal, no writer lock via
health CLI, unknown notification delivery without resend. Full suite not rerun.
Chat heartbeat `kity-9051-expiry` remains **PAUSED**; native VPS terminal is truth.

## Next scope

No threshold/cap/sizing changes. Current $215/20.3%/50bps/70s/15trigger/30min
policy remains separate from any proposed batch/WS version; $350 was proposed,
not approved. No batch/WS implementation or monetary attempt in this cycle.
Alpaca protection incident preempts further KITY/Elder/Reporting work.
