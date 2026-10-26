# PUMP4 public capture process implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Continue native execution under owner's existing engineering approval; no new monetary authority.

**Goal:** Remove collector/intake producer-consumer contention without changing frozen strategy, journals, epochs,60s entry gate or original account owner.
**Architecture:** Run the existing public collector in one credential-free interpreter. Parent keeps the DATA lock and remains the only intake/journal writer. Child sends bounded symbol/hash notices after fsync; parent verifies context/hour/files and calls the same intake immediately. Failure preserves partial evidence and forbids same-hour retry.
**Tech Stack:** Python stdlib subprocess/selectors/JSON, existing capture/Supervisor/LifecycleJournal.
**Spec:** reports/PUMP4_STREAM_HANDOFF_2026_10_25.md (actual13/17H1), plus bounds below.

## Global constraints

- Frozen intake9e37540b…9702aa/producer/universe137/epochs/cursors/observed clocks unchanged.
- No credentials/inherited DATA lock FD in child; fresh exec, close_fds and minimal environment.
- Strict notice schema PUMP4_PUBLIC_SYMBOL_NOTICE_V1: schema,symbol,capture_sha256 only;<=1024bytes/notice,<=137unique symbols. No arbitrary paths/pickle.
- Context hour must equal parent's intended H1; sha must match published source file. Final success requires137notices,child exit0,existing full seal.
- Source/notice receipt/publication/full-seal clocks separate. Parent receive/begin/end and child CPU are diagnostics only.
- Monotonic600s capture-process deadline; bounded stderr64KiB retained/1MiB fatal; terminate/reap on all failures.
- Capture attempt/completion markers prevent same-hour replay after any incomplete child/parent orchestration, even if a full seal already exists. Never rewrite prior evidence.
- Single existing systemd unit; future DATA-only quota2cores maximum on2vCPU host, same768MiB total memory. Quota is a ceiling, not reserved capacity. Verify sibling financial responsiveness.
- No moneyGO/POST/Monthly change; deploy only after exact offline local/VPS tests and bounded critical review.

## Review focus

Silent/oversized/noisy child; child exit after last notice before seal; parent failure after journal fsync; wrong-hour startup; inherited credentials/FDs. Tests in Task1 cover all five.

## Task1: Bounded existing-collector process transport

Files: scripts/capture_pump4_sources_v1.py; research_lab/pump4_supervisor_v1.py; tests/test_pump4_capture_process_v1.py.
Interfaces: capture(root,on_symbol) unchanged. CLI adds --stream-symbols. Supervisor default public_cycle uses _capture_process(archive,on_symbol,hour); custom test collectors remain supported.
- [x] Write failing real-subprocess fixture tests for parity,early durability,parent-only writing,minimal env,strict framing/hash/hour,stderr/backpressure,nonzero/missing inventory/seal/silent timeout and post-fsync parent failure.
- [x] Run tests and confirm missing transport failure.
- [x] Implement bounded selectors-driven transport and exact CLI notices; keep existing parent intake and final archive checks.
- [x] Run all PUMP component tests; compare journal/decision/timestamp bytes to in-process fixture; freeze hashes and commit.

## Task2: Existing bounded operational acceptance

Files: existing private packaging/handoff helpers; public evidence/checkpoint/START/roadmap.
Interfaces: reviewed candidate manifest/source pins, original account lock818853, existing DATA/financial units.
- [x] One critical review of new diff, fix Important defects RED→GREEN.
- [x] Same exact network-denied local/VPS acceptance, no fallback.
- [x] Existing state-preserving DATA/config OFF handoff; ONLY DATA CPU ceiling2cores, no second intake/account writer.
- [x] Actual new H1:all137 statuses,source/publication timing,queue diagnostics,child CPU,aggregate memory,sibling owner continuity.
- [x] Save actual verdict; no TINY_READY from synthetic/cached/late cases. Continue current-account/cost/native/OFF/TINY only after real gate.


## Task3: Previously started CATCHUP priority —26Oct continuation

Actual25Oct18:137publications/127PASS/15≤60s,median87.974s/max107.326s;
7CATCHUP34.545s parenttime,120CURRENT62.009s. Gate FAIL; no strategy change.

- [x] Defer only verified existing multi-bar CATCHUP, excluding bootstrap/seed-only/recovery.
- [x] Preserve per-symbol validation and sole parent writer; require fullseal/childsuccess
  and journal/epoch/batch hashes before deferred work; no entry from CATCHUP.
- [x] RED→GREEN ordering/failure/mutation/parity tests;79targeted/283local/283VPS PASS.
- [x] Independent bounded actualastra/high review0Critical/Important.
- [x] Existing DATA/OFF handoff5882783b,21376historyfiles retained, original818853,
  config125b0ae6/scopea527f12c/PID2955754,2freshGETflat barriers/NO_NEW_SIGNAL.
- [x] Actual26Oct09H1 via existing timer:CURRENT versus CATCHUP timing, classification
  overhead, fullseal, childCPU/memory, unchanged sole financial owner/Monthly.
- [x] Publish measured result/checkpoint; no further latency experiment or TINY claim
  from engineering tests.51shadow discrepancies/CR300 have separate source-only reports.

Actual09H1: priorityPASS12deferred,publicationFAIL20/133. See PUMP4_OWNER_DECISION_2026_10_26.md for84/cost/native-stop follow-up; no further latency experiment started.
