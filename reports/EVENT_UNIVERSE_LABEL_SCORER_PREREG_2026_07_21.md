# Event Universe V1 — prospective label scorer preregistration

Frozen before the first outcome-scoring pass on 2026-07-21. This document and
`configs/preregistered/event_universe_label_scorer_v1_20260721.json` define the
analysis; the observed returns must not be used to alter these rules in place.

## Question

Does an `event_ok` observation from the already-running public, closed-M5 event
collector contain a directionally useful 1-hour, 4-hour, or 24-hour follow-through
signal after a fixed 16 bps round-trip research hurdle?

This is a label study, not a trading strategy. The heuristic rank is not a
probability, 16 bps is not an account- or symbol-specific executable cost contract,
and this run has no authority to promote a sleeve.

## Frozen episode and outcome semantics

- Candidates are only stored scores with `ok=true`, `reason=event_ok`, and a
  stored direction of exactly `long` or `short`.
- Candidates are read chronologically. For each `(symbol, direction)`, take the
  first candidate and then the first candidate at least 24 hours after the last
  selected episode. Repeated cards inside the cooldown are observations of the
  same episode, not additional samples.
- Entry is the open of the exact next contiguous M5 bar after the final closed M5
  input bar that produced the candidate. That entry bar must later be observed as
  closed in an immutable replay object; a forming bar is never used.
- The 1h, 4h, and 24h endpoints are the closes of bars 12, 48, and 288 counted
  from the entry bar. Net endpoint return is the direction-adjusted simple return
  less 16 bps once. MFE and MAE use the closed bars' intrabar high/low path and are
  reported gross as positive favorable/adverse magnitudes.
- Long and short outcomes are never pooled without also retaining their separate
  summaries. Listing tier, direction × tier, and fixed feature buckets are frozen
  in the JSON spec.

## Fail-closed and provenance contract

The scorer makes no network, credential, broker, order, account, risk, or live
router call. It freezes the snapshot filename list at process start; validates the
entire snapshot/hash/delta replay chain; replays the original scores; rejects any
conflicting M5 bar; and requires every bar in an outcome window to be contiguous.
A broken chain aborts the whole pass. A mature but incomplete window is marked
`unscorable_missing_future_bars`; an endpoint beyond the chain head is `pending`.
Partial windows are never scored.

The deterministic receipt binds the scorer code hash, preregistration payload
hash, collector spec/config hashes, frozen snapshot count, chain-head hash, a
canonical source-chain hash, and every selected candidate/input hash. Re-running
the same code/config/data produces the same bytes. A later chain head produces a
separate content-addressed receipt.

## Interpretation guard

No minimum N is being invented after seeing the result. The receipt may say what
was observed, but it cannot call a sleeve profitable, live-ready, or promotable.
Any promising pattern requires a separate causal strategy specification, realistic
symbol/account costs, untouched forward data, concentration checks, and a shadow
canary. Any next hypothesis must receive a new preregistration rather than editing
this one around the outcomes.
