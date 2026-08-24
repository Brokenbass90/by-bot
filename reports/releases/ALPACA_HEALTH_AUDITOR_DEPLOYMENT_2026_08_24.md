# Alpaca deterministic health auditor deployment — 2026-08-24

**Authority:** read-only observation. This release cannot submit, cancel,
replace or close an order and cannot enable entries or promote capital.

## Deployment truth

- source commit: `98d75f1`;
- live root: `/root/by-bot`;
- deployment backup:
  `/root/by-bot/runtime/deploy_backups/alpaca_health_20260824T1258Z/`;
- pre-change crontab backup:
  `/root/by-bot/runtime/cron_backups/crontab_before_alpaca_health_20260824T1259Z.txt`;
- backup crontab SHA-256:
  `bbfc2c95f643bb3c9921f77e3f2e67837fc95c98651eab72aa56536f6825ce78`;
- installed crontab SHA-256 after adding the auditor:
  `d0cc882a4b70468ffd3b18860de0ae0d5e622d757bc7083adcf346a7876eeec2`.

Installed file SHA-256 values:

| file | SHA-256 |
|---|---|
| `scripts/alpaca_health_auditor.py` | `0c81432d365187cdf3c81bc4304124a36b44465c64a36d2ac2edd3b6ecac331b` |
| `scripts/check_alpaca_state_readonly.py` | `0e2fb6980538e1fce9951dd2f8fa86456c3c8246353a2d6615a37af36b7b1860` |
| `scripts/run_alpaca_health_auditor.sh` | `9d57d5c74ecd1c9b79173f714ad07f3ec726d69e0e4894e67108e2b8c6e9410c` |
| `configs/alpaca_health_auditor_v1.json` | `f257351270538224a444606448b6ee4202483967a1b6732268e70fcce6ce238d` |

The live schedule runs at `13:07/22/37/52` through `21:52 UTC` on weekdays,
once at `12:45 UTC` before the session, and every six hours on weekends. It
writes local evidence only; there is no AI or Telegram action in this release.

## First scheduled receipt

At `2026-08-24T13:07:03.538869+00:00` the scheduled audit returned `WARN` with
evidence SHA-256
`840f39bd211ee6190e615660309e75e4d51b70fb31dbd591a8bd1afbcc7cafa7`.

- broker mode: `LIVE`;
- new entries observed: `false`;
- promotion authority: `false`;
- `ABBV`: position/protected quantity `0.135734866`, broker stop and accepted
  floor `257.37`, full coverage, floor preserved;
- `SCHW`: position/protected quantity `0.563776973`, broker stop and accepted
  floor `108.20`, full coverage, floor preserved.

The only warnings were
`fractional_day_stop_not_persistent_across_sessions` for both positions. The
warning is intentional: the broker does not allow these fractional stops to be
GTC and the orders cannot execute outside regular market hours. The monotonic
floor prevents the nightly rearm from returning to entry minus five percent;
it does not eliminate overnight gap/slippage risk.

## Rollback

Restore the four files from the deployment backup and restore the saved
crontab. No order rollback is required because the auditor made no broker
mutation.
