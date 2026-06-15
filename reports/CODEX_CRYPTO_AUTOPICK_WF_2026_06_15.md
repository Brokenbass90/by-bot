# Codex crypto auto-pick WF — 2026-06-15

## What was tested

Goal: answer whether crypto can move toward first live-income canary by using automatic coin selection, not hand-picked SOL.

Deployed/read-only server tools:

- `scripts/strategy_coin_picks.py` — ranks coins per strategy via existing `scripts.strategy_scorer.score_for_strategy`.
- `backtest/crypto_multiwindow_wf.py` — anti-overfit multi-window WF with runner ladder + fees.
- `backtest/auto_pick_wf.py` — runs multi-strategy WF on auto-picked coins.

Important harness fix before server verdict:

- If 4h `240` cache is missing, `crypto_multiwindow_wf.py` now derives 4h bars from 1h `60` bars using timestamp-aligned aggregation.
- Time-stop remainder now pays closing fee.
- Majority gate is strict: 4 windows require 3 positive traded windows, not 2.

## Server auto-picks

Server scorer had 361 symbols with 1h data.

Top picks:

| strategy | top server picks |
|---|---|
| ASB1 | PIXEL, FLOW, SAFE, BERA, LPT, SIGN, GWEI, HMSTR |
| ARF1 | XAG, WIF, 4, CHIP, AAVE, BCH, LTC, SNDK |
| BREAKDOWN | STO, 1000TAG, BANK, PLAYSOUT, USELESS, KERNEL, HEI, DRIFT |

Meaning: automatic coin selection exists and works as a current-state fit ranker. It is not a profitability proof by itself.

## SOL verdict

Command:

```bash
PYTHONPATH=. .venv/bin/python3 backtest/crypto_multiwindow_wf.py --symbol SOLUSDT --signal-tf 60 --regime-tf 240 --windows 4 --fee-bps 10
```

Result:

| window | expectancy | PF | trades |
|---:|---:|---:|---:|
| 1 | -1.08R | 0.00 | 1 |
| 2 | +1.17R | 4.11 | 3 |
| 3 | -1.20R | 0.00 | 1 |
| 4 | -1.13R | 0.00 | 2 |

Verdict: `1/4` positive traded windows → `WEAK`. Do not promote ASB1/SOL to canary.

Diagnostic on old fast-TF pocket:

```bash
PYTHONPATH=. .venv/bin/python3 backtest/crypto_multiwindow_wf.py --symbol SOLUSDT --signal-tf 5 --regime-tf 60 --windows 4 --fee-bps 10
```

Result: only last window had trades: `+0.71R`, PF `2.08`, `n=10`; other windows `n=0`. Verdict: insufficient traded windows. The earlier positive SOL smoke was a single pocket, not a robust multi-window edge.

## Auto-pick WF verdict

Command:

```bash
PYTHONPATH=. .venv/bin/python3 backtest/auto_pick_wf.py --top-k 8 --signal-tf 60 --regime-tf 240 --windows 4 --fee-bps 10
```

No strategy/coin pair passed majority-positive gate.

Notable pockets that still failed:

| strategy | coin | windows positive | windows with trades | edges |
|---|---|---:|---:|---|
| ASB1 | SAFEUSDT | 1 | 1 | +3.40R |
| ASB1 | SIGNUSDT | 1 | 3 | +1.42R, -1.05R, -1.05R |
| ARF1 | XAGUSDT | 1 | 2 | +0.61R, -1.21R |
| ARF1 | BCHUSDT | 1 | 2 | +0.80R, -0.09R |
| ARF1 | LTCUSDT | 1 | 4 | +0.74R, -1.18R, -1.16R, -1.18R |

Verdict: no crypto risk increase from this run. The gate is doing its job.

## Data coverage finding

Auto-picked coins mostly have 1h data but not 5m or native 4h cache. The harness can derive 4h from 1h, but more frequent strategies need 5m history for the selected symbols.

Examples from server coverage:

| strategy | coin | 5m files | 1h files | 4h files |
|---|---|---:|---:|---:|
| ASB1 | PIXELUSDT | 0 | 11 | 0 |
| ASB1 | SIGNUSDT | 0 | 14 | 0 |
| ARF1 | XAGUSDT | 0 | 77 | 0 |
| ARF1 | BCHUSDT | 4 | 104 | 0 |
| ARF1 | LTCUSDT | 52 | 111 | 0 |
| BREAKDOWN | STOUSDT | 0 | 16 | 0 |

## Decision

- Alpaca: keep paper only.
- Crypto: keep current live risk posture; do not increase ASB1/SOL or auto-picked package risk yet.
- Automatic coin selection is a ranking layer, not a proof layer. The proof layer is now `auto_pick_wf`.

## Next engineering step

1. Build/refresh data coverage for top auto-picked symbols on required TFs:
   - 1h/4h for ASB1 and ARF1;
   - 5m/1h for BREAKDOWN and faster diagnostics.
2. Re-run `auto_pick_wf.py` after coverage refresh.
3. If still no pass, do not tune risk upward; instead:
   - loosen/repair entry logic only through A/B WF;
   - add new strategy candidates one by one;
   - focus on pockets with at least 3 positive windows out of 4 and enough trades.

Canary gate remains:

- majority positive windows with trades;
- PF > 1 after fees;
- no single-window-only wins;
- then tiny canary on current ~$100 account, not full capital.
