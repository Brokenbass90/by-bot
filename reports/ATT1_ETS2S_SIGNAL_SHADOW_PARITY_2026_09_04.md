# ATT1 + ETS2S strategy-to-shadow L1 parity — 2026-09-04

## Verdict

`PASS` for both frozen signal profiles on the hash-verified fixture.  This is
L1 signal parity only.  It authorizes preparation of a zero-risk VPS shadow;
it does not authorize orders, live risk, or a canary.

| sleeve | decision rows | signals | exceptions | field mismatches | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| ATT1 | 600 | 6 | 0 | 0 | PASS |
| ETS2S | 600 | 30 | 0 | 0 | PASS |

The two input files are the fixture bytes supplied in the 2026-09-04 handoff:

- `1000BONKUSDT.json`: `e4ae5ab63a53d0e028bcd98084cb08c712ae2c013146f61893aef0b28f66aadb`
- `1000PEPEUSDT.json`: `3e11ee1a54a2511eda3603f905ae082f614161feb3d8f45bb8a814d247fdf0f5`

The authoritative receipt is
`research_lab/results/att1_ets2s_signal_shadow_parity_20260904/receipt.json`.
An independent byte comparison also passed:

- ATT1 research/shadow journals: identical SHA-256
  `816350e4ab0cf7c621f9f75131a06d7dd80231e2d2f446abf2ee8d4e1882c9b4`;
- ETS2S research/shadow journals: identical SHA-256
  `12ee93705dbd37da3d09bdb69bf8831bb2171a7acb65fcedc97bc5a0d8be498c`.

## What was actually compared

For every one of 300 decision bars per symbol, the runner compared a direct
strategy call with the stateful live/shadow wrapper.  No-signal bars were
included.  Any exception forces `FAIL`, even when both sides raise the same
exception.

Compared fields include side, entry, effective stop, targets, target fractions,
reason, actual time stop, entry type/offset/wait, exact resolved configuration
hash, source-closure hash, data hash, and Store contract id.

ATT1 uses its native frozen wide configuration (`SL_ATR_MULT=6.60`, max stop
25%, 336h).  ETS2S applies the preregistered effective transform, rather than
merely labelling a raw signal: raw stop distance times four, native targets
unchanged, 336h time stop, short-only, limit metadata 0.2%/6 bars.

## Canonical Store decision

The canonical contract is `canonical_closed_utc_buckets_v1`:

- source H1 rows must be closed, ordered, on the UTC grid, gap-free in every
  consumed complete bucket, and have valid OHLCV geometry;
- higher timeframes are real UTC aggregation, not aliases for H1;
- an incomplete higher-timeframe tail is excluded;
- unsupported, finer, non-integral, and calendar-month requests fail closed.

The handoff proposal to expose a forming D1 was rejected.  The production
ATT1 wrapper and the monolith's `_ElderStore` both call `fetch_closed_klines`.
The raw Bybit fetch does include the forming candle, but the strategy boundary
removes it.  Therefore closed-only is the production-parity contract.

The supplied research etalons were not used as truth.  They report ATT1 14 and
ETS2S 7 signals, while the closed/frozen profiles produce 6 and 30.  They bind
different Store/config semantics.  In particular, the previous ETS2S sealed
economics cannot be transferred to this live profile until it is re-audited
under the closed-bar contract; L1 PASS proves implementation agreement, not
profitability.

## Exact blockers before a zero-risk VPS shadow

1. Add a default-off always-on caller that invokes `ElderShadowEngine` and the
   frozen ATT1 engine only after a newly closed H1 bar.  It must have no order
   or private-API import path.
2. Persist one append-only L1 row for every `(sleeve_id, symbol, bar_ts)`,
   including no-signal and exception rows, with unique-key deduplication and
   restart-safe state.
3. Separate timely `EXECUTION_FORWARD` observations from backfilled
   `ALPHA_FORWARD_BACKFILL`; backfill must never impersonate a standing order.
4. Freeze the VPS evidence universe and public-data manifest, then bind its
   source/config/data hashes to the heartbeat and each journal row.
5. Package the exact source closure and target Python dependencies; on the VPS,
   run import/startup smoke and compare deployed hashes with this commit.
6. Add health/heartbeat, stale-bar, gap, clock-skew, disk, and atomic-journal
   fail-closed checks plus an explicit rollback procedure.

After those six items, the zero-risk shadow can start its 72-hour burn-in.
Before any micro-canary, L2 execution telemetry and L3 fees/funding/net-R
accounting remain mandatory, as do clean burn-in results and a separate
economic/capacity verdict for ETS2S under closed bars.
