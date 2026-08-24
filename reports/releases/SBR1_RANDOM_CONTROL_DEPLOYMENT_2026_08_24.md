# SBR1 pre-first-admitted random-control deployment — 2026-08-24

**Authority:** public-data zero-risk shadow only. No broker, private API, order,
money or promotion authority.

## Deployment truth

- source commit: `2be11c2`;
- live root: `/opt/bybot-research/sbr1-zero-risk-shadow`;
- atomic rollback directory:
  `/opt/bybot-research/sbr1-zero-risk-shadow-backup-20260824T1301Z`;
- preregistration SHA-256:
  `dffa60b17b785b9182560b1bace7105eef9d715488866dd665df77825cac7b68`;
- enabled configuration SHA-256:
  `c671ed76d4c50596d24809aeac58715bbab26aee91e066675abab06f240677a5`;
- source-closure SHA-256:
  `6b2a64cc1b2ccb7830b56db4e9ae76628407e384cdaab743c751a3dc8f4daa10`.

Installed source SHA-256 values:

| file | SHA-256 |
|---|---|
| `bot/sbr1_zero_risk_shadow.py` | `8ab8524441e47b1df2535cbe6f02248d5af531f9934dc33ac94d2273eeb559af` |
| `bot/sbr1_shadow_random_control.py` | `6aa96cbb4e696a012c2e5ab91b1dcdc952a99c890fda0ba2f6136a7a91cfab1e` |
| `scripts/run_sbr1_zero_risk_shadow.py` | `5ebc2fa9e6f5fb42e1d0065ab9722f2d7790ddf4364ea81e35f83571a29ec75c` |
| installed systemd timer | `98d3d4e1af5216bb38e22f605c449b3976bbb64ff4c6015dea8858f017900d02` |

The timer runs every five minutes at second `20` and once more at minute
`03:20` inside the same 300-second decision window. A single public-data error
is isolated per symbol and can be retried without converting the whole cycle
into a false no-signal result.

## Post-deployment receipts

The `13:05:45 UTC` and `13:10:21 UTC` cycles both completed with
`ZERO_RISK_SHADOW_OK`, `orders_created_or_changed=0`,
`private_api_calls=false`, `broker_calls=false`, `decisions_admitted=0` and
`control_assignments_written=0`. The main journal remained at 54 events with
tip
`176f9e6d96efc2e3179cd800ce5c16de99b589aa7416bd8c165e0824df55fb0b`.

No control row exists yet because no SBR1 decision has been admitted after the
precommit. When the first decision is admitted, its deterministic assignments
must be persisted before the main evaluation. Absence before that event is the
correct state, not missing evidence.

The currently deployed universe is the major-8 smoke universe. The
preregistered evidence target is fixed-51 and the money universe remains
major-8. Fixed-51 does not become valid evidence until its own public-data
coverage and live-native parity receipt pass.

## Rollback

Stop the timer, atomically restore the named backup directory, restore the
previous unit files, run `daemon-reload`, and re-enable the prior timer. No
broker rollback is required because this deployment has no execution surface.
