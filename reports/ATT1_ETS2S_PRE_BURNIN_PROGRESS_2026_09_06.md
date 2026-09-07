# ATT1/ETS2S — progress before the burn-in boundary

## Current status — 2026-09-06T14:17:56.950Z

The owner explicitly authorized the exact onsite in-memory evaluator run. It
succeeded with aggregate-only output: raw signal data stayed on the VPS, no
remote file was written, and the deployed shadow was not modified. The exact
receipt is
`research_lab/results/att1_ets2s_burnin_20260906/onsite_receipt_20260906T141756Z.json`.

Status is `IN_PROGRESS`: 31 completed slots, 30 required after the completion
grace, zero missing required slots, 34 cycle receipts, zero duplicate
invocations, and two zero-row idempotent invocations. The journal contains
3,202 rows (3,100 forward plus 102 bootstrap) and 24 total raw signals across
the whole journal (the receipt does not expose a forward-only split). The
current receipt does not provide a sleeve split; no current ATT1/ETS2S split is
asserted here. Maximum observed service duration is 389,404 ms.

The burn-in evaluation remains earliest `2026-09-08 08:02 UTC`. Runtime release
SHA remains `773ce065270b5df16041e49e0985c5e950e5da10`. The prior first receipt
and its `FAIL_CLOSED` result remain preserved as historical evidence of the UTC
alias bug; the corrected evaluator has 34 passing evaluator tests.

The old pending-permission status below is superseded by this section.

## Historical snapshot — 2026-09-06 08:42:07 UTC

Snapshot: 2026-09-06 08:42:07 UTC. Canonical tree/branch remain
`bybit-bot-recovery-20260824` / `codex/recovery-20260824`.

## Outcome and current stage

The current ATT1/ETS2S release has a healthy L1 signal process, not a proven
money strategy. The shortest useful path is still operational burn-in → L2
execution lifecycle → L3 net accounting → clean zero-risk lifecycle → an
explicit owner-gated micro-canary. The VPS release was not modified.

The burn-in clock remains 2026-09-05 08:02 UTC to evaluation no earlier than
2026-09-08 08:02 UTC (11:02 Cyprus). Calendar completion alone is not a PASS.

## VPS facts refreshed, without reopening old research

The read-only server check exported fixed-key counts, timestamps, booleans
and hashes only. Its exact checker and result are preserved in
`research_lab/results/att1_ets2s_burnin_20260906/`.

| Observed fact | Result |
|---|---:|
| Scheduled forward cycles through 08:02 UTC | 25/25 |
| Forward decisions | 2,500 |
| Bootstrap decisions | 102 |
| Journal total | 2,602 |
| ATT1 / ETS2S raw forward signals | 6 / 15 |
| Side of those 21 raw signals | short |
| Missing hourly slots through latest cycle | 0 |
| Journal exceptions / nonzero authority-call fields | 0 / 0 |
| Cycle receipts / unhealthy receipts | 28 / 0 |
| Zero-row idempotent invocations | 2 |
| Observed service failure log events | 0 |
| Full journal chain and heartbeat tip | valid / matching |
| Manifest source files | 18/18 hashes match |
| Enabled config, manifest, launcher hashes | match deployment pins |
| Current free VPS disk | 7,617,019,904 bytes |

The new timer is active/enabled. Both legacy shadow timers were separately
checked active. Each forward cycle contains 100 decisions, 50 per sleeve;
HFTUSDT is still configured/available but unchanged. Signal rows are not
independent trades and do not establish profitability.

Runtime SHA stays `773ce065270b5df16041e49e0985c5e950e5da10`. The current money
broker/position state was not re-audited in this bounded cycle; no current
claim about its positions or PnL is made here.

## Delivered work

1. `research_lab/att1_ets2s_burnin.py` and
   `scripts/evaluate_att1_ets2s_burnin.py`: local read-only evaluator with strict
   input parsing, source/config/journal binding, per-sleeve symbol coverage,
   hourly-slot accounting, receipt-emission and invocation provenance, latest
   heartbeat reconciliation, resource observations and authority zeros.
2. `tests/test_att1_ets2s_burnin.py`: synthetic valid 72-hour case and
   adversarial failures. Independent strong-model review reproduced three
   false-PASS bugs in the initial implementation; all were repaired and their
   regression tests passed. Both in-memory and offline entry points share
   the same verification core. CLI receipt creation refuses overwrite.
3. `docs/superpowers/specs/2026-09-06-att1-ets2s-l2-l3-contract.md`: specific
   lifecycle/accounting specification and build order, independently reviewed.
   The review corrected protective exits during partial entries, event-time
   realized accounting after late fills, and float quantity dust.
4. `docs/superpowers/plans/2026-09-06-lab-ai-v0-implementation.md`: delegated
   LAB_AI plan, with V0A tasks 1–3 as the first usable slice, exact resource
   caps and deterministic technical gates. No model was trained or launched.
5. `reports/BOUNDED_EDGE_RESEARCH_2026_09_06.md`: bounded primary-source review
   of execution replay, an existing funding/basis screen, and independent
   Market Perception baselines. These are experiment proposals, not results.

Verification: **134 passed** in the combined focused suite (34 evaluator
tests plus the original 100 L1/release/Store tests). The machine record is
`research_lab/results/att1_ets2s_burnin_20260906/local_verification.json`.
No remote full-evaluator PASS is claimed.

## Findings that change the next implementation

- The runner records cycle-start observation, not per-signal readiness. The
  latest checked cycle ran from 08:02:00 to 08:08:23. Maximum observed service
  duration was 385835 ms. L2 must record ready/submit/fill times and cannot use
  an earlier H1 close or already-past next-open as an executable price.
- ETS2S L1 limit metadata says 0.2% and six bars, but its execution clock and
  cancellation semantics are not source-bound locally. L1 output also omits
  BE/trailing fields. Resolve the full execution profile before claiming L2
  parity; old sealed economics cannot fill that gap.
- A reproduced float issue in the existing target-close helper turns an
  intended 0.2 remainder into 0.19999999999999998 and can leave a 0.1-sized
  residual. The new L2 reducer will use Decimal/integer steps. The existing
  money helper was not patched or deployed in this cycle.

## Evaluation execution boundary

Status: `IN_PROGRESS`.
The owner-authorized onsite in-memory aggregate receipt is valid within its
stated scope; raw data stayed on the VPS and no shadow change was made.

Automatic approval review first rejected exporting the raw snapshot because
of potentially sensitive VPS payload. The narrower onsite-in-memory
alternative was authorized and completed: raw data stayed on the VPS and only
the aggregate receipt left it. The earlier rejected actions were not executed.

Prepared onsite command (only after that permission):

```bash
ssh -i /OWNER_HOME/.ssh/by-bot \
  -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 \
  root@64.226.73.119 'python3 -' \
  < research_lab/results/att1_ets2s_burnin_20260906/onsite_evaluate.py.txt
```

The payload consists of the exact evaluator, read-only fixed-path collection
and original deployment receipt; it writes no remote file and performs no
service/order/risk action. Its SHA256 is
`5a53aa33771a575197aa034c650f3417b86397852947f9fea60dcb0c4b823321`.

For an already authorized local snapshot, the offline command is:

```bash
.venv/bin/python scripts/evaluate_att1_ets2s_burnin.py \
  --snapshot-dir /absolute/path/to/authorized_snapshot \
  --deployment-receipt research_lab/results/att1_ets2s_vps_shadow_20260905/deployment_receipt.json \
  --output /absolute/path/to/new_receipt.json
```

At the boundary, collect after a service invocation finishes. Require all 72
hourly slots in the half-open burn-in interval, elapsed time at/after endpoint,
complete receipts and current health. Missing historical peak RAM is reported
as unavailable; it is not an invented post-hoc gate. CPU/duration/current disk
and the deployed per-cycle disk guard remain explicit resource evidence.

## Next bounded cycle

Use the completed aggregate receipt as the current operational evidence. In
parallel, implement L2 IDs/admission/partial-exposure state using synthetic
fixtures and the reviewed contract; no L1 redeploy. Recover the ETS2S wait
clock/full geometry from source specifications, without reading sealed
outcomes. Then build L3 event-time fee/funding cash accounting and independent
oracle fixtures. Keep economic hypotheses and execution-model sensitivity
separate from arithmetic parity. Freeze economic gates before the next new
evaluation cohort; neither raw cadence nor operational PASS authorizes money.
