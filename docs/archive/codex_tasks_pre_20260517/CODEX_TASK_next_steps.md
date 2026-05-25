# Codex Task: Next Steps After Foundation Deploy

## Context
Foundation deploy was done (systemd, heartbeat, watchdog, control plane crons).
Now we need three things in priority order.

---

## Task 1: IVB1 Regime Gating (Breakout Repair)

**Strategy:** `impulse_volume_breakout_v1.py`
**Current state:** Has a good pocket (PF=1.785 current90, PF=1.691 recent180), but trades longs only.
Annual walk-forward is weak because it tries to trade during bear phases.

**What to do:**

1. Add `IVB1_REGIME_MODE` parameter to `impulse_volume_breakout_v1.py` (same pattern as breakdown):
   - `off` = no regime filter (current behaviour)
   - `ema` = only trade when BTC EMA21 > EMA55 on 4H (bull bias)
   
2. Add env loading:
   ```python
   self.cfg.regime_mode = _env("IVB1_REGIME_MODE", self.cfg.regime_mode)
   self.cfg.regime_tf = _env("IVB1_REGIME_TF", self.cfg.regime_tf)  # default "240"
   self.cfg.regime_ema_fast = _env_int("IVB1_REGIME_EMA_FAST", 21)
   self.cfg.regime_ema_slow = _env_int("IVB1_REGIME_EMA_SLOW", 55)
   ```

3. Run a 360-day walk-forward with `IVB1_REGIME_MODE=ema` using the best r574 params:
   ```
   IVB1_MIN_IMPULSE_PCT=0.05
   IVB1_MIN_VOL_MULT=1.4
   IVB1_BREAKOUT_BUFFER_ATR=0.0
   IVB1_RETRACE_MIN_FRAC=0.15
   IVB1_RETRACE_MAX_FRAC=0.5
   IVB1_SL_ATR=1.0
   IVB1_RR=1.6
   IVB1_SYMBOL_ALLOWLIST=SOLUSDT,LINKUSDT,SUIUSDT,DOGEUSDT,1000PEPEUSDT,TAOUSDT,HYPEUSDT
   ```
   Use script: `scripts/run_crypto_core_walkforward.py --strategy impulse_volume_breakout_v1 --days 360`

4. Compare: `regime_mode=off` vs `regime_mode=ema` on the same 360d window.
   Expected: ema-gated version should have fewer trades but better annual PF and lower DD.

5. If IVB1 with regime gating passes (annual PF > 1.2, DD < 15%): add it to `core3_impulse_candidate_20260408.env` with `IVB1_REGIME_MODE=ema`.

---

## Task 2: Core2 Honest Walk-forward (Backbone Validation)

**Goal:** Know the true stability of core2 (breakdown + ARF1 only, no impulse) before scaling capital.

**What to do:**

1. Run 360-day walk-forward on core2 ONLY (no IVB1):
   ```bash
   python3 scripts/run_crypto_core_walkforward.py \
     --strategies alt_inplay_breakdown_v1,alt_resistance_fade_v1 \
     --days 360 \
     --tag core2_honest_wf_360d_20260408 \
     --env configs/live_candidate_core2_breakdown_arf1_20260404.env
   ```

2. Save results to `backtest_runs/core2_honest_wf_360d_20260408/`

3. Report: how many of 24 windows are positive? What's the worst window? Is ARF1 actually trading in all windows?

4. Record verdict in JOURNAL.md:
   - If ≥16/24 windows positive (>66%) AND annual DD < 20%: core2 is promotable backbone
   - If <16/24 positive: need to understand which regime kills it and gate accordingly

---

## Task 3: Capital Router Blueprint in ROADMAP

Add this section to `docs/ROADMAP.md` under P4:

```
### P4c - Capital Router (Regime-Aware Capital Allocation)

Goal: maximize capital utilization across regimes by shifting allocation
between directional and non-directional sleeves.

Concept:
  bear_chop:  funding_carry_weight=0.25, directional_weight=0.75
  bear_trend: funding_carry_weight=0.10, breakdown_weight=0.90
  bull_trend: funding_carry_weight=0.00, impulse_weight=1.00

Implementation:
  1. Extend build_portfolio_allocator.py with a `funding_carry` sleeve
  2. Output CARRY_POSITION_USD to portfolio_allocator_latest.env
  3. funding_carry_executor.py reads CARRY_POSITION_USD from env
  4. Run on same hourly cron as allocator

Prerequisites:
  - funding_carry validated on 365d window (done: PF positive, modest DD)
  - regime router stable in production (P1 requirement)
  - capital >= $2000 for meaningful carry yield (~$300/year)

Platform: Bybit only. No cross-platform routing.
```

---

## After All Three Tasks

Run `server_status.sh` and report:
- Bot running via systemd: yes/no
- Heartbeat fresh: yes/no  
- All control plane files fresh: yes/no
- Current regime: ?
- Active crons: list
