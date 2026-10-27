# PUMP4 — measured source recovery, 27 October2026

**Superseded actual status:** read `PUMP4_CRITICAL_PATH_2026_10_27.md` first.08H1 failed,09H1 guarded priority timing passed but protected-health guard failed/rolled back; normal10–12H1 failed. The pending08H1 section below is dated history.

Continue the installed source/consumer candidate and these receipts. No strategy audit, evaluator, PnL/judge rerun, new funding download, Monthly change or financial GO.

## Actual06H1: last candidateffb, FAIL

Full137 outcomes and archive hashes verified.117 CURRENT,7 CATCHUP_REPLAY,12 BLOCKED_SOURCE (allHTTP200/10006),1 unavailable.124 intake passes;23 publications <=60s. CURRENT median76.801s/max95.606s; catch-up followed current, final103.217s. CURRENT sources median45.686s/max66.809s. Classification7.182s; parent processing82.166s; childCPU27.243s. Zero signals; signal-only quote observer made0 GETs. No execution-delay cost inferred.

Four slow-in-hour NO_SIGNAL cases were replayed offline on temporary copies with exact result equality and original journal hashes unchanged. Replay wall0.200–0.232s, CPU0.190–0.202s outside the hour. This does not explain every in-hour stall. A post-hour CPU/RAM pressure snapshot is not proof that a later-started process caused that H1. In particular, the observed heavy ATT1 signal-shadow process started06:02UTC, after the06H1 process ended06:01:43; it was not stopped or changed.

## Actual07H1: STILL OLDffb, FAIL

The old selected timer started07:00:02UTC while the new package was staged/unselected. Do not call it the new package's proof. Full137 outcomes:118 CURRENT,11 CATCHUP,7 BLOCKED_SOURCE,1 unavailable.129 intake passes;22 by60s. CURRENT median73.807/max92.233s; finalcatchup102.777s. Zero signals. Complete archived files retained, no repeated collector or hour retry.

## Concrete consumer bottleneck and repair

The sole OFF financial consumer reread every historical observation each5s poll. A profiled read of9100 observations took19.707s/11.584CPU seconds with238,263 filesystem stat calls. Profiling adds overhead; this is a diagnostic, not the daemon's exact poll duration.

The negative-only cache stores only observations already stably read, decoded and checked for false authority, with explicit `signal is None` or an expired original absolute entry deadline. Each hit checks unchanged dev/inode/size/mtime/ctime/uid/gid/mode/link-count, regular-file custody, unchanged bound DATA/config and directory custody. Reads obtain metadata from the same opened descriptor before/after the bytes and compare the final path identity. Replacement/overwrite/permissions/symlink tests reject or reread; clock rollback clears the cache, expired hits require `now > deadline`. Memory stays within the existing20000-observation bound and vanished entries are removed. A cache hit can only suppress a negative; eligible candidates always read and verify the actual journal, source captures and causal plan. No strategy state is cached.

On identical9240-observation VPS input, no network/owner/credentials: old uncached three reads8.370–9.880s, CPU5.175–5.373s. New cold read4.643s/3.098CPU; subsequent warm reads0.373–0.466s, CPU0.289–0.342s. Result stays NO_SIGNAL. This is a consumer benchmark, not an actual new-H1 latency PASS.

## Concrete API loss and bounded recovery

The old collector abandoned a symbol on its first10006. The new DATA-only reader preserves selected rate headers, exact raw response bytes/hash and request/timing identity. A verified initial clock capture anchors the originalH1+60000ms once, with a monotonic budget to prevent clock reversal extending it. The clock request itself cannot be retried without that anchor.

Only HTTP200 with exact verified `retCode10006` may repeat the same query, at most3 total attempts. Shared cooldown applies before all workers' requests, including first attempts; no mutex is held during sleep, and later cooldowns can extend but never shorten it. Failed responses are durably published before another attempt. Only successful candle captures reach unchanged `closed_h1`; the separate failed-attempt ledger is included in the full archive seal. Actual attempts and successful capture pages are counted separately. Requests after the original retry deadline are not retried or credited as timely entry evidence; a late response remains DATA only. Network/other API errors are recorded without retries. HTTP403 latches the reader against further requests (already admitted requests may finish).

This follows the documented10006/reset-header and403 constraints in [Bybit's rate-limit rules](https://bybit-exchange.github.io/docs/v5/rate-limit). No financial POST retry or sealed-hour restart is introduced. Tests cover failure persistence, header fallback, timeout/deadline/rollback, HTTP403, a real two-thread cooldown interleaving, and collector recovery with the failed response outside successful candle inputs.

## Exact package and acceptance

Candidate `e4feca498f37e27d`, material `e4feca498f37e27da4f2059d1aed035fa4da9dd5fa7c5dcbd3d4a5ecdff6c1c6`; manifest `05b07e3c27644737778a17c8b566f2749b7b4d87c800842b96da98b4f262bd78`.
**355/355 local AND same355/355 VPS PASS**,0 failures/errors/skips,117 files,56 imports,20 test modules,0 checkout fallback, network denied,0 real broker requests/writes. Critical source/caching/retry review0 Important/Critical; follow-up403/concurrency review21testsPASS. Handoff review20testsPASS/0 Important. Its30→90s startup-receipt wait accommodates a cold history scan; it does not alter the60s entry deadline or authority dates.

Strategy, frozen intake, reference plan, universe, limits, risk basis, partial exits and financial send-once controls remain unchanged. Execution policy changes its source-manifest hash only;10bps reference drift remains an OFF proposal requiring a new exact future owner scope/GO.

## Financial decision and next contour

**LIVE BLOCKED**, economics **INCONCLUSIVE**. Same-input84closed+open1 parity and native84 memory protocol remain accepted; funding arithmetic is already unified, not actual cash-flow finality. A separate minimal technical micro does not require proving annual profitability, but needs actual technical/account gates and the owner's exact financial GO. No order/GO/extra capital is created by this work.

Polymarket remains the next intake. Source-only read of the existing22Oct `POLY_PUT_K_LIVE` and `POLY_PODKLYUCHENIE_TZ` at local research ref89f62b5a3c88357cdcde451b394d8cfd175959a9 identifies its existing frozen decision function `fabrika/poly_yes_ten.resheniya` and execution obligations: fresh NO book, FOK/IOC choice, tick/min-order/fill reconciliation, settlement cash accounting, limits and owner GO. These are dated design proposals, not current researchPASS, publication attestation, approved dollars or access/region proof. No new judge/sealed outcome was consumed and no duplicate research/collector or monetary connection was started.

Actual deployment and next untouched H1 receipt are recorded below when confirmed. New code tests must not be relabelled as a passing H1.


## Selected27Oct07:15UTC, independent readback07:18UTC

Both DATA and sole financial owner now selecte4feca498f37e27d. DATA binding `7c36a8daa2f815d70f15e7fa977100d9fb13bed21123d0a659c63bb859549d2d`;33,935 historical files preserved, old roots retained. No incomplete hour was interrupted.

Financial config `1a5a4eacf4b08dd56597fb5c78f69317c4e6a637e38d1d43416419b924caf470`, OFF scope `855fd45cae57239e01ef12dfc8210854ddda8d29d4eb3864b133e6de19ce90b3`, PID3029723, original818853 held,0 restarts. Two fresh GET-only flat/no-order barriers preceded selection. Independent literal readback verifies source/guard/config/data/policy pins,272 intake/epoch prefixes,26 clean actual NO_NEW_SIGNAL cycles, no financial history/GO and0 writes. Monthly unit remains `9d94467d301cf5f545bee18e50b838623c061b72f46a2fbdd9b7d1991932cc1d`.

New H1 proof is **PENDING**, notPASS. Next untouched existing timer:27Oct08:00:02UTC =10:00:02 Asia/Nicosia, source-hour1793088000000. One read-only observer already waits on this exact root; SSHsession67826, local `.private/pump4_source_20261027/actual08-progress.jsonl`, stderr `actual08-observer-stderr.txt`. It only reads immutable receipts and captures bounded public quotes if an actual signal appears; ends08:06UTC. Do not duplicate/restart the collector or observer. Previous06/07 failures belong to the oldffb candidate.

Earliest owner micro review follows actual technical/account PASS; a real trade also requires a valid signal and separate exact human financial GO. No precise trade time or future profitability is asserted. No personal action is requested while the technical result is pending.
