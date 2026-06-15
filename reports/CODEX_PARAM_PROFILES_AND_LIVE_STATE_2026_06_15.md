# Codex param profiles + live state — 2026-06-15

## What changed

Reviewed and deployed Claude's additive parameter-profile layer:

- `configs/strategy_param_profiles.json`
- `bot/param_profiles.py`
- `tests/test_param_profiles.py`

Also deployed the control-plane comparison primitive:

- `backtest/stack_comparison.py`
- `tests/test_stack_comparison.py`

Codex integration added:

- `backtest/auto_pick_wf.py --use-param-profiles`
- `tests/test_operator_console_api.py` now skips cleanly when optional web deps (`fastapi`, `pyotp`) are absent.

No live trading config was changed.

## Test status

Local:

- Targeted: `15 passed`
- Full suite: `255 passed`

Server:

- `tests/test_param_profiles.py`: `4 passed`
- `tests/test_stack_comparison.py tests/test_param_profiles.py`: `8 passed`

## Server WF with tier profiles

Command:

```bash
PYTHONPATH=. .venv/bin/python3 backtest/auto_pick_wf.py \
  --top-k 8 --signal-tf 60 --regime-tf 240 --windows 4 --fee-bps 10 \
  --use-param-profiles \
  --output-json reports/AUTO_PICK_WF_TOP8_60_240_param_profiles_latest.json
```

Result: no strategy/coin pair passed the majority-positive gate.

ASB1 profiles applied as intended:

- micro coins such as `PIXELUSDT`, `FLOWUSDT`, `SAFEUSDT`, `SIGNUSDT` used `ASB1_SL_ATR_MULT=1.10`, `ASB1_TIME_STOP_BARS_5M=432`, `ASB1_TP1_FRAC=0.65`.

But the A/B did not prove an edge:

| strategy | coin | result |
|---|---|---|
| ASB1 | SAFEUSDT | one positive traded window only (`+2.95R`) -> insufficient |
| ASB1 | SIGNUSDT | `1/3` positive windows -> weak |
| ARF1 | XAGUSDT | `1/2` positive windows -> weak |
| ARF1 | BCHUSDT | `1/2` positive windows -> weak |
| ARF1 | LTCUSDT | `1/4` positive windows -> weak |

Verdict: tiered params are a useful research mechanism, but they do not justify a live risk increase yet.

## Current live state

Latest server heartbeat:

- `open_trades=0`
- `trade_on=True`
- `dry_run=False`
- `regime=bull_trend`
- `risk_per_trade_pct=0.44`
- `max_positions=3`
- `allocator_global_risk_mult=0.8`
- `orch_global_risk_mult=0.55`
- feed is alive (`bybit_msgs` > 3.8M)

Runtime strategy risk:

| sleeve | enabled | live risk_mult |
|---|---:|---:|
| flat / ARF1 | true | 0.3 |
| IVB1 | true | 0.25 |
| ATT1 | true | 0.0 |
| BOUNCE1 / ASB1-style | true | 0.0 |
| BREAKDOWN | true | 0.0 |
| MIDTERM | true | 0.0 |
| HZBO1 | false | 0.0 |
| ELDER | false | effectively off |

`runtime/strategy_pause.env` confirms:

- `BREAKDOWN_RISK_MULT=0.0` due to degraded live performance.
- `ATT1_RISK_MULT=0.0` due to degraded live performance.

## What we should expect soon

With current risk posture, we should expect:

- bot alive / feed alive / Telegram proof-of-life;
- rare real crypto trades, mostly from `flat` and `ivb1`;
- no ASB1 canary until a multi-window WF candidate passes;
- no daily trade guarantee.

This is correct protection behavior. Silence does not mean dead; it means most sleeves are intentionally shadow/paused.

## Next step

1. Build/refresh missing TF coverage for auto-picked symbols.
2. Re-run `auto_pick_wf.py --use-param-profiles`.
3. Run `stack_comparison` on candidate trade streams to detect whether allocator/regime/slot caps help or hurt.
4. Only if a pocket passes gate (`>=3/4` positive windows, PF>1 after fees, enough trades), promote to tiny canary.

Alpaca remains paper-only until paper/live evidence meets go criteria.
