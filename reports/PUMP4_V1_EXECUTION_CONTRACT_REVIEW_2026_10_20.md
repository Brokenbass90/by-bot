# PUMP4 V1 — bounded pre-execution review, 20 October

**HISTORICAL REVIEW OF88f42ac — SUPERSEDED FOR IMPLEMENTATION.**

Evening20Oct: owner accepted published contractb138735 + request7b0a961. Both
are verified ancestors of fresh origin7e1ab0b. Declared source blobs match, the
missing helper and shadow producer are published, and the versioned contract
explicitly fixes.40/.60, two targets, static x4 stop,168H1 bars, no BE/trail and
137 current symbols.65 OK reference decisions plus one unavailable ASTER case
are provided. These source/spec blockers are CLOSED for starting the adapter.
Actual replay/parity/restart/broker acceptance remain NOT_RUN. Use the new
contract, not the obsolete.55 texts or the historical blockers below.
[Verified replacement receipt](evidence/pump4_execution_intake_20261020/versioned-contract.json).

Historical findings against88f42ac:
The published prereg result is preserved; no judge, returns simulation or new
outcomes were run. One independent astra/high source review, actual runtime
verified, produced18 deterministic offline assertions. These checks establish
implementation discrepancies, not strategy/execution PASS.

| Item | Source-backed result | Required resolution |
|---|---|---|
|137 vs138|Extra `BTCUSDT_B21.npz` is a historical BTC DEV archive added17Oct; the previous137 filenames are recovered exactly|Root cause CLOSED. Version the explicit137 list instead of a mutable glob; reconstructed manifest attached|
|TP fraction|Default signal first fraction is.40; evaluator uses the signal fraction, so.55 fallback is unused. Document declares.55|Publish actual effective run config and one unambiguous V1 mapping. Codex must not choose either fraction silently|
|Lifecycle|Evaluator uses first2 absolute targets, remaining quantity at TP2, static widened stop,168H1 bars, no BE/trail. Raw signal also contains3targets/48bar stop/trailing1.4|Do not pass raw TradeSignal to a generic manager; pin the evaluated mapping|
|Published source closure|`pereschet` imports missing `pervyy_argument`; original `ten_pump4.py` is not published|Publish actually used helper/producer bytes and their hashes, without inventing a substitute or overwriting the original verdict|
|Config|Strategy reads `PF_*`; request/pereschet set ineffective `PUMP4_*`; ambient PF could alter defaults|Pin effective parameters/environment and explicit universe|
|Cooldown/state|Every invocation decrements cooldown, including repeated timestamp; reset loses state|Per-symbol durable history/cursor/cooldown, exactly-once closed-bar processing; seven actual cases still need source-identical replay|
|Timing/bootstrap|Closed-prefix logic is conditionally causal; exact next-open price is a model. A200-bar Store does not preload this strategy's internal state|Specify observed close, eligibility/delay/gap handling and exact bootstrap cursor; never backdate a late fill|
|Terminal classifier|Last available bar with a real terminal is indistinguishable from truncated last-close fallback in current helper|Version research semantic repair; Codex does not recalculate/replace the published result|

These are V1 correctness/source questions, not V2 optimization. InPlay, new
funding/OI filters, breakeven and trailing remain separate research work.
The next research handoff should be a small versioned source/config/mapping
closure plus immutable decision fixtures. It does not require a new framework
or another arbitrary waiting period. Claude owns that clarification; Codex owns
adapter/parity/recovery and instrument/risk acceptance afterward.

Existing Bybit candidates provide request, exact dispatch, native stop,
reconciliation and restart primitives. Their KITY financial caps/GO, basket and
hold semantics must not be inherited. Existing Elder data validation patterns
can be reused, its.55 hedge/offset-limit/reanchoring cannot.

## Risk scenarios requested by owner — arithmetic only, not broker acceptance

For an initial single-position pilot, proposed aggregate nominal stop risk is r;
research's proposed -2r day / -3r week / -6r review thresholds give:

|Nominal r/trade|Max concurrent|Aggregate nominal stop risk|Day new-entry stop|Week new-entry stop|Drawdown review|
|---|---|---|---|---|---|
|1USDT|1|1USDT|2USDT|3USDT|6USDT|
|2USDT|1|2USDT|4USDT|6USDT|12USDT|
|3USDT|1|3USDT|6USDT|9USDT|18USDT|

All are **UNAPPROVED**. The table does not prove minimum-size feasibility or a
maximum realized loss: actual lot/tick, gap/slippage, fees, funding, leverage and
margin must be measured on a pinned plan. Until those checks, no scenario is
selected and no claim that1USDT is attainable for every instrument is made.
Loss thresholds halt new entries; they cannot undo an already incurred gap loss.

Money queue unchanged: Monthly active engineering first; PUMP4 V1 next. No real
PUMP4 order, financial unit, source epoch, research code or owner permission changed.

[Full source review and18 assertions](evidence/pump4_execution_intake_20261020/source-review.md),
[machine evidence](evidence/pump4_execution_intake_20261020/source-review.json),
[reconstructed137 manifest](evidence/pump4_execution_intake_20261020/universe-137.json).
