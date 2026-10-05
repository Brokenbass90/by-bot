# ETS2M — guarded one-shot October10 evaluator

**ARMED_LOCAL_ONE_SHOT**, due **October10 19:00UTC /22:00 Cyprus**, PID46460
with held writer lock at launch. This process needs no Codex API or quota.
No cron/launchd/login item was installed. Mac must stay powered and awake;
logout/reboot/process termination can prevent execution. It is not a VPS job.
The current research map has conflicting counts1169/1004 and a VPS label;
actual local entry inventory was1461, not a maturity verdict. No collector moved.

The evaluator was found in ignored local `research_lab/yadro.py`, not a committed
research object. Its fullSHA beginsb413a48f67158ccb, matching the saved original
ETS2M epoch. Strategy6439db1f9df4f728 and configuration4b461ab97e44daf5 match too.
Prereg, cluster implementation, strategy, evaluator and epoch fullSHA pins,
plus the exact sorted first900 cohort SHA, are in
`ETS2M_UNATTENDED_MANIFEST_2026_10_05.json`. This pins the existing evaluator;
it does not rewrite research rules or falsely describe ignored files as committed.
The prior collector-only inventory was incomplete; `ten.py` is not the judge.

The independent launcher `scripts/ets2m_unattended_verdict.py` waits for the fixed
UTC gate. Before due, `--check` reads source pins/cohort inputs only; no outcome
files or branch statistics were opened. At due it verifies pins again and takes
an isolated snapshot of the first900, executions, outcomes and relevant ETS2S
source records. Later research population is explicitly outside this cohort.
Strict JSONL parsing rejects torn rows and conflicting duplicates. Conflicting
eligible `(symbol,signal time)` terminal source rows block before comparison.

Only unchanged function bodies from pinned yadro/vnutri are executed. Collector,
strategy/module bootstrap, network, credentials and money imports are absent.
Original source-parity function runs for this cohort before the original
`otsenit(ETS2M,900)`. Missing slow terminals remain NOT_MEASURED/BLOCKED_DATA;
no duration censoring or exit-at-last-bar. Source files are read-only; all copied
inputs/temporary judge paths and the terminal receipt live in Codex private runtime.

Terminal file:
`.private/ets2m_verdict_20261010/terminal.json`.
It records output, return code, frozen cohort/source snapshot pins, observed clock
and hash. First terminal is create-exclusive; retries cannot overwrite it.
Source/cohort drift, conflicts, missing data or early process failure are BLOCKED,
not a completed research PASS.11 synthetic launcher tests PASS; original real
cohort evaluator has **not** run early.

**EVALUATED_RESEARCH_ONLY means the evaluator completed; exit0 is not strategy
PASS or READY_FOR_BUILD.** Its frozen printed acceptance is paired gain>0,
cluster sigma>2.50, same gain sign in halves, branch meanR>0. Main-window PASS
only admits the disjoint next900 confirmation window. No money authority.

Safe pre-due check:

```sh
.venv/bin/python scripts/ets2m_unattended_verdict.py --manifest reports/ETS2M_UNATTENDED_MANIFEST_2026_10_05.json --runtime .private/ets2m_verdict_20261010 --check
```

Do not launch a second `--wait` while PID/lock exists, reset the due date or edit
source to force success. If the Mac stops, preserve schedule/log/terminal evidence
and report the missed unattended run. A later once-only invocation after due can
use the same frozen manifest; it must not invent on-time execution. Stop only this
job if required: first verify PID against schedule.json, then ordinary SIGTERM;
never target trading/research collectors. Re-arming after failure requires an
explicit continuation decision, not silent retries.
