# KITY Oct15 source hardening — current gate

## CURRENT — October15 CAPTURE_OBSERVATION_PASS

[Sanitized terminal receipt](evidence/kity_oct15_source_observation_20261015/source_observation_terminal.json).
The original one-shot observer ran exactly once at **00:01:46.055UTC /
03:01:46.055 Cyprus** after verifying every published manifest/code/config pin.
Actual capture **Oct14 23:50:20.224UTC**, completed **23:50:21.809UTC**,
equivalent to Oct15 **02:50:20.224–02:50:21.809 Cyprus**. Both lie within the
original frozen window. Producer/raw/snapshot/publisher hashes match; OI checks
passed without missing-to-zero substitution.

Private date-bound terminal receipt is retained unchanged and self-hash verified.
Only the compact sanitized public receipt/checkpoint were added. No C2/C1,
PnL/judge, broker/order, source write, restart or Claude edit was performed.
The original heartbeat is **PAUSED**, with no repeat or date extension.
Actual source capture is now PASS; independent C2, prospective lifecycle and
money gates remain separate. Alpaca remains frozen/HALTED, pending its existing
fresh preflight and separate exact owner GO.


## October14 readiness — KITY_OCT15_CAPTURE_READY (A1.3)

[Terminal receipt](evidence/kity_oct15_source_hardening_20261014/capture_readiness_terminal.json).
Research `e27ef524c94f8d7835c5e8e99f5d77ab6fdc5552` is independently verified
on origin; producer SHA256
`8d05c3988f34d2939c06cdcd56cdceb19fa3b143c5c1ded96abc6bbc2326140a`.
A1.3 uses immutable raw files per attempt and binds their hash into the success
receipt. All previously demonstrated defects are closed on the replayed paths.
[15 source checks PASS](evidence/kity_oct15_source_hardening_20261014/a13_offline_source_replay.json);
[reproducible fixture](evidence/kity_oct15_source_hardening_20261014/replay_a13_source_only.py).
Observer/C2 tests **49 PASS** including raw conflicts and capture timing.
Nine economic/source functions and frozen constants match after the approved
I/O and source-receipt guard normalization; four research pins and three C2
pins remain exact. No outcome, real snapshot, C1/C2 or money PASS is asserted.

Actual18:15:50UTC readback: one Python **29930**, started17:42:17UTC after the
owner's restart, disk source predates it and matches A1.3; inherited and own
writer locks **HELD**. Heartbeat17:42:18UTC is within the hourly schedule.
Five unrelated prior Python PIDs remain unchanged. Mac is on AC,100%, sleep0;
future Oct15 files absent. Codex did not restart/edit the source or other
processes. Loaded-source hash is checked against the future real publisher
receipt; it has not been invented from a future capture.

[Pre-capture deployment manifest V2](evidence/kity_oct15_source_hardening_20261014/deadline_deployment_manifest_v2.json)
and exclusive private config are sealed. The old PENDING code manifest/V1
blocker receipts below remain historical and are superseded, not rewritten.
The SAME one-shot heartbeat now pins the reviewed V2 observer/config; original
Oct15 **03:01 Cyprus** check and COUNT=1 are unchanged. No date extension.

Actual snapshot window remains Oct15 **02:50 ≤ completion < 03:00 Cyprus**.
External target: `research_lab/data/kity_bybit_ten/2026-10-15/snimok_2355.json`;
producer receipt `snimok_CAPTURE_RECEIPT.json`, raw
`popytki/tickers_<capture_ms>.raw`; failure `snimok_PROPUSHCHEN.json`.
Independent observer validates producer/raw/snapshot hashes, capture/completion
clock and OI; it writes its own date-bound result and never writes these files.

Exact one-check command AFTER original deadline only:

```sh
.venv/bin/python scripts/kity_oct15_deadline_v1.py --config-sha256 d6b689603ca9f4a24c2f131af0ac63d54617a15b9a148cc8f51344c64a38674b
```

Before deadline this returns WATCH_PENDING with no terminal/source writes.
After deadline it preserves one CAPTURE_OBSERVATION_PASS or exact CAPTURE_BLOCKED;
no polling/retry/reapproval. Automation pauses/deletes after that single check.
A reboot/delayed wake is recorded honestly, not promised away. C2 independently
reconstructs only after actual raw sources exist; this observer does not run it.
Alpaca remains frozen/HALTED; no orders, judge, strategy/risk/hold/cost change.

## Historical A1.1 blocker — resolved by A1.2/A1.3

**KITY_OCT15_CAPTURE_BLOCKED: A1.1 source defects reproduced offline.**
This is source engineering, not a strategy, C1/C2, PnL or money verdict.
Alpaca's frozen STATIC_PREFLIGHT_PASS and LIVE HALT remain unchanged.

Research A1.1 commit `566c6d13a134d9235c24e16f04bddc5cdb7be35c` is actually
published on origin. Producer SHA256 is
`916a849ad5a7c01fb4ae8c9c2702e089d169507a7a13368df8a47b9055df0c82`.
The original source and A1 are retained in Git; no old capture is rewritten.

Independent AST fixture execution confirms A1.1 fixes missing/null/NaN/negative
OI, overwrite and already-late HTTP responses. It still:

- accepts positive infinity and boolean true as OI;
- publishes a partial final JSON if `os.write` returns a short count;
- can publish a timestamp at midnight between its deadline check and timestamp;
- does not retain raw failed ticker bytes;
- has no immutable success receipt proving the pinned source, snapshot hash and
  actual completed publication time.

[Counterexamples](evidence/kity_oct15_source_hardening_20261014/a11_offline_counterexamples.json)
use temporary paths and stubbed HTTP only. No actual prospective input or
outcome was read. Corrected finite/type checks, a full-write loop, recorded
completion and retained raw/source receipt were requested together from Claude.
These are requirements of the original source-only GO, not new strategy gates.

[AST parity](evidence/kity_oct15_source_hardening_20261014/a11_source_only_ast_parity.json)
matches nine existing source/economic functions after ordinary write-call
normalization; frozen numeric constants match. No ranking, universe, k, hold,
cost, funding or C1–C3 change is approved.

## Independent deadline observer

Implemented `research_lab/kity_oct15_deadline_v1.py` and
`scripts/kity_oct15_deadline_v1.py`. Observer + existing independent C2:
**45 targeted PASS**. Tests exercise short writes, fsync failure, no overwrite,
missing/late/corrupt/source-drift evidence, unknown OI, early wake, delayed reboot,
immutable terminal receipts and source replacement during a read.
[Frozen code manifest](evidence/kity_oct15_source_hardening_20261014/observer_code_manifest.json).

One heartbeat `kity-oct15-one-source-deadline-observation` is ACTIVE for
October15 03:01 Asia/Nicosia, COUNT=1. It inspects only the fixed first source
window: **October14 23:50 ≤ completion < October15 00:00 UTC**, equivalent to
October15 02:50–02:59 Cyprus. It pauses/deletes itself after its single check.
This is separate from the producer and does not promise Mac reboot survival.
A delayed wake records its actual time and does not fabricate an on-time check.

Own terminal path is `.private/kity_bybit_c2/2026-10-15/receipts/source-deadline.json`.
CLI before deadline returns WATCH_PENDING without writing a future result.
Without a reviewed final source/config, it writes explicit
CAPTURE_BLOCKED / PRODUCER_APPROVAL_PENDING after the deadline.

Expected producer receipt: external
`research_lab/data/kity_bybit_ten/2026-10-15/snimok_CAPTURE_RECEIPT.json`,
with `status=CAPTURE_PASS`, `day=2026-10-15`, `producer_sha256`,
`snapshot_sha256`, and integer UTC `completed_ms` inside the original window.
The observer reads source files without importing shadow strategy/outcomes;
it cannot create a snapshot, approve a producer, reconstruct C2 or grant money.
Final reviewed deployment/config pins are **PENDING** and have not been invented.

## Actual process state and next action

Fresh 17:34–17:35UTC readback found an external restart, not performed by Codex:
one actual KITY Python PID **27731**, start17:24:42UTC; caffeinate child27786
is not a second writer. Both inherited `kity_bybit.lock` and own
`kity_bybit_ten.lock` are actually HELD. Heartbeat17:24:42UTC; future Oct15
directory/snapshot absent. Disk source matches A1.1 and predates the process;
an explicit loaded-code hash attestation is not yet published.

Codex performed no producer deployment/restart, no Claude checkout edits, no
broker requests/writes, no PnL/judge/C1/C2, and no changes to other processes.
Do not use broad pkill or `podnyat_vse.sh` for this fix.

Next: receive corrected committed/published source hash, replay the same
bounded fixtures and confirm source-only diff; only then perform one exact
KITY-only handoff if still needed and verify one writer/locks/source/heartbeat.
Freeze config/receipt pins before the first prospective window. Missing or
incompatible source remains BLOCKED; there is no synthetic snapshot or date
transfer. Separate exact owner GO remains necessary for any future money.
