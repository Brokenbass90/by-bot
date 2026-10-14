# Liquidation source V2 — actual isolated launch, October14

**COLLECTOR_RUNNING_WAIT_FIRST_EVENT.** Direct owner GO covers implementation
and continuous public-source collection only. No strategy/judge/outcome run,
trading client, credentials, money/risk authority or LIQ_OTSKOK_4H_V2 launch.
Alpaca's separate October14 16:00 Cyprus fee-check remains the money priority.

Actual independent readback at07:56:50UTC/10:56:50Cyprus:

- `bybit-liquidation-source-v2.service` active/running, PID2094234, NRestarts0;
  subscription confirmed, public ping/pong observed, systemd45s watchdog fed.
- 12 frozen major symbols;196.251 seconds since subscription acknowledgement.
  **0 observed liquidation events**,10 received protocol frames. This is a
  quiet source, not actual event-normalization proof or a completed experiment.
- Raw frame/hash-chain integrity PASS, no observed schema/time/duplicate QA
  flags. Actual event side/causal reconstruction remains WAIT_FIRST_EVENT.
  Full exchange completeness remains UNKNOWN: this topic provides no sequence
  or backfill proving absence of missing events. Quiet does not imply freshness.
- A real second-writer probe returned73/ALREADY_RUNNING before network/capture;
  original writer remained active. Restart/recovery/partial-record and storage
  failure behavior is tested offline; no intentional service crash/restart.

Read [deployment evidence](evidence/bybit_liquidation_collector_v2_20261014/DEPLOYMENT_RECEIPT.json),
[frozen source manifest](evidence/bybit_liquidation_collector_v2_20261014/SOURCE_MANIFEST.json)
and [package/test pins](evidence/bybit_liquidation_collector_v2_20261014/PACKAGE_RECEIPT.json).
Source manifest SHA256:
`a9bcb7a12973a57e451557bcdc8d9297830e5e6c1a54098a6b5fd98d6d59ff5e`.

## Source and causal schema

Normalized source version `BYBIT_ALL_LIQUIDATION_SOURCE_V2`, epoch
`ec8456549b574850a44cb051b68c08ba`. [Official Bybit protocol](https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation)
defines S as liquidated position side: Buy→long, Sell→short; p is bankruptcy
price. It is not an execution-price or fee/slippage input. Public connection and
20-second JSON ping follow [official connection guidance](https://bybit-exchange.github.io/docs/v5/ws/connect).

Each fsynced journal record binds original WS text payload (or exact base64
bytes), receive UTC/monotonic timestamps, raw payload SHA, canonical raw item
SHA, normalized events and a record hash chain. Transport headers are not
captured. Event fields retain raw T as `ts_ms`, frame `ts` as `frame_ts_ms`,
receipt as `t_available_ms`, symbol/position side, bankruptcy quantity/price
basis, manifest SHA and a unique **capture** event ID. Capture IDs are not
exchange event IDs. Wrong units/missing T/schema/topic are retained as raw QA
failures without substituting receipt time. Clock-skew events have explicit
UNKNOWN causal-clock status.

Identical source-item hashes are **duplicate candidates**, retained with flags;
legitimate identical exchange events cannot be distinguished without an ID.
The online recent-item cache is bounded to50000, supplemented by restart replay.
Observed event count includes candidates; it is not a deduplicated or statistically
independent research sample count. Future research preregistration decides its
eligible population; this collector chooses no direction, horizon or outcome.
There are no candles/execution prices/funding/labels in this source package.

## Operation and preservation

Dedicated root `/opt/bybot-research/liquidation-source-v2-20261014`:

- `app/`: seven byte-pinned source/test files; no V1 code replacement.
- `runtime/source-manifest.json`: immutable epoch/config/source identity.
- `runtime/runs/<run-id>/frames.jsonl`: separate durable raw/event hash chains.
- `runtime/heartbeat.json`: atomic current health, public counters/QA and digest.
- `runtime/writer.lock`: one writer across service/manual entry points.

Automatic watchdog/process recovery uses the same sealed epoch and validates
all existing capture chains. Restart/disconnect intervals remain UNKNOWN gaps;
partial/corrupt captures or changed code/config stop explicitly. They are not
truncated, repaired or silently repinned. Max raw capture4GiB/min free1GiB are
source storage bounds; hitting them exits78 without a restart loop. No automatic
cleanup/delete/limit increase. Service is enabled at boot, with192MiB memory,
20% CPU, low I/O priority and write permission only for its runtime. Existing
broker config/env/runtime and SSH files are inaccessible inside this unit.

Actual before/after verification preserved all37 installed Alpaca app files,
HALT bytes and cron hash; Bybit1648585, web1623208, ATT11584802, V1492740 all
retain NRestarts0. V1 script/unit SHA and data prefix/inode unchanged. The existing
V1 collector continues its previously running append-only work; no old data or
directional result is rewritten/rejudged. October12 semantic-taint inventory is
retained as dated evidence; V2 is outside the legacy latest-file directory.
Claude checkout/processes, KITY and Alpaca broker state were not queried/changed.

Validation: **48 local targeted PASS**, **34 new-collector VPS targeted PASS**,
systemd unit verification and actual independent readback. Full suite not rerun;
its historical NOT_GREEN result remains. Root review only; prior independent
review quota restriction was preserved, no external signoff claimed.

Scoped stop/rollback is `systemctl disable --now bybit-liquidation-source-v2.service`;
preserve its app/manifests/raw history. No V1/production restart, broker action
or source-directory cleanup is part of rollback. It was not executed.

Next: collect actual events under this version. **LIQ_OTSKOK_4H_V2 remains OFF**
until separate preregistration, its source-count gate and separate owner GO.
