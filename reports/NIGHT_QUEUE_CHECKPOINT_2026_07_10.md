# Night Queue Checkpoint — 2026-07-10

## Decision first

- Do not enable a second or third live-money crypto sleeve tonight.
- Git and VPS are not the same thing: local/origin is `0d9443b`; VPS checkout is still `f7ed011`, ten commits behind, with a dirty worktree and selected P0 files deployed manually.
- Bybit is flat at the exchange and only ATT1 has positive money risk (`0.10`).
- Alpaca real account remains safe-hold with four positions and broker stops `4/4`.
- Fresh research improved truth but did not produce a promotable crypto or FX sleeve.

## Fresh Alpaca data

An isolated research cache was refreshed successfully for all `59/59` equity and benchmark symbols through 2026-07-10. No broker API, picks publish or live runtime was touched.

- shifted 24-month top4: `31` trades, PF `7.2864`, WR `83.87%`, compounded `+58.0781%`, max monthly DD `-3.856%`;
- correct forward evaluation must include the April signal month for May entries;
- April signal -> May execution: `TXN +10.586%`, `SBUX -4.764%`, portfolio compounded `+6.38%`, PF `2.2222`;
- this is positive but only `N=2`, so it does not authorize scale or re-enable daily rotation.

## Crypto sleeve readiness

### ATT1

Current live remains unchanged. The `R2 >= 0.80` challenger improved the ordinary run but failed adverse costs (`PF 1.078`, `1/4` positive folds). It is execution research, not a replacement.

### Level-memory short

The prior attractive unseen-symbol holdout did not persist on a clean fresh period. Frozen Apr-30..Jul-05 forward after warm-up:

- `17` trades, `-4.2035R`, PF `0.6171`, WR `35.3%`;
- stress `-5.4223R`, PF `0.5414`;
- clean BTC/ETH/DOT holdout `8` trades, PF `0.9032`;
- verdict `NO_PROMOTION`.

The initial fresh run was stopped before interpretation because five symbols shared a 3.6-day M5 data gap. The reported verdict uses only the clean universe.

### InPlay maker

The frozen long/short decomposition completed without any order path:

- long-only: `23` stress trades, `+3.31R`, PF `1.298`, `3/4` positive folds, but concentration `51.1%`; verdict `FAIL`;
- short-only: `67` stress trades, `+10.15R`, PF `1.410`, `3/4` positive folds, unfilled `35.0%`, but concentration `36.4%` versus the frozen `<35%` limit; verdict `FAIL`.

The short side is the closest second-sleeve hypothesis, but a near-threshold failure is still a failure. A post-run data preflight also found a shared `1,033`-bar M5 gap in ADA/SUI, while the original runner accounted cross-symbol portfolio occupancy by candle index instead of timestamp. The side-split metrics are therefore not promotion evidence. Short may advance only to a clean, timestamp-synchronised, fixed-parameter independent-symbol additivity test at risk zero; long-only is frozen pending a new event-expansion contract.

That single follow-up was pre-registered, before outcomes, in `configs/research/inplay_short_independent_additivity_20260710.json` and executed from pushed Git head `3836378`. The independent BTC/ETH/BNB/XRP/AVAX universe had identical M5 timestamps, coverage `0.998852`, zero internal gaps, and no overlap with the five development symbols. The frozen result is `NO_PROMOTION`:

- stress full: `42` trades, `+1.4389R`, PF `1.075`, WR `45.2%`, unfilled `14.3%`;
- chronological folds: `3/4` positive, but fold 2 PF `0.569` and `-3.2846R`;
- final 90-day holdout: `16` trades, `+2.0344R`, PF `1.286`;
- only ETH and AVAX produced trades (`2/5` breadth), only ETH was positive (`1/5`), and gross-profit concentration was `67.7%` versus the frozen `<35%` limit.

The positive recent holdout is useful for successor design, but the edge does not transfer broadly enough for shadow or money. Do not weaken the gates and do not retune the old maker grid.

## FX/CFD fresh gate

Fresh Dukascopy M5 was aggregated to `12,341` USDJPY H1 bars through 2026-07-06; coverage `0.988625` passed. Long and short were independent, with chronological 50/25/25 splits and base/stress costs.

- standard `00/50` short: `190` trades, PF `0.963`; stress PF `0.789`; validation and holdout negative;
- `1 JPY` big-figure short: full PF `1.349`, but validation negative and stress holdout PF `0.764`;
- legacy `10 JPY` short: PF `2.306` on only `12` already-selected trades, so it is contaminated historical control, not OOS evidence;
- independent EURJPY/GBPJPY additivity failed: big-figure short stress PF `0.573` and `0.450`, with both validation and holdout deeply negative;
- verdict `NO_PROMOTION` for FX demo/live.

XAUUSD needs schedule-aware CFD coverage before another serious gate. No FX process or capital is active.

## Operational truth

- web service active, `/ping` healthy, one configured user; end-to-end password/TOTP login still requires the owner to retry;
- web JWT secret remains weak/default-like and must be rotated;
- VPS idempotent Alpaca ledger from `23f9446` is not deployed pending corrupt-history reconstruction;
- Alpaca paper v1 still has accounting/entry-price divergence and one PLTR paper position without a broker stop; do not trust v1 PnL or promote it;
- no blind VPS `git pull`: normalize from a manifest in a flat window.

## Morning continuation

1. Freeze old InPlay maker: both sides and the clean independent short additivity gate are formal FAILs.
2. Write separate event-first successors: exhaustion/unwind short and expansion/retest long, with clean data and timestamp-based portfolio accounting from the start.
3. Reconstruct Alpaca v1 broker-fill ledger, then deploy idempotency safely.
4. Prepare a manifest-based VPS normalization and JWT-secret rotation.
5. Keep all new crypto/FX sleeves at risk zero until their complete gate passes.
