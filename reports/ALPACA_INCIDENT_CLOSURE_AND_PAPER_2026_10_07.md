# Alpaca incident closed operationally; PAPER candidate staged — October 7

**Incident verdict: `ISOLATION_DEPLOYED_RECONCILED_ENTRY_HALTED`.**
**Actual Dynamic PAPER verdict: `BLOCKED_DATA`; not `PAPER_EXECUTION_PASS` or LIVE GO.**
The broker is flat, entry HALT remains, and no broker order was sent in this cycle.
Read the companion JSON for exact IDs, source hashes, timings and receipts.

## Real exits and retained history

At 16:07:34 UTC the selected LIVE account readback was cash/equity **$496.12**,
accrued fees zero and **$0.02 pending regulatory fees**. CRWD and META were sold by
the already-executed emergency MARKET exits, not by their expired stops:

| Symbol | Exit order | Quantity | Average fill | Fill time UTC |
|---|---|---:|---:|---|
| CRWD | `cefd3e9f-d0a0-48f4-825a-4c21a8cfbae9` | 0.469970151 | 275.43 | 13:30:21.138159586 |
| META | `ac20286f-6184-412e-b19e-fc807d97e51a` | 0.141939508 | 736.062 | 13:30:21.44294938 |

Exact terminal orders and authenticated FILL activities agree with owned entry
quantities/prices. Combined gross PnL is **+$6.380157352418 before fees**. This is
not final net PnL; no pooled entry fee is arbitrarily allocated.

Under the existing runner and account locks, immutable original lifecycle,
HWM/floor, proof, emergency receipt and broker evidence were durably archived at
`/root/by-bot/runtime/alpaca_intended_live/incident_20261007/source.json`.
Its canonical source hash is
`da0271033bf32696ce188c62a0841f36b63e0b92a27a1b3d09e875ad4d1bbc96`.
The existing reentry ledger retains AMD exclusions and all entry intents, with
exact MARKET emergency provenance added separately. Native active floor state
now equals `{}`, matching the broker. No history was erased or stop fill invented.
The archive preparation receipt alone is not an apply/postcheck receipt.

`alpaca_emergency_reconcile.py` has no broker client, credentials or order path.
Its caller must supply authenticated complete evidence while holding account
locks. Replay only accepts exact before/after states; uncertain changes fail.
Archive and ancestor-directory fsync precede ledger retirement.

## Installed isolation correction

Selected production package:
`/opt/bybot-research/alpaca-rearm-isolation-20261007-r2/app`.
Its 61-file manifest SHA is
`ca9559400a62a7ebb4d2b8a823d08630e73b65e8fff7ed05232c4100c677a5f6`.
The only changed existing production source is the native bridge's reviewed
re-arm error isolation. The other 57 prior source pins are unchanged; three
explicit recovery/test files were added. Old package and draft staging remain.

One rejected symbol no longer prevents protection attempts for other owned
symbols before aggregate HALT/emergency handling. It does not lower floors,
reprice a rejected stop, blindly retry, change quantity, risk or entry policy.
The existing runner wrapper now selects this app. Cron, profile, binding,
capital **$487.42**, gross **0.70** and maximum **4** stay unchanged.
No service was restarted. An existing-wrapper `--read-only` invocation passed.

Final GET-only preservation at **16:40:30 UTC**: positions zero, open orders zero,
HALT true with exact pre-apply bytes retained, native HWM empty, one NEW schedule,
OLD schedules/processes absent and all 61 installed pins match. Cash and pending
fees remain as above. MainPID/NRestarts: bybot **1648585/0**, web **1623208/0**,
public ATT1 **1584802/0**. KITY census PID **1804770** and all three source/schedule
pins remain unchanged. Its October7 **23:55 UTC** cutoff was not reset or extended.

Caveat: the scheduled runner can report `LIVE_CYCLE_COMPLETE` and
`money_authority:true` while the separate durable entry HALT remains true. Those
fields describe the bound LIVE runner, not permission for new entries or proof of
an active protected sleeve. Broker truth plus HALT is authoritative here.

## Isolated PAPER continuation

Staged, without a daemon or automatic sender:
`/opt/bybot-research/alpaca-dynamic-paper-maintenance-20261007/app`.
23-file source manifest SHA:
`4f6e5288790174b9a9fdfb031d4e7a229c8b852ed2eef96785003d30961f76d3`.
19 prior sources unchanged; only PAPER CLI and reviewed bridge updated, with
maintenance module/tests added. Frozen selector, policy and ranking are unchanged.

The old first-window job remains terminal `ORDERS_OFF_RANKING_CAPTURED`. Its
21 source pins, original deadline, first receipt and SQLite bytes are untouched.
A separately writable continuation book copies the exact sealed source bytes:
`runtime/rehearsal/replacement.sqlite` beneath the new staging directory.
Ancestor SHA is
`f34d90c8669dc1f1b61710852d47381c23c0f98dbeff8333b540ccb5e76919f7`:
one ranking, three owned slot lineages, zero intents and zero exits at staging.
No backdated reservation or fill is introduced.

PAPER account `4cdbfb77-d1e0-4789-86b2-341bc886efaf` had five legacy positions
ABNB/ABT/AMZN/MA/SCHW, preserved. Its active legacy preserve-only manager would
otherwise attempt to manage XOM. At **16:42:20 UTC**, under the original PAPER
account lock, authenticated GET proved XOM flat/no orders. Only
`XOM: ALPACA_DYNAMIC_V1_PAPER_PENDING` was added to its exclusion list; original
bytes are durably archived and the installed native skip gates were checked.
Existing exclusions, legacy wrapper/cron and LIVE state were not changed.
New exclusion SHA is
`8171cd5ef14f8374e75f6406476d254c816465ef96cab8a52ac335d2f2122e3f`.
This is preparation, not a permanent all-writer ownership guarantee; recheck it
and active writers in the actual entry window, retain it through terminal finality.

Maintenance requires the exact initial PAPER intent/account/entry/latest buy and
owned native ledger. It persists deterministic DAY re-arm before POST; uncertain
or lost responses reconcile by CID without resend. Exact floor and quantity
remain. Emergency exit is one proof-scoped, quantity-bound MARKET sell; no
account-wide flatten or adoption of legacy positions. Pending/partial exits,
stop fills during cancellation and mixed stop/MARKET exits preserve actual kind.
Native retirement is preceded by durable terminal preparation. Gross remains
separate from fees/finality. See the updated Dynamic runbook for exact commands.

## Verification and next gate

- **151 targeted PASS locally**; **64 incident PASS +87 PAPER PASS on VPS**.
- Final full suite **4089 PASS /57 exact pre-existing FAIL**, no new or removed
  failures against the retained baseline. Suite is not globally green.
- Independent bounded financial review used runtime-verified `gpt-6-astra/high`.
  Incident archive durability and five PAPER recovery scenarios were reproduced,
  fixed, and targeted closure accepted. Synthetic tests do not prove real PAPER.
- Foreign untracked allowlist remains unstaged, exact SHA
  `add587f1bd7059c2c706f1f7c604e36c2fb7b36b258b127e01fcd2101d3f19a1`.

Next actual plan window: **October8 13:30–13:35 UTC /16:30–16:35 Cyprus**.
Use the existing XOM ranking, current authenticated quote/asset/minimum,
earnings/concentration, exact cash/fee/liability provenance and real slot exits.
All three inherited positions are now flat; deterministic frozen slot ordering
chooses the actual vacancy. Do not force AMD sizing, create an unused fourth
slot, rescan the market or reprice a persisted intent.

Then actual isolated PAPER entry, full native protection/readback, recovery,
DAY expiry/re-arm (October9 if held overnight), exact terminal/unwind and cost
finality. A future actual `PAPER_EXECUTION_PASS` precedes an exact LIVE handoff,
kill/rollback dossier and **separate owner GO**. HALT does not clear itself.
KITY source/parity and account economics remain the next crypto money priority;
no research rerun, Claude messages, OS2 production integration or ATT1 changes.
