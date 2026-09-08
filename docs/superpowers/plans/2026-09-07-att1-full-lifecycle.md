# ATT1 full zero-risk lifecycle implementation plan

> Workers use superpowers:subagent-driven-development. Owner explicitly authorizes
> this complete ATT1-only implementation and zero-risk deployment. No further
> routine plan approval is needed. Money authority remains separately gated.

**Goal:** signal -> causal admission -> simulated execution/partials/nonfill ->
protection/exits -> restart/recovery -> complete scenario costs/funding -> net-R,
then a distinct public-only VPS lifecycle service without changing L1.
**Architecture:** Keep frozen ATT1 strategy and L1 source files unchanged. New
source-bound profile/admission, pure lifecycle coordinator over reviewed L2/L3,
and independent durable journal. Public market observations and simulated fills
are explicitly distinct. The coordinator never imports a broker or places orders.
**Spec:** docs/superpowers/specs/2026-09-06-att1-ets2s-l2-l3-contract.md.
**Stack:** Python stdlib/existing canonical Store; no new trading framework.

## Global constraints and resolved decisions

- Scope is ATT1 only. No Alpaca, LAB_AI, ETS2S semantics or new strategy research.
- Existing L1 sources/config/journal/services remain unchanged. Work in the
  existing owner-designated canonical recovery checkout; no competing source of
  truth. Canonical branch is clean at base86642fd. Independent workers have
  disjoint files. Root reviews/integrates; workers do not commit or spawn.
- All money/orders/private/promotion authority false. Synthetic core profile ID
  remains SYNTHETIC_ATT1_LIFECYCLE_V1; public shadow is simulated execution, never
  real fills/account fee tier or automatic profit/promotion proof.
- Source-bind ATT1 market/offset0/wait0, H1 short, original wide stop, TP1/TP2
  1.20R/2.50R and .55/.45, 336h from first fill. BE trigger0 and ATR trailing0
  are explicitly disabled; retain source-resolved BE lock .02, ATR period14 and
  trailing activation1 as inert fields. Do not activate disabled strategy rules.
- Frozen ATT1 source cooldown is 96*M5 from signal decision bar start (the code
  passes bar-start into maybe_signal), not an invented 8h since exit. Admission
  also requires a later bar after terminal exit; active book ownership blocks.
- New virtual execution policy: risk1USDT per independent research book/symbol,
  max notional100USDT, maximum signal age300000ms, max submit delay1000ms,
  instrument freshness3600000ms, market observation max age2000ms, entry IOC
  lifetime2000ms, adverse entry risk expansion0.10. These are versioned simulation
  assumptions, not recovered broker rules or money settings.
- Exact decimal strings -> Fraction/integer steps. Floor quantity; reject below
  min quantity/notional, never round up. Round short stop upward to tick; target
  prices downward per live-native _rebased_targets after finalized entry VWAP.
- Preserve actual partial exposure/protection independently of entry finality;
  targets are armed only after entry finality. Time-stop never resets. No net-R
  until entry finality, flat exposure, exit finality and all explicit costs.
- Stable execution identity excludes transport receive timestamp. Conflicting
  economics fail; late exact delivery never rewinds event clocks or repeats cash.
- Append evidence before publishing derived state. Restart replays the full
  verified journal; stale derived snapshots are disposable, torn/conflicting
  journals fail closed. Unknown market gaps mark cohort incidents, do not fake
  continuous monitoring or fill observations.

## Task 1: source-bound profile and admission

Files: create research_lab/att1_lifecycle_profile.py and
 tests/test_att1_lifecycle_profile.py only.

Interfaces:
- build_profile(root: Path) -> dict: captures source SHA256 map, exact resolved
  ATT1 config under frozen_profile_env(ATT1_PROFILE,FIXED51_UNIVERSE), compares
  resolved hash to PROFILE_FIXED51_CONFIG_HASHES['ATT1'], and computes a canonical
  profile_sha256. It must verify pinned ATT1 source aggregate before claiming
  source binding. It reads source/config only, no history/runtime/outcomes.
- validate_profile(profile: Mapping) -> None: strict schema/keys/types/exact
  frozen strategy and policy fields; recompute profile SHA. No opt-in authority.
- admit_signal(profile, signal, instrument, book_state, *, book, submit_ms)->dict.
  Always returns accepted(bool), code(str), plan(dict or None); malformed inputs
  raise ProfileViolation. Missing evidence rejects/fails, never default-enable.
- signal strict fields: schema_id='att1_lifecycle_signal_v1', symbol, side,
  stream, bar_close_ms, source_available_ms, signal_ready_ms, entry, sl, tps,
  tp_fracs, be_trigger_rr, be_lock_rr, trailing_atr_mult, trailing_atr_period,
  trail_activate_rr, time_stop_bars_5m, source_sha256, data_sha256, profile_sha256.
  Numeric market values are decimal strings. source_sha256 is the immutable
  full signal receipt hash provenance (not the strategy aggregate); profile
  binds the strategy. bar_close is positive aligned H1. Full fields must agree
  with profile; require valid short geometry and exact target RR within 1e-10
  relative tolerance for legacy float-to-text signal serialization only.
- instrument strict fields: symbol,tick_size,qty_step,min_order_qty,min_notional,
  max_market_qty,observed_ms,source_sha256. Exact positive decimal strings;
  observed_ms<=submit and age<=profile limit. Metadata is a current observation,
  not proof of historical filters. No symbol outside FIXED51_UNIVERSE.
- book_state strict fields: active_decision_id(str or None), last_admitted_bar_ms
  (int or None), last_terminal_ms(int or None). active includes pending/partial/
  reconciling. Reject repeated/earlier bar and signal-bar-start cooldown<8h;
  require bar_close_ms>last_terminal_ms. Null state means a genuinely new book,
  not fallback after recovery failure.
- Require EXECUTION_FORWARD; bar_close<=source_available<=ready<=submit;
  submit-bar_close<=300000 and submit-ready<=1000. All timestamp fields int,
  not bool; all SHA lowercase64. No bootstrap/backfill admission.
- accepted plan keys: profile_id,profile_sha256,book,symbol,decision_id,order_id,
  bar_close_ms,signal_ready_ms,submit_ms,nominal_entry,original_stop,requested_qty,
  qty_step,price_tick,planned_risk_amount,signal_source_sha256,data_sha256,
  instrument_source_sha256. decision hash binds book/symbol/bar/profile/full
  signal hash/data/instrument; research order ID derived from decision ID.
- Quantity=floor(min(1/(rounded_stop-entry),100/entry,max_market_qty)/step)*step.
  Reject wrong stop side, nonpositive rounded targets, quantity/notional minima.

[x] RED fixtures: frozen profile values/hash, source drift rejects, env override
 isolation, bootstrap/stale/future/missing fields, bool/NaN, active/duplicate/
 cooldown, wrong symbol/hash, tick/step and dust/min-notional refusal. Literal
 fixture entry100/stop110/step.01 => qty.1, stop110, planned risk1.
[x] Implement; run .venv/bin/python -m pytest -q tests/test_att1_lifecycle_profile.py.
[x] Report exact API/output example and test result to root; no commit.

## Task 2: independent durable event journal

Files: create research_lab/att1_lifecycle_journal.py and
 tests/test_att1_lifecycle_journal.py only. No imports from Task1 or engine.

Interfaces: JournalViolation; LifecycleJournal(path, *, max_bytes=67108864,
 max_record_bytes=1048576); methods read()->tuple[dict,...],
 append(event:Mapping)->bool, tip()->dict with rows and tip_hash.
Caller owns runtime directory creation. Strict JSON event requires nonempty
'event_id' <=256 chars and schema_id='att1_lifecycle_event_v1'; all other fields
are validated by engine. Wrapper row has seq,prev_hash,event,event_sha256,hash.
Canonical JSON ASCII/sort/separators/no NaN, reject duplicate keys on reading.
Exact event_id+canonical payload append returns False; conflicting ID rejects.
Strict finite JSON only; no Python object/string coercion.

[x] RED: reopen equivalence, exact duplicate no-op, changed same ID failure,
 corrupted seq/hash/payload, truncation, duplicate JSON keys, NaN, oversize,
 symlink file/parent and hardlink, competing writer and readonly/path refusal.
[x] Implement safe openat O_NOFOLLOW parent traversal, 0600 regular single-link
 journal, flock across read/validate/append/fsync, parent fsync on creation.
 Never create or repair a file on read(); absent file is empty. Reject truncate,
 inode/hardlink or format incidents; no auto-repair/delete/overwrite old rows.
 append writes one complete line and fsync before returning; bounded read checks
 fstat size before allocating. Hash every immutable event and chain row.
[x] Run .venv/bin/python -m pytest -q tests/test_att1_lifecycle_journal.py.
[x] Report API/test result to root; no commit.

## Integration gates and current completion

September 8: Tasks 1–4 pass 118 tests; fixture covers 23 durable restart
boundaries and two literal final net-R oracles. Task 5 remains in progress;
no VPS lifecycle deployment is claimed yet. Task 6 remains time gated.

### Exact task sequence

3. Implement the ATT1 coordinator over profile/admission and L2/L3. Event and
   fill accounting receive one shared normalized ID/quantity stream; independently
   verify partial/nonfill, ACK/exit finality, price/time triggers, funding and
   terminal net-R. Explicitly resolve delayed funding receipt reconciliation
   without assigning fabricated receipt times or changing past decisions.
4. Add executable local end-to-end fixture verifier and durable recovery runner;
   replay before/after every durable boundary produces identical state/cash.
5. Add public-only observation transport and separate VPS lifecycle package,
   pinned dependency closure/authority/systemd/resource/rollback checks. Deploy
   only after strong review and actual target-Python smoke. If public observation
   completeness or settlement coverage is insufficient, record NOT_CONFIRMED;
   never claim a clean fill/parity cohort from snapshot-only proxies.
6. Final 72h L1 evaluator after Sep8 08:02UTC; heartbeat scheduled11:25Cyprus.
   PASS plus clean complete lifecycle permits preparing a micro-canary dossier,
   not switching money on. Keep any unproven net economics gate visible.
