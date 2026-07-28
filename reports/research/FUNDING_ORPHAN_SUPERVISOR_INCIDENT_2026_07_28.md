# Funding orphan supervisor incident — 2026-07-28

Status: resolved locally. Research-only; no broker orders or live trading were
affected.

## What happened

The screen-visible funding supervisor was correctly protected by the new
single-writer lock, but an older pre-lock shell remained orphaned outside
`screen -ls`:

- parent PID `31550`, started `2026-07-27 12:52:14` local time;
- loop PID `31553`, same start time;
- command: `scripts/run_cross_exchange_funding_shadow_loop.sh`.

It could no longer race the lifecycle state writer after the newer supervisor
owned the lock, but its already-loaded shell body still invoked the ROI
calculator without the post-cutover filter. At `2026-07-28T11:14:38Z` it
overwrote `runtime/arb/arb_roi_estimate.json` with a mixed `N17` cohort.

That `N17` receipt is quarantined and has no promotion or capital authority.

## Resolution

- Exact process inspection confirmed one new screen supervisor plus the orphan.
- PID `31553` and parent `31550` received `TERM` and exited.
- A second process inspection confirmed only the screen-owned chain
  `12041 -> 12042 -> 12045`.
- The ROI receipt was regenerated from
  `runtime/arb/cross_exchange_funding_shadow.json` with:

```text
--cohort explicit_validation_v1
--opened-after-utc 2026-07-27T10:53:00Z
```

## Restored truth

- eligible post-cutover closed cycles: `7`;
- excluded pre-cutover cycles: `10`;
- wins/losses: `0/7`;
- median return per total-capital cycle: `-0.1930%`;
- p25: `-0.2308%`;
- remaining to initial N20 gate: `13`;
- capital authorized: `false`.

The collector remains low-priority research. No live service, ATT1 setting,
risk, universe, order, or broker position was changed.
