# Alpaca regime + exit repair

Date: 2026-07-28  
Verdict: `NO_GO_THIS_REGIME_REPAIR`

Adding causal SMA slope or SMA50/SMA200 confirmation did not remove the small
2022 loss.  At the stressed 10 bps/side contract:

- baseline SMA200: `-0.51%` in 2022, `+53.52%` recent;
- SMA200 rising 20 sessions: `-0.51%`, `+54.28%`;
- SMA50 above SMA200: `-1.16%`, `+54.28%`.

The only losing 2022 cohort opened after the January month-end, when the
available trend state was still permissive; eliminating it would require
hindsight or a genuinely new causal feature such as volatility/breadth, not
another SMA rearrangement.

No arm passed the preregistered two-window gate.  We stop this tuning branch
instead of optimizing away one known month.  The retained direction is:

1. current selector and SPY defence;
2. monthly-horizon holding;
3. a separately preregistered distant broker catastrophe stop;
4. Massive PIT universe and untouched replay before any canary.
