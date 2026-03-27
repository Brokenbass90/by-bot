# Alpaca Whale Overlay Plan

## Goal

Add a testable `whale / insider conviction` overlay above the existing monthly equities sleeve.

This is **not** blind copy-trading.

The overlay should:
- add a score bonus to already strong candidates,
- add a penalty to weak / crowded / low-conviction names,
- remain optional and fully backtestable,
- never bypass the base regime / breadth / concentration rules.

## Why this shape

Blind "buy because a whale bought" is noisy and usually delayed.

A better structure is:
- base sleeve selects strong names,
- overlay adjusts ranking confidence,
- allocator decides whether a whale sleeve deserves some capital later.

## Data we can realistically use

Phase 1:
- insider activity summaries
- delayed institutional / leader snapshots
- curated conviction watchlists

Phase 2:
- richer holdings-change history
- manager-level leader scoring
- sector / theme conviction rollups

## Required point-in-time rule

Every overlay datapoint must be timestamped and usable only from that date forward.

No hindsight:
- do not use "best whale" lists learned from the future
- do not leak later filings into earlier months

## Backtest integration

The monthly equities simulator now supports:
- `--overlay-csv`
- `--overlay-score-mult`

Expected CSV schema:
- `day,ticker,score`

Supported `day` formats:
- exact snapshot day: `YYYY-MM-DD`
- monthly bucket: `YYYY-MM`

Behavior:
- base candidate score is preserved in `base_score`
- overlay value is stored in `overlay_score`
- effective ranking score becomes:
  - `score = base_score + overlay_score_mult * overlay_score`

## First clean experiment

Run three comparisons on the same core sleeve:

1. baseline:
- no overlay

2. mild overlay:
- `overlay_score_mult` small, e.g. `0.20 .. 0.50`

3. stronger overlay:
- `overlay_score_mult` medium, e.g. `0.75 .. 1.25`

Evaluate:
- compounded return
- red months
- worst month
- max monthly DD
- concentration drift
- ticker turnover

## Safe usage rule

Overlay may reorder candidates, but should not:
- disable earnings blackout,
- override breadth / benchmark gates,
- override cluster / correlation rules,
- force a buy in an otherwise rejected ticker.

## Good next step

Build a first synthetic overlay dataset from:
- manual conviction flags,
- insider/leader notes,
- or a simple score file derived from curated monthly research.

Once that works end-to-end, replace synthetic inputs with real point-in-time leader data.
