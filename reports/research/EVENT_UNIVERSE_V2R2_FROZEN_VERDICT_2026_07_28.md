# Event Universe V2r2 frozen verdict — 2026-07-28

## Verdict

- `FAIL_AGGREGATE` at 1h and 4h after the frozen 16 bps cost hurdle.
- `BLOCKED_DATA` at 24h because only 669 of 1,377 selected episodes were
  scoreable at the frozen chain head.
- `MONEY_NO_GO`; no strategy threshold or live risk was changed.

The collector completed 1,504 immutable five-minute snapshots and the frozen
scorer validated its source/hash chain. The receipt is research-only and has
no promotion authority.

## Frozen aggregate

| Horizon | Scored | Mean net | Median net | Positive |
|---|---:|---:|---:|---:|
| 1h | 1,333 | -6.33 bps | -16.00 bps | 40.4% |
| 4h | 1,236 | -12.57 bps | -16.00 bps | 44.1% |
| 24h | 669 | -21.06 bps | -16.00 bps | 49.0% |

The revealed 24h side split is asymmetric:

- long: -207.77 bps, N=340;
- short: +171.90 bps, N=329.

This is a discovery, not a PASS. It may be bear-regime beta and was observed
after opening the frozen results. The only valid continuation is a new
short-only preregistration with point-in-time regime/beta controls and an
untouched forward window. The long and short statistics must remain separate.

## Data quality

- snapshot count: 1,504;
- selected episodes: 1,377;
- scorer validation: passed;
- private/broker/API calls: none;
- orders or risk mutation: none;
- 24h pending: 228;
- 24h unscorable because of missing future bars: 480.

Source receipt:
`reports/research/event_universe_v1_labels/event_universe_label_receipt_s001504_3d6581e1e564_dbea2f658e29.json`.
