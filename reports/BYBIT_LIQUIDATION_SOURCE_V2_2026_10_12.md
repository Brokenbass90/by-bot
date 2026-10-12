# Bybit liquidation semantics — separate V2 and evidence inventory

**SOURCE_V2_ENGINEERING_READY / PRODUCER_NOT_DEPLOYED.** This is a source
correction, not a strategy or outcome run. Official Bybit allLiquidation `S` is
the liquidated **position** side: Buy→long, Sell→short. `p` is bankruptcy price,
so qty×p is a notional proxy, not an execution price/cost source.
[Official protocol](https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation).

The preserved `scripts/collect_bybit_liquidations.py` interprets S inversely;
its `order_side` retains raw S under an incorrect label. Its source/tests,
deployed service and all archived events are unchanged. New pure opt-in
`bot/bybit_liquidation_source_v2.py` emits
`BYBIT_ALL_LIQUIDATION_SOURCE_V2`: explicit raw/normalized position side,
bankruptcy/notional basis, raw event T, optional receive timestamp and canonical
raw-item hash. It rejects missing/unknown side/T, invalid quantity/price,
topic/symbol mismatch and unrelated topics; receive/frame time never replaces T.
Canonical item hash is not a wire-byte hash. No credentials/client/orders/writer.

Source contract and pinned static inventory:
`evidence/bybit_liquidation_source_v2_20261012/SOURCE_CONTRACT.json` and
`CONSUMER_INVENTORY.json`. Inventory covers13 source/config/reference entries
in recoveryHEAD32d43de and research36ab6ff; actual dynamic/deployed consumers
were not inventoried. No performance artifact or new outcome was consumed.

| Directional consumer | Evidence consequence |
|---|---|
| `research_lab/liquidation_cascade.py` | Directional V1 evidence source-blocked |
| `backtest/liquidation_sweep_run.py` → `liquidation_sweep_research.py` | Real V1 event path affected; synthetic OHLC source separate |
| Claude `research_lab/discovery_paket3.py`, L1 FORCED_FLOW_LIQ | L1 affected; quarterly T1/T2/T3 are separate |
| Claude `research_lab/fabrika/kaskad_maker.py` | Directional event/ITOG/trade evidence source-blocked |

Mark derived directional evidence **SEMANTICALLY_TAINTED where its source pin
proves inverted V1 normalization**. Unproven source identity remains UNKNOWN /
BLOCKED_SOURCE_SEMANTICS, never READY_FOR_BUILD or money evidence. No old PASS/
KILL is silently reversed and no judge is rerun. Later correction requires a
distinct version/source manifest and preregistration; preserved raw S may be used
only after proving the original source/time identity.

`run_cascade_real_gate.py` and `liq_fuse.py` sum total USD without event side;
S inversion alone does not invalidate their volume totals. Advisory auditor and
inventory references do not supply directional performance. Timestamp gaps,
bankruptcy-price meaning and coverage remain separate data questions.
The old overnight launcher picks newest `runtime/liquidations/*.jsonl`; future
V2 must use a **separate directory** and explicit pins, avoiding mixed semantics.

V2 + preserved V1 targeted tests: **14 PASS**, including Buy/Sell, exact event T,
missing-T despite receive/frame timestamp, symbol mismatch, invalid fields,
canonical identity and overflow. Combined with Brain targeted regressions:
55 PASS. No collector restart/redeploy, historical rewrite, new source epoch,
strategy retuning, research/Claude edit or money authority. Next implementation
step is explicit source-version producer/consumer rollout; it was not performed
inside today's read-only Alpaca window or claimed as running here.
