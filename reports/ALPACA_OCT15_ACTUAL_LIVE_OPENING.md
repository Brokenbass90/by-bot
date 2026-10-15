# Alpaca Oct15 actual first LIVE opening

Final GET-only check13:56:31.988UTC: same NET qty/full native STOP277.69,
manager13:55:00–13:55:03 exit0,53static pins still match. Private capture
observations/oct15-owned-guard-1792072591988.json SHA
`bdc21b849ad63a416689b411c693b0cfc9756cbe7bb09e19f2e1d51fd8004a64`.
Actual ATT1 `att1-lifecycle-zero-risk-v2.service` PID1584802 and LIQ
`bybit-liquidation-source-v2_1.service` PID2095785 remain active/NRestarts0.
Old similarly named units are historical and must not be mistaken for these.

Current at 13:30:56 UTC: **LIVE_PROTECTED / NONFLAT**. Do not repeat entry or
run flat-only preflight. Preserve owned management, exact GO, book and ledger.

The timer started exactly13:30:00UTC; entry service completed13:30:08, exit0.
Actual LIVE BUY `705a1b5b-1d45-4ba1-97cf-9c646033d78d` filled13:30:06.234131UTC:
NET **0.325167779 at $311.222**, notional **$101.199366515938**. Broker native
STOP sell `28ecadfb-376d-4e4f-b34f-40e5fd16843c` submitted13:30:07.737636UTC,
status `new`, full **0.325167779**, price **$277.69**. Initial modeled price risk
**$10.903525965428**, excluding gap/slippage/final posted costs. One actual position,
one full stop, durable `PROTECTED`, native record1. No duplicate entry.
Controller `OPENING_PATH_COMPLETED` is supported by execution `LIVE_PROTECTED`
and actual broker readback, rather than used alone as proof.

Private capture: observations/oct15-opening-1792071055168.json SHA
`a97ef8e8c6d9a9d3523e0f5a32bb9c1cc41388040ad08dcfcaaa18f4e1387437`.
The13:30 manager tick preceded the session binding and returned2. Actual regular
tick13:35:00–13:35:03 returned `LIVE_PROTECTED`, exit0. Readback13:35:43.534UTC
confirmed the same position/full STOP/durable PROTECTED. Private manager capture
observations/oct15-manager-1792071343534.json SHA
`a86e0441877c998229e10dd35d5aadb64158cf162b1e11947b5541efe0c9e823`.
The13:50 manager also exited0. Entry protection and recurring management are
actual. No LIVE posted-fee finality/net claim.

Earlier preparation/arming facts below are retained history:

Fresh GET account at 13:04:57 UTC: ACTIVE/unblocked, cash and nonmarginable cash
$496.12, pending/accrued fees zero, positions/open orders zero. NET is active,
tradable and fractionable. Native ledger empty, source intents/attempts zero,
no LIVE database. All 53 frozen static pins and source roles match; original
account lock held for the check and competing monthly cron remains retired.

IEX returned raw CTS `2026-10-14T20:00:01.977130548Z`, ask zero. This is unusable,
not today's quote or a fresh dossier. No price or quantity was invented.
The human explicitly approved the fixed first-intent envelope despite that
premarket limitation, conditional on actual opening quote and all existing gates:

`GO ALPACA_DYNAMIC_FIRST_INTENT_V1 198903481c94357e3ae76d11688aa23f9a8740f2515062a64c7c267f0600f2fd`

Direct reply: `call_c768d5e4cc8e471aa5569c67f1981417`. This supersedes only the
earlier requirement to receive a fresh-price dossier before this exact GO.
One NET attempt Oct15 only, qty <= .469970151, notional <= $124.699999985736,
modeled stop risk <= $10.906127324106, limit <= $349.82. Gaps/slippage can exceed
modeled loss. No repeat, reprice, risk increase or session transfer.

At **13:10:34.051 UTC /16:10:34 Cyprus**, fresh flat/no-orders/cash and custody
were rechecked under the original account lock. Exclusive GO/provenance files
were written0600. Original scoped HALT retained byte-for-byte in private
`CONTROL/session/original-halt.json`, SHA
`e1a137bc8fd2f918c38b3d4cc5c5e844b6dd6bf3ae6fc694e4d2d376997f53ad`.
Only the four already-pinned unit templates were installed and only the entry
and owned-manager timers started. At13:11:29 UTC both enabled via exact
`timers.target.wants` symlinks, leaving unit bytes unchanged. Entry waits13:30 UTC;
owned management uses the frozen five-minute cadence. Persistent=false prevents
a past opening from being replayed after reboot.

Post-arm independent readback **13:15:35.049 UTC**: actual `load_spec` and
`OpeningDispatcher._validate_static` PASS,53pins, source active0, no terminal,
no adapter invocation, entry service PID0/inactive, timer active/waits13:30 UTC.
Zero broker writes/source reservations at these observations. Arming is not a
fill or protection result.

The first operator command stopped on `KeyError: max_notional` before any write;
the corrected operator lookup uses existing `max_notional_usd`. No trading code,
intent or source pin changed. It was not a broker/order failure or second entry.

Private operational receipt folder:
`/opt/bybot-research/alpaca-dynamic-live-20261013/control/oct15-first-entry-v1-1/session/`:
`owner-go.json`, `owner-go-provenance.json`, `arming-receipt.json`,
`armed-readback.json`, original HALT. Public account/quote capture pins:
[preopen_readonly.json](evidence/alpaca_oct15_actual_opening_20261015/preopen_readonly.json).

At opening read dispatch fresh/reserve/invoking/terminal and actual broker
readback. Return actual ENTRY_PROTECTED / NO_FILL / BLOCKED first. No retry after
uncertainty. Preserve manager during owned exposure; use the frozen scoped
maintenance/kill/rollback runbook. No additional PAPER or research gate.

Telegram watchdog investigation: old root-cron script still reads the intentionally
stopped bybot heartbeat. New KITY owner PID2147336/NRestarts0/fresh ORDERS_OFF,
0POST; old bybot/web PID0 and startup conditions deny restart. Old warnings do
not describe the new owner's health. After Alpaca handling, the separate
owner-aware observer was actually switched13:39:48UTC (8 focused tests), with
exactly one cron line/current KITY custody rebind; read KITY_OWNER_HEALTH_2026_10_15.md.
No Alpaca config/unit/authority changed and no old writer was restarted.
