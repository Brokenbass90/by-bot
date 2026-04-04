# Incident And Recovery Summary

Date: 2026-04-02

## What happened

1. A strong historical crypto baseline (`v5`) was previously validated on:
   - a fixed symbol union
   - a fixed env overlay
   - a fixed annual window

2. Later diagnostics mixed that validated baseline with exploratory runs that changed:
   - symbol universe
   - window
   - env reconstruction fidelity

3. That produced misleading comparisons, including extremely negative numbers that were not true apples-to-apples baseline reruns.

## What is now confirmed

### Confirmed historical baseline
- `full_stack_baseline_20260325_reconstructed_v5_dynamic_allowlist_probe_annual`
  - net `+94.76`
  - PF `2.141`
  - DD `2.89`
- `full_stack_baseline_20260328_v5_dynamic_allowlist_recent_annual`
  - net `+89.65`
  - PF `2.121`
  - DD `2.88`

### Confirmed exact-overlay holdout reruns
- `v5_overlay_current90_true`
  - net `-4.13`
  - PF `0.839`
  - DD `7.52`
- `v5_overlay_180d_true`
  - net `-23.61`
  - PF `0.663`
  - DD `24.92`

## Main conclusion

The historical edge was real, but it was not robust enough across newer / adjacent windows.

This means:
- the old positive results were not fabricated
- but the system was not sufficiently validated for regime robustness

## Current live-stack diagnosis

On exact-overlay holdout reruns, the main damage comes from:
- `inplay_breakout`
- `alt_inplay_breakdown_v1`

The least harmful / most stable sleeves are:
- `alt_resistance_fade_v1`
- `alt_sloped_channel_v1`
- `btc_eth_midterm_pullback` (quiet but not strong)

## Structural gaps now acknowledged

1. No portfolio-level live regime orchestrator
2. Crypto dynamic allowlist is advisory, not auto-applied
3. `breakout` and `breakdown` are too permissive in the current market
4. Validation discipline was too weak:
   - exploratory vs baseline results were mixed

## Recovery plan

1. Enforce strict validation protocol
   - exact overlay
   - exact symbols
   - exact strategies
   - exact fees/slippage
   - clear result class labels

2. Build regime orchestrator
   - sleeve on/off
   - global risk multiplier
   - symbol bias / narrowing

3. Repair `inplay_breakout`
   - not via exit tweaks only
   - via stricter entry quality
   - regime-aware gating

4. Repair or demote `alt_inplay_breakdown_v1`
   - current bear-window performance is not acceptable

5. Continue new candidate fronts
   - `pump_momentum_v1`
   - later `pump_fade_v4r`

## Current truth status

The bot is not currently trustworthy as a stable always-on self-adapting portfolio.

The project still has usable components and real historical edge evidence, but it needs:
- stricter validation
- portfolio-level regime control
- repair of the momentum sleeves
