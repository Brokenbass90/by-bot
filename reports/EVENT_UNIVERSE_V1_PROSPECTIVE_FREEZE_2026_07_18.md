# Event Universe v1 — prospective research freeze

Frozen at `2026-07-18T07:28:00Z`, before any public collection from this implementation.

## Decision

`event_universe_v1` is a discovery layer, not a trading strategy. It exists because the current live scanner covers only 20 mature symbols on H1/H4 and therefore excludes AKE/BANK/LYN/US-like events before setup geometry is evaluated.

Authority is deliberately empty: public Bybit GET only; no API keys or environment credentials; no private endpoints, accounts, broker calls, positions, orders, transfers, withdrawals, risk mutation, live-router expansion, performance claims or promotion authority. Default invocation is a no-network/no-write preflight.

## Frozen causal contract

- Universe source: all point-in-time `Trading` linear USDT-settled perpetual instruments returned through cursor pagination, joined to the same-cycle public ticker snapshot.
- Eligibility: listing age at least 24h; separate `fresh_shadow` tier until day 7; 24h turnover at least $1m; valid bid/ask; spread at most 35 bps; missing launch time, ticker, price change or book fields fails closed.
- M5 prefetch is bounded to 100 symbols: two-thirds event proxy (`abs(24h move) × log liquidity`), with the rest liquid controls. This is a discovery compromise, not a claim that the omitted instruments have no setups.
- Score input: exactly 72 baseline plus 3 recent closed, contiguous M5 bars. Forming/future bars are discarded. True quote turnover is taken from the exchange kline field, never inferred from base volume.
- Advisory event gate: recent quote turnover >= $100k, inflow multiple >= 1.5, robust inflow z >= 1.5, range expansion >= 1 prior ATR and absolute recent return <= 18%. Ranking is explicitly a heuristic, never a probability.
- Candidate cards include only `ok=true` scores. High-ranked rejected observations remain separately visible for diagnosis.
- Source/local clock skew is capped at 120s; snapshot cutoffs must increase strictly; each public cycle is capped at 240s and 2 requests/s.

## Reproducibility and survival

- Seven-day / 2,016-snapshot maximum; 512 MiB whole-tree stop cap; 20 GiB minimum free space; STOP/NO DELETE/NO ROTATE.
- Immutable deterministic-gzip snapshots, strict sequence/as-of/hash chain, atomic `latest_state`, single-writer lock, normalized path containment and 0600 persisted files.
- Normalized score replay is exact: first appearance is a 75-bar checkpoint; later cycles store only append-only closed-bar deltas linked by prior/current input hashes. Offline validation reconstructs every tail and requires `score_event_m5` canonical equality.
- Replay scope is stated narrowly: normalized score replay is verified; the full exchange response bodies behind source hashes are not retained. Source hashes are asserted and tamper-bound, not independently source-replayed.
- Launch receipt pins preregistered spec, config, deadline, storage limits and the SHA-256 of core, runner, launcher and supervisor implementations.
- A process verifies the complete existing chain once on startup, then carries the verified chain head in memory. This prevents an O(N²) revalidation loop while preserving full restart verification.

## Interpretation lock

Thresholds and universe rules cannot be tuned from this run. Screenshot examples are not labels. This station cannot authorize a trade or promotion. Any downstream consumer—horizontal breakout/hold/retest long, sweep/reclaim long, sloped-support bounce long, sloped-support break/retest short, pump continuation or pump fade—must have a separate side-specific preregistration, cost model, sealed time/symbol test and prospective shadow gate.

## Frozen files

- `bot/event_universe_v1.py`
- `scripts/run_event_universe_v1.py`
- `scripts/launch_event_universe_v1.sh`
- `scripts/supervise_event_universe_v1.sh`
- `configs/preregistered/event_universe_v1_20260718.json`
- `tests/test_event_universe_v1.py`

The first public observation may begin only after these files are committed and pushed.

Freeze verification: `25 passed` in the focused event-universe suite and `1463 passed in 31.80s` in the full project regression.
