# ATT1 bounded evidence — October 5 21:10 UTC

Observed **21:10:24.515 UTC /October 6 00:10 Cyprus**, one bounded read-only SSH
query for the new 21:08 heartbeat. Machine receipt:
[ATT1_EXECUTION_SHADOW_PROGRESS_2026_10_05_2110.json](ATT1_EXECUTION_SHADOW_PROGRESS_2026_10_05_2110.json).
Private raw query SHA256: `b3686d48608d1690fe2275f0ce1cd0d430b4f7d8a3c948f4c226d77f708c0c2e`. No restart, deployment,
broker call, live write or policy change; this is not the final 48-hour report.

Public lifecycle: **14 sessions /7 RECOVERY_GAP /1 verified clean terminal /0 held**.
The additional gap is **WLD**, previously held at 14.8 simulated units. Its journal
records `public polling continuity gap` at **2026-10-05T17:57:53.995+00:00**, then a simulated
full exit at 0.5593. That exit earns no clean-terminal credit. The previously
unidentified sixth gap is **UNI**, with the same recorded reason at
**2026-10-05T08:23:03.842+00:00**. These event reasons do not establish the underlying timing
or transport cause. All seven captured gap journals passed local canonical/hash
chain validation; dirty-journal deployed replay was not run. Sources remained
unchanged during capture. WLD journal SHA256:
`b647cb17cc31caf857a2263c34204f09c9ffc574b91a3832b8443957e3e4c2c1`.

ADA remains the same single clean decision
`0f495bfefe236160aa3d561eb65dcb5aba1bafffbe492c21c172d698672f8477`.
Exact deployed closure replay PASS, journal SHA25620e24c9f… and frozen profile
79d23e38… match; simulated net-R remains `-1284979741/1225000000` (−1.048963).
No duplicate credit and no claim of positive edge or selected-account truth.

Both probes RUNNING under original PIDs1676226/1676227, NRestarts0. Study/context
hashes and the original 32-file manifest mapping match. Production services are
active under original PIDs1648585/1623208/1584802, NRestarts0; deployed driver
97239996… unchanged. Transport file snapshot2,251,423,732 bytes (heartbeat
2,251,362,958), funding4,613 bytes, below each 4GiB cap. Free disk39,639,478,272 bytes
exceeds the 5GiB guard. Original deadlines **October 6 14:12:25.311/.515 UTC
/17:12 Cyprus** remain fixed. No reset or extension.

Incremental transport batch: **390,986 complete gzip members**, 8,660 REST books,
366,713 WS books, 15,613 trades. All375,373 book raw hashes/projections matched.
Three REST books violated CTS freshness, all already stale at the server timestamp,
all paired with a previously received CTS-fresh WS book; REST seq lagged that WS
by3323/1519/3574. Two would appear fresh if `ts` replaced `CTS`. The first example
had REST CTS age2305ms, server-minus-CTS2223ms and WS CTS age88ms at REST receive.
It is source evidence of differing publication freshness, not proof of a cache
or quiet-market root cause and not a reason to switch live transport.

| New batch | CTS receive age p50/p99/max, ms | Receive→use p50/p99/max, ms |
|---|---|---|
| REST | 246 /1065 /2305 | 1 /13 /482 |
| Received WS books | 93 /136 /568 | 0 /1 /219 |

No new disconnect/reset/quiet event appears in this analyzed batch. Earlier
ping-timeout/reconnect evidence remains; received fresh WS messages do not cover
silence. Missing CTS stays UNKNOWN, quiet is not proof of freshness.
Across disjoint processed batches:51,427 REST/2,120,566 WS books,38 REST use-time
violations,32 server-stale and26 causal REST-stale/WS-fresh pairs. Percentiles
are batch-specific, not averaged. Cursor: `capture-497548.jsonl.gz`, offset45,805,839,
`.private/att1_execution_shadows_20261004/analysis_cursor_20261005T211024.json`. Analysis covers captured book receive clocks only through
October5 04:30:26.225UTC, well behind this 21:10 snapshot. Remaining capture
analysis is pending; do not present these counts as the complete 48h population.

Funding adds **TRX**, exact source prefixc8b0a9dc… at21:01:56.134UTC after the original
ten-header baseline. XMR/UNI/WLD are not counted again. Four unique future START
intents are all outside the frozen eight-symbol execution admission:
**0 admitted policy comparisons /INSUFFICIENT_EVENTS /NOT_MONEY_READY**. No universe
expansion. Synthetic quantities/draft risk and dated fee assumptions remain
separate from actual account cash, funding, risk and costs.

Actual packet remains **BLOCKED_DATA**, NEW orders OFF. Strategy, admission, risk,
hold, fees, hard2s gates, live transport, mode and authority stay unchanged.
Promotion still requires2–3 clean filled terminals/net-R, actual inputs, fresh
exclusive dossier and separate owner GO. Monitor remains ACTIVE until actual
termination/deadline; preserve real coverage and report any early failure as
BLOCKED, never completed48h. Alpaca/KITY/ETS/Claude work was not inspected or changed.
