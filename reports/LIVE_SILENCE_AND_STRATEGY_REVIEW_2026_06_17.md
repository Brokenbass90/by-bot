# Live Silence And Strategy Review — 2026-06-17

## Short answer

The server is quiet for two separate reasons:

1. **Live risk/config is mostly muted.** The live process has `IVB1_RISK_MULT=0.0`, `ENABLE_RANGE_TRADING=0`, `ENABLE_INPLAY_TRADING=0`, `ENABLE_RETEST_TRADING=0`, `BREAKDOWN_RISK_MULT=0.0`, and only tiny `FLAT_RISK_MULT=0.10` / `SLOPED_RISK_MULT=0.10`.
2. **The IVB1 / breakout-retest entry logic is not the owner's discretionary setup yet.** It still uses rolling highs/lows and a reclaim-close entry, not true S/R levels with limit entry on retest.

So yes, the current control plane is defensive enough to suppress live trading, and one of the enabled-but-muted strategies is also logically weak.

## Ground truth from live process

Checked `/proc/<smart_pump_reversal_bot.py>/environ` on the server at 2026-06-17:

- `DRY_RUN=false`
- `ENABLE_IVB1_TRADING=1`
- `IVB1_RISK_MULT=0.0`
- `ENABLE_RANGE_TRADING=0`
- `ENABLE_INPLAY_TRADING=0`
- `ENABLE_RETEST_TRADING=0`
- `ENABLE_BREAKDOWN_TRADING=0`
- `BREAKDOWN_RISK_MULT=0.0`
- `ENABLE_FLAT_TRADING=1`
- `FLAT_RISK_MULT=0.10`
- `ENABLE_SLOPED_TRADING=1`
- `SLOPED_RISK_MULT=0.10`

Important: `reports/SERVER_SNAPSHOT_latest.md` safe_config includes some keys that are not present in the live process environment, such as `ENABLE_ARS1_TRADING=1` / `ARS1_RISK_MULT=0.80`. Treat the live process environment as ground truth for what the running bot can actually trade. The snapshot exporter should be improved to show config source and live-process env separately.

## What Claude changed vs what Claude only specified

Implemented in code:

- `strategies/impulse_volume_breakout_v1.py`: mirrored short support via `IVB1_ALLOW_SHORTS` / `IVB1_DIRECTION_MODE`.
- `strategies/inplay_breakout.py`: direction mode support via `BREAKOUT_DIRECTION_MODE`.
- `strategies/alt_range_scalp_v1.py`: optional range repair filters `ARS1_MAX_ADX`, `ARS1_MIN_BODY_FRAC`, `ARS1_MIN_VOL_MULT`.
- Autoresearch configs for IVB mirror, breakout-retest v2, Elder EMA50, range v3, VWAP.

Not implemented yet:

- `reports/IVB1_INPLAY_LOGIC_REVIEW_2026_06_16.md` is a diagnosis/spec, not a code rewrite.
- IVB1 still uses rolling-high/rolling-low levels.
- IVB1 still enters after a reclaim-close bar.
- IVB1 does not yet use `sr_levels.py` / `chart_geometry.py` / `router_geometry.py` for true levels.
- IVB1 does not yet place a limit-style retest entry with tight stop behind the level and target before next level.

## Current research verdict

- **Range v3 / "пила от границ флэта"**: first real green candidate. Interim local run found 8 PASS rows in the first 155 checked. Best row `range_scalp_v1_annual_repair_v3_r004`: `net=+16.85`, `PF=1.691`, `DD=6.58`, `108 trades`, `4 negative months`.
- **IVB mirror / "импульсный пробой с откатом"**: currently 0 PASS in local early run; best seen around `PF=1.02`, not canary material.
- **Breakout-retest v2 / "пробой уровня с ретестом"**: currently 0 PASS in early local run; logic likely needs the same level/retest rewrite.

## Immediate next actions

1. Compare live-current vs `range_scalp_v1_annual_repair_v3_r004` on identical period/fees/slippage.
2. Run stack comparison for range v3 to see whether the bot's control plane improves or suppresses it.
3. Rebuild IVB/inplay around true levels and retest entry as specified in `reports/IVB1_INPLAY_LOGIC_REVIEW_2026_06_16.md`.
4. Fix snapshot/export wording so it cannot confuse `.env`, safe_config, overlays, and live process env.
