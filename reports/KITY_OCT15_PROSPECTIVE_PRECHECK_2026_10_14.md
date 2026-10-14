# KITY Oct15 prospective precheck — read-only

**KITY_OCT15_CAPTURE_BLOCKED**. This is a source/operational verdict, not a strategy verdict, actual C1/C2 result or money approval.

[Receipt](evidence/kity_bybit_c2_20261014/oct15_readonly_precheck_receipt.json).

Confirmed now: all five frozen research/source pins at cb47f0e and all three independent C2 pins match; exactly one Python collector PID14408, inherited writer lock actually held, caffeinate active and AC sleep0. Latest heartbeat16:30:14UTC. Existing UTC60s loop correctly selects Oct14 23:50–23:59 / Oct15 02:50–02:59 Cyprus; this is not a cron job. Storage has eight empty owner-only0700 directories and about67.7GiB free. External first-snapshot directory is not yet created, correctly. Independent C2 remains offline, does not import Claude's shadow/outcomes, and rejects wrong-day/stale/nonfinite/missing sources.23 targeted tests PASS; no actual reconstruction/comparison or PnL run.

Three material source guarantees requested by the owner are not met:

1. **SNAPSHOT_WRITE_NOT_CREATE_EXCLUSIVE.** Frozen `kity_bybit_ten.py:45–51` uses `exists()` then `write_text()`. Single writer prevents concurrent duplication but does not provide O_EXCL/fsync/atomic complete publication. An interrupted write can leave an existing partial file that the next loop simply skips.
2. **MISSING_OI_COERCED_TO_SYNTHETIC_ZERO.** At line49 `float(t.get("openInterestValue") or 0)` converts missing/null OI into0. A memory-only counterexample with a missing field publishes zero with no UNKNOWN/BLOCKED. The independent C2 cannot distinguish this from a legitimate zero solely from the normalized snapshot.
3. **MISSED_WINDOW_TERMINAL_NOT_IMPLEMENTED.** `shag`/loop139–165 have no date-bound missed-window BLOCKED receipt. A memory-only00:00UTC fixture calls no capture and returnsNone. Late HTTP completion can write a timestamp outside the allowed window; C2 correctly rejects it, but producer does not emit the requested terminal receipt. The existing generic watchdog checks logs/locks, not this frozen KITY deadline. Expected `com.tradingstation.research-station` and `com.bot.teni` jobs are not loaded; a plist file alone is not reboot supervision. No automatic reboot recovery is claimed.

No real future snapshot was manufactured: counterexamples used AST-extracted frozen functions with memory path/network stubs only. No producer/import/`--proverka`/judge was executed. Current healthy process is preserved, not stopped. No Claude message or checkout edit; no Alpaca, ATT1, KITY rule/config or Liquidation mutation.

Next actionable scope is narrow **source-only** hardening of completed exclusive publication, missing-field UNKNOWN and a persisted missed/late-window receipt, with source/version review before any replacement of this frozen runtime. Ranking, universe, signal, hold, costs, prereg and C1/C2/C3 remain unchanged. This precheck does not authorize that deployment/restart or a new collector. Do not mark capture READY merely because hourly pulse is healthy. The real Oct15 point remains prospective and must be accepted or BLOCKED using its actual sources.
