# Bounce Claude source handoff — 2026-10-11

Status: `BLOCKED_RESEARCH_SOURCE_CONTRACT`. This is a source-only bounce intake. No prices, funding rates, signals, trades, outcomes, strategy run, judge, config edit, or money authority is included.

The bound universe is the existing majors baseline, `BTCUSDT` and `ETHUSDT`. The eight-symbol prereg remains a separate hypothesis. The existing baseline/config/cost assumptions are frozen: next-open execution, fee `6 bps/side`, slippage `2 bps/side`, with the source and config hashes in `reports/evidence/bounce_claude_handoff_20261011/manifest.json`. These are historical assumptions, not current-account cost evidence.

The immutable v2 derived packet has `31,635` H1 rows and `7,908` complete UTC H4 bars for each symbol. Timestamps are opening timestamps. Prices are widened from stored float32; this does not restore exchange precision. Three leading H1 rows are excluded from H4 because the source begins at 01:00 UTC. No shifted bucket or incomplete trailing H4 is asserted. The packet is closed-prefix derived data; raw M5 provider, assembly, publication, and point-in-time lineage are `UNKNOWN`.

Funding archives are present and hash-bound for BTC/ETH. The broad archive has `3,958` rows per symbol through `2026-08-12 00:00 UTC`, as-of `2026-08-12 07:37:18.343 UTC`. The narrower archive has `3,012` rows per symbol through `2025-09-30 16:00 UTC`. A directory name such as `preholdout` does not establish holdout independence. Funding debit/credit, timestamp matching, missing-data behavior, and held-position coverage remain `UNAPPROVED`; missing funding is not zero. No funding-rate distribution or outcome was read into this handoff.

Before Claude preregisters baseline versus any causal context and its KEEP/KILL rule, Claude must declare and hash the concrete inputs:

1. A versioned funding treatment contract: debit/credit sign, settlement timestamp alignment, missing/partial coverage behavior, and the archive/version used for every held interval.
2. The raw M5 provider identity and retained raw files or manifest, assembly/deduplication rules, publication/availability timestamps, and the H1/H4 point-in-time derivation receipt. The current packet's declared twelve M5 children per H1 is not raw lineage proof.
3. A complete discovery/consumption ledger for candidate historical windows, plus an admissible validation interval with source hashes and an independence statement; alternatively, a genuinely frozen forward start after all inputs are fixed. Existing declared windows are contaminated candidates, not certified unused data.
4. The baseline and causal-context source/config identities, context availability rule and publication timing, comparison population, and predeclared KEEP/KILL/judge inputs. Claude must supply these declarations without selecting a context, threshold, new validation outcome, or result in this handoff.

Missing/unknown source items are recorded explicitly in the manifest. No SSH/network access, Claude checkout change/message, root canonical-file edit, Alpaca edit, or strategy/judge execution was performed.
