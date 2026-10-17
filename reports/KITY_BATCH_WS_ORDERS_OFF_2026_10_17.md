# KITY batch/private WebSocket — October 17

**KITY_BATCH_WS_ORDERS_OFF_CANDIDATE. Not a money-ready active runtime.**

Owner scope: batch/private WS engineering only, unchanged ten-leg basket,
gross215, collar50bps, immediate15USDT exit trigger with accepted overshoot,
30-minute lifecycle, no averaging/re-entry, separate execution-only ledger.
No new policy/GO issued; expired9051 and all prior GO remain unusable.
The one-policy70s permission is not extended by this delivery.

## Implemented

- Separate `BatchJournal`: ten entry intents are ONE durable transaction before
  the single possible HTTP call. Old sequential journal/reducer unchanged.
- Exact ten guarded IOC requests to `/v5/order/create-batch`. Each request embeds
  native Full/Market/LastPrice protection. No sequential entry fallback.
- Correlate result.list and retExtInfo.list by exact own link/symbol; ACK is not
  a fill or stop confirmation. Per-item rejection blocks entry and invokes
  existing owned unwind. Unknown send never repeats the batch.
- Separate final-fence no-wire proof permits actual flat/no-execution finality;
  a transport timeout stays uncertain and requires reconciliation of all links.
- Reuse original account lease/platform checks, real signed GET, source replay,
  post-GO compiler and explicit new batch approval namespace. Legacy GO cannot
  activate the batch owner. Default dispatch performs no mutation or HTTP.
- Fresh view uses65 distinct GET routes once: common account sources, exact
  instrument/mode/eligibility/fees/tickers and ten books fetched last. Ten entry
  validators and final send reuse that bounded view without another pricing
  anchor. CTS2s and physical dispatch deadline remain mandatory.
- Complete account-wide flat/no-orders and aggregate actual depth notional are
  checked, including favorable Sell prices increasing gross. No215 overshoot
  hidden by ten separate per-leg calculations.
- Private DATA socket only (`/v5/private`), auth/subscribe/ping allowlist.
  order.linear/execution.linear/position.linear; no trading socket/operation.
  Immutable raw inbox, writer-thread financial projection, execId deduplication,
  foreign identities retained but never adopted. seq is not globally unique.
- Disconnect/restart requires complete REST reconciliation; no-event stream
  never proves flat. Position stream is advisory, not final accounting.
- `BatchRuntime` composes WS projection with the existing native-stop,
  loss/deadline, scoped exit, recovery and accounting loop. Construction starts
  no process and grants no authority.

## Verification

**160 targeted PASS**, including33 new batch/WS cases and existing runtime,
native, account readback, physical owner, post-GO and integration tests.
RED missing-module run and later failures retained privately. Final command
and hashes are in `evidence/kity_batch_ws_20261017/verification.json`.
No broad legacy suite rerun or waiver of its historical60 failures.

Signed transport harness uses actual signing, lease, journal, exact claim and
all account/instrument/CTS validators:65 GET, ONE batch POST, ten owned ACKs.
Only the disk-source parser boundary and exchange wire are synthetic. ACKs are
not counted as ten fills. Partial rejection/restart/scoped safe-flat accounting
and local-no-wire versus uncertain-send cases are separately exercised.

Actual VPS private auth/subscription/pong probe: **1.835s** including post-probe
readback. Before/after complete GETs: positions0/openorders0. Owner PID2314960,
NRestarts0, heartbeat ORDERS_OFF/NO_ACTIVE_PLAN/error=null.153 protected pins,
unit and original lock inode unchanged;0 broker POSTs. The successful probe
references the earlier protocol candidate SHAe6120734…e6df; final account/runtime
delta is pinned separately. No actual private fill/stop event occurred or was
fabricated. Two probe-wrapper path errors are retained privately, not hidden
as successful observations; they did not change the account/writer.

Final source kit is separately installed **disabled**, all source hashes and
isolated import verified. Previous candidate directories remain immutable.
See `installation.json`; the source verifier has no network/GO/order option.

## Exact remaining boundary

The existing account service still runs its preserved sequential source kit.
The batch library/source kit has NOT been selected as its production entrypoint
or activated. Therefore **no KITY_10_OF_10_READY / EXECUTION_PASS claim**.

Before another financial attempt: finish reviewed single-owner service/control
binding to this kit orders-OFF (no second writer), then one newly dated bounded
policy and fresh compatible215/rounding/eligibility/account sources. Only then
the human may personally authorize the new policy. No expired proposal/launcher
or watcher READY is reusable. This is operational work, not a research gate.

Official contracts: [batch place](https://bybit-exchange.github.io/docs/v5/order/batch-place),
[private connection](https://bybit-exchange.github.io/docs/v5/ws/connect),
[execution stream](https://bybit-exchange.github.io/docs/v5/websocket/private/execution).
