# Monthly v5 actual FAIL; complete clock correction v6 — 25 October 2026

## Verdict

**v5 personally activated, but operational FAIL. v6 engineering PASS, UNSELECTED.**
The owner ran v5 once. Independent readback verified its scope/unit/GO and two
completed systemd cycles. Both rejected ACCOUNTING and LOSS_ADMISSION with
`MONTHLY_PENDING_FEE_STALE_SOURCE`. Source collection passed; no opening occurred.
The dated authenticated snapshot was flat/no open orders/cash496.31/pending0.
No activation or money command was repeated by the agent. This report does NOT
claim two healthy real v6 cycles, market execution, fee finality or profitability.

## Root cause and corrected acceptance

Previous v5 moved three manager clock anchors but missed the outer CLI. `main()`
sampled wall time before expensive authority checks and passed that fixed value
into dispatch. Later fresh fee evidence could therefore appear future/stale.
The one-line correction passes the original optional clock: production `None`
lets dispatch sample time after authority; explicit deterministic fixtures remain.

One bounded independent review found the analogous gap in native maintenance.
Maintenance now includes custody/lock elapsed time. Entry admission also compares
fresh account/clock/quote reads against current elapsed time, retaining the account
observation anchor. Broker tolerance5s and quote limit300s remain unchanged;
future quotes and stale broker clocks are still rejected. Numerical frozen
selector, weights, stops, monthly calendar, reserve and loss policy are unchanged.
The implementation identity hash changes because it includes the native file;
CONTRACT/reference bytes do not change. Helper checks exactly that distinction.

The new CLI regression deliberately supplies NO `now_ms`, runs actual
CLI→dispatcher→manager with slow authority and checks that only its deliberate
missing source fails. Native tests cover slow custody, broker+6s, fresh quote after
slow account, stale301s and future1s quote. RED failures were reproduced before
fixes; final exact candidate runs **266 local / same266 VPS PASS**, network denied,
53source files/40imports/18test files, no fallback/skips/errors/failures. These are
not532 independent broker checks. The final manifest explicitly executes all five
new native parameterized cases; earlier unselected manifests omitted them.

Actual saved fee evidence was replayed GET-only with two explicit diagnostic
clock offsets: old pre-capture time rejects, post-capture time passes. This is a
counterfactual source diagnostic, not broker attestation or actual cycle PASS.
See [evidence](evidence/monthly_clock_default_cli_20261025/).

## Exact prepared personal action

Candidate `/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-70fb661c269ad460-tfee25909`.
Source material SHA256 `70fb661c269ad4601498ba1f1eeee14739c7a30ea63a95bc2ae057e16747720c`.
Scope `af7a11594367e3532a1e448e212c2dbafbda4df868c3b1a7be13d157b686f12e`.
Spec `a78d94727388d942839626c5e0812dc29efc53bbb88f9e53326f94a5acabd30f`.
Packet `eb4c53d81d1fa3e3c56c0772f7b1ca35815164816c46fdeceb59c99933c74f66`.
Helper `54be0dd547a7a54f9271b68a70fc5939d5f4ac393dc4a5e5e3c0f6bef86b24d9`.
Read-only observer v2 `b287861cd36fac2dfde28546ebe5453f5e4aae8622888c46e9086eb8d44c37ee`.
Full pin manifest and final actual read-only verify are in evidence. v6 GO/attempt
absent; selected v5 remains BLOCKED until the HUMAN executes the source correction.

```bash
bash /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/money_completion_20261025_v6/owner-monthly-v6-once.sh
```

Run ONCE, never automatic retry after any error or ambiguous SSH result. This is
a new packet, not a repeat of spent v5. It retains400capital/280gross/40reserve,
max4/new single168/loss admission8 (BUY latch, not maximum-loss guarantee), no new
margin,2Nov2026 14:30UTC→1Feb2027 00UTC. No purchase now or forced catch-up entry.
Same original book, Alpaca lock813893, retired NET, cancelled SHOP and legacy HALT.

The established personal launcher is HUMAN OWNER ONLY and needs a new source-bound
personal GO. Prior budget approval persists; the agent must not mint that GO or
execute the monetary helper. Verify mode is read-only. It verified actual flat
account and pinned custody with no new GO or units changes.

Activation write-ahead claim prevents retry; helper disables timer/waits for the
old cycle without killing it, repeats fresh flat GET under original lock, requires
empty positions/exits/dispatches and no latches, revokes only old future-entry
scope, publishes new personal scope and atomically selects the reviewed unit.
Past GO/claims/book/evidence remain. No broker POST/PATCH/DELETE is issued.

The launcher then waits READ-ONLY up to240s for TWO completed actual post-GO
DISPATCH_TICK records. Only clean source+accounting+maintenance/loss-admission with
OUTSIDE_MONTHLY_WINDOW/no opening can produce `ACTUAL_IDLE_CYCLES_PASS`.
ARMED/PENDING alone is not acceptance. Observer uses exact selected source/scope/
unit pins: CLI-only `production_entrypoint` is added after persistence and is not
a stored record field. Six verdict cases include saved actual v5 rejection.
Seven helper negative checks reject changed budget/loss/period/reserve/frozen
source/contract and invalid owner text before I/O. Bash syntax passed.

Next: after personal command, independently re-read actual two cycles, account,
book, original lock and selected unit. If blocked, preserve the exact failure and
perform GET-only reconciliation; never repeat activation. Actual30Oct selection
and2Nov fresh account/native protection remain future market gates even if idle
acceptance passes. No new trading authorization was invented.

## Review scope and limits

One verified actual `gpt-6-astra/high` critical reviewer independently tested six
new cases; its Important maintenance gap was fixed. Code and previous-path packet
semantics had no remaining Critical/Important findings. Final manifest/path rebind,
helper seven negative checks and observer verdicts received root review. Targeted
peer observer followup hit usage limit; not silently replaced with another model.
No independent signoff is claimed for the final observer, nor financial approval.

## PUMP4 — corrected timing verdict and next gate

Existing single ownerPID2865120/original818853/ORDERS_OFF remains separate from
Monthly fees and personal action. No PUMP financial GO. Previous93/132 'timely'
referred to SOURCE capture time, not financial decision availability: **actual
publication proxy was late for ALL132** (84.544–230.339s vs60s limit). Filesystem
mtime is explicitly a publication proxy, not authenticated exchange time. Correct
that interpretation wherever the old count is read; do not widen the gate or
backdate records. Existing epochs/journals/producer/137universe/HFT unavailable stay.

Current warm source archives the entire census before processing/publishing
individual decisions. Read-only existing-journal profiling also found repeated
full replay/snapshot/canonical serialization work (ZRO20decisions,0.297s in one
snapshot), unchanged journal/hash, zero broker/state/outcome/judge writes.
Next bounded engineering task: publish each completed per-symbol capture through
the EXISTING causal intake before the full census completes; reuse verified replay
state safely, keep capture and decision-publication clocks separate, then measure
actual next-H1 publication. No new framework, frozen producer change, delayed row
promotion or financial activation. PUMP TINY remains NOT_READY until actual timely
source→account→sizing/admission ORDERS_OFF and exact risk/cost packet pass.

Queue Monthly correction/readback → PUMP publication/execution/TINY → Polymarket
→ KITY. No new architecture or broad audit. Research/Claude checkout untouched.
