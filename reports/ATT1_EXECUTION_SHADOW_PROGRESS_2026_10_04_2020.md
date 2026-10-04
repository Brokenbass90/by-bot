# ATT1 bounded research — first six-hour check

Observed **October4 20:20:03UTC /23:20 Cyprus**. One read-only SSH query;
no restart, redeploy, broker API call, source alteration or money-policy change.
Receipt: `ATT1_EXECUTION_SHADOW_PROGRESS_2026_10_04_2020.json`.

Both probes RUNNING with original PIDs1676226/1676227, NRestarts0, recent
heartbeats, exact original study/context/app hashes and deadlines. Deadline
remainsOctober6 14:12:25UTC. Main1648585/public1584802/web1623208 unchanged,
NRestarts0; deployed public driverSHA97239996… unchanged. Free disk41.4GB;
transport525788146 bytes <4GiB cap, funding1214 bytes. No deadline extension.

**New operational signal:** public heartbeat reports11 sessions,5 gaps,
**1 clean terminal**, no held simulated positions. Clean was counted only when
terminal=true, costs_complete=true, net-R non-null and incidents empty. Full
terminal journal/identity/net-R was not retrieved/replayed in this single query:
status **PUBLIC_HEARTBEAT_ONLY**, no fresh sealed gate credit claimed. Next check
must replay the terminal using the exact deployed closure, bind source hashes
and net-R to its identity, and preserve the receipt. No profit claim or NEW GO.
The additional fifth gap's causal source was not audited in this heartbeat.

Transport now contains22029 REST books,972777 WS books,65069 trade frames and
one connection. The35s analysis batch processed495243 complete gzip members,
covering **14:12:27–16:38:25UTC**, not the full six-hour capture population.
Cursor ends atcapture-497536.jsonl.gz, compressed offset68350549 of its snapshot
101505507 bytes. Completed earlier prefixes must not be scanned again.

In this batch:8744 REST books,444800 WS books;453544 wire hashes verified,
no mismatch. Seven REST use-time CTS violations: **five stale already at receipt**
and **two fresh at receipt but stale after local use delay**. All444800 observed
WS books passed the same CTS freshness test. No missing CTS, disconnect, sequence
regression or delta-without-snapshot was observed in this processed batch.
This is bounded observed evidence, not a guarantee about unprocessed records.

All five receipt-stale examples are **SEIUSDT**: CTS ages2169/2289/2764/2663/2947ms.
They were already2085–2866ms old at the REST server timestamp. A previously
received WS frame had CTS fresh at REST receive time and a higher cross-sequence
in every case. Each example pins raw-wire SHA and compressed member offsets.
This demonstrates contemporaneous divergence between the observed public paths;
REST cache/publication implementation and quiet-book root cause remain unproven.
No WS transport cutover or freshness threshold relaxation is authorized by it.

Batch receipt CTS age p50/p99/max: REST243/975/2947ms; WS94/177/1738ms.
Local use delay p50/p99/max: REST1/32/2518ms; WS0/1/212ms. Do not average batch
percentiles into an invented full-population percentile.

Funding has exactly one new unique START, **XMRUSDT**, submit16:02:48.031UTC,
outside the frozen eight execution-admitted symbols. Explicit
OUTSIDE_EXECUTION_ADMISSION; no universe expansion. No duplicate prefix and
**zero admitted-symbol policy comparisons** yet. This is INSUFFICIENT_EVENTS,
not reserve candidate PASS; existing dated fee/synthetic sizing caveats persist.

Private `analysis_cursor.json` preserves processed offsets/inodes, cumulative
counts, batch bounds and funding prefix identities. `inspect_next_heartbeat.py`
is prepared for the next single read-only query: resume offsets and verify only
reported clean terminal journals under their actual owning user/deployed closure.
It has been syntax-checked locally, not yet executed on VPS. After each batch,
advance the private cursor from the returned bounds; do not mutate capture files.

Local/Git documentation is refreshed; this read-only heartbeat did not sync VPS
documents. Runtime receipts, not older VPS documentation, are current evidence.

Actual packet remainsBLOCKED_DATA: mode/cash/finality/handoff/economic policy/
selected-account lifecycle gates remain. NEW ordersOFF; keep2–3 verified clean
filled prospective terminals/net-R +fresh exclusive dossier +separate ownerGO.
The bounded heartbeat remainsACTIVE; studies have not terminated. AlpacaOctober5
13:30UTC/16:30Cyprus re-arm remainsP0 and was not inspected or modified here.
