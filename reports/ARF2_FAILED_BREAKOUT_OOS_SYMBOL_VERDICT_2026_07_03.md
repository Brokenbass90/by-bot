# ARF2 failed-breakout OOS-symbol verdict — 2026-07-03

## Verdict

NO-GO for canary/live in the current form.

The focused candidate on `DOGEUSDT,XRPUSDT,ONDOUSDT` looked strong, but the
main registered risk was symbol selection after analysis. The independent
OOS-symbol gate was run with the same variants/geometry on a fresh non-selected
symbol set:

`BTCUSDT,SOLUSDT,LINKUSDT,ADAUSDT,AVAXUSDT,DOTUSDT,SUIUSDT,LTCUSDT,ATOMUSDT,BNBUSDT,BCHUSDT,XLMUSDT,1000PEPEUSDT,HYPEUSDT,TAOUSDT`

## Result

| variant | trades | netR | PF | WR | symbols+ | years+ | months+ | worst month |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| failed_breakout_short | 132 | -15.48 | 0.83 | 37.1% | 8/15 | 1/2 | 5/13 | -7.46R |
| failed_breakout_volfade_short | 112 | -11.62 | 0.85 | 38.4% | 7/15 | 1/2 | 8/13 | -8.87R |

Selected-symbol headline for context:

| variant | symbols | trades | netR | PF |
|---|---|---:|---:|---:|
| failed_breakout_short | DOGE/XRP/ONDO | 73 | +25.87 | 1.65 |
| failed_breakout_volfade_short | DOGE/XRP/ONDO | 60 | +18.92 | 1.57 |

The OOS-symbol gate directly invalidates promotion. The focused result was
selection-inflated.

## Interpretation

- The failed-breakout idea is not dead, but the current `DOGE/XRP/ONDO`
  focused candidate is not robust enough for risk.
- This should not be enabled as a second live sleeve now.
- Do not use `level_entry` for this setup; earlier broad diagnostics showed it
  harmed reclaim-entry failed-breakout logic.
- If revisited, it needs a symbol-agnostic dynamic scanner/gate based on market
  conditions, not a hand-picked symbol list.

## Next action

Move ARF2 failed-breakout from “canary candidate” back to research:

1. Add regime split: bear/chop vs bull/chop vs trend.
2. Add failed-breakout quality score: reclaim speed, rejection distance, volume
   fade, distance to higher-timeframe resistance.
3. Re-run preflight on broad symbols before any expensive OOS.
4. Only if broad OOS-symbol expectancy turns positive again, reconsider shadow.

## Evidence

- `reports/research/arf2_failed_breakout_oos_symbols_20260703/summary.md`
- `reports/research/arf2_failed_breakout_oos_symbols_20260703/analysis/summary.md`
- `reports/research/arf2_failed_breakout_focused_20260703/summary.md`
- `reports/research/arf2_failed_breakout_focused_20260703/analysis/summary.md`
