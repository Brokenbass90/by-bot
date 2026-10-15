# Bybit actual-owner health monitoring — Oct15

**OWNER_HEALTH_MONITORING_SWITCHED_ORDERS_OFF**, actual13:39:48UTC.
New owner PID2182409, NRestarts0, source error null, ORDERS_OFF, no active plan,
GO, actual lifecycle database or trading POST at that observation. Old bybot/web remain stopped with
the same inhibition marker/drop-ins. Alpaca is independently LIVE_PROTECTED;
no Alpaca files, units, stop, profile or account authority changed here.

The Telegram warnings were sourced to the legacy root cron watchdog reading
`/root/by-bot/runtime/bot_heartbeat.json`. Its repeated `systemctl restart bybot`
was denied by the handoff condition. They did not describe the active KITY
owner. Original watchdog source SHA1b2d6c4a…9812ba is retained unchanged.

Exactly one root cron line is replaced with a single-instance, read-only
actual-owner observer. It checks the new service PID, matching heartbeat,
schema/mode/error, freshness and account-lock inode, while requiring old owner
PIDs zero and intact handoff markers. It has no restart, broker, risk or order
authority. Missing/conflicting sources stay UNHEALTHY. After a complete rollback
with no inhibitors/marker/new owner it observes legacy health without restart.
Notifications remain on actual failure with10-minute cooldown; no test message
was sent. Actual cron13:40:02 returned HEALTHY, new PID2182409, heartbeat age2658ms.

| Current artifact | SHA256 / location |
|---|---|
| Observer | `4c1674865daf0e2da2014642d2d474f8e206c2c885f14f0cc40bc16b65654ed8` |
| Health spec | `87d419af4ea92dfd7a1c6463afbfcfba4c41920e6afe62f9436478cf49dff747` |
| Owner config | runtime/config-v1-3-health.json, `1699930e80fc314612388867761d3eed6241cd46de1b5e2ddfeed894d5b1d7f2` |
| Owner unit | `88ef47e4f1b27e8a241dcf55bfe2163db329e01bbb2dba59170ce9d125e1be7d` |
| Root cron | `f01f0d95e854dcf60edffc4b5b29bf152071b33dd0828443a6aced81dbb507cd` |
| Trading app | unchanged app-v1-2; all14 source pins unchanged |

The observer/spec live under
`/opt/bybot-research/kity-micro-owner-20261015/monitor-v1/`. Owner config changes
only guard_source_files, original_cron_sha256 (current custody pin) and normalized
unit_template_sha256. No frozen policy/math/fees/risk/hold/research changes.
Old config-v1-2/unit/cron receipts and source epochs are immutable history.
Use the updated [operator runbook](KITY_MICRO_SCOPED_HANDOFF_RUNBOOK_2026_10_15.md).

Fresh complete linearUSDT observations before/after the orders-OFF owner stop:
positions0/open0/recentorders0/executions0; final source
29d8432a5b0c440ace32801d45fc1ac6d53cad8e53cce83fae13841d8b1c0f5e.
No unprocessed commands/GO/journal/sends existed. Account lock inode818853 stayed
the same. Never restart old writers beside this owner.

An initial operator switch rolled back completely because it checked the old
heartbeat immediately after systemd assigned a new PID. Failure/start receipts
are preserved. The corrected operator waits boundedly for the actual new PID's
fresh heartbeat; no trading code changed. Final applied receipt:
`runtime/health-migration-applied-v2.json`; previous failed/rollback receipt:
`runtime/health-migration-failed-v1.json`. No money order/retry occurred.

Verification:8 focused tests PASS, covering intentionally stopped old owner,
new heartbeat stale/future/bool/schema/PID/mode/error/inode, competing writer and
missing owner. Actual installed --no-notify health returned HEALTHY before and
after switching; subsequent real cron returned HEALTHY. The prior558 trading
tests were not rerun because the trading14-file app is unchanged. Root review.

One subsequent actual PREPARE at13:40:58–13:41:03UTC produced plan
`ffeb4bc4924fe64586469377372dca88caaa9545544dc2920f3d1bc438ee6570`,
gross206.482530<215, STATIC=[], FRESH_ONLY=[] at capture. Fee reference.21637790625,
margin reference29.752873 (not exchange-certified exact margin), funding scenario0
(not future actual zero/guarantee). Account available1020.24090422USD. Exact10
orders, full bounds and separate owner GO text are in
[owner_go_packet.json](evidence/kity_owner_health_20261015/owner_go_packet.json).
The proposal is dated and requires actual fresh per-order gates; no reprice.
Subsequent direct human GO call_21f2e55ad6384a808313ca5b32add1f7 was consumed once
at13:49UTC. Command1792072189069696558 returned EXACT_GO_BOUND_ONE_EXPERIMENT.
Fresh dispatch rejected the fixed IOC limit: durable UNWIND event13:49:55.629,
reason `DISPATCH_PREFLIGHT:EXACT_IOC_LIMIT_NOT_MARKETABLE`. At13:49:59.372,
FINALITY_NO_SEND completed: **NO_SEND_NOT_LIFECYCLE_PASS**,0POST/intents/fills,
no first-send/deadline, no30min holding test. Independent13:51:43.592 complete
GET confirms0 positions/open orders/recentorders/executions,source
54e086566e1aab096214eb999bd41e0f483a5571bd68dd10155c37131dea1882.
Actual GO/plan/journal remain immutable; do not reset/reprice/retry. Terminal
net0 denotes no trade, not a strategy result or actual lifecycle PASS. No
KITY/C1–C3/edge inference is allowed. A later experiment/pricing intent needs
separate explicit authorization; this exact GO cannot transfer.
