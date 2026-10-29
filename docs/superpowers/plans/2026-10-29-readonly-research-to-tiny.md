# PUMP4 read-only observation and one-candidate Research → TINY plan

> For agentic workers: use superpowers:executing-plans; execute inline with TDD and one bounded final critical review.

Goal: deliver actual PUMP4 facts to a separate Brain observation journal and run a minimum intake on the existing KITY shadow packet. No new trading engine.

Spec: current owner attachment 6d6177e3-a983-4796-ab8f-4bd5f9e5f939; existing PUMP4 scope fec235e3…fcf794 and Monthly v6 remain unchanged. Owner asks implementation, not another architectural audit; continue in existing codex/recovery-20260824 branch and preserve foreign allowlist.

Global constraints:
- No broker POST/PATCH/DELETE, GO creation/extension, financial owner/lease constructors, strategy changes, sealed judges/outcomes, source journal repairs, service/cron changes or research code edits.
- Source capture reads bytes only from the exact selected PUMP4 packet/runtime and validates source pins. Local destination is independent from production and source paths.
- Reuse BrainEventJournal/ShadowJournal durability; shard by stable event-ID prefix to respect existing 4096-row/8MiB limits.
- Actual receipt IDs remain stable across snapshot/restart; new later outcomes/advice are separate observations, never revisions of old facts.
- Missing/late/unversioned advice is UNKNOWN, not a successful Brain decision. Hypothetical outcomes stay MODEL_ONLY. Positive costs/finality are never inferred from missing records.
- Expiry NO_TRADE needs a fresh post-deadline capture and empty durable financial history. Before deadline report WAITING; never extend authority.
- KITY: use original 5L/5S, no padding/retuning. Published dossier helper still says 4L/4S: report drift, do not silently fix producer. Economic INCONCLUSIVE blocks money independently of engineering PASS.

Task1: add file-only PUMP4 observation adapter, CLI and tests.
Files: research_lab/pump4_live_observer_v1.py; scripts/import_pump4_live_observer_v1.py; tests/test_pump4_live_observer_v1.py.
- RED tests: source/config/scope pins; stable receipt import/replay; corruption/path aliases; partial journals; stable shard capacity; expiry pre/post/deferred custody; no future/backdated advice promotion; actual facts distinguished from model/cost finality.
- Implement secure capture reader; reuse existing BrainEventJournal for receipt facts + separate lifecycle snapshot, advice coverage and expiry status. No Brain policy execution.
- GREEN targeted tests; negative CLI/default no-network behavior.

Task2: one KITY intake profile, not a generic executor.
Files: research_lab/research_tiny_intake_v1.py; scripts/prepare_research_tiny_intake_v1.py; tests/test_research_tiny_intake_v1.py.
- RED tests: exact source manifest/known captured symbols; 8-vs10 contract drift; incomplete gates never READY; rounding/notional constraints and full per-leg fees/funding; active single-owner conflict; missing economic proof and new GO always block money; no outcome use.
- Implement normalized file-only dossier checks reusing accepted signal/C2 evidence and existing quantity/depth primitives where applicable. Freshness/account/margin/native gates are explicitly separate.
- GREEN tests. Run on actual already-opened KITY22Oct packet; do not run judge or read future outcomes.

Task3: actual evidence/delivery and closeout.
- Acquire bounded original PUMP4 receipts/scope/flow prefixes with GET/file-only source checks. Import once + replay into separate local Brain data directory. Advice snapshots remain research inputs with exact source-time bounds.
- Record sampled status coverage separately from strategy opportunity completeness. Actual first-fill/fees/outcome unavailable => UNKNOWN.
- Validate existing Monthly unchanged and PUMP4 expiry. Prepare reusable expiry report; if current source is pre-deadline leave real expiry gate pending.
- One critical review of final changed files/evidence, fix confirmed issues, rerun affected tests. Commit/push report + exact SHA and update canonical checkpoint.

Review focus: live-history capture race; retroactive advice timestamps; stable IDs under later snapshots; source/target alias and journal uncertainty; fail-closed economic/account ownership gates. No extra research families/frameworks.

Implementation refinement: stable event-ID prefix buckets replace the proposed hour buckets. A regression demonstrated that changing source time otherwise moves an existing identity to another shard, evading conflict detection. Source UTC time remains an immutable event field.
