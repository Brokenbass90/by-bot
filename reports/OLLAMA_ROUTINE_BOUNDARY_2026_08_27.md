# Ollama routine boundary — current truth and safe expansion

**Snapshot:** 2026-08-27. **Authority:** local, proposal-only, no capital,
orders, deploy, promotion, or unreviewed code mutation.

## What is actually running

The active supervisor currently runs from the legacy workbench
`bybit-bot-clean-v28`, not the canonical `bybit-bot-recovery-20260824` tree.
Its latest station status reported `6/6` healthy research jobs. The active audit
cycle calls Ollama about once every six hours. Installed local models observed by
the read-only audit were `qwen3:8b` and `qwen2.5vl:7b`.

Ollama is not the research engine. The deterministic layer first finds structural
facts such as stale evidence, unreachable tested modules, stopped collectors, and
research tools without self-tests. Qwen receives a bounded digest and may return
at most three falsifiable hypotheses. It does not receive money authority.

The current registry has 389 historical/current records, 228 current rows and
three actionable rows. The frequently quoted `219` is a count of accumulated
deterministic audit candidates in an older ledger, **not 219 confirmed bugs found
by Qwen**. At the current snapshot there were no confirmed or rejected model
candidates, so the model's precision has not yet been measured.

## Correct division of labour

| Routine | Deterministic component | Ollama role | May mutate? |
| --- | --- | --- | --- |
| frozen runs/tests | Station v3 or an exact allowlisted runner | explain completed receipts | no |
| SHA/file parity | hash manifest and verifier | summarize a mismatch | no |
| JSON/CSV/table reconciliation | schema-aware diff and arithmetic validator | classify likely meaning | no |
| logs | bounded, secret-redacted parser | group anomalies and propose falsification | no |
| reports/checklists | evidence assembler | draft a concise narrative | draft only |
| UI | screenshot/spec/test artifacts | critique usability | no direct production edit |
| config/risk/orders | exact gate and owner release | no decision role | forbidden |

The model must never compose an arbitrary shell command that is then executed.
Allowlisted code launches a frozen command; Qwen can only comment on its receipt.

## Missing pieces before adding more routine

1. Select one runtime root. Moving the currently healthy processes is a separate
   controlled operation; until then, canonical code changes do not alter the
   running auditor.
2. Build one deterministic, secret-free `routine_digest` with an explicit source
   allowlist: hashes, mtimes, receipt freshness, test receipts, schema-aware table
   diffs, and bounded redacted log tails.
3. Store every digest and every model answer as a timestamped immutable receipt.
   The current daily output can be overwritten by a later empty cycle, which
   weakens observability.
4. Add a human review ledger: `confirmed`, `rejected`, `duplicate`, `needs_data`.
   Report Qwen precision only after at least 30 reviewed hypotheses.
5. Keep the old nightly strategy queue stopped until every enabled task is
   reclassified. Its current allowlist contains legacy parameter sweeps; an
   allowlist alone does not make an experiment scientifically valid.

## Recommended next implementation package

This is suitable for a lighter Codex/Claude implementation after the current
ATT1/SBR1 preflight package is committed:

1. `configs/local_ai_routine_digest_v1.json` — explicit safe paths and size caps;
2. `scripts/build_local_ai_routine_digest.py` — deterministic collection and
   redaction, no model call;
3. `scripts/classify_local_ai_routine_digest.py` — one bounded Ollama call,
   maximum three proposals;
4. schema/invariant tests proving no credentials, commands, private APIs, or live
   mutation can enter either receipt;
5. one supervisor job in the selected canonical runtime tree.

This extension can absorb log triage, report condensation, documentation and
table explanations. It should reduce paid-token use without pretending that an
8B local model can validate financial evidence or safely repair production alone.
