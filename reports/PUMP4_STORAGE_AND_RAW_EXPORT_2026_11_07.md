# PUMP4 storage recovery and raw export, 7 November 2026

The DATA service exited on 6 Nov at 14:02:05 UTC. Subsequent starts failed
PUMP4_DATA_DISK_RESERVE. About 3.01 GB were free against the 3 GiB gate.
The financial owner PID3669955 continued and reported missing current H1 receipts.
The old expiry cron's main account separately returned 33004. The selected
PUMP4 handoff readback completed against the bound credentials and returned
OWNER_ACTION_REQUIRED with source health UNHEALTHY.

Storage recovery offloaded 12,741 public symbol JSONs from the inactive
candidate e4feca498f37e27d. The Mac archive is 979,612,810 bytes. Every file's
length and SHA were checked against the remote manifest before the VPS copies
were removed. Unit, cron and process references were checked. Reclaimed bytes
2,857,377,792, free after 5,907,578,880. The archive and its restore manifest
are in .private/pump4_cold_archive_20261107. Active source, financial state and
archive metadata remain at their original paths. The disk reserve stays 3 GiB.

The exact strict DATA service was started after the space check. It was active
as PID1200512 at first readback. Financial owner PID3669955 and lock818853,
DATA lock4294867 and the existing scope remained stable. The first new H1 at
7 Nov 21:00 UTC (23:00 Cyprus) passed. All134/134 publications were timely,
with the last at36.470s and zero raw signals. The financial owner confirmed
coverage from the same H1 receipt at21:02:57.992UTC. Independent readback
21:03:00.966UTC observed active DATA PID1200512 and the unchanged financial
owner. Recovery processed4,020 closed bars with zero blocked symbols.
Earlier missing hours remain missing in the prospective coverage ledger.

The legacy expiry monitor now labels the binding as legacy and explains that
PUMP4 has a separate key check. Installed SHA
e36fcca73d55ab6f2359352f9dad8fd7f8b0090c37e70649044e0582d1036c71.
Old bytes backed up, root cron hash and owner PID preserved. No manual alert sent.

## Daily signal delivery

Active local automation pump4-live-raw-signals-claude-data at 03:20 Cyprus.
The pinned exporter reads the bounded H1 DATA publication index over SSH and
writes the Mac pump4_live_signaly.jsonl plus pump4_live_signaly.coverage.json.
Rows contain sym, ts_ms, decision_id, status, reason and actual known_since_ms.
UNKNOWN means that a decision-bound financial disposition is unavailable.
ATTEMPTED only proves an immutable attempt marker. A timestamp after the
60-second deadline proves the publication was late. Absence from an incomplete
day is unknown. Replaying a stable input preserves the original signal prefix.

4 and 5 Nov each covered 24/24 hours and had zero raw signals. 6 Nov covered
14/24 and had zero in the available segment. The 3 Nov legacy source probe
failed PUBLICATION_SCOPE. The exporter left that day's data untouched.
First positive prospective signal delivery remains to be observed.

## Research checks

Breakout source replay reused bridge V2 on the exact M5 prefixes and
reproduced the frozen plan for all 16 unique IDs. There were 27 plan rows,
5 unique plans inside the epoch and 5 existing research deal records.
No in-epoch plan lacks a deal record. No rerun or journal mutation was needed.

Mac screen lists psig and psig3. nfp is absent, with a completion line in its
6 Nov log. The V3K acceptance task and concrete contract blockers are in
POLY_V3K_SOURCE_ACCEPTANCE_2026_11_07.md. The independent Monthly local
candidate result is in MONTHLY_CENTS_CAPTURE_LOCAL_2026_11_07.md.

Evidence: evidence/pump4_data_storage_recovery_20261107.
