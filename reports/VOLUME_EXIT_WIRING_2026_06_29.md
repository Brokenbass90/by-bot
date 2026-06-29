# Volume-fade exit — wired into backtest engine + real-data validation (2026-06-29)

Author: Claude (central). Recheck/deploy + full WF: Codex (server, no resource cap).

## What was done
- `bot/volume_exit.py` — volume-fade early exit (owner setup A "ключевая деталь":
  exit the runner when the impulse's volume dies before reaching target).
  Now with an **impulse gate** (added after real-data testing, see below).
  Unit tests: `tests/test_volume_exit.py` — 11/11 green.
- Wired into `backtest/portfolio_engine.py` exit loop, **additive, default OFF**,
  flag-gated by `VOLUME_EXIT_ENABLE=1`. Closes the remaining qty at bar close with
  reason `VOL_FADE`. Engine still parses + runs (verified by smoke backtest).

## Env flags (backtest + later live)
```
VOLUME_EXIT_ENABLE=1            # off by default
VOLUME_EXIT_STRATEGIES=inplay   # csv substring filter; empty = all
VOLUME_EXIT_BASELINE_WINDOW=20  # run-up volume window
VOLUME_EXIT_IMPULSE_WINDOW=3    # recent (impulse) window
VOLUME_EXIT_FADE_RATIO=0.70     # recent/baseline below this = fading
VOLUME_EXIT_PEAK_FADE_RATIO=0.45# recent/peak below this = exhausted
VOLUME_EXIT_REQUIRE_STALL=1     # also require price stall (no new high/low)
# (module also has min_impulse_mult=2.0: only act if a real thrust happened)
```

## Real-data finding (why the impulse gate exists)
Ran `volume_fade_exit` across real LINK & SOL 5m caches (~30d each). First version
fired on ~39% of bars — it was exiting in flat chop, because in chop recent volume
trivially dips below the (also-low) run-up while price "stalls". That's wrong: the
owner's rule is to exit a **dying impulse**, not to exit chop.

Fix: added an **impulse gate** — only arm the fade-exit if a genuine volume thrust
happened (peak_vol ≥ `min_impulse_mult` × baseline). After the gate, fire rate
dropped to ~24% of all bars. Note: across-all-bars is NOT the operating metric —
in a backtest the exit is only evaluated while a position is open (a few bars after
an impulse entry, on the runner), so the operational rate is far lower and is the
intended "exit promptly once the impulse fades" behaviour.

## Why the full comparison isn't in this doc
The 1GB sandbox OOM-kills multi-symbol `inplay_retest_v3` backtests (the strategy
recomputes levels per bar — heavy). Only tiny single-symbol smokes complete here.
The fixed-TP vs volume-exit WF comparison should run on the server.

## For Codex — run the comparison (server)
```bash
SYMS=SOLUSDT,LINKUSDT,SUIUSDT,DOGEUSDT,HYPEUSDT,TAOUSDT,1000PEPEUSDT,ADAUSDT
# baseline (fixed TP)
BACKTEST_CACHE_ONLY=1 VOLUME_EXIT_ENABLE=0 python3 backtest/run_portfolio.py \
  --symbols $SYMS --strategies inplay_retest_v3 --days 240 --end 2026-04-05 \
  --tag irv3_base_240 --starting_equity 100 --risk_pct 0.005 --leverage 1 \
  --max_positions 4 --fee_bps 6 --slippage_bps 2 --entry-on-next-open
# volume-fade exit
BACKTEST_CACHE_ONLY=1 VOLUME_EXIT_ENABLE=1 VOLUME_EXIT_STRATEGIES=inplay \
  python3 backtest/run_portfolio.py \
  --symbols $SYMS --strategies inplay_retest_v3 --days 240 --end 2026-04-05 \
  --tag irv3_vol_240 --starting_equity 100 --risk_pct 0.005 --leverage 1 \
  --max_positions 4 --fee_bps 6 --slippage_bps 2 --entry-on-next-open
# compare summary.csv net_pnl / profit_factor / trades / max_drawdown, then WF if vol wins
```
Send me both `summary.csv` (and `trades.csv` if you want a per-trade VOL_FADE
breakdown) and I'll interpret + tune params and take it to the WF gate.

## Note
`portfolio_engine.py` is modified (uncommitted). Commit together with the prior
foundation files (commit still must be done on host — sandbox can't release git's
index.lock).
