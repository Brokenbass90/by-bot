# Brain V2 local A1/A2 runbook

This import-only engine is orders OFF. It cannot place an order or change LIVE,
strategy, broker mode or risk. Actual-source worker/prospective epoch is not armed.
Use `reports/BRAIN_V2_A1_A2_ORDERS_OFF_DELIVERY_2026_10_12.md` and source manifests;
do not activate anything by treating ENGINEERING_READY as a research verdict.

The public Python API is `Opportunity`, `RegimeBar`, `signal_available_ms`,
`build_contexts`, `assess_request`, `empty_brain_state` and `BrainJournal`.
Example for an already sourced JSON request in a new isolated local runtime:

```python
from pathlib import Path
from research_lab.brain_v2_a1 import BrainJournal
from research_lab.os2_shadow_journal import strict_json

request = strict_json(Path('/absolute/path/source-bound-request.json').read_bytes())
with BrainJournal(Path('/absolute/path/isolated-brain-runtime')) as writer:
    receipt = writer.process(request)
```

Do not use any existing OS2/Alpaca/BOUNCE runtime directory. The journal requires
an owned absolute directory, no symlink, mode700; lock/journal600, one writer.
OS2 defaults retain their own schema, so neither writer can adopt the other's
prefix. Single paired append contains three logically separate arm ledgers.

INIT requires request_id, initial_equity_usd, epoch_start_ms (whole hour),
source_hash and explicit capital_known/positions_known/protection_known=True.
This is independent **simulated** initial capital, not an authenticated account.
All arms start with equal supplied E and separate empty positions. Active frozen
table is cut off2025-10-01; historical earlier/fold replay cannot use this table.
For a genuine future epoch independently pin its actual publication/observation
timestamp and begin after it; the pure model's cutoff check is not that proof.

HOUR requires a complete consecutive hour, sealed_at_ms≥h+1h,
coverage_end_ms=h+1h, source_hash, positions_known/protection_known/costs_known,
opportunities, exact-ID contexts and terminals. Never send an unfinished list as
complete or missing positions/funding as zero. Empty lists require an actual
coverage manifest. Source hash fields are commitments, not signature/authentication.

`build_contexts` consumes supplied canonical BTC H4 and per-symbol H1 `RegimeBar`
histories, each with source_hash. Keep the raw data/receive-time manifests outside
the paired journal under immutable pins. Preserve canonical history start for
Wilder seeding; changing the origin/window is not source parity. Context h is
known at h; missing or unavailable inputs become UNKNOWN and sleeve fallback.
No competing env/regime.json writer or trend-based admission veto is introduced.

Terminal input identifies the exact opportunity, actual_exit_ms/available_ms,
source_hash, finality=FINAL and COST_MODEL
`BRAIN_V2_V1_6BP_2BP_ACTUAL_FUNDING`. gross_return_frac is side-adjusted return on
unadjusted reference prices **before costs**, exit_notional_ratio is exit/entry
notional, and funding_cost_frac is actual cumulative signed cost divided by
entry notional (negative means income), including changing notional. No guessed
flat rate, funding envelope, table-net R or double-fee/slippage accounting.
Unknown finality/costs blocks the transaction without releasing risk.

Per A1, known exits of previously admitted positions in the current hour release
before that sealed hour's batch. Same-hour new admission+terminal and late prior
hour terminals fail BLOCKED_DATA rather than create hindsight capital. Integration
must resolve those actual lifecycle cases causally; do not edit or backdate state.
The model is hourly research accounting, never an intrahour dispatch schedule.
For mixed H1/15m packets the frozen virtual fill time/price after whole-hour
selection still requires a research timing clarification. Do not feed old
next-open outcomes or call an allocation a fill before that contract is sealed.
This is a prospective/developing integration blocker, not a reason to retune.

RAW/FOUNDATION order by(t_available,id); BRAIN by(-z,t_available,id). .06E budget,
.005E risk×mult, .40B sleeve and .60B direction; first violation in exact source
order, continue afterward. Fees6bps+slip2bps each side are model cash inputs;
signed funding is supplied factual exposure. No venue rounding/canary sizing.

Successful receipt is EPOCH_INITIALIZED_ORDERS_OFF or HOUR_RECORDED_ORDERS_OFF;
BLOCKED_DATA is an inert durable receipt. Duplicate identical request returns
the exact existing receipt; conflicting input under the same ID blocks. An
uncertain append poisons this process: close, GET/read existing prefix by reopening,
verify exact prior request, never blind retry/repair/delete. Corrupt tail stops.

Inherited explicit bounds: 2MiB request/receipt, 8MiB journal, 4096 transactions,
≥512MiB free disk, ≤1000 opportunities/hour. These are a bounded local observer,
not adequate evidence of16/26-week unattended retention. At a bound stop BLOCKED;
prospective retention/compaction must be reviewed before autonomous deployment.
Marks/MTM-DD and complete actual opportunity coverage remain required evaluator
sources; closed-net receipts alone cannot establish the frozen research PASS.

Verification:

```sh
.venv/bin/python -m pytest -q tests/test_brain_v2_a1_context.py tests/test_brain_v2_a1_allocator.py tests/test_brain_v2_a1_journal.py tests/test_brain_v2_a1_review_regressions.py tests/test_brain_v2_frozen_primitives.py tests/test_os2_shadow_journal.py tests/test_os2_shadow_bridge.py tests/test_os2_shadow_cli.py tests/test_os2_shadow_review_regressions.py tests/test_bounce1_intake_protocol_limits.py tests/test_strategy_shadow_ledger.py
```

Rollback for this local-only delivery: do not start a worker; preserve receipts
and their code pin. Revert the scoped candidate in a new commit if necessary,
never reset sealed prefixes or downgrade an A2 journal to superseded A1. No live
rollback is implied because no deployed service/config was changed.
