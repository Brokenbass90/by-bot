# Research Station v3

Research Station v3 is a local, research-only orchestrator. It does not select a
cache, call an exchange, modify live state, place orders, or promote a candidate.
Its only output is immutable evidence for later human review.

## Run

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
python3 research_lab/station_v3.py \
  --project-root . \
  --config research_lab/configs/my_station_v3.json \
  --runs-root runtime/research/station_v3 \
  --run-id my_family_20260721_a1b2c3d4
```

Use a new, unique `run-id` for a new immutable experiment. Re-run the exact command
with the same `run-id` to resume. To execute a bounded slice, add
`--max-trials 25`; this writes `PAUSED`, never `COMPLETED`, and the next invocation
skips the receipted trials.

Completion is established only by `completion.json` whose manifest hash and ledger
tail match the current run. Text in a `.log` file is never read as state.

## Config contract

All paths are explicit files relative to `--project-root`. Globs are rejected.

```json
{
  "schema_version": 3,
  "authority": "research_only_no_live_or_promotion",
  "promotion_authority": false,
  "runner": {
    "path": "research_lab/my_pure_runner.py",
    "args": []
  },
  "spec_path": "configs/research/my_preregistered_spec.json",
  "code_paths": [
    "strategies/my_candidate.py",
    "backtest/engine.py"
  ],
  "inputs": [
    {
      "name": "BTCUSDT_M5",
      "path": "data_cache/frozen/btcusdt_m5.csv",
      "timestamp_column": "timestamp",
      "timestamp_format": "epoch_ms",
      "interval_seconds": 300,
      "alignment_epoch_seconds": 0,
      "coverage_start": "2024-01-01T00:00:00Z",
      "coverage_end_exclusive": "2026-07-21T00:00:00Z",
      "source_as_of": "2026-07-21T00:05:00Z",
      "finality_lag_seconds": 300,
      "calendar": {
        "kind": "continuous",
        "timezone": "UTC",
        "closures": []
      }
    }
  ],
  "trial_timeout_seconds": 14400,
  "trials": [
    {"id": "fixed_001", "params": {"lookback": 24, "rr": 2.0}},
    {"id": "fixed_002", "params": {"lookback": 48, "rr": 2.0}}
  ]
}
```

For FX/session data, gaps are legal only if the config says the market was closed:

```json
"calendar": {
  "kind": "weekly_schedule",
  "timezone": "UTC",
  "open_windows": {
    "0": [["00:00", "24:00"]],
    "1": [["00:00", "24:00"]],
    "2": [["00:00", "24:00"]],
    "3": [["00:00", "24:00"]],
    "4": [["00:00", "22:00"]],
    "6": [["22:00", "24:00"]]
  },
  "closures": [
    {"start": "2026-12-25T00:00:00Z", "end": "2026-12-26T00:00:00Z"}
  ]
}
```

Windows are half-open `[start,end)` and overnight windows must be split at midnight.
Coverage is also half-open. Every missing interval, including leading and trailing
coverage edges, is checked. `source_as_of` must be at least
`coverage_end_exclusive + finality_lag_seconds`; the lag is a source-specific frozen
policy (for example, `300` adds one full settlement interval after an M5 bar closes).
Station v3 enforces this assertion but cannot independently prove when an upstream
source took its snapshot. An open-market gap, duplicate, unsorted row, misaligned
timestamp, malformed interval, incomplete finality bound, or hash change refuses
the run.

## Runner protocol and isolation

Station v3 adds `--request REQUEST.json --result RESULT.json` to the hashed runner.
The runner must echo the request's idempotency key:

```json
{
  "status": "ok",
  "idempotency_key": "<exact request value>",
  "metrics": {"net_r": 1.2}
}
```

The worker receives a credential-free, locale/timezone/hash-seed-normalized
environment. Network sockets, subprocess/process-spawn APIs, common credential-file
reads, SQLite writes, descriptor-relative writes, and filesystem mutations outside
the per-trial directory are blocked. This is a fail-closed guard for ordinary
research code, not a security boundary against intentionally malicious native
extensions.

The immutable manifest hashes the Station code, worker, Python executable, config,
runner, spec, listed code files, and every input CSV. Changing any one requires a
new run id. A recorded integrity refusal is terminal even if old bytes are later
restored. Runner
exceptions, timeout, non-zero exit, missing/malformed output, and key mismatch create
a failed receipt and stop the run; they are never converted to an empty signal.

Inputs remain path-based rather than copied into the run tree. They must therefore
be quiescent frozen files: Station v3 hashes before/after validation and around each
trial, but no path-based checker can prove that a file was not changed and restored
entirely between two observations.

This is local tamper evidence, not an external notarization: a party able to rewrite
the whole run tree can rewrite local hashes too. The runner must be deterministic and
all imported research code/dependencies that can affect results must be pinned or
listed; Station v3 does not prove semantic purity of arbitrary runner code.

## Evidence layout

- `manifest.json`: immutable intent and file hashes;
- `trials.jsonl`: hash-chained, logically append-only trial ledger;
- `receipts/<idempotency-key>.json`: atomic authoritative trial receipt;
- `trial_work/...`: request, result, stdout, and stderr with hashes in the receipt;
- `checkpoint.json`: atomic state whose manifest identity and ledger prefix are
  validated before resume;
- `completion.json`: manifest-bound completion proof;
- `*_failure.json`: explicit fail-closed exception/integrity evidence.

Run the focused contract tests with:

```bash
python3 -m pytest -q tests/test_research_station_v3.py
```

## Research Conveyor V1: a separate readiness queue

Research Conveyor V1 is adjacent to Station v3, but it is **not** a Station
v3 run and its receipts are not interchangeable with Station receipts.  Station
v3 uses its own config contract and can resume the same immutable `run-id`.
Conveyor V1 declares the exact policy and receipt authority
`research_only_no_live_risk_order_promotion_or_private_api_authority`. Every
invocation requires a **new path that does not already exist**; any existing
path, including an empty one, is refused rather than resumed.

The executable queue is
`configs/research/research_conveyor_v1.json`.  Its initial `manifest_sha256`
(SHA-256 of the canonical JSON payload, not a raw manifest-file hash) is
`3acee610628448efda834b17e847ab7291013c142154dc9e8929597fa49e26cb`.
It contains ten strategy families, all initially blocked and therefore no
runnable adapters.  The canonical manual preflight is
`runtime/research_conveyor/manual_20260901_v3/terminal_receipt.json`; its
embedded self-hash is
`b4523610e1f9938bd7aa1f5c954ae02f05225cf54870b5d77a2cc8e5c5ed5c22`.
It records ten terminal receipts: three `BLOCKED_DATA_OR_PARITY`, seven
`BLOCKED_ADAPTER`, and zero phase receipts, phase logs, or adapter launches.

Run Conveyor only from the canonical checkout and choose a fresh directory for
every command:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824

# Validate the manifest and publish readiness receipts without adapters.
python3 scripts/run_research_conveyor.py \
  --config configs/research/research_conveyor_v1.json \
  --run-dir runtime/research_conveyor/manual_<UTC_UNIQUE>_dry \
  --dry-run

# Publish the formal preflight; this also launches zero adapters.
python3 scripts/run_research_conveyor.py \
  --config configs/research/research_conveyor_v1.json \
  --run-dir runtime/research_conveyor/manual_<UTC_UNIQUE>_preflight \
  --preflight

# Only after a card has a reviewed hash-bound four-phase adapter: run it.
python3 scripts/run_research_conveyor.py \
  --config configs/research/research_conveyor_v1.json \
  --run-dir runtime/research_conveyor/manual_<UTC_UNIQUE>_run \
  --run
```

`BLOCKED_*` is a valid terminal readiness verdict, not a failed experiment and
not a result.  `PASS_DIAGNOSTIC` means only that all four frozen research
phases passed their diagnostic contract.  Neither verdict authorizes shadow,
paper, capital, promotion, live configuration, risk, orders, broker calls, or
private API access.  The initial queue has no `RUNNABLE` card, so all three
commands above launch no adapter today.  No scheduler, LaunchAgent, or cron is
installed by this change; a scheduler can only be proposed after a manual run
and an independent audit.

This authority is a policy and receipt contract, **not** an OS sandbox. The
runner uses `shell=False`, a stripped environment, and hash-bound reviewed
script paths, but it does not technically block sockets, credential-file reads,
or arbitrary subprocess side effects. The canonical preflight is safe because
it has zero `RUNNABLE` cards and launched zero adapters. A future `--run` is
permitted only after separate adapter review proves research-only behavior with
no network, private, live, broker, order, or risk side effects; Station v3
isolation or an equivalent guard should be used when stronger enforcement is
required.

For a compliant reviewed research adapter no external rollback is expected. Do
not overwrite, remove, or reuse the existing receipt tree: retain it as
evidence and simply do not launch another Conveyor invocation. A corrected
manifest or adapter needs a new scoped commit and a new path that does not
exist. If an adapter causes side effects despite review, treat it as an
incident: reconcile the external systems first, because receipts alone cannot
roll back those effects.

The first adapter-conversion queue is deliberately narrow:

1. shared deterministic controls and data-parity contract for XSEC;
2. Bull Continuation detector and execution adapter on frozen inputs;
3. independent causal XAU data/cost parity, then its adapter.

Each conversion must add its own frozen contract, adapter bytes in
`contract_refs`, focused tests, manual receipt, and review before its manifest
card changes to `RUNNABLE`.
