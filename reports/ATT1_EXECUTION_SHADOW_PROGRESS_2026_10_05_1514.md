# ATT1 bounded evidence — October 5 15:14 UTC

Observed at **15:14:03.940 UTC /18:14 Cyprus**, using one bounded read-only SSH
query. Machine receipt: `ATT1_EXECUTION_SHADOW_PROGRESS_2026_10_05_1514.json`.
Private raw query SHA256:
`86d09ba6a20c98f9bd58ee3bdca97236b8da2a3056b2222b3700b2f8a6b347aa`.
No second SSH query, restart, deployment, broker call or policy change.

Public lifecycle: **13 sessions /6 RECOVERY_GAP /1 verified clean terminal**.
This is one additional gap since 08:19; its identity/cause was not captured by
this bounded query. Do not infer a cause or a clean UNI terminal. The next
inspection recipe retains gap identities. WLD is held/protected at 14.8 units
in public simulation, with no recorded incident in that held session.
ADA remains the same single clean decision
`0f495bfefe236160aa3d561eb65dcb5aba1bafffbe492c21c172d698672f8477`, exact deployed
closure replay PASS and simulated net-R `-1284979741/1225000000` (−1.048963).
It is not credited again. These are simulation results, not broker/account truth.

Both probes remain RUNNING under original PIDs1676226/1676227, NRestarts0.
Study/context hashes and the original32-file source-manifest mapping match.
Production PIDs1648585/1623208/1584802 and deployed driver97239996… are unchanged.
Transport capture1,919,469,678 bytes, funding3,482 bytes, below their4GiB caps;
free disk39,979,175,936 bytes exceeds the5GiB guard. Absolute deadlines remain
**October6 14:12:25.311/.515 UTC /17:12 Cyprus**. Never reset or extend them.

New35-second incremental batch:385,163 complete gzip members;9,758 REST books,
361,328 WS books,14,077 trades. All371,086 book wire hashes/projections matched.
Eight REST use-time stale books include seven stale at the server timestamp;
two had a previously received CTS-fresh WS book. One CTS-stale book would appear
fresh if ts were substituted. REST CTS receive-age p50/p99/max251/1122/3038ms;
use delay1/6/188ms. WS receive-age91/130/729ms, use delay0/1/101ms.
Received WS books were fresh; silence is outside that population. No new
disconnect/reset/quiet evidence in this batch; earlier discontinuity remains.
Missing CTS stays UNKNOWN; quiet does not prove freshness. No transport switch.

Across disjoint batches:42,767 REST/1,753,853 WS books,35 REST use-time violations,
29 server-stale and23 causal REST-stale/WS-fresh pairs. Do not average percentiles.
Cursor preserved at `capture-497546.jsonl.gz`, compressed offset6,037,504 in
`.private/att1_execution_shadows_20261004/analysis_cursor_20261005T151403.json`.
The analysis frontier still trails capture; these are not completed48h findings.

Funding adds WLD prefix21768ad4… after the original ten-header baseline.
Three unique future START intents (XMR/UNI/WLD) are all outside the frozen eight:
**0 admitted policy comparisons /INSUFFICIENT_EVENTS /NOT_MONEY_READY**.
Exact prefix pins deduplicate events. Dated fees and synthetic sizing remain
assumptions, separate from actual selected-account evidence.

Actual packet remains BLOCKED_DATA. NEW orders OFF; strategy/risk/hold/fees/2s
gates unchanged. Promotion still requires2–3 clean filled terminals/net-R,
actual inputs, fresh exclusive dossier and separate owner GO. The heartbeat
remains ACTIVE while the probes run. At termination preserve actual coverage,
report early failure as BLOCKED, and close the monitor without fabricating48h.
