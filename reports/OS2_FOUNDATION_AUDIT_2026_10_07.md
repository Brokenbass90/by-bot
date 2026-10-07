# Trading OS v2: foundation intake, October 7

Status: **AUDIT_COMPLETE / ORDERS_OFF**. Codex assessment of the supplied B3
implementation: **BLOCKED_IMPLEMENTATION**; this is not a strategy FAIL or a
replacement for Claude's research verdict. No integration has been installed.
The owner requested restoration of the common bot foundation and explicitly
deferred Alpaca inspection to the next cycle.

## Sources and scope

Verified origin: recovery `abf1187ffae86f399817477f3322361d0bc6e6d3`, research
`001f8226804f65961fca0449e04b06069686db09`. The handoff is actually at
`research_lab/os2/PEREDACHA_CODEX_OS2_2026_10_07.md`, not at the lab root.
Research was fetched into the recovery repository only. Claude's checkout,
plumbing branch and files were not changed or merged; no message was sent.
Read source/protocol/locks and synthetic tests, not historical trade streams,
fresh sealed outcomes or a judge. B3_KONFIG SHA256:
`9b65e28c2d283f2cdf1e4ab17d95cc46a7afe672fdf9d72085685a90d4f2256f`.

The attachment's direction is accepted: simple strategy sleeves, causal market
state, deterministic portfolio admission, execution/risk, decision evidence,
degradation diagnostics and bounded research proposals. Reuse existing modules.
Their presence/imports/tests alone do not prove that a portfolio is operating.

## Actual wiring

| Existing component | Verified local integration | Decision |
|---|---|---|
| strategy_priority_router | Pure ranker; no production caller found. Candidate money_authorized is an additional guard, not sufficient authorization. VPS file missing. | USE in isolated shadow first |
| strategy_regime_gate | Local monolith breakdown path 13284; enabled/fail-closed defaults. Not shared by every sleeve. | USE with explicit validated input |
| regime_side_gate | RANGE path 10739; neutral/unknown permits either configured side. | TEST; do not treat as fail-closed availability gate |
| exposure_gate | Definition/tests, no production call found. | USE after explicit position/cluster inputs |
| sleeve breakers | Generic helper 2910, RANGE caller 10757; ATT1/breakdown separate. Generic default OFF. | Preserve existing safety; prove each new caller |
| decision_bus | ATT1 emitters via att1_live_wiring; default OFF. | Separate shadow journal; never another authoritative lifecycle writer |
| edge_monitor | ATT1 alert-only hook/default OFF. | USE as evidence/alert; no silent risk or promotion |
| champion_challenger / research_orchestrator | Pure research transitions/proposals, no live caller found. | USE for proposed lifecycle changes |
| setup/Elder/level libraries | Existing sleeve dependencies, not a universal market classifier. | TEST incremental value per sleeve; no mass activation |

The actual legacy entrypoint is `smart_pump_reversal_bot.py`; there is no
`bot/runner.py`. Local and deployed monoliths differ, so the table is a local
call graph, not proof of each deployed effective flag. Existing production
source was never overwritten with the local monolith.

## Four pre-judge financial defects

All are P1 engineering blockers confirmed by one independent financial review.
Three were reproduced against exact pinned code using disposable synthetic
inputs; the fourth is a source-bound numerical counterexample. No historical
effect or direction of a changed verdict is known.

1. **Initial loss missing from DD** — `os2/replay.py:40–46`: a single −2R trade
   reports DD=0 because cumsum starts after that loss. An initial zero gives 2R.
2. **Unclosed outcomes used in training** — `os2/wf.py:30–42`: inclusion checks
   entry time only. Thirty 336-hour holds, none terminal at the training cutoff,
   already permit a BULL affinity. The probe directly checks srodstvo; the same
   condition is present in filtr_nog. Require evidenced terminal/result
   availability at the cutoff, not invented closure from a maximum hold.
3. **Incomplete closed 4h candle** — `os2/rezhim_v1.py:18–35`: aggregation accepts
   three H1 members as a complete 4h bar. Check unique consecutive timestamps,
   order, finite OHLCV and closure before producing a valid state. This proves
   a missing validation, not that the historical dataset contains that gap.
4. **DD resets between folds** — `os2/wf.py:52–55`: max(fold DD) is not continuous
   stitched DD. Folds [+2,−1] and [−1,−1,+2] have individual max DD 2R but
   continuous DD 3R even after correcting the initial-zero defect.

Claude owns these research files. Repair in an explicitly versioned amendment
with old/new source locks and synthetic regressions, preserving thresholds,
signals, train/test bounds and costs. Do not silently overwrite a frozen lock or
rerun a consumed judge. First check the research receipt state without outcomes;
if a verdict was already consumed, disclose invalidation and use a separately
approved fresh protocol. No repair was applied in this cycle.

The SEALED_V2 ledger acknowledges known ATT1/ETS aggregates. Its regime slices
may be unseen according to that ledger, but strict statistical independence
is not established by that fact. Declare partial contamination; obtain genuinely
untouched evidence or a prospectively frozen forward test before money policy.
Also, normalized closed-trade R is not USD margin, funding capacity or portfolio
mark-to-market risk. B3 alone cannot certify account execution/capital readiness.

## Regime parity and deployed state

At **10:25:05 UTC /13:25:05 Cyprus**, one bounded read-only VPS inventory found
bybot PID1648585, web1623208 and ATT1 public1584802, active/NRestarts0, unchanged
from their previous receipts. No broker calls or Alpaca inspection.

- Frozen local/research compute source SHA `56952650…f85370` matches the lock.
- Deployed source SHA `665371bb…f69ef` differs only in the strategy override
  prefix dictionaries in the inspected diff: ASLB1/BOUNCE1 versus ASB1. One
  additional bounded source-only read explained this drift; no deployment.
- **6,724/6,724 closed synthetic label comparisons PASS** across four fixture
  paths, research/local/deployed compute labels. Overrides differ in 2,322
  comparisons; label equality does not certify executable override parity.
- `runtime/regime.json` is missing and no expected BTCUSDT_240 cache was found.
  Existing `runtime/regime/orchestrator_state.json` says `bear_chop`, timestamp
  10:00:03.964905UTC, risk multiplier0.82. That is another producer/contract,
  not a REZHIM_V1 live receipt. Same-actual-bars parity remains **BLOCKED_DATA**.

UNKNOWN data is distinct from a valid NEUTRAL market. compute_regime's old
insufficient-data return allows both sides, and regime_side_gate permits unknown.
The future shadow bridge must validate availability separately; it must not
copy embedded legacy overrides into money configuration. A global bull label
does not alone prove that ATT1 should be disabled: test each sleeve's causal,
after-cost affinity with its own admission/cooldown and portfolio opportunity set.

## AI authority and continuous audit

Deployed executor SHA `746a88c4…83c5a` has
EXECUTOR_MUTATIONS_QUARANTINED=True and first-action guards on patch, execute,
deploy and rollback. Deployed Telegram handler has the disabled /ai_deploy path.
Local autoresearch submits proposals/restricted research jobs, not money changes;
web response text has no execution authority. No additional live flag needed.
File-sourced OPERATOR_USE_API=0/TRADE_REVIEW=0 is not full effective-runtime proof:
dotenv/reload can change process state. Do not infer it from /proc alone.

Local Ollama GET /api/tags at **10:27:36UTC** confirms qwen3:8b, llava and
qwen2.5vl:7b installed; model calls0. A later bounded process snapshot found no
named legacy audit/supervisor/chat workers; this does not exclude other workers.
Continuous project auditing remains NOT_CONFIRMED. The old local chat allowlist
uses August reports, the canonical static AI state is dated July21, and the
canonical audit launcher explicitly holds until snapshot parity exists. Do not
restart that old all-strategy sweep: it can run broad research/evidence readers.

The useful AI next stage is a bounded snapshot/diff reviewer with source dates,
hashes, abstention, dedup and reviewed finding labels. No per-bar model calls,
keys, shell execution, judge consumption, risk writes or autonomous promotion.
Measure confirmed/rejected findings before expanding scope. Self-improvement
means proposal → reproducible challenger → review → paper → owner decision.

## Verification and next gate

**111 PASS**: 77 production dependency/authority tests, 23 quarantine/research/
operator tests and 11 synthetic research tests. One historical-lock test was
deliberately deselected; no full-suite or historical lock/judge rerun.
Warnings: existing passlib crypt deprecation and unregistered slow pytest marker.
Private exact sources, probes, runtime receipts and hashes live at
`.private/os2_foundation_audit_20261007`; public evidence index is the adjacent JSON.
Mechanical reviewer6-luna/medium and financial reviewer6-astra/high verified from
rollout turn_context; supported6-luna explicitly substituted for unavailable
AGENTS5.6-luna. No claim of measured cost saving.

Reviewable first-stage design:
`docs/superpowers/specs/2026-10-07-os2-shadow-bridge-design.md`.
It restores the common orders-OFF admission/journal spine, not another framework.
Implementation awaits written-spec review. B3 research repair goes to Claude;
the owner can use the four source-bound findings above without a blind merge.
KITY first unseen raw OI **Oct7 23:55UTC** and Oct8–9 reconstruction/account
feasibility retain money priority. Alpaca is inspected next cycle as requested.
Cleanup follows USE/TEST/ARCHIVE, dependency inventory, hash/reference and archive
verification; no files were removed. Foreign allowlist remains unstaged with
SHA `add587f1bd7059c2c706f1f7c604e36c2fb7b36b258b127e01fcd2101d3f19a1`.
