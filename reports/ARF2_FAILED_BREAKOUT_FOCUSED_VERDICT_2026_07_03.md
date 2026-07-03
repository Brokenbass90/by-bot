# ARF2 failed-breakout focused verdict — 2026-07-03

## Status

Research candidate, not live/canary yet.

The broad ARF2 failed-breakout run was only weakly positive and not promotable:
`177` trades, `+6.02R`, PF `1.05`, unstable months.

Post-analysis showed the edge is symbol-specific. A focused rerun on the only
credible symbols (`DOGEUSDT`, `XRPUSDT`, `ONDOUSDT`) with denser 15m checks
produced a materially stronger result:

| variant | trades | netR | PF | WR | symbols+ | years+ | months+ | worst month |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| failed_breakout_short | 73 | +25.87 | 1.65 | 50.7% | 3/3 | 2/2 | 7/12 | -3.42R |
| failed_breakout_volfade_short | 60 | +18.92 | 1.57 | 50.0% | 2/3 | 2/2 | 8/11 | -3.96R |

Fee/slippage stress at `12 bps` per side still survives:

| variant | trades | netR | PF | WR |
|---|---:|---:|---:|---:|
| failed_breakout_short | 73 | +21.94 | 1.52 | 50.7% |
| failed_breakout_volfade_short | 60 | +15.64 | 1.45 | 50.0% |

Stress at `16 bps` per side also survives:

| variant | trades | netR | PF | WR |
|---|---:|---:|---:|---:|
| failed_breakout_short | 73 | +18.01 | 1.41 | 50.7% |
| failed_breakout_volfade_short | 60 | +12.35 | 1.34 | 50.0% |

Temporal sanity on the stressed run:

| variant | split | trades | netR | PF |
|---|---|---:|---:|---:|
| failed_breakout_short | first half | 36 | +12.69 | 1.68 |
| failed_breakout_short | second half | 37 | +9.25 | 1.40 |
| failed_breakout_short | last 90d | 17 | +7.01 | 1.76 |
| failed_breakout_volfade_short | first half | 30 | +7.12 | 1.44 |
| failed_breakout_volfade_short | second half | 30 | +8.51 | 1.46 |
| failed_breakout_volfade_short | last 90d | 16 | +5.75 | 1.62 |

## Interpretation

This is the first concrete horizontal/range-family candidate after ATT1 r001.
It is not broad enough for immediate live because the symbol set was selected
after inspecting the first run. But it is strong enough to move to a strict,
pre-registered gate.

Important implementation notes:

- Use failed-breakout reclaim entry directly.
- Do not use `level_entry` here; it hurt the edge in the broad run.
- Keep it short-only for this candidate.
- Keep the symbol set fixed for the next gate: `DOGEUSDT,XRPUSDT,ONDOUSDT`.
- Use cost stress in the gate; 12 bps/side survived.

## Next gate

Pre-register:

- sleeve: `arf2_failed_breakout_short_focused`
- symbols: `DOGEUSDT,XRPUSDT,ONDOUSDT`
- side: short only
- variant: `failed_breakout` primary; `failed_breakout_volfade` challenger
- check frequency: 15m equivalent (`step=3` on 5m data)
- cost stress: base 8 bps/side, stress 12 bps/side
- reject if second half or last 90d turns negative in rerun
- reject if DOGE alone explains most of netR after updated data

Only after that: shadow/canary discussion.

## Evidence

- `reports/research/arf2_failed_breakout_focused_20260703/summary.md`
- `reports/research/arf2_failed_breakout_focused_20260703/analysis/summary.md`
- `reports/research/arf2_failed_breakout_focused_cost12_20260703/summary.md`
- `reports/research/arf2_failed_breakout_focused_cost12_20260703/analysis/summary.md`
- `reports/research/arf2_failed_breakout_focused_cost16_20260703/summary.md`
- `reports/research/arf2_failed_breakout_focused_cost16_20260703/analysis/summary.md`
