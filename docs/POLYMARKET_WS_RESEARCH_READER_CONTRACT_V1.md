# Polymarket VPS archive: research reader contract V1

DATA-only interface to the existing archive. No trading authority, new collector,
judge implementation, research-rule change or LIVE permission is created here.
The archive is separate from older Mac journals; retain source identity on joins.

Root: bybit-bot-clean-v28/research_lab/data/poly_ws_vps_v1.
Epoch: poly-ws-data-20261102. Roles: sports, clob, catalog.

| Layer | Required interpretation |
|---|---|
| sealed segment | `<role>/sealed/<ms>-<session>-<index>.jsonl.gz` plus identical `.delivery.json`; completed publication only |
| seal | POLY_WS_SEGMENT_DELIVERY_V1; exact epoch/role/path, compressed bytes/hash, raw bytes/hash, rows, session, first/last received_ms, closed_ms |
| import receipt | receipts/SHA256(canonical seal).json; verify both file/seal hashes and first_local_mtime_ns; actual_import_ms is local arrival, never retimed |
| raw row | POLY_WS_RAW_V1; kind, epoch, role, session, seq, received_ms, monotonic_ns, payload; original bytes preserved |
| row identity | epoch + role + immutable segment SHA/path + seq; seq resets in every segment, session+seq alone loses events |
| payload | RECV.payload.frame is original WS text. Other kinds preserve subscriptions, connects, disconnects, errors; do not filter these before coverage QA |
| clocks | received_ms is VPS user-space receipt; monotonic_ns orders that host/session; CLOB timestamp is venue time. Preserve all; one cannot replace another |
| availability | join Sports/CLOB by what had actually been received before decision; future book snapshots, future metadata and final outcomes cannot provide earlier signals |
| durability | a source timestamp or pre-fsync timestamp alone is not an independent historical durable-before-decision witness |
| gaps | disconnects, crash partials, stale catalogue, unknown sequence coverage or failed imports produce UNKNOWN; no interpolation/resealing or silent skip presented as complete coverage |
| outcome sides | catalogue market tokens are both distinct outcomes; preserve token IDs/names and use actual ask ladders for the desired outcome |
| depth | apply complete level updates or invalidate book depth after an unprocessed update; a last-book aggregate cannot substantiate new-price executable liquidity |
| execution model | actual price levels/size at receipt, accepting/trading status, timing, fees and slippage all need contemporaneous provenance; a complement price is not a purchasable quote |
| dedup joins | retain source/version and match identity. Do not double-count Mac and VPS observations or multiple related markets as independent matches |
| runtime proof | result includes reader SHA/version, input segment hashes/counts, read/error counts, coverage and gap flags. A file edit or RUNNING process alone is insufficient |

Reuse the existing importer's `validate_segment` contract and canonical encoding
when validating copied data. On disagreement preserve original bytes and report a
conflict; do not silently overwrite or repin. Raw source receipt is distinct from
Mac import time and from any later prospective decision witness.

The frozen collector remains limited to its original150 markets/top1000 events
and time filter. Sports game IDs outside that selection do not count as
executable opportunities. This document does not expand that universe.

Acceptance handoff to Claude: completeness now confirmed for one fixed snapshot;
implement the remaining timestamp/depth/side/coverage/version fixes in the owned
research reader, publish its SHA and show the next running result's reader SHA.
Do not change frozen V2 economic rules to compensate for a reader defect. The WS
judge and separate V2 paper results require separate source-lineage checks.
