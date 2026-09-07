# LAB_AI_V0 — read-only evidence assistant design

Date: 2026-09-06
Status: owner-approved architecture. Subsequent owner instructions authorize
safe read-only research implementation without another routine approval;
implementation remains planned, not a running LAB_AI_V0 result.
Canonical tree: `bybit-bot-recovery-20260824`
Branch: `codex/recovery-20260824`

## Outcome

Build a useful local laboratory assistant on top of the existing deterministic
audit, Trial Ledger and Research Conveyor. The assistant retrieves verified
project evidence, calls explicitly allowlisted read-only tools, detects
conflicts and proposes falsifiable experiments. It does not predict prices,
grade its own work, change code/configuration, run arbitrary commands, contact
brokers, or receive order, risk, promotion, deployment or money authority.

The first useful product is a quant-research assistant, not an autonomous
trader. Fine-tuning and market perception are later, separately gated layers.

## Why this is the selected approach

Three approaches were considered:

1. Build a thin evidence-grounded vertical slice and expand it only after an
   evaluation set proves value. This is selected because it can reuse Ollama
   and existing project registries while the money path continues independently.
2. Install the full MLX/Qdrant/DuckDB/MLflow/Optuna stack immediately. This has
   a larger initial surface, duplicates existing infrastructure and delays the
   execution-parity path.
3. Postpone local AI until the bot earns money. This avoids engineering cost but
   leaves repetitive evidence triage on paid models and loses a safe source of
   parallel productivity.

## Authority boundary

Exact V0 authority:

`local_readonly_secret_free_proposal_only_no_code_config_process_network_broker_order_risk_promotion_deploy_or_money_authority`

The model may:

- retrieve allowlisted, non-secret evidence;
- compare exact receipts through deterministic tools;
- group already materialized failures and anomalies;
- identify stale or contradictory claims;
- propose at most a bounded number of falsifiable next experiments;
- draft reports whose factual claims cite exact source paths and hashes.

The model may not:

- read `.env`, credentials, private broker payloads or unrestricted logs;
- generate a shell command that is executed automatically;
- write to the repository, runtime, registry or deployment directories;
- change an experiment, verdict, strategy stage, parameter, risk or authority;
- call public or private network APIs;
- declare profitability or promotion from its own text.

All model output is untrusted proposal data. Deterministic code and source
receipts remain authoritative.

## Existing components to reuse

V0 is not a new laboratory from scratch. It builds on:

- `research_lab/continuous_audit.py` and `research_lab/audit_registry.py`;
- `research_lab/negative_outcome_registry.py`;
- `research_lab/experiment_lifecycle.py` and the Trial Ledger;
- Research Conveyor manifests and terminal receipts;
- `reports/OLLAMA_ROUTINE_BOUNDARY_2026_08_27.md`;
- canonical Store and ATT1/ETS2S parity/deployment receipts;
- existing local Ollama `qwen3:8b` as the initial inference model.

Existing audit output is evidence to index, not permission to trust every old
claim. Inputs must pass path allowlisting, schema checks, freshness checks and
hash capture before retrieval.

## Architecture

```text
allowlisted reports / preregistrations / ledgers / receipts
  -> deterministic evidence catalog
  -> structured facts + rebuildable text chunks
  -> read-only retrieval and comparison tools
  -> local Ollama model
  -> cited proposal receipt
  -> human labels: confirmed / rejected / duplicate / needs_data
```

### Deterministic evidence catalog

One manifest lists permitted roots, file classes, schemas, maximum sizes,
freshness expectations and redaction rules. Collection fails closed on symlink
escapes, unexpected file types, invalid JSON, duplicate keys, non-finite
numbers or a path outside the allowlist.

Every catalog row records source path, source SHA-256, observed timestamp,
schema/type and whether the content is current, superseded or contradictory.
The catalog never silently resolves a conflict.

### Storage

Source files and existing hash-bound ledgers remain the truth. Derived stores
are disposable and reproducibly rebuildable:

- DuckDB is the first structured query/index layer for receipts, metrics,
  experiment lineage and later Parquet market data;
- text chunks retain path, SHA, section and line provenance;
- Qdrant is added only for the semantic-retrieval slice after exact and lexical
  retrieval have a measured baseline;
- Polars is reserved for large lazy/streaming market-data transformations, not
  required for the first assistant answer;
- DVC or MLflow is a later experiment-artifact integration, not a second source
  of project truth.

### Read-only tools

The model receives typed functions rather than filesystem or shell access.
Initial tools:

- `get_current_project_state()`;
- `get_trial(experiment_id)`;
- `compare_trials(experiment_ids)`;
- `find_similar_failures(query, filters)`;
- `get_shadow_health(shadow_id, time_range)`;
- `find_status_conflicts(subject)`;
- `draft_experiment_card(hypothesis, falsification)`.

Tools return bounded JSON with source citations. They cannot mutate files,
launch processes, call a broker or access secrets. A proposal is stored by a
separate deterministic wrapper only after schema validation; the model itself
does not write it.

### Answer contract

Every answer separates:

1. verified facts with path/SHA citations;
2. conflicts or stale evidence marked `NOT_CONFIRMED`;
3. inference explicitly labelled as inference;
4. proposed next test and its falsification condition;
5. forbidden conclusions, including money or promotion decisions.

Numeric claims without a source receipt are rejected by the answer validator.

## Delivery phases

### V0A — deterministic context pack

Implement the previously designed bounded routine digest in the canonical tree:
safe source manifest, freshness/hash/schema collection, redacted bounded tails,
immutable input/output receipts and one bounded Ollama call. No vector database
is required yet.

### V0B — evidence retrieval

Build the derived DuckDB catalog, exact/lexical retrieval and conflict search.
Establish retrieval accuracy before adding Qdrant. Add Qdrant only if semantic
queries materially improve the frozen evaluation set without weakening source
provenance.

### V0C — typed laboratory tools

Expose the allowlisted read-only functions above. The model cannot choose an
arbitrary function name, path or command. Tool results and final proposals are
immutable, timestamped and hash-bound.

### V0D — evaluation and quiet operation

Create a frozen evaluation set containing current-state questions, superseded
claims, conflicting metrics, repeated experiments, cost-killed edges, data
leaks and secret/capability attacks. Only after this gate may V0 run on a quiet
schedule or serve interactive project questions.

### V1 — researcher adapter

Capture human-reviewed V0 examples in `train.jsonl`-compatible form. MLX-LM
QLoRA becomes eligible only after at least 500 reviewed training examples and
100 untouched evaluation examples exist. The first adapter classifies research
quality (`VALID_TEST`, `DATA_LEAK`, `COST_ARTIFACT`, `DUPLICATE`,
`NEEDS_EVIDENCE`); it does not forecast price.

PEFT/TRL is the future server training stack. An adapter must use the exact base
model it was trained against, pass the same frozen evaluation set and remain
proposal-only.

## Acceptance gates

V0 is useful only when all are true:

- 100% of numeric factual claims in the frozen evaluation have resolvable
  source path/SHA citations;
- zero secret-canary disclosure and zero accepted mutation/capability escape;
- stale or contradictory sources produce `NOT_CONFIRMED`, never a guessed
  resolution;
- deterministic tools reproduce their results without the model;
- the model cannot alter a trial, verdict, config, process or authority;
- at least 30 model proposals receive human labels before precision is reported;
- evaluation reports both false positives and false negatives, not only good
  examples;
- resource caps keep the assistant from starving market-data collectors or VPS
  shadows.

Failure keeps the system proposal-only and returns the failing receipt. It does
not trigger self-repair.

## Relationship to the money path

`LAB_AI_V0` never blocks or promotes ATT1/ETS2S. The money path remains:

`72h L1 burn-in -> L2 execution lifecycle parity -> L3 fees/funding/accounting -> zero-risk lifecycle shadow -> owner-gated micro-canary`.

V0 may be implemented in parallel by lighter models from scoped tasks. Strong
model review is reserved for evidence semantics, capability boundaries,
evaluation design and promotion interpretation.

## Later project: Market Perception Engine

Market Perception is deliberately separate from V0. Its future pipeline is:

`Market State -> Pattern Memory -> Regime/Drift -> Strategy Experts -> Meta Gate -> Shadow`.

It will encode causal multi-timeframe state, retrieve historical analogues and
estimate outcome distributions with uncertainty. It may initially say
`TAKE/SKIP` for an existing setup only in research/shadow. Training, replay,
matched controls, drift evaluation and prospective shadow are required before
any money gate. No nightly model may retrain itself and trade the new version
the next morning.

## Explicitly deferred

- price-prediction LoRA;
- autonomous code repair or experiment promotion;
- unrestricted RAG over the whole filesystem;
- automatic Optuna promotion or optimization against OOS;
- broker/network tools;
- news, execution and market LoRA adapters;
- replacing deterministic random controls, cost models or independent audits
  with an LLM verdict.
