# DATA Brain restored after clock-guard exit —30Oct2026

Owner reported lost schedules. The three local delivery heartbeats Monthly58,
LIQ and PUMP4→Brain were still ACTIVE; viewed in the app, no duplicate created.
The completed first-join heartbeat `brain` was intentionally deleted earlier.
Native Monthly/PUMP and both export timers were running. An unrelated old NET
preflight pause was rejected by app automatic review (no separate cancellation
approval); it remains ACTIVE. No workaround or financial automation change.

Real incident: `brain-context-shadow.service` exited10:21:57UTC with
BRAIN_TIMELY_CONTEXT_CLOCK_STEP. The guard compares wall and monotonic time;
its measured discrepancy exceeded1s. The origin of that change is UNKNOWN;
current NTP sync does not establish its historical cause. Not an OOM: peak13.1MiB.
The guard and code were preserved, not relaxed.

Preflight verified exact manifestddd62974…f007/all11source files, complete10event
journal chain, same epoch and original seven-day deadline. NTP synchronized,
eight-second wall/monotonic deviation0.007704ms; independent public Bybit time
GET offset160.5ms. First inspection used a wrong manifest location and performed
no mutation; corrected from actual unit ExecStart, not a guessed/new source pin.

One `systemctl start brain-context-shadow.service` after those checks. No retry,
unit edit, policy change, epoch reset, journal repair, deadline extension or
financial action. Reuses the isolated network-denied public-data jail.

Independent12:04:32.320UTC /14:04:32.320Cyprus readback: active PID3397056,
14complete events. Original10event byte prefix unchanged. Epoch/source manifest/
unit bytes unchanged. New4events include a durable causal witness before its
future outcome window. Missed decision windows are not backfilled or retimed;
older source-backed descriptive joins remain descriptions of BTC, not trade PnL.
Original deadline6Nov07:46:18.164UTC /09:46:18.164Cyprus retained.
PUMP financialPID3198429 and DATAPID3152955 unchanged; Monthly timer waiting.

[Preflight](evidence/brain_context_cycle_20261030/clock-recovery-preflight.json),
[independent readback](evidence/brain_context_cycle_20261030/clock-recovery-readback.json),
[schedule/allowance snapshot](evidence/brain_context_cycle_20261030/scheduled-status-20261030.json).
Weekly usage97% at check; reset4Nov09:47:49Cyprus. Native VPS workers do not invoke
Codex; app DATA pulls still do. Native Mac DATA transport remains a proposal,
not an installed replacement. Keep Mac/app available for local file tasks:
[official scheduled-task documentation](https://learn.chatgpt.com/docs/automations?surface=app).

PUMP4 source accounting patch2efcd79 published;177local/same177VPS. Next money gate
is the actual cost-release policy plus real-source OFF/handoff, not more Brain
features. No new LIVE/TINY-2 GO was created. See PUMP4_TINY2_SOURCE_ACCOUNTING_2026_10_30.md.
