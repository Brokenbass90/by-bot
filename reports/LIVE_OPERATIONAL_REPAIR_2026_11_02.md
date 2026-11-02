# LIVE operational repair — 2 November 2026

Monthly did **not buy** in its14:30–14:35UTC window. All five real OPENING attempts
returned `MONTHLY_PENDING_FEE_STALE_SOURCE`. The live-account GET at17:39:59.079632UTC
matched both the signed Monthly scope and manager: positions0, open orders0,
recent orders0. This is **NO_ADMISSION**, not CASH or a profitable trade missed.
The existing reader has bounded recent history, not proof of full account-history
or terminal cost finality. No catch-up purchase, date transfer or new GO was run.

The previous idle-cycle acceptance did not exercise OPENING. Treating that as
market-execution readiness was too strong. The original v6 LIVE code and its
400/280/40 financial terms remain unchanged during this repair.

## Monthly: reproduced and repaired in an unselected candidate

The before-entry source was freshly captured at14:30:32.133UTC, with activity coverage
through14:30:31.215571435. Ticket preparation completed around14:30:34.589;
the failed cycle was observed14:30:37.673. The fixed five-second freshness gate
correctly rejected evidence that had aged during source/authority/account work.
Before-entry collection alone did not keep the evidence fresh at later uses.

The local fix scopes the existing read-only cost/finality callback to OPENING.
Only an exact stale-source classification may recollect evidence once per failed classification; it then
reads the account again and uses elapsed monotonic time. There is no order retry,
retimed source document, relaxed TTL, financial budget change or generic engine.
A nested capture reuses the actual held account-lock descriptor, checks its inode
and leaves the original writer lock held. Other lock callers retain their old
lifetime; the context manager now optionally yields its descriptor.

Independent review found a real regression in the first draft: a new account
could validate fees while old cash/equity were retained for sizing and the cash
anchor. Fixed by refusing changed identity, money and blocked-status fields and
classifying refreshed evidence against the original account. Eight negative
cases reproduced the problem before the fix. Full OPENING fixtures reject cash
or blocked-status changes before reservation/POST; successful recovery sends
exactly one in-memory BUY plus STOP, and recovery does not repeat the BUY.

Evidence distinguishes fixtures from production:

-15 new targeted tests pass. The full source-pinned candidate has53 source files,
  19 test files and40 imported source files, with no checkout fallback.
-Exact local acceptance:281 PASS; same281 VPS PASS after custody-only packaging
  correction. Network denied, zero real broker requests/writes; no skips/errors
  or import fallbacks. VPS elapsed590.209s under50% CPU/Nice19; this is isolated
  engineering evidence, not a real opening or broker performance benchmark.
-The first VPS packaging attempt preserved Mac UID501 through tar. Existing
  FILE_CUSTODY guards correctly rejected those files. The failed results are
  retained. Ownership was corrected only in the inert candidate; guards were
  not weakened and no installed financial file was changed.
-Candidate is UNSELECTED: source material
  `4bb6b9e8cefc8a10286edd305f3015ae24f4f894088ba5af32a4ff46e5821a55`,
  `/opt/bybot-research/monthly-opening-refresh-20261102/candidate-4bb6b9e8cefc8a10-ta1a4f4e1`.
  This is not an actual broker OPENING PASS or READY_FOR_OWNER_GO.

Next Monthly gate: prepare a versioned source/ownership handoff and demonstrate
fresh evidence through the final dispatch boundary without orders. The missed
2Nov window stays spent; any exceptional future window needs an explicit decision.
No personal activation command is issued from fixture results.

## PUMP4: serial processing consumes the minute

Read-only diagnostics compare completed source hours; all rows are actual saved
public-source receipts. No stream/owner restart or 60-second change was made.

| UTC hour | Within60s / expected | Last publication | Sum receive→publication across134 handlers | Raw signals |
|---|---:|---:|---:|---:|
|09:00|134/134|51.886s|50.166s|0|
|10:00|134/134|52.470s|50.967s|0|
|11:00|134/134|49.544s|48.094s|0|
|12:00|134/134|52.586s|50.837s|0|
|13:00, before Polymarket cutover|134/134|58.368s|56.306s|0|
|14:00|127/134|62.742s|61.129s|0|
|15:00|134/134|57.888s|55.795s|0|
|16:00|128/134|62.747s|60.815s|0|
|17:00|127/134|62.772s|60.917s|0|
|18:00|134/134|57.696s|56.116s|0|

The actual receive loop calls synchronous `s.feed()` before the next `ws.recv()`.
It durably captures raw data, computes the warm reducer, verifies/publishes the
result, then receives the next frame. For13–16UTC,134 confirmed-close frames were
matched to their receipts. Their server timestamps span only+0.110–1.128s, while
local reads stretch to+58–62s. Server clocks are not independent network-arrival
witnesses; the synchronous control path and measured cumulative handler time are
stronger evidence of the local serialization bottleneck.

The backlog existed before Polymarket. Its extra contribution remains unmeasured;
intermittent failures do **not** rule out continuous background contention. No
causal conclusion follows merely from14:00/16:00 failing and15:00 passing.

Historical sysstat is available. Ten-minute samples show about6–10% I/O wait and
variable host steal; they cannot identify individual first-minute stalls.
Catalogue runs near13:50–13:52,14:20–14:23,14:50–14:52,15:20–15:27,
15:53–15:55 and16:23–16:25 do not coincide with the14:00/16:00 publication burst.
Archive work can overlap and its contribution is not isolated. Existing research
CPU/IO priority restrictions remain. Buying a second VPS is not yet justified.

Pinned readback at18:13:18.596UTC reports LIVE_ARMED_HEALTHY / LIVE_FLAT_WAITING_SIGNAL,
134 publications checked,3 unavailable instruments,0 raw signals, same scope/config
and ownerPID3669955. The source status is ENTRY_WINDOW_CLOSED_COVERAGE_CHECKED;
this is not an entry signal or durable multi-hour reliability proof.17UTC was still
blocked. H1 receipt hashes, frame identities and the readback are in evidence.

Next PUMP gate is a bounded performance repair in this existing DATA receive/feed
path, measured on exact copied public input, then independently timed real H1.
Preserve raw-before-use durability, ordering, source pins and original60s cutoff.
Do not hide failures as NO_NEW_SIGNAL or change the financial owner to mask them.

## Polymarket: preserve WS, repair delivery and catalogue retry loop

The14:06 DATA acceptance was real but did not prove ongoing operation. Later,
Mac's240s parent timeout killed long backlog imports. Individual batches could
already have been ACKed; a single full-round PASS could not describe that state.
Catalogue captures under10% CPU also sometimes exceeded180s wall time. Restarts
left partial captures and consumed the role's128MiB quota. This is a role-cache
limit, not a full VPS disk: about8GB remained free.

Installed DATA-only repair:

-Delivery uses globally oldest sealed segments across roles. A round has a120s
  work budget including initial listing/scanning, checked between batches; the
  parent has720s headroom for bounded SSH/validation work. Backlog continues
  after2s instead of300s, including seals created during the round.
-Hash/raw/seal/receipt/first-mtime verification precedes every source ACK/eviction,
  unchanged. No unacknowledged deletion, reseal or crash-partial repair.
-Catalogue timeout600s, same10% CPU/128MiB budget. A capture first requires64MiB
  headroom, so retries wait for archival instead of refilling freed space with
  another incomplete capture. Measured capture is about23MiB plus temporary data;
  per-write limits still apply. More than64MiB of retained non-archivable data
  would remain an explicit blocker rather than being deleted automatically.
-Only catalogue unit selection and Mac consumer selection changed. No explicit
  catalogue restart, no Sports/CLOB restart, no financial restart. Both financial
  lock inodes818853/813893, all checked financial/source units/PIDs and both WS
  PIDs3763433/3759160 were unchanged before/after installation.

Exact final DATA tests:48 local / same48 VPS PASS, network denied. One bounded
critical review found two completion defects (new-arrival backlog and timeout
headroom); both were reproduced/fixed. The final catalogue headroom follow-up
found no new issue. These are not96 independent live observations.

Delivery uses candidate998a72ddb80e0337, manifest
`998a72ddb80e0337b1f7b0292c092f463e333815eac7c236d98e118f092c6aa1`.
Catalogue headroom uses candidate4c00ff6a26760e7a, manifest
`4c00ff6a26760e7a964eaa458e1c947bb90dd08146368f3de3876f26704ee52f`.
Sports/CLOB keep their previously selected candidateb79fcd827bea31cc.

Initial real delivery rounds succeeded:48segments/13,485,296bytes freed, then
64segments/17,985,407bytes freed after verified Mac ACK. At those observations
CLOB was reconnecting against a stale catalogue; **do not call that continuous
healthy CLOB coverage**. Final actual catalogue/WS/backlog readback is appended
below. Gaps stay UNKNOWN and cannot be backfilled as prospective evidence.

## Claude reader: loss repaired; executable-window acceptance still open

At18:12:22UTC, an independent fixed sealed-file snapshot verified every hash,
raw row count, import receipt and first local mtime. The current reader returns:

| Role | RECV rows | Valid non-ping JSON frames | Current adapter returns | Old unsafe key unique rows |
|---|---:|---:|---:|---:|
|Sports|10,133|10,133|10,133|118|
|CLOB|33,722|32,379|32,379|2,124|

Sports contains98 distinct game IDs, **not98 eligible matches/trades**. The loss
fix is confirmed for these bytes; current source SHA is
`d2692172d49aebbb77dfde1a4462758ec027be81cd86b67a69043a4fac937247`.
No judge, outcome evaluation or research code edit was run by Codex.

Remaining reader issues to hand to Claude through the owner:

1. Seal existence alone is not hash/schema/epoch/row/receipt validation; corrupt
   rows are silently skipped by the reader. Expose an explicit incomplete/error state.
2. `stakan()` uses venue timestamp for availability while Sports uses VPS receive
   time. Retain both; join by actual local receipt, never by an earlier venue clock.
3. Depth from a previous book is carried across best-price changes without applying
   level updates. It cannot establish current executable depth at the new ask.
4. The judge maps only tokenA and may synthesize the other side as1-bidA. Use the
   actual tokenB ask/depth; missing sides and gaps are UNKNOWN.
5. The running storozh started07:59:29UTC; it reloads the judge, but imports the
   adapter normally. A corrected file does not prove its cached module was reloaded.
   Require a runtime source version in its next result.

These findings concern the WS adapter/judge path. They do **not** automatically
invalidate the separate six reported V2 observations; that requires their actual
source lineage. Six wins cannot establish a durable win rate, regular7/day or a
credible annual return. Keep the frozen9Nov checkpoint and separate economic GO.

Origin research/fabrika-v1 remained30951f9 at this check. Local source edits and a
pasted git commit command are not publication proof. No Claude message was sent.
Formal interface: [reader contract](../docs/POLYMARKET_WS_RESEARCH_READER_CONTRACT_V1.md).

## Closeout and next gate

The late one-shot `monthly-2` task was deleted after its durable NO_ADMISSION
receipt. Native Monthly and other jobs were preserved. Foreign NET automation
closure and allowlist changes remain untouched and outside this repair commit.

Independent reviewer runtime: gpt-6-astra/high, session
01a19d6b-1695-7531-9c77-f860c6944778; model/effort verified from turn_context.
Final fixes after findings were checked by the primary; no second financial
approval is implied.

Evidence: [directory](evidence/live_operational_repair_20261102/). Public artifacts
exclude account balances, IDs, keys and raw broker responses. Next engineering
work is the PUMP serial throughput bottleneck and a versioned Monthly handoff,
not another strategy or Brain expansion.

## Final actual recovery evidence

At18:23:13UTC the completed150-market catalogue was fresh (generated18:19:52.315UTC,
258.421s elapsed). Both original WS PIDs were RUNNING. After that catalogue was
published, checked recent sealed CLOB data contained8 real books,309 price changes
and one market with books for both outcome tokens. These are DATA events, not trades.

Native delivery round at2026-11-02T18:27:46.188000+00:00: exit0, 64 newly imported
segments, 18007812 source bytes freed after verified ACK,
321 segments still queued in that observation; warnings=[].
This proves resumed progress, not completion of the entire backlog. Native catch-up
continues without AI or another collector. Catalogue and both WS remain on one VPS;
financial files, permissions, account lock ownership and risk were preserved.

The64MiB catalogue headroom reserve shortens the earlier2–3h estimate for Mac-offline
buffering. The source cache is finite; overnight Mac-sleep continuity is not accepted.
No paid storage, larger quota or silent retention deletion was introduced.

Monthly candidate remains UNSELECTED despite281/281 acceptance. The live v6 OPENING
bug has not been declared fixed in production. PUMP DATA throughput repair likewise
remains the next bounded change; one passing18UTC hour does not erase earlier failures.
