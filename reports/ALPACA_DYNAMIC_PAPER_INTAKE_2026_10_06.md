# Dynamic V1 — PAPER adapter and first-source job

**Implemented PAPER adapter; isolated orders-OFF source job armed. LIVE promotion
remains BLOCKED_DATA.** Read companion JSON for source/test/install hashes and
the canonical checkpoint for current priorities. Continue a9cf3b6; do not rebuild
the sealed V1 book/selector or revive the old monthly-reserve prerequisite.

## Delivered and measured

- `alpaca_dynamic_paper.py` binds an unchanged reserved plan to a distinct PAPER
  account. Exact quantity, capped DAY limit buy, actual terminal fill and full
  native stop readback; fractional quantity uses DAY. Limit rounds down, fill
  floor rounds up to retain the fixed risk distance. This is a PAPER execution
  candidate, not a change to current LIVE fills/stops.
- Durable dispatch before POST, deterministic entry/stop IDs and lookup-only
  ambiguous recovery. No missing-order resend, repricing, slot release or adoption
  of legacy PAPER positions. Partial terminal fills receive full actual-quantity
  protection. A zero fill, uncertain cancel/stop or changed ownership blocks.
- CLI defaults to GET-only, exact PAPER host, no redirects or LIVE key fallback.
  No account-wide flatten/PATCH route. It requires the exact plan in its source
  book and uses the original broker checkout's shared account lock, not the new
  package ROOT. Native floor persistence reuses the existing tested helper.
- Separate closed-hour collector validates all59 frozen names, ordered/unique/
  finite bars, the immediately prior session's full regular hourly grid and no
  future bar. Earnings UNKNOWN and missing survivor-correlation evidence block
  eligibility. Selector numerical rules remain unchanged.

Local118 targeted PASS; final adapter/source/CLI68 PASS locally and on VPS.
Full3970 PASS /57 exact existing failures, no new failure; that full run preceded
the final shared-lock-path and capture-timeout regressions, separately covered by final68. One bounded
financial review produced four reproduced/fixed findings: hidden foreign order,
window expiry during network calls, unknown correlation, clock/source provenance.
Model requested6-astra/high; new runtime routing metadata was unavailable, so
actual routing is not claimed verified. Foreign allowlist hash preserved.

## Actual accounts and preservation

PAPER account `4cdbfb77-d1e0-4789-86b2-341bc886efaf` already holds ABNB/ABT/AMZN/MA/SCHW.
No PAPER order was sent; none of those positions was reset, adopted or closed.
Current shared account is not an empty sandbox. Selected-symbol positions/open
orders reject, and truncated broker pages cannot pass.

Fresh LIVE GET **October6 18:18UTC /21:18Cyprus**: CRWD0.469970151 and
META0.141939508; accepted full DAY stops **275.45 /668.76**, IDs agree with durable
floors. One NEW schedule, OLD absent,58 source pins and cap487.42/gross0.70 match.
No LIVE/config/cron write. Current protection is verified; continuous open re-arm
and improved net edge remain separate evidence questions.

## Fixed native job: public capture then authenticated GET-only ranking

Base `/opt/bybot-research/alpaca-dynamic-v1-20261006-paperintake-v2`;
initial PID **1764534**,21 source files pinned,68 VPS tests passed before launch.
Production bybot1648585 /web1623208 /ATT1public1584802 remained active/NRestarts0
and unchanged across install. No service restart, cron change or AI call.

- **Oct6 20:15UTC /23:15Cyprus**: one bounded public download into isolated
  `runtime/hourly`, preserving monthly LIVE cache. Capture bound900s/disk guard.
- **Oct7 13:30–13:35UTC /16:30–16:35Cyprus**: reverify source hashes, read broker
  account/clock/positions/orders, check causal eligibility, seal first ranking.
- **Fixed terminal deadline Oct7 13:35UTC**. No automatic retry/reset/extension.
  The source job has no sender. It does not produce a replacement reservation,
  exact quantity, authenticated cash-finality claim or broker PAPER fill.

Inspect `runtime/terminal.json`, `closed_source.json`,
`first_window_receipt.json`, `selection/replacement.sqlite` and `launcher.log`.
Healthy waiting is not completed capture. Early failure or absent terminal is
explicit BLOCKED; preserve evidence and diagnose before any separately scoped
attempt. Do not start another copy. No LLM availability is needed for this job.
Abort only after checking current `/proc/<pid>/cmdline` matches the exact script
and runtime; stop that owned job only, preserve evidence, no broker rollback.
The unused earlier draft archive is not an installed source or rollback target.

## Next acceptance, then owner money decision

After first real ranking, obtain contemporaneous quotes/assets, exact sizing,
cash/liabilities and fee provenance; construct the unchanged reserved plan in
the source book. Do not turn unauthenticated booleans or scenario10bps into
actual cash/fee truth. The old AMD pooled entry-fee allocation is still pending.

PAPER read-only command, **only after an actual reserved plan exists**:

```bash
/root/by-bot/.venv/bin/python /opt/bybot-research/alpaca-dynamic-v1-20261006-paperintake-v2/app/scripts/run_alpaca_dynamic_paper.py \
  --plan <actual_plan.json> --plan-store <actual_replacement.sqlite> \
  --paper-env /root/by-bot/configs/alpaca_paper_local.env \
  --paper-account 4cdbfb77-d1e0-4789-86b2-341bc886efaf \
  --runtime /opt/bybot-research/alpaca-dynamic-v1-20261006-paperintake-v2/broker_paper
```

The CLI's explicit `--paper-submit` permits PAPER only. It is not scheduled or
called by the source job. Complete isolated manager/ownership coordination before
using it; an initial `PAPER_PROTECTED` readback proves protection at that instant,
not DAY re-arm, trailing, terminal fees/finality or autonomous lifecycle. Those
operational gates and proof-scoped unwind remain required. No LIVE sender exists
in this candidate. Do not copy its synthetic book into LIVE ownership.

Prepare a separate concrete LIVE GO dossier only with actual ticker/quantity,
source pins, earnings/concentration/reentry, gross/cash/fees, management handoff,
monthly-entry overlap exclusion and scoped kill/rollback. No request to activate
money is justified by local tests or an empty ranking.

## Other lanes

KITY08–09October preempts further Alpaca improvement research: exact raw23:55OI,
independent actual basket parity, Bybit minimum/depth/funding/account fees/mode/
cash, smallest equal-notional size, fixed caps, unwind/finality and owner dossier.
Research/2k251-vector implementation stays frozen, no crypto money without GO.

ETS2M bounded source inventory: **BLOCKED_DATA**, original900 source not found.
Do not repin current rows or alter Oct10 19UTC judge/job. First-window PASS, if
ever honest, advances only to the separately frozen disjoint second900 gate.
ATT1 full48h probes are complete, not restarted; actual packet/money gate remains.

Claude `abd906e` is already an ancestor of verified remote `ecb9749b`; Bitget
prospective collector/prereg files exist. No duplicate push/merge, Claude message,
Factory launch or new outcome consumption by Codex. Continuous Factory runtime
is NOT_CONFIRMED here. Claude owns KITY forward, Bitget/Factory WIP1 and next
independent crypto basis/range/event/Gold proposals; PX1Oct14 remains scheduled
research. Planning a queue is not strategy PASS or READY_FOR_BUILD.

Pre-capture repair: original waiting PID1764106 was proof-checked and stopped
before any hourly download, with immutable ABORTED_BEFORE_CAPTURE receipt.
The fixed collector rearmed at PID1764534 in a distinct v2 directory; capture
20:15UTC, first window and13:35UTC deadline unchanged. Old sealed sources were
not edited. Timeout now propagates to terminal BLOCKED instead of being swallowed
as one UNKNOWN earnings date. Final68 tests include that RED/GREEN case.
