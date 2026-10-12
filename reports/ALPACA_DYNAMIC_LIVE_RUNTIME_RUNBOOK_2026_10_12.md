# Alpaca Dynamic LIVE runtime — exact-plan runbook

**Local candidate only, orders OFF.** Do not execute application examples before
actual lifecycle completion, source binding, separate owner GO and authorized
deployment. This document installs nothing and never clears HALT.

## Original PAPER schedule

Keep `/opt/bybot-research/alpaca-net-paper-session-20261012` and its original
guard unchanged. October13 regular re-arm13:30UTC, scoped unwind>=13:35,
hardend14:00. `alpaca-net-13` observations13:32/14:05 are read-only; pause after
terminal/second check. Use the existing finality capture command from
`ALPACA_OCT13_MONEY_HANDOFF_2026_10_12.md`. Do not use the initial two-order
validator after re-arm, retry a PAPER entry or turn its validation exit into a
LIVE vacancy. Actual process restart was not performed by this implementation.

## Static preparation and source custody

Complete dependency/source/ownership work before the next opening. Stage these
three new files with their delivery hashes, the existing intake/Dynamic/native
dependencies and an explicit original LIVE profile. No keys belong in Git.
The CLI checks original profile directory and original account lock derivation;
changing a role/env overlay cannot bypass source/account/endpoint checks.

Binding schema `ALPACA_DYNAMIC_LIVE_RUNTIME_V1` contains:

- `endpoint`, `account_id`, `policy_sha256`, `intake_sha256`;
- `broker_root`, `runtime`, `source_book`, `lock_path`, `ledger_path`, `halt_path`;
- `native_bridge_sha256`;
- `sources`: `authority`, `paper`, `old_terminal`, `cost`, each with physical
  absolute `path` and byte `sha256`, matching the intake's corresponding pins.

`authority` must record the original account/endpoint/lock/native ledger and
verified single entry owner/manager/old-monthly-entries-OFF. `paper` must be the
actual terminal `PAPER_EXECUTION_PASS` source with `live_orders_allowed=false`.
`old_terminal` must identify the original LIVE account/order/full quantity and
`BROKER_LIVE / TERMINAL_FINAL`. `cost` must bind actual fee/protocol source,
commission rate, regulatory reserve and unresolved liabilities. Physical hashes
alone do not establish broker truth; retain underlying raw evidence and review.

Create a **separate** LIVE DynamicBook. Reuse the existing sealed weekly ranking
and verified OLD slot sources with their original timestamps/pins; no scan,
backdating or PAPER intent/fill/validation-exit adoption. Book meta must contain
the exact policy digest and `runtime_kind=LIVE_DYNAMIC_SEPARATE`. Use the existing
planner for a new opening-time snapshot/plan; custody requires the exact active
plan in that book. The dispatch journal (`runtime/live.sqlite`) is separate.
Do not call `register_paper_fill` to create LIVE lineage. This first exact-plan
canary does not authorize subsequent plan/slot promotion automatically.

Before activation, bind fresh writer/process inventory and mutually exclusive
symbol ownership to the original shared account lock. Exactly one manager may
manage this new owned lifecycle. Old monthly entry stays OFF; original HALT
remains until a separate scoped activation decision. No services were installed
in this delivery. All approved static files/commands must be ready before T−15m;
the opening path must not discover code, read documentation or run broad tests.

## Read-only verification

Run the CLI with explicit paths and **without** `--apply`:

```text
.venv/bin/python scripts/run_alpaca_dynamic_live_v1.py
  --binding <private-binding.json> --intake <private-intake.json>
  --live-profile <original-configs/live-profile.env>
  --output <new-private-read-only-receipt.json>
```

The sealed policy digest is fixed in the CLI. An expired/mismatched plan returns
BLOCKED, never a refreshed quantity. Read-only verification creates no reservation
or broker order. Existing dispatch state returns `LIVE_READ_ONLY_RECOVERY_REQUIRED`;
it is not a recovery action. Default transport is writes-OFF.

## Exact owner-GO and opening application

After the actual lifecycle, give the owner ticker, exact quantity/limit/notional,
fill-relative risk distance, modeled stop risk/gap caveat, fees/reserve, session,
ownership, entry/exit and rollback. Request approval only for that concrete plan.
No broad earlier wish to start trading is substituted for this approval.

The independently approved private permit has exactly:

```text
schema = ALPACA_DYNAMIC_EXACT_OWNER_GO_V1
account_id = exact LIVE account
endpoint = https://api.alpaca.markets
intake_sha256 = exact immutable intake digest
binding_sha256 = exact binding digest
owner_go_text = GO ALPACA_DYNAMIC_V1 <exact intake digest>
session = exact plan session
```

No permit generator or automatic owner approval exists. `--apply --owner-go
<private-permit.json>` is the application interface, subject to the unchanged
HALT/window/source gates. Fresh account/clock/positions/exhaustive orders/cash
less liability reserve/asset/raw quote CTS are read under the original lock.
The exact quantity/limit is frozen; no market-price substitution or reprice.
The five-minute opening bound remains; a missed window is a terminal no-dispatch
decision. A reservation without a prior POST cannot submit a late BUY on restart.

## Owned management, kill and finality

The same exact binding/intake/profile/GO with `--apply --maintenance` manages only
its saved lifecycle under the original lock. HALT continues blocking new entries
while this management remains permitted. Reuse the approved manager schedule at
deployment; do not create a competing writer. DAY expiry is reconciled before
one stable-ID re-arm. Native HWM/floor are monotonic; no floor lowering.

`--apply --maintenance --kill` persists HALT and requests only an exact owned
quantity exit. Stops/replacements with unknown outcomes block a racing SELL;
resolve their exact broker IDs first. A definitive422 uses the existing scoped
emergency path. No account-wide flatten, foreign position adoption, uncertain
dispatch resend or repeated cancellation. Preserve journal/native state.

Exit status is `LIVE_EXIT_PENDING_FINALITY` until an external account/day report
is bound using `--maintenance --cost-finality <private-source-report.json>`.
Schema `ALPACA_DYNAMIC_BROKER_COST_FINALITY_V1` requires exact account/intake/exit
hash, gross, commission/regulatory fees, unresolved liability0, cash-before/
cash-after/other cash movements, observed/coverage timestamps, underlying source
file hashes and manifest digest, `closure_status=ACCOUNT_DAY_FEES_RECONCILED`.
Runtime independently reads order fills/cash, preserves fee-source identity and
returns exact net only after reconciliation. Missing fee rows are not zero.
Restored finality is dated; it does not free a new monetary slot or authorize BUY.

Rollback before any dispatch: keep HALT and entry owner OFF; retain staged sources.
After an owned fill: retain management until exact exit/finality; stopping the
manager is not rollback. Unknown outcome => HALT plus read-only exact-ID evidence,
one explicit blocker/next action. Never delete journals/ledger/lock or clear HALT
to retry. Changing binding/GO for an active saved lifecycle is a scope conflict.

Terminal launch boundary: actual PAPER pass + actual LIVE dossier + separate
owner GO. No extra PAPER/statistical requirement; concrete execution/source
defects alone may block. Native/PAPER/monthly guards stay unchanged.
