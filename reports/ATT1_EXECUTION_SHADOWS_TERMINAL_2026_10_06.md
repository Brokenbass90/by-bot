# ATT1 48-hour execution research — terminal October 6

**Capture COMPLETE_DEADLINE; all archived snapshot members processed.**
**Money verdict BLOCKED_DATA /NOT_MONEY_READY.** Terminal capture is not strategy
PASS, evidence of net edge, permission to change policy, or canary readiness.
Machine receipt: `ATT1_EXECUTION_SHADOWS_TERMINAL_2026_10_06.json`.

Transport deadline **14:12:25.311UTC**, funding **14:12:25.515UTC** October6,
exactly48hours from their original starts. Both persisted heartbeats report
COMPLETE_DEADLINE; systemd inactive/MainPID0/Resultsuccess/NRestarts0 is expected
successful termination, not a lost original PID. Original PID records1676226/
1676227 remain in heartbeats. Terminal heartbeat publication occurs308ms/5795ms
after deadline; final received transport record is14:12:25.305UTC, before deadline.
No reset, extension, restart or deployment. Read-only remainder scan started
14:59UTC and final broker postcheck15:10UTC; study population is unchanged.

Original32-file manifest mapping, context5b7d909e…cf9a37, both study pins match.
Production PIDs bybot1648585/web1623208/public ATT1 manager1584802, NRestarts0,
remain unchanged. Driver97239996…d6885 unchanged. Transport3,194,924,348 compressed
bytes, funding8,201 bytes, each below4GiB; free disk38,658,371,584 bytes above5GiB.
Postscan capture file inode/byte inventory is unchanged. Full capture remains on
VPS under `/opt/bybot-research/att1-execution-research-20261004/runtime`.

## Transport findings

Disjoint compressed-member offsets total **6,459,441 records**, exactly equal to
terminal collector kind counts: **172,636 REST books /6,019,469 WS books /
267,329 trades**, plus7 start/control/connect/disconnect/quiet records.
All **6,192,105 book raw-wire hashes** were verified. Independent raw-wire
projection reconstruction was added during the study and covers **4,766,571**
books; older batches only used the captured projection. This partial independent
coverage is explicit, not a claim that every derived field was independently
reconstructed. Earlier bounded batch receipts and terminal cursor are pinned.

- REST use-time CTS gate: **631 STALE**, 172,005 FRESH; 543 already stale at server
  publication timestamp. At least335 have stale CTS despite fresh `ts` under the
  later CTS-vs-ts classifier. `ts` must not silently substitute for missing/stale CTS.
- At least459 repeated CTS/sequence observations; counters reset at batch
  boundaries, so repeats and CTS-vs-ts counts are lower bounds, not exhaustive.
- **158 causal REST-stale/previously received WS-fresh pairs**, cross-sequence
  evidence pinned in samples. This demonstrates a transport discrepancy for
  observed SEI/SUI books, not its cache/quiet/publication root cause.
- Every received WS-book projection was within2s; **silence is excluded**. One
  quiet timeout, one keepalive disconnect, reconnect and both-symbol snapshot
  resets were captured with exact source member/hash pins. A received fresh
  snapshot does not prove continuous WS coverage or production compatibility.
- Maximum receipt→use delay across disjoint batches: REST2518ms/WS290ms;
  maximum CTS use-age REST5190ms/WS1738ms. Batch p50/p99 are retained in JSON;
  global percentiles were not computed or averaged from batch percentiles.

Missing CTS remains UNKNOWN; quiet is not proof of freshness. Cache/quiet root
cause remains unproven. No live REST→WS replacement, threshold relaxation,
observation candidate deployment or assertion that all public gaps are fixed.
The useful next bounded task is a separately reviewed CTS-aware transport/
observation candidate with raw causal replay and disconnect handling; existing
2s gate, single journal writer, strategy/admission/risk/hold remain frozen.

## Funding population

Exactly **7 unique future public START intents after the ten-header baseline**,
deduplicated by exact source prefix pin. XMR/UNI/WLD/TRX/PEOPLE/LDO are outside the
frozen eight-symbol execution admission. SOL is inside but synthetic R$0.40/
N$100 sizing returns BELOW_MIN_QTY. **0 comparable admitted policy events**:
terminal result **INSUFFICIENT_COMPARABLE_EVENTS**, not candidate PASS or KILL.
Do not extend study, expand universe, raise risk, or fabricate a policy comparison.
Dated fee/synthetic sizing assumptions do not establish actual account cash,
funding, quantity or reserve readiness. Existing money reserve stays unchanged.
Prior historical reserve study may support a separate reviewed contract; this
48hour prospective sample supplies no admitted policy-comparison evidence.

## Public lifecycle / remaining money gates

Snapshot15:03:12UTC: **17 sessions /10 RECOVERY_GAP /1 verified clean ADA /0 held**.
ADA exact deployed closure replay PASS, same profile/journal and simulated
net-R **−1284979741/1225000000 ≈−1.048963**. It is not credited twice and proves
only one simulated lifecycle, not profitable edge or actual broker execution.

New tenth gap LDO, decision657d4334…87e2cc, journal56df668f…677d955:
recorded `rejected future/stale public book`, exchange14:01:29.101UTC and
received14:02:11.954UTC. This disjunctive classification does not establish which
source clock/scheduling/root cause failed. Separate SEI/SUI study evidence cannot
be assigned to LDO. All10 captured dirty journals pass local strict canonical,
event/hash-chain validation; prior nine hash pins unchanged. Dirty deployed
replay NOT_RUN, underlying new gap cause NOT_CAPTURED.

Actual account packet remains BLOCKED_DATA; inherited LINK/cash/reserve inputs
were not freshly solved in this closure. Money still requires2–3 clean
prospective filled terminals/net-R, actual inputs/fresh exclusive dossier and
separate owner GO. No broker mode write, NEW orders, authority/admission/risk/
hold/fee/2s/live-transport change. OLD entry retirement remains preserved.

## Preservation and continuation

Private raw initial/final/postcheck receipts and10 journal copies are read-only;
full hashes, final disjoint offsets and inventory are in JSON and
`.private/att1_execution_shadows_20261004/analysis_cursor_terminal_20261006.json`.
Complete-member accounting, book hashes, original deadlines, journal chains and
funding population assertions PASS. The research-only services stay inactive;
the public ATT1 manager continues unchanged. The completed heartbeat `att1-bounded-continuity-evidence` was **deleted through
the automation tool** after preserving this terminal evidence. No new study was
started and no deadline changed.
KITY unseen-source acceptance is the next new production intake; preserve all
ATT1 evidence for separately reviewed continuity/reserve work.
