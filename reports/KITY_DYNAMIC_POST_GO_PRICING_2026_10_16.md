# KITY micro — dynamic post-GO pricing, October16

**DYNAMIC_POST_GO_PRICING_READY / INSTALLED_ORDERS_OFF. No monetary GO received.**

The owner requested a bounded correction for
`PLANNING_DEFECT: HUMAN_APPROVAL_LATENCY_INVALIDATES_ABSOLUTE_PRICE_BANDS`.
The earlier Oct16 intent86b5349b…b1205 remains spent NO_SEND, with its original
selection/claim/capture/receipt unchanged. There is no retry or authority transfer.

The new policy contains no absolute prices or preselected quantities. It freezes
the exact five-long/five-short basket, original minimum common-target sizing and
floor-rounding frontier (shortfall≤20.3%), gross≤215USDT, ±0.5% pricing,
15USDT immediate all-in exit trigger with accepted execution overshoot, 30-minute
maximum lifecycle from the first durable entry intent, native Full stops,
single-writer ownership and existing no-reentry/recovery/accounting rules.
It is execution-only, never KITY/C1–C3/edge evidence.

Policy ID:
`e3b3f5310b2c9afdf4f503b453673054607a3a3ecca7d222817f7e2352d54325`.
Exact published policy file SHA256:
`3fb02561c47a342f2bfa3ad36b6867e009e57e40ced5f960fcf56d4135209fd4`.
Policy expires **October17 00:00 Asia/Nicosia (October16 21:00 UTC)**. It is not
extended automatically. The original ten-minute absolute-price intents remain
history; this separately approved flow uses a session-bounded price-free policy.

After the human personally issues the new GO, exactly one full account/depth
capture produces fresh quantities, costs, funding reserves and guarded IOC
requests. Pricing anchor: the worst depth level consumed for that sized quantity
in this capture, using the unchanged compiler. Limits round inward to exchange
ticks within ±0.5%; worst upper-band reference gross and actual/limit gross must
fit215. All existing source/account/instrument/CTS≤2s/permission/ownership gates
remain. Existing per-leg GET revalidation does not reprice or resize the plan.

Every new entry POST must begin within **60 seconds of the owner's server-side
GO issue timestamp**, including queue/capture/binding time. There is no report,
rehearsal, coding or second human approval in that interval. A missed deadline or
source failure consumes the attempt; it cannot take a second capture. Before
any fill the result is NO_SEND; after exposure/uncertainty the existing owned
unwind/reconciliation takes over. The entry deadline never disables exits,
native-stop management or final accounting. Restart persists no-reentry and
recovers owned exposure rather than resending entries.

The single writer is now app-post-go-v1, runtime/post-go-20261016, same unit
`kity-execution-micro-owner.service` and original account lock inode818853.
Installation07:20:27UTC: PID2286916/NRestarts0, HEALTHY/ORDERS_OFF; complete broker
positions0/openorders0 before, under exclusive quiescence, and after switching.
A second lease was refused. Old bybot/web remain inhibited; ATT1/LIQ unit state,
cron and prior apps/history were verified unchanged. No Alpaca/Claude changes.
All16 previous trading source files are reused byte-for-byte; only two new
modules were added. Installed config SHA:
`0b91589535f4cc8c0f7e09130419d61d41acc8d325f3be9e3c4cf8d6c58bc914`.

Pre-GO preparation1792135272982096679 and GET-only rehearsal1792135274489071764
passed. Rehearsal gross175.684210 is a dated diagnostic, not the future quantity,
price, required exchange margin or an execution acceptance guarantee. No actual
selection, policy claim, journal, owner authority or new broker POST was created.
Authenticated instrument availability does not prove actual order acceptance.

Verification: **108 targeted PASS**, including long human delay, single capture,
failed/late capture, wrong/old GO, changed policy/bounds, stale CTS, final-custody
expiry, no-wire recovery, exit after expiry and ten native stops/restart/deadline/
actual cash accounting against a deterministic fixture venue. Exact saved
Oct16 rejected capture replays offline through the new flow: ten requests,
gross209.505230, 7.131s after the old actual GO, zero network/orders. This is
development evidence, not a rerun of the spent money experiment.

Full suite: **5089 PASS /60 FAIL /1 warning**,234.09s. All60 names exactly match
the previously published Alpaca-runtime baseline; added/removed failure sets
are empty. Full suite is **NOT_GREEN**, no KITY failures. Root-only review;
the earlier independent-review quota restriction remains. No independent
financial/research signoff claimed. Exact names are in verification.json.
The unrelated untracked allowlist changed during the cycle; it was not edited,
restored or staged by this work (final observed SHA e8652150…d11f8).

If the HUMAN accepts this new policy as a separate monetary decision, personally
run exactly once:

```bash
bash /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/kity_post_go_20261016/owner-post-go-micro-once.sh
```

**AGENTS MUST NEVER EXECUTE, DELEGATE OR SCHEDULE THAT COMMAND**, nor invoke
`--owner-go-policy` or submit GO_POST_GO themselves. The personal command is
the new exact MONEY GO, not another request to accept legal terms. No extra
chat confirmation is needed after the human personally runs it. It claims a
local one-shot marker before SSH; unknown send/SSH outcome requires read-only
inspection, never blind replay. The new runtime performs the authorized
lifecycle autonomously; agents may inspect actual receipts/positions/costs
read-only afterward. COMMAND_QUEUED alone is not a fill or execution PASS.

Receipts: evidence/kity_post_go_pricing_20261016/{policy,readiness,verification}.json.
Private raw/account/installation/owner-launch artifacts stay outside Git.
Code and policy are frozen at this readiness receipt; no new research, strategy,
Alpaca, ATT1/LIQ, Factory/Claude or risk changes are authorized by this delivery.
