# KITY_BYBIT — independent C2 preparation, October14

**C2_CALCULATOR_READY_WAIT_FUTURE_SOURCES**, not actual C2/C1 or money PASS.
Read [the preparation receipt](evidence/kity_bybit_c2_20261014/preparation_receipt.json).
Frozen research remote `cb47f0eb57e7a64ea5fcb948d7ae12d617c2abe1` was verified;
five committed specification/shadow/interface files byte-match Claude's current
files. Nothing was edited or executed in his checkout. No new judge/outcome read.

The independent stdlib calculator imports no shadow/comparator, credentials or
trading transport. It reads raw artifacts and writes only new files under this
checkout's `.private/kity_bybit_c2`. 23 new counterexamples plus existing M3/CLI/
251-vector coverage total392 targetedPASS. Full suite not rerun; historical
NOT_GREEN remains. Root review only. Frozen math/universe/hold/costs unchanged.

At the morning observation there is one actual KITY Python cycle, PID14408;
SCREEN/login/sh/caffeinate are its launch wrappers, not four extra Python
collectors. Log heartbeat05:28:41UTC was read. No process was started/restarted.
First snapshot is not yet present: its frozen window is October14 23:50–23:59
UTC, **October15 02:50–02:59 Cyprus**. Do not fabricate that prospective input.
This Bybit-native window differs from Binance M3's exact23:55 contract.

## Raw input bundle

Schema `KITY_BYBIT_C2_INPUT_V1`, `day` and exact `research_ref` above, with:

- `snapshot`: absolute physical `path` and raw byte `sha256` of the external
  `snimok_2355.json`; keep the actual `vremya`, `oi_usd` and instrument mapping.
- `candles`: symbol→physical file pin for every independently selected top50.
  Each file is a public GET capture with `venue=BYBIT`,
  `endpoint=/v5/market/kline`, `params={category:linear,symbol,interval:D,
  end:<UTC day start−1>,limit:75}`, `request_ms`, `receive_ms`, exact `raw` JSON
  response and its raw `sha256`. Capture after d−1 is closed. Never substitute
  today's unfinished bar or read post-signal return outcomes.
- `archives`: symbol→physical file pin for raw daily trade `.csv.gz` bodies.
  Use `https://public.bybit.com/trading/<SYM>/<SYM><d−1>.csv.gz`; exact symbols,
  original compressed bytes and matching shadow `potok.json` SHA. Bodies and
  candle captures belong in our separate directory, not Claude's writer state.

The shadow retains trade aggregates/SHA but does not persist gzip bodies or raw
candle replies. Reacquire the same immutable archives and retain independent
candle captures before C2. There are no actual October15 sources yet; this is a
required intake action, not claimed completed collection. No collection daemon
or second shadow was deployed. Do not run Claude's comparator: it writes into
his ledger. Our own comparison requires full archive-hash coverage and raw replay;
a nonempty unrelated/partial hash dictionary cannot become C2 PASS.

## Execute after sources actually exist

From the recovery checkout, seal reconstruction **before** loading the external
signal for comparison:

```text
.venv/bin/python scripts/kity_bybit_c2.py reconstruct --bundle <absolute-own-bundle.json> --output <absolute-own-private-root>/codex-2026-10-15.json
.venv/bin/python scripts/kity_bybit_c2.py compare --codex <absolute-own-private-root>/codex-2026-10-15.json --shadow-signal <absolute-external-signal.json> --shadow-flow <absolute-external-potok.json> --output <absolute-own-private-root>/comparison-2026-10-15.json
```

No network/order operation exists in these commands. Files are create-exclusive,
fsynced, and cannot overwrite a previous attempt or Claude's directory. Source
pin drift, incomplete mature-name raw data, malformed/future sources and fewer
than30 eligible names return BLOCKED_DATA. No padding/substitution. CSV is
streamed, with1GiB compressed/8GiB uncompressed per-file resource bounds; exceeding
them is an explicit source-resource blocker, not a reason to drop a name.

Exact frozen calculation: top50 by descending OI with snapshot-stable ties;
closed d−1 candle eligibility; Buy/(Buy+Sell) using foreignNotional or size×price;
ranking by(feature,symbol); `k=n//10`. Compare exact feature symbol sets,
long/short sets, every eligible archive SHA and absolute feature difference
strictly `<1e-6`. NaN, tampered/rehashed receipts and incomplete hash coverage fail.

Repeat the independently sourced procedure for October22. C1 two operational
weeks, C3 guard, actual venue/account/caps/cost/finality and separate owner GO
remain distinct. A C2 mathematical match is not READY_FOR_CANARY or permission.
