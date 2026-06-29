# CODEX HANDOFF — 2026-06-29

Branch: `codex/dynamic-symbol-filters`. Stage only explicit paths; the worktree
still contains many old untracked docs/scripts and generated proof-of-life files.

## What changed today

Pushed commits:

- `639339b` — `bot/strategy_breaker.py`, `bot/market_context.py`, ATT1/Alpaca docs.
- `0b67a19` — corrected ATT1 strong short-only + ARS1 additivity research spec.
- `0f7aff0` — wired ATT1 canary breaker into `smart_pump_reversal_bot.py`.
- `c74abad` — isolated ATT1 canary env from other sleeves.
- `93ab864` — added explicit operator live override layer loaded after
  `runtime/strategy_pause.env`.

Server deploy status:

- Code through `93ab864` copied to `/root/by-bot`.
- `bybot.service` restarted with current env only; no ATT1 risk was enabled.
- Server checks passed:
  - `python -m py_compile smart_pump_reversal_bot.py`
  - `pytest tests/test_strategy_pause_contract.py`
- Live heartbeat after restart: `open_trades=0`, `trade_on=true`, `dry_run=false`,
  regime `bear_chop`.

## ATT1 short-only canary

Execution-accurate evidence:

- `att1_short_only_exact_local_20260629`: 296 trades, net `+28.17R`, PF `1.402`,
  WR `59.1%`, max DD `6.59`, red months `2`, max red streak `1`.
- Strong bidirectional revalidate r005: 457 trades, net `+37.35R`, PF `1.325`.
- Short side is the main edge; long side is for a later bull-regime package.

Important runtime fact:

- `runtime/strategy_pause.env` currently contains `ATT1_RISK_MULT=0.0` because
  the live-vs-backtest monitor marked old `att1_trendline_touch` performance as
  degraded.
- Therefore the canary must be enabled through the new explicit operator override,
  not by editing/deleting `strategy_pause.env`.

Canary file:

- `configs/att1_short_canary_20260629.env`
- Sets `ENABLE_ATT1_TRADING=1`, `ATT1_RISK_MULT=0.10`, `ATT1_ALLOW_LONGS=0`,
  `ATT1_ALLOW_SHORTS=1`, `MAX_POSITIONS=3`, `ATT1_MAX_OPEN_TRADES=3`.
- Pauses other price sleeves for clean attribution: `FLAT_RISK_MULT=0.0`,
  `RANGE_RISK_MULT=0.0`, `BREAKDOWN_RISK_MULT=0.0`, etc.
- Arms breaker: `ATT1_BREAKER_ENABLE=1`,
  `ATT1_BREAKER_STRATEGY_NAME=att1_trendline_touch`, soft/hard PnL gates,
  consecutive-loss gate, expiry `2026-07-20`.

Dry env simulation on server confirmed:

- without operator override: `ATT1_RISK_MULT=0.0`, `FLAT_RISK_MULT=0.30`;
- with canary override: `ATT1_RISK_MULT=0.10`, `FLAT_RISK_MULT=0.0`,
  breaker enabled.

To enable canary only after owner OK:

```bash
cd /root/by-bot
printf '\nALLOW_OPERATOR_LIVE_OVERRIDES=1\nOPERATOR_LIVE_OVERRIDE_ENV=configs/att1_short_canary_20260629.env\n' >> .env
systemctl restart bybot.service
```

Then confirm in `runtime/bot_heartbeat.json` /
`runtime/runtime_diagnostics.json`:

- `strategy_runtime_config.operator_live_override.loaded=true`;
- `risk_mult.att1=0.10`;
- `risk_mult.flat=0.0`, `risk_mult.range=0.0`, `risk_mult.breakdown=0.0`;
- `strategy_runtime_config.breaker.att1.enabled=true`;
- `open_trades=0` before enabling is preferred.

Rollback:

- remove/comment the two operator override lines from `.env`;
- `systemctl restart bybot.service`.

## Research queue / server

Currently running:

- `screen arf2_structured_20260629`
- spec: `configs/autoresearch/arf2_structured_resistance_fade_20260628.json`
- progress observed: rows 1–4/192 completed, all FAIL so far.
  - r001/r003 were profitable PF~1.7 but failed monthly stability
    (`neg_months>3;neg_streak>2`).

Corrected ATT1+ARS1 package:

- `configs/autoresearch/package_att1_strong_short_ars1_additivity_20260629.json`
- It replaces the invalid old `package_att1_short_ars1_additivity_20260628`,
  whose control rows used a weak ATT1 baseline.
- Let ARF2 finish or pause it before launching this on the 1GB VPS.

SpikeFadeV3:

- `spike_fade_v3_link_short_bounded_20260627` best r008:
  32 trades, net `+5.10`, PF `1.987`, WR `59.4%`, DD `1.27`.
- Candidate/diversifier only; low frequency, not first engine.

## Alpaca

Status:

- Candidate remains monthly v38 hybrid top4.
- Evidence in `reports/ALPACA_500_LIVE_GO_NOGO_2026_06_29.md`: about `22–23%`
  annualized in research, small sample, suitable for a $500 pipeline canary.
- Server has paper configs only. No committed live profile was found, which is
  correct for secrets.
- Latest monthly refresh files are from `2026-06-26T12:32:15Z`; daily refresh cron
  is scheduled at `12:30 UTC` Mon–Fri.
- US market open on 2026-06-29 is `13:30 UTC` / `16:30 Asia/Nicosia`.

For live $500:

1. Owner must create server-only `configs/alpaca_live_v38.env` with real keys.
2. First run must be `ALPACA_SEND_ORDERS=0` dry-run against the live account.
3. Guard self-test should fail closed if confirm vars are missing.
4. Only after owner confirms real account/buying power/open orders, set
   `ALPACA_SEND_ORDERS=1` after market open.

Do not place Alpaca live orders from Codex without explicit owner confirmation.

## Next practical steps

1. Ask owner for explicit OK before enabling ATT1 crypto canary.
2. If OK: apply operator override, restart, verify heartbeat, then monitor signals
   and first closes.
3. At/after `12:30 UTC`, verify Alpaca daily refresh; after `13:30 UTC`, run live
   dry-run if owner supplied real env.
4. Continue ARF2 research; if no PASS after full sweep, keep ARF2 research-only and
   launch corrected ATT1+ARS1 additivity.
5. Build owner volume-inflow layer from `reports/OWNER_STRATEGY_SPEC_2026_06_25.md`.
