# KITY scoped physical handoff — October15

CURRENT subsequent13:39:48UTC monitoring rebind: read KITY_OWNER_HEALTH_2026_10_15.md
and the updated RUNBOOK. Trading app-v1-2/14 sources unchanged, current config
config-v1-3-health.json1699930e…1d7f2,unit88ef47e4…1be7d,cronf01f0d95…507cd,
PID2182409. Exactly one legacy watchdog line replaced; new observer has no
restart/order authority. Original v1.2 receipts below are immutable dated history.
Subsequent exact micro GO ffeb4bc4…6570 was consumed13:49UTC; terminal NO_SEND
at13:49:59, exact IOC limit not marketable,0POST/fills, independent flat readback.
Not actual lifecycle PASS; do not repeat/reprice/reset or reuse that GO.

**KITY_EXECUTION_MICRO_LIVE_READY — engineering, ORDERS_OFF.**

Remaining known STATIC material blockers: **[]**. FRESH_ONLY and OWNER_GO are separate below. This is readiness for the separate execution micro experiment; actual venue acceptance/fills/protection/finality have not been exercised with money and are not claimed PASS. No KITY/C1–C3/edge authority changes.

Final physical readback: **2026-10-15T08:28:28.984000+00:00**. New service `kity-execution-micro-owner.service`, PID **2147336**, active/enabled, automatic NRestarts0. Explicit orders-OFF restart changed PID2146563→2147336. The second account-lock acquisition was rejected; lock inode818853 remained stable.

The owner-authorized handoff stopped only `bybot.service` and `trading-journal-web.service` after complete fresh linear-USDT flat/open-order/history/execution checks, before/while quiesced/after stop. Their original unit/source bytes and enabled state remain retained; scoped condition drop-ins inhibit restarts. SIGKILL was used only on these confirmed-flat units to avoid shutdown broker-write callbacks. Their current systemd state is failed/MainPID0 from that deliberate stop; web control is consequently offline. Watchdog systemctl start attempts cannot bypass the condition. The root crontab is byte-identical.

Final account readback: **positions0/openorders0/recentorders0/recentexecutions0**. Trading POST barriers0, owner GO absent, active plan absent, actual lifecycle DB absent. The no-send rehearsal used temporary explicitly non-trading journals that were removed; it created no monetary permit/reservation/intent.

Installed final source: `/opt/bybot-research/kity-micro-owner-20261015/app-v1-2`. Runtime `/opt/bybot-research/kity-micro-owner-20261015/runtime`. Config `config-v1-2.json` SHA `7ee8a1b6f88473946e728523292fa46c5ee508c89b519db82cc3e5971c0e8cdd`; unit SHA `d87870493ee8fe552e6bc570e1360a73dc697355ce1ae9f74fce163e54079c08`. Fourteen explicit source pins; credential values remain only in the existing selected private source, never in the package/receipts. Only the selected existing credentials are read; old risk/env overlays are not loaded.

**Actual no-send evidence.** The final service prepared the exact ten legs, then exercised fresh checks and the physical POST inhibitor for all ten. Six reached fresh-PASS/post-inhibited. Four had moved beyond their saved fixed IOC price (LTC/XAUT/XPLUS/XAG): FRESH_ONLY, no automatic reprice. Source/permissions/instrument/lease wiring did not produce a STATIC blocker. Native protection, fills and accounting are locally tested execution paths, not actual money claims.

**Dated proposal, 2026-10-15T08:26:15.474000+00:00:** gross **208.084850USDT** ≤215; approximate margin at unchanged configured leverage **29.946145**, not an exchange-certified initial-margin quote. Fully-funded reference **208.30255046100**; constant-price roundtrip fees **0.21770046100**; captured 30min funding scenario0 because its sourced next settlements fall beyond that interval. That forecast is not future posted cash/funding truth.

Bounds unchanged: 215 gross; **15 all-in immediate exit threshold**, execution overshoot accepted; 30min from first durable entry intent; floor shortfall≤20.3%; exact5L/5S; no averaging/scaling/re-entry. Native Full/Market/LastPrice stops supplement the portfolio trigger. Sum of reference stop-price distances×quantities is 14.774750USDT before costs, not a guaranteed realized loss cap.

| Symbol | Side | Qty | Fixed IOC limit | Native stop |
|---|---|---:|---:|---:|
| BTWUSDT | Buy | 10 | 2.04159 | 1.89656 |
| XAUUSDT | Buy | 0.005 | 4164.84 | 3868.98 |
| LTCUSDT | Buy | 0.3 | 58.42 | 54.27 |
| VVVUSDT | Buy | 0.96 | 22.3340 | 20.7480 |
| BNBUSDT | Buy | 0.03 | 721.18 | 669.95 |
| XAUTUSDT | Sell | 0.005 | 4153.39 | 4448.44 |
| XPLUSDT | Sell | 276 | 0.07811 | 0.08365 |
| XAGUSDT | Sell | 0.380 | 56.81 | 60.84 |
| GRASSUSDT | Sell | 34 | 0.63290 | 0.67780 |
| SPCXUSDT | Sell | 0.14 | 148.65 | 159.21 |

This exact saved proposal is dated; the rehearsal already proves that some limits can become unmarketable. Use the existing PREPARE command for a fresh reviewed proposal before requesting money GO. A plan must never be repriced after GO, substituted or automatically transferred.

**FRESH_ONLY:** actual authenticated account/key permissions/mode/cash/margin/instrument/fee/funding/ownership and raw common CTS≤2s; fixed price must remain marketable and gross/rounding/capital caps must hold. **OWNER_GO:** separate human `GO KITY_EXECUTION_MICRO_LIVE <exact plan_id>`; none received. These are not unfinished engineering.

**Verification:**558 targetedPASS including the original251 signal vectors; actual installed authenticated GET rehearsal and explicit no-GO restart. Full repository suite not run. Root-only review under the existing quota ruling. No independent review is claimed.

Root review closed PLANNING_DEFECT cases before money: bound native SL queries used the wrong identity; one order read error could skip later orders; Full stop resizing/cancellation needed exact handling; recurring funding rows conflicted on observation-time dedup; restart/preflight rejection before any send needed explicit NO_SEND finality; loss of an existing journal must never silently create an empty one. Tests observed failure before correction for these counterexamples. Installed v1 and v1.1 and their unit/config receipts remain intact alongside final v1.2.

ATT1 PID1584802 and LIQ V2.1 PID2095785/NRestarts0 retained. Alpaca53 static source pins still match, HALT present; its Oct15 opening remains P0 and its separate exact GO is still required. Claude files/processes, KITY producer/prereg/C1–C3/B3/Brain outcomes were not modified/consumed.

**Reuse boundary.** This owner is locked to KITY exact10 and its micro bounds. Elder can reuse reviewed transport/lease/identity/recovery patterns, but needs its own signal/position contract and separate money approval. Historical Elder DEV does not replace its frozen prospective verdict; Brain STOP variants are not revived.

Operational commands and all remaining layers: [runbook](KITY_MICRO_SCOPED_HANDOFF_RUNBOOK_2026_10_15.md), [matrix](evidence/kity_micro_handoff_20261015/late_blocker_matrix.csv), [exact dated proposal](evidence/kity_micro_handoff_20261015/owner_go_packet.json), [physical readback](evidence/kity_micro_handoff_20261015/physical_readback_v1_2.json).

Official source contracts used: [one-shot create/IOC/attached Full SL](https://bybit-exchange.github.io/docs/v5/order/create-order), [system-resized native stops](https://bybit-exchange.github.io/docs/v5/position/trading-stop), [error semantics](https://bybit-exchange.github.io/docs/v5/error), [cash rows](https://bybit-exchange.github.io/docs/v5/account/transaction-log).
