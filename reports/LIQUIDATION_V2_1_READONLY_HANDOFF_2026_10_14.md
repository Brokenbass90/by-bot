# Liquidation V2.1 — prereg-compatible source epoch and read-only handoff

**V2_1_SOURCE_RUNNING_RESEARCH_GATE_PENDING.** The 12-symbol source could not
meet Claude's frozen requirement of BASE events across at least15 symbols.
Published prereg byte pin `3f73a2507c8e4a26c9b2da205114f819d4d5e709669e97dc1ae219d634421a63`
was verified at research remote `ca8a9e86187a319b0d199e14c374b79a1306d289`.
No research files, hypothesis, judge, horizon, costs or outcome were changed/run.

## Frozen universe before outcomes

Source rule was saved BEFORE the public census, SHA
`cb6ade293e85e9c048d9c30e7540a77d229b6c21570ba4c527b1129a785633e0`:
Trading linear perpetuals, USDT quote/settlement, no prelisting/TradFi,
supported source symbol grammar; turnover24h≥10M USDT; top25 by descending
Decimal(turnover24h), lexical symbol ties; **no refresh**. Selection reads only
[instrument metadata](https://bybit-exchange.github.io/docs/v5/market/instrument)
and [tickers](https://bybit-exchange.github.io/docs/v5/market/tickers), not
liquidation populations/strategy results. Two actual public GETs covered906
instruments/complete cursor frontier, yielding63 eligible liquid crypto perps.
The first unpublished census draft misclassified commodity perps with empty
marketRegion/underlyingTicker. The already-declared no-TradFi rule was corrected
using symbolType before activation/outcomes; draft retained, never launched.
No new public capture, liquidation-driven symbol choice or PnL selection.

Exact universe in frozen ranking order:

```text
BTCUSDT ETHUSDT SOLUSDT ZECUSDT NEARUSDT XRPUSDT HYPEUSDT STRKUSDT
BTWUSDT ENAUSDT SUIUSDT WLDUSDT OPUSDT QNTUSDT ADAUSDT DOGEUSDT
PUMPFUNUSDT 1000PEPEUSDT UNIUSDT TRUTHUSDT INJUSDT TIAUSDT BATUSDT
ONDOUSDT OGNUSDT
```

Universe manifest:
`fca461efdb07fbe8395c4acf56e2519368c2601a88c9f3cef0db1a149a0785b3`.
Source epoch started **October14 08:35:34.223UTC /11:35:34.223 Cyprus**,
ID `0688909d05884004b991bec76c6e4847`, source manifest
`46895caaef1e1689cd4224a544bb3e3287f41ef8a8a4ad702fd403cdcc2a4ddd`.
Normalized schema remains `BYBIT_ALL_LIQUIDATION_SOURCE_V2`; original semantics,
core collector, lock, watchdog, reconnect and raw retention are reused byte-for-byte.

## Actual health and evidence

At **11:42:49Cyprus**, new unit `bybit-liquidation-source-v2_1.service`
PID2095785, active/NRestarts0, confirmed subscribe/pong, watchdog advancing.
**50 raw observed liquidation items across14 symbols**,65 protocol/data frames,
no observed duplicate/schema/time QA flags or transport/restart gaps. Independent
raw/hash-chain and actual side/timestamp reconstruction PASS. First QNT Buy
maps to liquidated long with raw T/receive provenance; bankruptcy price stays
a notional proxy, never an execution/cost price.

These50 are **not BASE events**. Prereg still requires14-day warmup, ≥200 BASE
events after warmup across≥20 different UTC days/≥15 symbols, source QA and
the frozen additional checks. BASE count NOT_COMPUTED; source gate NOT_PASS.
Twenty-five subscriptions merely make the breadth requirement possible.
Full exchange completeness remains UNKNOWN_NO_SEQUENCE_OR_BACKFILL. Unknown
disconnect/restart/unobserved intervals must not become zero-liquidation hours;
duplicate candidates remain retained until preregistered eligibility/dedup.

Read [epoch receipt](evidence/bybit_liquidation_collector_v2_1_20261014/EPOCH_COMPLETION_RECEIPT.json),
[universe receipt](evidence/bybit_liquidation_collector_v2_1_20261014/UNIVERSE_RECEIPT.json),
[source manifest](evidence/bybit_liquidation_collector_v2_1_20261014/SOURCE_MANIFEST.json)
and [machine handoff](evidence/bybit_liquidation_collector_v2_1_20261014/READONLY_HANDOFF.json).

## Read-only paths for Claude

Dedicated VPS base `/opt/bybot-research/liquidation-source-v2-1-20261014`:

- Active journal: `runtime/runs/*/frames.jsonl`; normalized stream is each
  FRAME record's `normalized_events`. Raw/control/gap evidence stays alongside it.
- Universe: `source/universe_manifest.json`; source/config: `runtime/source-manifest.json`.
- Current health: `runtime/heartbeat.json`; metadata counts are raw/source-only.
- Flat initial snapshot: `runtime/exports/normalized-initial-20261014.jsonl`
  plus `.receipt.json`, both create-exclusive/read-only. It contains50 rows;
  it is a dated snapshot, not an automatically refreshed live file.

Local read-only50-row mirror:
`.private/liquidation_v2_1_20261014/readonly_exports/normalized-initial-20261014.jsonl`
plus receipt. Hash and raw prefix pins are in the machine handoff. New immutable
snapshots can be exported with `scripts/export_bybit_liquidation_v2_1.py
--root <runtime> --output <runtime>/exports/<new-name>.jsonl`; never overwrite an
old snapshot, mutate collector files or combine epochs. The exporter preserves
all duplicate candidates/UNKNOWN flags and makes no research eligibility decision.
OpportunityRecord adaptation, clustering/dedup and source compatibility remain
Claude's lane; no Codex message or Claude checkout/process write was performed.

## Original epoch and stop incident

Original12-symbol manifest/app/raw history retained. It collected157 raw items;
all246 records, raw SHA/side/time and full330280-byte chain validate. It is not
eligible for this ≥15-symbol experiment and cannot be merged/backfilled into V2.1.
Its unit is disabled, PID0. The controlled stop exceeded systemd's20-second
timeout and was SIGKILLed AFTER its STOPPED heartbeat. This is an explicit
retired-source shutdown incident, not a graceful-stop PASS. The initial install
receipt failed its too-narrow inactive-only assertion; diagnostic/failed receipt
is preserved. No reset-failed, repeated install/start/stop or old data repair.
Completion independently required disabled/PID0 and actual old-chain integrity.

67local/53VPS targetedPASS. Full suite not rerun; historical NOT_GREEN remains.
Root review only; independent-review quota restriction not retried/replaced.
All37 Alpaca files/HALT/cron, production Bybit/web/ATT1/V1 PIDs preserved; V1
directional evidence and existing service unchanged. No broker private calls,
orders/risk/money authority, strategy, judge, PnL or LIQ_OTSKOK_4H_V2 launch.

Collector engineering stops here; source accumulates under the frozen epoch.
Alpaca16:00Cyprus and KITY's first prospective window retain priority.
