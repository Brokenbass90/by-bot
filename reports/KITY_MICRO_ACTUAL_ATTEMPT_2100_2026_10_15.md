# KITY actual micro attempt — October 15, 21:00 Cyprus

**BLOCKED_EXECUTION_ACCOUNT_TERMS / FLAT_FINALITY_COMPLETE.**
One actual owner-approved experiment, not a KITY strategy canary or C1–C3
evidence. The complete ten-leg lifecycle did **not** pass.

Human reply `call_ef4ab3ff455b4f8789ee315eb1bdbc3a` authorized intent
`f040d23eec5a951e324825e0568764e45b74d699491a2aa610995a7d8961c436`.
PREPARE command1792087329484261664; GO command1792087447559644944.
Derived plan `43c744f0d2b35c6db6c17729cd0c90a22247072e47791bc5b20c80bc2e59444b`.
Old7aa/7d7 intents were expired/unselected/unexecuted at the fresh precheck;
their human replies remain provenance, never transferred. New GO consumed once,
followed by one actual fresh capture, fixed quantities and existing fresh gates.

## Actual execution and unwind

First durable entry intent18:04:18.996UTC. BTWUSDT Buy10 filled1.86998 at
18:04:19.289UTC; native full STOP10 at1.74928 read back. Entry order
`7a82c0b7-593a-4f58-9683-a3654f7efa9a`, stop
`7003fff8-ca40-4008-967a-751f4fac7218`.

Second create XAUUSDT returned HTTP200/retCode110123:
`You must agree to the Trading Terms before trading this contract.`
Exact signed-request barrier/raw response retained. Authenticated realtime,
history and execution readback found no XAU order/fill. No other entry attempted.
The earlier GET-only preflight did not establish these instrument-specific terms.

Two implementation defects: (1) symbol position pagination appended an empty
placeholder to the real row; exit verifier rejected aggregate length as unknown
mode; (2) documented110123 refusal was absent from definite-create rejections,
leaving the XAU intent UNKNOWN. Both are recorded as PLANNING_DEFECT.

For emergency recovery the main writer was stopped, operator acquired original
lock inode818853, verified exact journal-owned BTW10/sole matching native stop/
no foreign exposure, and appended ordinary EXIT_INTENT before one existing
SignedPostOnce reduce-only Market dispatch. Native stop retained until flat.
No simultaneous second writer/new entry. Original supervisor resumed readback.

BTW Sell10 filled1.86408 at18:07:22.818UTC, order
`8c951831-5f13-48dd-bc5b-56428050c1bc`. Native stop then terminal/zero fills.
Early unwind after~3m03.5s was due to incomplete basket, not a scheduled30min hold.
Original maximum deadline18:34:18.996UTC was never reset.

| Actual accounting | USDT |
| --- | ---: |
| Gross realized | -0.05900 |
| Posted entry fee | 0.01028489 |
| Posted exit fee | 0.01025244 |
| Funding cash | 0 |
| Net, exact actual transaction reconciliation | **-0.07953733** |

Slippage is already in fill prices, not subtracted twice. No strategy inference.

## Recovery-only V2.2 — current deployed identity

Original kits/config/intent/GO/plan/wire sources and journal history preserved.
Separate16-file kit `/opt/bybot-research/kity-micro-owner-20261015/app-v2-2-recovery`.
Only three source files changed: refusal mapping, exit source, exact existing
experiment recovery. No risk/sizing/signal/cost change. Exit uses complete
settleCoin nonzero positions; flat native cancellation requires explicit one-way
empty-position source. Saved refusal resolution requires exact request/response
hashes, documented code and fresh exact order/history/execution/position checks;
empty GETs alone never prove rejection/no-send.

Config `runtime/config-v2-2-recovery.json`, SHA256
`1033ffe728d9a4809840a6cc324f752579e0c3a9eabf115ec31a8979377d068e`;
unit SHA256 `a284dd9c6fbb4be53a0fef8a1d2fc005d9f02afc6b551b9fb1cdec9738ab3d99`.
Same service kity-execution-micro-owner.service, PID2208912/NRestarts0,
same818853lock; independent second lease refused. Config OWNED_RECOVERY_ONLY
binds this existing intent/plan to original config6d420ec0…5f54b2; PREPARE/new
selection/journal creation forbidden. No GO/source was rewritten to new config.

Journal extended with sourced DISPATCH_REJECTED and actual FINALITY at
18:14:34.889UTC, net-0.07953733/funding_complete=true. Independent18:15:14.237UTC
GET: positions0/open0; journal TERMINAL/entry_blocked/all_ten_complete=false,
ownership_conflict=false/no unknown fees. Three POSTs total: BTW entry, refused
XAU create, BTW exit. Zero additional POSTs during V2.2 installation/closure.

**160 targeted tests PASS**, including13 incident cases; original defects
reproduced failing first. Root review only; full repository suite/independent
financial review not performed. Old bybot/web remain inhibited; ATT1 PID1584802
and LIQ PID2095785 active/NRestarts0; cron/source guards unchanged. Alpaca and
Claude untouched; no independent new Alpaca broker audit in this operation.

Official contracts checked October15:
[positions](https://bybit-exchange.github.io/docs/v5/position),
[create-error codes110123/110125](https://bybit-exchange.github.io/docs/v5/error).

## Next action

Owner personally reviews/accepts applicable Bybit Trading Terms for XAU; agent
did not accept legal terms. Other eight unattempted legs are not thereby proven
executable. No substitution/reentry/new intent/automatic follow-up from spent GO.
Future experiment needs a fresh proposal and separate exact human GO; current
recovery-only config cannot start it. Preserve all original/spent experiments.

Receipt `evidence/kity_pricing_intent_20261015/micro_terminal_2100.json`, SHA256
`f9beea66a7ab08855dde83bd5e1d1cecac17fb3856415812fef36399c3356a48`.
