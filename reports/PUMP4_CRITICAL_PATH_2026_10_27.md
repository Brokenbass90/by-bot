# PUMP4 — actual critical path and alternative source, 27 October 2026

Supersedes the pending08H1 status in `PUMP4_SOURCE_RECOVERY_2026_10_27.md`.
Continue candidate `e4feca498f37e27d`; no new strategy audit, judge/PnL run,
funding download, Monthly selection, 300s entry rule or financial GO.

## Actual installed path

| H1 UTC | CURRENT within original60s | Median / maximum publication | Interpretation |
|---|---:|---:|---|
|08:00|48/129|67.239 /82.931s|FAIL, first complete new-e4 H1|
|09:00|135/135|37.895 /56.265s|Timing PASS during guarded priority trial; protected-health trial FAIL|
|10:00|45/134|69.0485 /86.450s|FAIL after priority rollback|
|11:00|43/134|67.4465 /84.828s|FAIL after priority rollback|
|12:00|51/135|67.242 /83.547s|FAIL after priority rollback|
|13:00|50/135|67.717 /85.587s|FAIL, ordinary priority; isolated probe ran separately|

Each of these six archives passed its file hashes. No signals occurred.
CURRENT-before-CATCHUP ordering passed wherever catch-up existed;08H1's seven
catch-up publications finished by89.020s,11H1's one by87.074s. Unavailable and
blocked symbols remain explicit in the [summary](evidence/pump4_critical_path_20261027/h1-summary.json).
No completed hour was restarted or recollected.

At08H1,136 sources were ready and one unavailable; all14 failed10006 attempts
were retained and recovered.289 actual HTTP reads,275 successful capture pages,
zero BLOCKED_SOURCE. Source delivery and durable publication are separate:
CURRENT source median44.833s/max62.475s; parent processing73.771s and classifier1.881s.
The previous observation-cache benchmark was real, but did not make this H1 timely.

## Measured resource bottleneck and failed protected trial

The08H1 parent used28.47 CPU seconds and accumulated49.29s runnable queue wait
within89s wall time. DATA had200% quota,768MiB ceiling, zero quota-throttling;
child aggregate CPU28.695s. The financial consumer used6.45CPU seconds over97s.
The2CPU VPS had load about7 and3.68% steal. CPU scheduling is the strongest
measured bottleneck, not the sole one: interval PSI accumulated IO-some11.74s /
IO-full0.63s and memory-some12.35s /memory-full1.64s. Existing other scopes were
observed only; their settings and work were not changed.

A reviewed one-H1 DATA-only CPUWeight100→1000 experiment kept the exact source,
root, strategy,200% quota,768MiB, timer and financial owner unchanged. Monitor5s,
Monthly existing-receipt age<=90s/sourcePASS/issues[]/waiting-session/accounting[],
PUMP PID/lease/OFF/heartbeat, and NET inactive were protected. A separately armed
09:03UTC rollback timer was installed before the weight change.

**Automatic rollback occurred09:00:57.314UTC**: Monthly's latest receipt exceeded
90s. The last accepted age was89.447s; this is an actual guard failure, not proof
of a Monthly financial error or a proven causal attribution. Do not relax the guard
or call this a safe production PASS. The135 CURRENT publications finished before
the rollback; subsequent H1s were back at normal priority and failed timing.

Readback12:50UTC: original DATA unit restored, SHA
`6acbf62f473876e6be790727b4bed1b02db0c19930bfd0c97d831655a15dc424`;
expiry service succeeded, timer inactive after firing. Rollback tests9PASS cover
interrupted/concurrent/repeated restoration and foreign-temp refusal; both
independent critical reviews closed their Important findings. No financial unit,
configuration, scope, PID or original account lock was changed by this trial.

## Bounded alternative DATA experiment

Fixed before13H1: AAVEUSDT,ACTUSDT,APTUSDT,BANANAS31USDT,BTCUSDT,ETHUSDT,SOLUSDT,ZROUSDT.
No outcome selection or replacements. Detached public-only process3057831,
`/opt/bybot-research/pump4-server-orders-off-20261023/source-architecture-probe-20261027-13`.
The production DATA timer and sole financial owner continue e4 unchanged.

Eight late two-row REST reads of the12UTC boundary matched sealed full captures
for the closed candle and following open:8/8. Individual reads0.171–0.485s,
278–294bytes. This is payload/content evidence after the deadline, never timely
entry evidence. A separate content-only check composed1000 already-closed prefix
rows plus one newly closed row and following open:1001 closed Decimal OHLCV/turnover
rows matched the complete12H1 archive for8/8 symbols. The prior forming bar was
replaced, never reused as closed. No signal replay or monetary authority occurred.
[Content diagnostic](evidence/pump4_critical_path_20261027/prefix-content-diagnostic.json).

WebSocket13H1: connect12:58UTC, end13:02UTC; original deadline13:01UTC.
Original V1 result **VALIDATION FAIL**, not a clean prospective PASS. Captured raw/hash/UTC/monotonic clocks before parse, subscription ACK,
confirmed closed candle and next-open event separately. No last-trade timestamp
substitution, overwrite of changed duplicates or reconnect continuity claim.
Malformed JSON, rejected ACK, disconnect and failed reconnect disqualify support.
Compare only the eight observations with the existing full sealed13H1 archive.
No second137-symbol census. One diagnostic source is not a trading writer.

The probe follows [Bybit public kline semantics](https://bybit-exchange.github.io/docs/v5/websocket/public/kline),
[REST kline scope](https://bybit-exchange.github.io/docs/v5/market/kline), and
[connection/ping guidance](https://bybit-exchange.github.io/docs/v5/ws/connect).
Code and regression tests are separate from production source pins.15 probe tests
and9 rollback tests PASS. Focused independent probe/schema/evidence re-reviews:
0 Important. All117 installed production-package files still match the e4 manifest.

### Actual13H1 result and explicit diagnostic correction

One connection, successful ACK12:58:00.769UTC, no disconnect or rejected ACK.
All eight combined close/open frames arrived at original receive timestamps
T+338,381,631,660,662,753,773,1025ms. V1 rejected them because its validator
incorrectly required the closed row's `timestamp <= row.end`. Actual combined
frames carry a timestamp after the old candle's end, shared with the new candle
and frame timestamp. For example the first closed row endsT-1 but has timestamp
T+254 and was receivedT+338. This was a probe defect, not a signal/strategy change.

The immutable [original V1 receipt](evidence/pump4_critical_path_20261027/original-ws13-receipt.json)
and [manifest](evidence/pump4_critical_path_20261027/original-ws13-manifest.json)
preserve all eight errors and false support. The detached VPS package was not
changed or re-run after observing the result. V2 corrects the unsupported timestamp
upper bound to `timestamp <= frame.ts`; confirm/start/end/interval, frame timestamp
at or after boundary and receive time at or after boundary remain necessary.
Timestamp never substitutes for original receive time or proves closure alone.
Observed-pair regression failed before the fix;15 probe tests pass afterward,
including future-of-frame timestamp rejection. Independent critical schema reviewPASS.

[Offline V2 derivation](evidence/pump4_critical_path_20261027/derived-ws13.json)
reprocesses the same raw-log bytes/hash against the independent sealed REST files:
8/8 closed Decimal OHLCV/turnover, float OHLCV and next-open values exactly match,
no conflicting duplicates, same connection, original338–1025ms pair-receive delays.
Raw/receipt/parser hashes are explicit. It retains original V1 FAIL and sets
`clean_prospective_pass=false`, `production_admission=false`. A focused independent
review reproduced the derivation and verified extracted raw frames/hashes/base64.
Wall/monotonic divergence<=7.263ms measures local clock stability, not absolute UTC
accuracy or a new source-clock certification. Eight-symbol capacity and production
financial publication are not established by this offline result.

The normal13H1 pipeline independently failed50/135 timely publications. Sampled
parent CPU25.55s and runnable-queue wait52.060s, child29.013CPU seconds, no quota
throttle. This is consistent with the08H1 contention finding. The isolated probe
supports an engineering delivery hypothesis; it does not repair the selected path.

An eight-symbol success would support a delivery hypothesis, not137-symbol capacity,
source-to-financial-publication PASS or TINY_READY. Current `closed_h1` still requires
1002 rows captured after the boundary, and `causal_plan` revalidates them. A future
incremental adapter needs a versioned custody/source contract: sealed prefix,
contiguous confirmed new row, exact universe/config/code, original timestamps and
epoch, independent state/parity validation. Historical prefix rows must never gain
fresh timestamps. Existing5s source freshness,60s deadline, risk and protection
rules remain in force. This probe cannot be wired directly into financial admission.

## Financial result and precise next gate

At13:06UTC, original owner PID3029723,0restarts, lock818853 held,3458 clean
actual OFF cycles, empty financial histories, no GO and0writes; source and config
pins passed. Monthly v6 unit/config unchanged; at13:06UTC existing receipts had
sourcePASS/issues[] and OUTSIDE_MONTHLY_WINDOW. No reactivation or NET exit.

**LIVE BLOCKED / TINY_READY false.** Outstanding: sustainable installed-path timing
without violating protected scopes; incremental source custody/admission integration
if the diagnostic succeeds; fresh read-only account/minimum-size/fees/capacity and
quote/native-protection evidence on an eligible signal; exact owner risk/cost policy
and financial GO. Economics remains INCONCLUSIVE, not disproved by funding and not
proven profitable. A separately authorized technical micro and income deployment
are different decisions. No exact trade time or earnings are promised.
