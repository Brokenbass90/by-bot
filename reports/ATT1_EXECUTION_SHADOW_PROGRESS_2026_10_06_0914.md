# ATT1 bounded evidence — October 6 09:14 UTC

One bounded read-only SSH query for the new09:14 heartbeat, observed
**09:14:55.190 UTC /12:14 Cyprus**. Machine receipt:
`ATT1_EXECUTION_SHADOW_PROGRESS_2026_10_06_0914.json`. Private raw-query SHA256:
`f1534d10a81ea559c1c927bd3b5487b0ebd4eaf9aae46100b9e4806eacc953de`. No second SSH, broker calls,
restart, redeployment, source rewrite or production policy change.

**Public16 sessions /9 RECOVERY_GAP /1 verified clean ADA /0 held.** Two new gaps:

- **SOL** (`80505b4da02de1676ed842d24ce25cba56d48818a48befb85f501d7252872ab8`), recorded `public polling continuity gap`
  at **2026-10-06T09:02:01.426+00:00**. Earlier filled0.2 simulated units, then full simulated
  exit0.2 at120.53; it earns no clean terminal credit.
- **PEOPLE** (`83853dc0811e47fbc041c18746cea2f1b49d5a8a837310f92db91ba7665a51d8`), recorded
  `rejected future/stale public book` at **2026-10-06T09:02:16.331+00:00**. Three simulated
  entry fills441+228+719=1388 units, followed by simulated exit482+906=1388.
  The reason is a disjunction: no assertion here that future timestamps rather
  than stale CTS caused it. No clean terminal credit.

Source hashes bind both captured journals (SOL60b1b388…/PEOPLEb9478771…). All nine
captured journals pass local canonical/event/hash-chain validation; prior seven
retain exact hashes. Dirty-journal deployed replay was not run. Underlying
transport/scheduling/CTS-vs-ts root cause is **NOT_CAPTURED** by these journal
receipts; do not infer it from a separate SEI/SUI probe or alter live transport.

ADA exact deployed closure replay PASS, same journal/profile and simulated
net-R−1.048963; not credited again. These are public simulations, not broker
positions/PnL or proof of profitability. The clean gate remains unmet.

Both research probes **RUNNING**, original PIDs1676226/1676227, NRestarts0.
Original32-file manifest mapping, study and context pins match. Production
PIDs1648585/1623208/1584802 and NRestarts0 unchanged; deployed driver97239996… matches.
Transport compressed snapshot2,911,498,019 bytes, funding7,070 bytes, each below
4GiB; free disk38,960,615,424 bytes exceeds5GiB. Persisted deadlines remain
**October6 14:12:25.311/.515 UTC /17:12 Cyprus**, never reset or extend.

New incremental transport batch: **358,236 complete gzip members**, 8,333 REST,
335,673 WS books and14,230 trades. All344,006 wire hashes/projections match.
No CTS-freshness violation or new disconnect/reset/quiet event in this processed
batch; this does not establish production continuity or cover the later SOL/
PEOPLE event times. Batch CTS receive-age p50/p99/max: REST242/915/1917ms,
WS93/155/1393ms; receive→use REST1/19/1277ms, WS0/1/290ms. Earlier published REST/
WS discrepancy and disconnect evidence stands. Missing CTS stays UNKNOWN and
silence is not proof of freshness. No averaging per-batch percentiles.

Disjoint processed totals:68,799 REST/2,820,674 WS books,39 REST use-time violations,
33 server-stale and27 causal REST-stale/WS-fresh pairs. Cursor `capture-497553.jsonl.gz`,
offset22440273 in `.private/att1_execution_shadows_20261004/analysis_cursor_20261006T091455.json`. Analyzed receive clocks
only through **Oct5 09:20:16.765UTC**, substantially behind capture. Complete48h
analysis remains pending; this is not the terminal report.

Funding adds **PEOPLE**, source prefix82b7dc93… after the ten-header baseline;
other five prefixes are not recounted. **Six future unique STARTs**, five outside
frozen8; SOL alone is inside but its synthetic R$0.40/N$100 sizing was rejected
BELOW_MIN_QTY. The newly captured SOL START header independently matches the
exact funding prefix pin. Its nominal entry120.73, raw stop125.38449999999999 and
minimum qty0.1 imply a nominal stop-distance lower bound0.465449999999999USDT,
already above the synthetic0.40 cap before buffer/fees/funding. This arithmetic
is not a rerun of rounded money admission or a claim about actual broker risk.
**0 comparable admitted funding-policy events**. Candidate remains
research-only; synthetic sizing and dated fees do not establish actual cash,
risk, costs or a new money policy. No silent universe expansion.

Actual packet **BLOCKED_DATA**, NEW orders OFF. Strategy/admission/risk/hold/fees,
hard2s gates, live transport, broker mode and authority remain frozen. Money
requires2–3 clean prospective filled terminals/net-R, actual inputs, fresh
exclusive dossier and separate owner GO. Heartbeat remains ACTIVE until actual
termination/deadline; early failure must be reported BLOCKED, never completed48h.
Alpaca/KITY/ETS/Claude not inspected or changed in this cycle.
