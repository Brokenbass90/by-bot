# PUMP4 — explicit entry, OFF executor and actual H1, 27 October 2026

Continue this receipt; no strategy audit, producer change, evaluator/PnL rerun or funding download. Monthly v6 and its calendar remain unchanged. Economics stays **INCONCLUSIVE**. Technical micro and an income-producing strategy deployment are separate owner decisions.

## What is closed

The native-stop adapter committed in `3a62f86` is retained. The 84 frozen reference geometries pass memory protocol through entry/native protection/TP40–60/restart/readback/send-once/reconciliation. All84 are not financial admissions: unchanged source sizing admits2 fixture cases, blocks51 for capacity and31 for cost-inclusive capacity. Terminal fake-account result remains `FLAT_COSTS_PENDING`, not real cash finality.

The previously incompatible entry contracts are now explicit. Legacy flows keep their exact-open/5s rule and old config/CIDs. New flows may use `PUMP4_EXPLICIT_ENTRY_EXECUTION_POLICY_V1`: deadline measured from original H1 open, maximum60000ms, separately named reference-price drift, unchanged original risk policy, full source manifest, native mapper and quote/interval conventions. The installed OFF proposal uses10bps reference drift; this is **not an approved monetary value**, nor the same quantity as the existing10bps execution-impact assumption.

Checked current quote and forming H1 interval must be fresh, identify the exact symbol/hour/reference open and show no earlier native-stop or TP1 touch. Bid for SHORT/ask for LONG determines executable reference drift; LastPrice determines trigger geometry. Evidence is embedded with bounded compression and verified on resume. Final wire rechecks deadline, evidence, exact authority and source age; a reserved or ambiguous send cannot be retried. Entry expiry does not disable owned custody/exits. Different scope/source/policy requires a new exact human GO; no actual GO is created here.

Independent critical review found one custody issue: Bybit `execTime` was compared with local reservation time. Fixed with a verified pre-dispatch **exchange-clock** lower bound, persisted in the immutable observation and linked to each CID through its observation hash. Tests accept a legitimate post-dispatch fill below local reservation time and reject a genuinely historical fill. Focused follow-up review:0 remaining Critical/Important findings,22 entry tests PASS. Handoff review:0 Critical/Important,20 tests PASS.

Frozen candidate `ffb31e24c703d9ed`, material `ffb31e24c703d9ed71cfa3acd4e64c9d6fd1b6e9d0251843fc16c4a156971f1a`, manifest `5f96887bcade49634a9b5c6ab27d86cd71d2a32b115bc6a3435f8e1f477dde5c`: **326/326 local and same326/326 VPS tests PASS**,0 failures/errors/skips,115 source files,54 imported files,19 test modules,0 checkout fallback. Socket blocking and VPS network namespace prohibit network in acceptance. All wire activity is fictional.

## Actual installed path before this handoff: 26Oct20H1

Full137 census was preserved; no hour retry/reseed. This measured selected70d4 before the new single-replay change.

| Group | Results | Publications <=60s | Median / maximum delay |
|---|---:|---:|---:|
| CURRENT_CLOSED_BAR |114|46|64.8355 /77.995s|
| CATCHUP_REPLAY |4|0|80.690 /81.565s|
| BLOCKED_SOURCE |18|not admissions|Bybit10006 in all18|
| UNAVAILABLE_INSTRUMENT |1|not admission|HFTUSDT|

All114 current sources arrived by60s:10.123–53.999s, median36.2925s. All118 intake passes combined:46 by60s, median65.4875s, maximum81.565s. CURRENT-before-CATCHUP ordering **PASS**; timeliness **FAIL**. Classifier2.658s, parent symbol processing66.460s, childCPU26.492s. These are actual per-hour process measurements. Later unmodified70d4 hours at27Oct03/04/05UTC also fail:21/128,24/120,18/129 by60s, respectively. Do not infer a stable improvement from one earlier hour.

The18 failures are explicit API responses `retCode10006`:11 on the first candle page,7 on the second. They are not missing strategy signals or evidence to bypass. Failed raw captures are preserved. Their cursors may catch up prospectively, never become backdated entries. Rate-limit diagnosis/collector correction remains an actual separate residual issue.

Narrow prefix fix removes the duplicate **pre-append** producer replay only for one contiguous current bar with no recovery batch. The entire producer prefix is still replayed and validated under the existing append lock before journal write. Catch-up, bootstrap, recovery and duplicate paths retain their existing full checks. Frozen intake and strategy bytes do not change. Byte-identical result/journal/observations comparisons, foreign-domain rejection and crash recovery tests pass. A new actual H1, rather than tests or a local benchmark, must establish the resulting timeliness.

## Observed quotes and economics

The one-hour observer completed10 public ticker GETs, linking137 symbol publications to later quotes. Additional quote lag from publication:0.134–8.626s, median4.399s. **Zero actual strategy signals occurred.** These are explicitly delayed reference observations, not fills or signal-conditioned execution prices. They do not validate the earlier <=.005R claim, estimate an84-trade realized delay cost or prove actual execution slippage. Do not subtract them as a measured trading expense.

Research publication29366fb/76c9041/99da9ef was already verified. Same-input parity84closed+open1 remains PASS. The51 old missing cases were already classified as skip-before-producer/cooldown state divergence; do not reopen or retune the strategy.

Unified84-case arithmetic using the dated26Oct account fee observations and Claude funding scenario gives mean net .0603007R at2bps/side, .0565555R at5bps/side, .0503134R at10bps/side. At5bps:September−.0729140R,October+.3154944R. Old .0479598R at10bps before funding plus the same funding scenario .0023536R equals .0503134R. See `evidence/pump4_funding_bridge_20261026/bridge.json`. These are consistent assumptions, not new PnL/evaluator runs.

Funding uses historical rates with entry-notional assumptions; actual settlement mark prices, boundary ordering and complete cash ledger remain unproved. Partial residual in code is correctly.60; .45 was prose only. Current-cap funding stress still constrains sizing. Positive aggregate mean does not establish durable future income. None of this alone vetoes a separately approved minimal technical micro once technical/account gates pass.

## Owner decision

**BLOCKED for first LIVE / not READY_FOR_OWNER_REVIEW as an executable TINY packet.** Reasons: no passing actual new H1 publication measurement; API10006 source losses; no qualifying current signal with fresh actual-account sizing/lot/cost/protection admission. A live exact scope and personal financial GO are absent. No increase of risk/capital,60→300s, strategy change or KITY switch is authorized or performed.

Next P0 remains the measured DATA path: obtain the next untouched hourly receipt on the installed candidate, classify timing and10006 losses, and correct that producer-independent bottleneck without relaxing60s. The income roadmap remains Monthly→PUMP→Polymarket→KITY, then portfolio/diagnostic/Brain/Factory expansion from actual costed evidence. No automatic promotion or AI monetary authority.

Evidence: `evidence/pump4_entry_and_h1_20261027/`. Deployment and independent post-selection receipt below supersede the pre-handoff state when present.


## Actual deployment27Oct05:30UTC

Both DATA and the sole financial owner now select **ffb31e24c703d9ed**, strictly OFF. DATA binding `b90a8a8123c2bc2e6ee8b103085197b7f2c9e1e12869713c7ce976aa7e0e23e2`;32,843 historical files preserved, all old roots retained. Two fresh GET-only account bundles proved flat/no orders before and after stopping the old owner. No position was handed off.

Financial config `19f9cd74f6ce87f9bc99c2e012333c6910864399e48d9e81062e337885457d4c`, OFF scope `9acdeac664b4ce1b317ab10360a36488c80bc9c5d86226cf432d53416afdd172`, PID3023060, original818853 held,0 restarts. Independent literal pathlib/proc/systemctl readback verifies exact code/guard/data/policy pins,272 intake/epoch prefix files, empty financial history, no GO and8 clean actual `NO_NEW_SIGNAL` cycles at05:31:59UTC. Monthly unit SHA remains `9d94467d301cf5f545bee18e50b838623c061b72f46a2fbdd9b7d1991932cc1d`. The prior legacy306/70d4 financial state is history, not the current selected owner.

On VPS, three before/three after measurements of ONE preserved current-bar case give median0.302→0.229s (CPU0.286→0.216s), identical result/journal hashes. This is a bounded benchmark, not a137-symbol latency forecast. Source/strategy/intake/clock semantics stay frozen.

**Actual new H1 remains PENDING.** The unchanged hourly timer's next untouched window is27Oct06:00:02UTC (08:00:02 Asia/Nicosia), source-hour `1793080800000`. Read that candidate's immutable capture-process/stream/cycle receipts after completion; do not rerun the hour or start another collector. Only that real path can close the latency gate. No owner action is needed while this technical gate is unresolved; no executable LIVE command is supplied.


One read-only06H1 observer is running (SSH session42219), with keepalive, against
this exact selected DATA root. Local output `.private/pump4_entry_20261027/actual06-progress.jsonl`,
stderr `actual06-observer-stderr.txt`; script `observe06_readonly.py`. It reads immutable
receipts only and makes bounded public ticker GETs **only if an actual signal is
published**. Ends after all137 outcomes/process proof or06:06UTC. No new collector,
systemd unit, cron, owner lease or financial authority. Do not duplicate it. A
future observer file is not a present H1 PASS; source files remain authoritative.
