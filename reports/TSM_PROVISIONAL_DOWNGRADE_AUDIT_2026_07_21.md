# TSM tsm4 long/short — corrective audit (2026-07-21)

## Decision

`tsm4 long_short` is **not a promotion-grade PASS**.  Its previous PASS label is
superseded by `RESEARCH_BLOCKED`.  It must not be wired to the VPS, called a valid
shadow, or used to authorize capital until a corrected, immutable rerun passes.

This does not prove that weekly time-series momentum has no edge.  It proves that
the current receipt cannot establish that edge.

## Blocking findings

1. **The weekly anchor is not fixed.**
   `station_tsm_v2_holdout.py` starts at a symbol-dependent warm-up index and then
   advances by seven rows.  Because histories start on different weekdays, the
   decision weekday differs by symbol (BTC Wednesday, ETH Monday, SOL Friday,
   XRP/ADA Thursday, DOGE Wednesday).  The proposed shadow is described as Monday
   execution, so backtest and shadow are not the same strategy.

2. **The cost statement and implementation disagree.**
   The preregistration says `6+2 bps/side`, but `backtest_daily()` subtracts
   `FEE_SIDE` once when a trade closes.  A complete open-and-close cycle therefore
   receives only one modeled side instead of two.  Funding is also a fixed adverse
   `3 bps/day`, not a verified point-in-time funding series.

3. **The result is anchor-sensitive and concentrated.**
   Independent fixed-weekday replay ranged from `-8.01R` to `+91.48R`.  A
   Monday-to-next-open interpretation produced `+16.09R` pooled but calendar 2023
   was `-19.52R`, which fails the frozen `year >= -15R` gate.  The original
   `+61.39R` is dominated by 2021 (`+46.86R`, about 76% of total).

4. **Perpetual-futures survival is not modeled.**
   The strategy is always long or short at fixed notional, but the backtest has no
   mark-price, maintenance-margin, liquidation, borrow/availability, or funding
   settlement model.  DOGE had entry-to-adverse-high excursions around `2.5–2.7x`;
   a nominal 1x USDT-perpetual implementation cannot simply assume survival.

5. **The local shadow ledger is not a valid parity clock.**
   `tsm_shadow_local.py` has no fixed exchange-time anchor, `as_of` closed-bar ID,
   source hash, run identity, or idempotency key.  Two entries were appended on
   2026-07-21 with different closes.  They are duplicate same-day observations,
   not two valid weekly records.  Valid parity weeks remain `0/8`.

6. **Evidence was not immutable.**
   The runner, downloaded daily files, output JSON, and local shadow ledger were
   untracked when the PASS was announced.  The result therefore lacks an
   immutable Git/data/config receipt.

## Required rerun contract

- one explicitly preregistered UTC weekday and decision close for every symbol;
- signal from closed bars only, entry at the exact next tradable open;
- both entry and exit fees, point-in-time funding (or a documented conservative
  stress distribution), slippage and gap handling;
- mark/maintenance/liquidation survival for each symbol and venue;
- fixed equal-risk or equal-notional portfolio semantics (do not call it
  dollar-neutral unless both gross and net exposure constraints are actually met);
- immutable code/config/input hashes and a one-shot sealed evaluation;
- prospective shadow receipt with one record per anchored week, idempotent reruns,
  source cutoff/hash and offline parity comparison.

Only a corrected frozen PASS can start an eight-week parity clock.  The current
code and ledger remain useful research artifacts, but have zero promotion
authority.
