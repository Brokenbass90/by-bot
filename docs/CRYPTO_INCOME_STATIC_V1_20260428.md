# Crypto Income Static V1 — 2026-04-28

## Candidate

First current high-income crypto package:

- `alt_trendline_touch_v1` (`ATT1`)
- `alt_resistance_fade_v1` (`ARF1` / flat)
- `alt_inplay_breakdown_v1` with ER macro-quality gate
- `btc_eth_midterm_pullback`

Config:

- `configs/crypto_income_static_v1_candidate.env`

Runner:

- `scripts/run_crypto_income_static_v1_candidate.sh`

This is still a research/live-candidate package. It is not a server deploy file
until it passes dynamic control-plane and canary checks.

## Results

All runs use cached 5m data, 1x leverage, 1% risk per trade, 6 bps fee, 2 bps
slippage, and symbols:

`BTCUSDT,ETHUSDT,SOLUSDT,ADAUSDT,LINKUSDT,LTCUSDT,DOTUSDT,SUIUSDT`

| Run | Window | Net | PF | WR | Max DD | Trades | Red Months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `crypto_income_static_v1_repro_20260428` | 365d to 2026-04-25 | `+70.17%` | `1.545` | `58.7%` | `6.23%` | `445` | `2/12` |
| `crypto_income_static_v1_recent180_20260428` | 180d to 2026-04-25 | `+50.98%` | `1.805` | `62.3%` | `3.76%` | `236` | `0/5` |
| `crypto_income_static_v1_recent270_20260428` | 270d to 2026-04-25 | `+60.89%` | `1.637` | `59.7%` | `7.13%` | `350` | `2/8` |
| `crypto_income_static_v1_oldend360_20260428` | 360d to 2026-03-27 | `+69.64%` | `1.478` | `57.6%` | `9.91%` | `491` | `2/12` |

Worst red month in these probes is September 2025:

- 365d run: `-2.17%`
- 270d run: `-3.44%`
- old-end 360d run: `-2.66%`

## Attribution

365d to 2026-04-25:

| Strategy | Trades | Net | PF | WR |
| --- | ---: | ---: | ---: | ---: |
| `alt_trendline_touch_v1` | `299` | `+39.05` | `1.44` | `60.2%` |
| `alt_inplay_breakdown_v1` | `75` | `+16.42` | `1.78` | `57.3%` |
| `alt_resistance_fade_v1` | `55` | `+7.61` | `1.52` | `54.5%` |
| `btc_eth_midterm_pullback` | `16` | `+7.08` | `2.46` | `50.0%` |

Recent 180d:

| Strategy | Trades | Net | PF | WR |
| --- | ---: | ---: | ---: | ---: |
| `alt_trendline_touch_v1` | `167` | `+34.44` | `1.79` | `65.3%` |
| `alt_inplay_breakdown_v1` | `48` | `+10.84` | `1.83` | `58.3%` |
| `btc_eth_midterm_pullback` | `9` | `+4.94` | `2.71` | `55.6%` |
| `alt_resistance_fade_v1` | `12` | `+0.75` | `1.19` | `41.7%` |

## Read

- `ATT1` is the current tradeful engine.
- `breakdown_v1` becomes useful only with the ER/macro quality gate.
- `ARF1` is a stabilizer, not the main income source in the recent window.
- `btc_eth_midterm_pullback` is sparse but additive.
- This package is stronger than the current reproduced golden-baseline state,
  but it is static. It still needs the live control-plane path checked.

## Dynamic Control-Plane Replays

Dynamic runs use historical regime/router/allocator replay with 30d windows.
The final 2026-03-26 -> 2026-04-25 window is skipped by the harness coverage
check because `.cache/klines` does not contain full-window millisecond slices
for all requested symbols, so these results cover 11 populated windows.

| Package | Router | Net | PF | WR | Max DD | Trades | Red Months | Read |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `ATT1 + ARF1 + breakdown + midterm` | dynamic | `+42.60%` | `1.387` | `58.8%` | `5.87%` | `534` | `1` | Positive, but breakdown attribution is negative. |
| `ATT1 + ARF1 + breakdown + midterm` | fixed symbols | `+35.94%` | `1.302` | `56.9%` | `10.73%` | `575` | `2` | Worse than dynamic router. |
| `ATT1 + ARF1 + midterm` | dynamic | `+45.30%` | `1.489` | `59.9%` | `5.77%` | `454` | `1` | Best current live-canary candidate. |
| `ATT1 + ARF1 + midterm` canary v2 | dynamic | `+45.44%` | `1.493` | `59.9%` | `5.95%` | `456` | `1` | Deployed profile: v7 cut, ARF1 bull_chop guard, direct raw regime overlay disabled. |
| `ATT1 + midterm` | dynamic | `+26.94%` | `1.334` | `59.9%` | `5.91%` | `409` | `1` | Too much income is lost by removing ARF1. |

Dynamic attribution says:

- `ATT1`: `+32.49` net over `390` trades in the best canary replay.
- `ARF1`: `+12.80` net over `64` trades, but the worst month is caused by
  ARF1 in bull_chop.
- `breakdown_v1`: negative in dynamic replay, so keep it out of live for now.
- `btc_eth_midterm_pullback`: no stitched trades in this replay; keep enabled
  only as a sparse additive sleeve and monitor live activity.

Current deploy candidate:

- `configs/crypto_income_live_canary_v2.env`
- `configs/portfolio_allocator_policy_canary_v2.json`
- package: `ATT1 + ARF1 + btc_eth_midterm_pullback`
- risk: reduced canary risk; breakdown/range/bounce/impulse/v7/vwap disabled
- live hardening: `REGIME_OVERLAY_ENABLE=0`, `PORTFOLIO_ALLOCATOR_ENABLE=1`;
  orchestrator still refreshes state, allocator applies the canary policy.

Server deploy on 2026-04-28:

- `bybot.service` restarted successfully.
- Startup flags: `midterm=True`, `att1=True`, `flat=True`,
  `breakdown=False`, `ivb1=False`, `elder=False`.
- Heartbeat after restart: fresh, `ws_guard_active=0`, Bybit messages flowing.
- Open trades at deploy check: `0`.

## Next Gates

Before live expansion:

1. Run one more recent-window replay after refreshing `.cache/klines`, so the
   skipped April 2026 window is included.
2. Add a bull_chop guard or lower ARF1 bull_chop risk, because the only red
   month is ARF1-driven.
3. Monitor canary v2 for 48-72h: heartbeat, `ATT1`/`flat`/`midterm` attempts,
   live trade events, and any unexpected disabled-sleeve activity.
4. Keep `breakdown_v1` in repair until dynamic attribution turns positive.
