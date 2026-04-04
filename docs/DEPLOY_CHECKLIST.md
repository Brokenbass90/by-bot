# Deploy Checklist

## Goal

Roll out the current crypto canary core safely:

- `alt_inplay_breakdown_v1`
- `alt_resistance_fade_v1`

Using:

- [live_candidate_core2_breakdown_arf1_20260404.env](/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/live_candidate_core2_breakdown_arf1_20260404.env)

Do **not** wipe the server blindly. Keep the base server `.env` as the source of secrets and infra defaults, then apply the strategy overlay on top.

## Preconditions

- Server repo path is known.
- Current live positions are flat or manually understood.
- Latest code with TP/SL failsafe is uploaded.
- Overlay file is present on server.

## Safe rollout steps

1. Back up the current server env.

```bash
cd /root/bybit-bot-clean-v28
mkdir -p state/env_backups
cp .env "state/env_backups/.env.pre_core2_$(date -u +%Y%m%d_%H%M%S).bak"
```

2. Upload the new code and overlay.

Recommended files:

- `smart_pump_reversal_bot.py`
- `strategies/alt_inplay_breakdown_v1.py`
- `configs/live_candidate_core2_breakdown_arf1_20260404.env`
- control-plane files if server is behind local:
  - `scripts/build_regime_state.py`
  - `scripts/build_symbol_router.py`
  - `scripts/build_portfolio_allocator.py`
  - `configs/portfolio_allocator_policy.json`
  - `configs/strategy_profile_registry.json`

3. Apply the overlay on top of server `.env`.

```bash
cd /root/bybit-bot-clean-v28
python3 scripts/apply_env_overlay.py \
  --target .env \
  --overlay configs/live_candidate_core2_breakdown_arf1_20260404.env \
  --backup-dir state/env_backups
```

4. Restart the live bot.

If the live bot is managed by the repo screen helper:

```bash
cd /root/bybit-bot-clean-v28
bash scripts/restart_live_bot.sh
```

If the server uses `systemd`, restart the real unit instead.

5. Immediate post-start checks.

Check that only the intended sleeves are enabled:

```bash
cd /root/bybit-bot-clean-v28
grep -E 'ENABLE_(BREAKDOWN|FLAT|BREAKOUT|SLOPED|MIDTERM|PUMP_FADE|BOUNCE|RANGE)' .env
```

Expected:

- `ENABLE_BREAKDOWN_TRADING=1`
- `ENABLE_FLAT_TRADING=1`
- everything else from the old crypto core off

6. Log checks in the first 10 minutes.

Look for:

- successful bot start
- no repeated `TP/SL set FAIL`
- no `FAILSAFE CLOSE` loop
- entries only from:
  - `alt_inplay_breakdown_v1`
  - `alt_resistance_fade_v1`

Example:

```bash
cd /root/bybit-bot-clean-v28
tail -n 200 runtime/live.out
```

7. Risk staging.

Week 1-2:

- keep `ORCH_GLOBAL_RISK_MULT=0.50`

Week 3+ only if live stats are acceptable:

- move to `ORCH_GLOBAL_RISK_MULT=0.70`

Month 2 only if live PF remains healthy:

- consider lifting `BREAKDOWN_RISK_MULT`

## What counts as success

After rollout, success means:

- bot starts cleanly
- no naked positions survive a TP/SL failure
- only `breakdown + ARF1` trade
- no surprise sleeves wake up from the old stack

## Abort / rollback

If anything looks wrong:

1. flatten any open position manually if needed
2. restore the last `.env` backup
3. restart the bot

```bash
cd /root/bybit-bot-clean-v28
cp state/env_backups/<backup_name>.bak .env
bash scripts/restart_live_bot.sh
```

## Notes

- This is a **canary rollout**, not the final adaptive portfolio.
- `breakout`, `ASC1`, `midterm`, `VWAP`, `elder`, and `support_bounce` continue in research / repair tracks.
- Alpaca, forex, and other sleeves stay outside this crypto canary rollout.
