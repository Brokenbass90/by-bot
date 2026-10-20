# PUMP4 V1 bounded execution source review — 20 October 2026

**HISTORICAL88f42ac REVIEW. Superseded for implementation by published contractb138735/request7b0a961; see versioned-contract.json.** The source/spec questions are now closed for adapter development. The original diagnosis below is preserved, not a current contract rejection. Execution replay/restart/broker acceptance remains NOT_RUN.

**Verdict: execution contract BLOCKED; no money or research verdict change.**
Pinned published source: `88f42ac16f7baf002b064074f7686bd46996f6a5`.
Strategy bytes match `2ea8d1f`. This review used Git objects and synthetic
source/geometry checks, never market-data arrays, new outcomes, a judge,
returns simulation, broker calls, credentials or service changes.

## Material blockers

1. **Published evaluator dependency is incomplete.** `pump4_pereschet.py:21`
   imports `pervyy_argument` from `research_machine`, then calls it at line 93.
   The published `research_machine.py` contains no definition or import of that
   name. The reference thus cannot reproduce its evaluator dependency closure
   as published. `research_lab/ten_pump4.py` is also absent from this Git tree
   (and no path history was found in local refs). Publish the actually used
   dependency/producer hashes and effective config; do not locally invent a
   replacement or rerun the verdict.

2. **The declared 0.55 first exit fraction is not the clean-environment source
   contract.** `pump_fade_v4r.py:309–310` initializes targets `[0.9,1.8,3.0]`
   and fractions `[0.40,0.30,0.30]`. `pump4_pereschet.py:110` passes
   `(s.tp_fracs or [F1])[0]`: `F1=.55` is only a fallback. Thus the inspected
   default code passes **0.40**; `research_machine.py:94,107–112` takes only
   the first two target prices and exits **0.40 then 0.60**. The third target
   is ignored. Request/readiness claim 0.55. This is a V1 source/spec mismatch,
   not permission to change the fraction or relabel the existing result.
   An external `PF_PARTIAL_FRACS` could alter this, but no effective run-env
   receipt proves such an override. Need versioned producer/config clarification.

3. **The configured prefix is wrong; defaults are not hermetically pinned.**
   Strategy constructor reads `PF_*` (lines 289–433); pereschet/request set
   `PUMP4_*` (pereschet 79). Synthetic check: `PUMP4_SYMBOL_ALLOWLIST=ONLYUSDT`
   leaves strategy allowlist empty, and `PUMP4_ALLOW_SHORTS=0` has no effect.
   External symbol iteration currently scopes pereschet to journal symbols,
   so this finding alone does not prove out-of-universe research signals.
   A production adapter must bind its explicit universe and effective config;
   do not rely on those unused variables or ambient `PF_*`.

4. **A2/A3 are not accepted by this source review.** V4 signal computation
   (`_on_bar_v4`, lines 640–750) reads only accumulated past/current inputs;
   no forward indexing was found. Pereschet filters closed bars (88), feeds
   chronological bars (95–98), uses one instance per symbol (93), and never
   feeds `bars[i+1]` into signal generation. This supports conditional
   closed-prefix causality, not actual source availability/latency acceptance.
   Strategy has no bar-finality, timestamp monotonicity, duplicate, gap,
   per-symbol isolation or persistence guard. `on_bar` appends inputs and
   decrements cooldown on **every call**, even the same timestamp
   (1027–1053). Exact duplicate fixture consumed all 24 cooldown calls.
   State reset loses history and cooldown; sharing an instance across symbols
   would mix both. Persist per-symbol state plus last processed bar and atomic
   signal identity; apply every eligible closed bar once, including no-order
   bars. Cooldown starts on signal emission, not fill/exit, and suppresses the
   next 24 calls; the 25th may emit. Restoring only open orders is insufficient.

5. **Next-open is a reference model, not yet an executable timing contract.**
   Signal close is known at `signal_open+1h`; evaluator assumes exact following
   bar open (`research_machine.py:83–88`). Real dispatch follows observed
   finality and cannot guarantee that historical price. Pereschet labels
   FORWARD at `zapisano-ts <=3h` (105–106), while prereg addendum 1 says `<=2h`;
   neither is exact next-open availability, and the code has no lower bound.
   Define reference open, actual fill, close-event availability, accepted delay,
   gap handling and NO_SEND/reconciliation receipts before execution; never
   backdate a late fill. Validate target/stop side again at entry: strategy
   validates geometry at signal close, not the later open. Missing bars must
   not silently redefine 168 H1 bars as a different elapsed horizon.

## Exact lifecycle to preserve or reconcile

The inspected `research_machine.simulate:82–116` and `random_control.sim_geo:51–79`
agree on static-stop, two-target mechanics:

- Entry is `bars[i+1].open`; widened stop is
  `entry + (raw_sl-entry)*4`, **not** signal close plus four times close risk.
  Nonpositive signed risk rejects. Pereschet rejects `entry/risk>100`.
  This ratio is research normalization, not account-leverage authorization.
- Targets remain the strategy's absolute prices, calculated from **signal
  close/raw stop**. At equal close/open, `.9/1.8` raw-stop units become
  `.225/.45` widened-stop units; a next-open gap changes those ratios.
  Do not rescale to `.9/1.8` of widened risk.
- Stop test comes before targets on each OHLC bar; if stop and target both
  touch, stop wins. Otherwise TP1 and TP2 may both fill in one bar.
  There is **no breakeven or trailing movement after TP1**.
- Hold includes entry bar as bar 1, processes through `e+167`, and exits
  remaining quantity at that bar's close. Returned `bars=167` is a zero-based
  offset, not only 167 held bars. Intrabar exact terminal timestamps are not
  recoverable from H1 OHLC.
- Generic `TradeSignal` is not the final execution plan: it carries three
  targets/fractions, `time_stop_bars=48`, and warm-history
  `trailing_atr_mult=1.4`, whereas the evaluator uses two targets, 168 and no
  trailing/BE. Reusing a generic manager without an explicit frozen mapping
  would change V1. Class `interval_min=5` remains the frozen default although
  inputs are H1: short/long detection windows are 12/36 **H1 calls**. Setting
  interval to 60 to match feed nomenclature would change signals.
- Model fees are two fixed 6 bps charges scaled by entry/risk. Stop fills at
  the stop price even across gaps. No actual funding, slippage, partial-fill,
  margin or rejection model is present; these are execution acceptance work.

**Terminal classifier defect, bounded scope:** `zaversheno:68–72` treats a
stop/TP2 on the last available bar as still open when fewer than 168 bars
exist, because it tests strict `<` against the last offset. Synthetic
classifier-only check confirms this; no price path or returns were simulated.
It cannot distinguish such a real terminal from `simulate`'s artificial
last-close fallback without an explicit terminal reason. Do not change the
published verdict here; research must version that semantic repair.

**Warmup caveat:** pereschet begins calling the stateful strategy at index
200; assigning `Store.rows=b[:i+1]` does not preload the 200 bars because this
strategy's first argument is a symbol and its state only grows on calls.
It reaches the default V4 46-call minimum around input index 245. This is
causal but not equivalent to a fully prewarmed instance at index 200.
Bootstrap/cursor parity needs an exact source contract, not a guessed fix.

## Seven repeats and universe

Cooldown-reset mechanism is source-confirmed and synthetic reset-sensitive.
The claim that **these exact seven** historical cases are caused solely by
reset remains **NOT_INDEPENDENTLY_REPRODUCED**: missing published producer and
immutable original inputs/run config prevent exact continuous/restart parity.
No seven-case outcomes were read or selected. Their outcomes remain UNKNOWN.

The 137/138 mismatch is deterministically explained:
`0ee472f` (17 October) adds only `data/h1/BTCUSDT_B21.npz`; its parent has 137
NPZ paths, current/frozen-ref tree 138, with no removed paths.
`data/factory_v3/OKNA_MANIFEST.json` assigns the extra file to historical BTC
`KRIPTO_D1_2021H2_2022`, role DEV, hash
`524bc5e3af11c91bce86c6102954409c422c1f52ecbce78cba3abeb99448c77f`.
It is an archive dataset, not a 138th current Bybit symbol. `evidence.json`
saves the exact original 137 filename list. This closes the root-cause
question without outcomes; publish/acknowledge an explicit versioned symbol
manifest before production instead of a mutable glob or silent subset.

## Reuse and next gate

Reuse the existing Bybit transport/ownership/recovery/native-stop primitives
in `research_lab/kity_micro_transport_v1.py`,
`kity_micro_physical_owner_v1.py`, `kity_micro_account_bridge_v1.py` and
`kity_execution_micro_runtime_v1.py` only through a separately scoped PUMP4
plan. Their tests already cover durable native protection and lost-reply
reconciliation. Do not inherit KITY's caps, authority, basket/time semantics
or deploy/select a new manager.

For decision-to-plan checks, reuse exact first-record/hash/clock/instrument
validation patterns from `elder_hedge_orders_off_v1.py`; its `.55` hedge policy,
offset-limit fill and proportional reanchoring are **not PUMP4 rules**.
The existing `simulate`/`sim_geo` source is the comparator for frozen lifecycle,
not a reason to run another returns experiment.

Next gate is a small versioned **source closure + effective geometry/config +
explicit137 manifest + producer/state/bootstrap/timing clarification**. Then
bounded non-PnL fixtures can close A1–A3 before instrument/risk/account tests.
No new framework, V2 filters, InPlay, funding veto, altered targets, trailing,
BE, cooldown or fresh sealed research belongs in this V1 repair.

Verification: `python3 .private/pump4_execution_review_20261020/source_checks.py`.
18 deterministic source/synthetic assertions; evidence hashes included.
These assertions confirm findings, not strategy/execution PASS.
No tracked edits; only this ignored private evidence directory was written.
