# OS2_SHADOW_BRIDGE_V1 local orders-OFF runbook

This is a one-shot evidence assessor, not an installed service or entry owner.
It imports the existing frozen regime label computation, strategy regime gate,
priority router, exposure gate, decision bus, side-specific sleeve registry,
edge monitor and research orchestrator. There are no broker keys, transports,
order/model senders, env overlays or live configuration writes.

## Start and authority

Read `OS2_SHADOW_BRIDGE_DELIVERY_2026_10_07.md`/JSON and the approved spec/plan.
The implemented fixture policy has three slots, two same-side slots, one slot
per beta cluster, correlation threshold0.6, cluster risk1.5%, no scaling and
600000ms symbol cooldown. These are **synthetic fixture units**, not LIVE caps.
Ranking uses constant1 with a declared fixture rank; it is not measured expectancy.

`FIXTURE` proves wiring only. `EXTERNAL_PUBLIC` always returns
`BLOCKED_DATA / POLICY_UNAPPROVED`, allocates no shadow slot and contributes no
fixture terminal outcomes. No current baseline entry is created or vetoed.
Health/lifecycle output is tagged advisory, non-actionable and zero money authority;
registry stages remain shadow with risk_mult0. No lifecycle recommendation is applied.

## Input contract

Place a bounded JSON input in `runtime/os2_shadow_bridge_v1/inbox/`, or synthetic
fixtures in `.private/os2_shadow_bridge_v1/`. Never copy credentials into either.
Input must be a regular single-link owner file; symlinks and writable foreign
sources are rejected. Alternate input/runtime roots are refused before file read.

Top-level schema `OS2_SHADOW_BUNDLE_V1` has request_id, mode, decision_ms,
clock_uncertainty_ms, source, positions, correlations, policy and events.
IDs use bounded `[A-Za-z0-9_.:/-]`; hashes are lowercase SHA256. All numeric inputs
must be finite and booleans cannot supply numeric timestamps/risk.

- `source`: id, symbol=BTCUSDT, timeframe=1h, observed_ms, rows, sha256. Each H1 row is
  `[open_ms, open, high, low, close, volume, first_available_ms]`.
  SHA binds the canonical JSON rows. Require240..800 rows, a multiple of4,
  consecutive UTC hours, coherent positive OHLC and nonnegative volume;
  finite4h aggregation is mandatory.
  Every group contains four closed H1 members. Latest cutoff is
  `floor((decision_ms−uncertainty)/14400000)*14400000`; never aggregate partial4h.
  All availability times precede observation and the conservative decision cutoff.
  Observation age≤300000ms; clock uncertainty0..250ms. This is regime-source
  freshness; existing execution-book2s gates are not replaced or relaxed.
- `positions` and `correlations`: id, observed_ms, coverage_ms, complete=true,
  rows, sha256. Coverage is explicit and bounded by observation/cutoff freshness;
  missing data does not imply no exposure. Position rows require symbol, side,
  risk_pct and beta_cluster. Correlation rows `[symbolA,symbolB,value]` must cover
  each admitted candidate/held pair. Missing pair returns UNKNOWN_CORRELATION.
- `policy`: schema `FIXTURE_POLICY_V1`, allowed_regimes mapping strategy IDs to
  NEUTRAL/BULL_TREND/BEAR_TREND lists. Policy/domain and local dependency hashes
  are pinned on first valid intake; no later body can swap the policy/source domain.
- `SIGNAL`: type,id,source_id,source_pin,strategy,version,dependencies (code hashes),
  symbol,side,beta_cluster,risk_pct,rank,signal_ms,available_ms,
  regime_source_pin,regime_closed_cutoff_ms,regime_observed_ms. Optional
  money_authorized must be false; unknown fields reject. The regime reference
  must match the actual canonical source, and source observation must precede
  signal generation. Strategy version/dependency/source identity is frozen across
  intents. The signal is adapted, never reconstructed or retuned by this observer.
- `NO_SIGNAL`: type,id; optional bounded source/strategy/symbol metadata.
  Missing identity/provenance is visible in the rejection record, not invented.
- `TERMINAL`: type,id,origin_id,source_id,source_pin,owner=OS2_SHADOW_BRIDGE_V1,
  terminal_ms,available_ms,filled=true,continuity=CLEAN,costs_complete=true,
  finality=true,finite net_r. Optional strategy/version/symbol/side must match
  the owned reservation. The terminal must follow the stored admission decision.
  Trusted side/strategy come from that reservation. Gap/unknown/wrong-owner/
  pre-admission/duplicate evidence cannot free a slot or count as a clean result.

All observed valid IDs retain exact body hashes, including refused opportunities.
Changed bodies require new identities and cannot silently amend old receipts.
Revision memory retains known H1 hashes throughout the admissible800-hour horizon
even if a later source window shrinks. Same supplied content is not broker/source
authenticity; actual transport/account acceptance remains separate.

## Execute once

Use the project Python:

```bash
.venv/bin/python scripts/run_os2_shadow_bridge.py \
  --input runtime/os2_shadow_bridge_v1/inbox/bundle.json
```

The default journal root is `runtime/os2_shadow_bridge_v1/store`. Fixtures may
select a separate store strictly inside the dedicated fixture namespace.
Source and runtime must not overlap. No scheduler/retry/deployment is installed.

Exit0 = SHADOW_WIRING_PASS (fixture engineering only); exit2 = BLOCKED_DATA;
exit3 = BLOCKED_IMPLEMENTATION/resource/writer suspension. Output is canonical
JSON. The same request_id and exact input hash returns the same saved receipt;
changed input under that ID returns request_identity_conflict.

## Durability, bounds and stop

One flock writer; regular owner-only single-link lock/journal files, no symlink
runtime ancestry. Each append contains the complete assessment and state_after,
sequence, input hash and predecessor hash. Success follows fsync. Restart scans
at most8MiB and syncs the verified prefix before returning a saved result.
The running instance checks file identity, size and modification metadata, rather
than repeatedly rereading the entire prefix. Hashes detect corruption; they do
not authenticate against malicious rewriting by the same OS account.

Bounds: input/append2MiB,64 events/bundle,4096 event identities/receipts, journal8MiB,
two store files, free disk≥512MiB plus next append, one-shot deadline30s.
Any bound suspends only this observer. An uncertain append poisons the current
instance. Close it and inspect the preserved prefix; reopening accepts only a
fully verified chain. Partial/corrupt tails remain BLOCKED_DATA; no truncation,
repair, deletion, reset or dropping durable reservations is automatic.

Rollback is to stop invoking this one-shot observer and retain its store/input
hashes. Production held positions continue under their existing manager/exits.
Do not start an old AI worker or env overlay as a substitute.

## Next gates

Alpaca Dynamic's original October7 13:30–13:35UTC source window and KITY's raw
October7 23:55UTC/October8–9 unseen intake preempt further OS2 work. Preserve
ATT1 completed research,2–3 clean terminals+dossier+GO and ETS2M's original source
and deadline. OS2 actual data adapter/deployment is a separate bounded task.
Claude must resolve the four source-backed B3 findings in
`OS2_FOUNDATION_AUDIT_2026_10_07.md` before transparent amended hash-lock/judge;
no historical or sealed outcomes were consumed here. A repaired B3 verdict still
does not grant money authority. Actual deterministic policy integration requires
the later separate `ORCHESTRATOR_POLICY_V1 GO`. Ollama remains a separate advisory
worker scope; this assessor makes no model calls.
