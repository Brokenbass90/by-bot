# Bybit API credential rotation control plane — 2026-08-06

## Outcome

The owner-submitted Bybit credential rotation is now applied and independently
verified in the live process.

- The web audit recorded the env update at `2026-08-05T12:03:43Z`.
- Before intervention, `.env` and the running bot had different one-way key
  fingerprints: the web form had stored the new credential, while the bot still
  held the old credential in memory.
- The candidate credential passed Bybit `query-api` and position-list checks.
- The account was directly confirmed flat before restart.
- `bybot.service` was restarted at approximately `2026-08-06T08:50:58Z`.
- The restarted bot published a fresh heartbeat and `main: auth OK`, with equity
  approximately `1020.69 USDT`, `trade_on=true`, `dry_run=false`, and no open
  positions.
- The safe runtime receipt is
  `runtime/bybit_credential_rotation_status.json` with
  `status=applied_verified` and `need_restart=false`.

No live risk, ATT1 signal parameters, strategy universe, positions, orders, or
capital allocation were changed.

## Root cause

The old web workflow performed only two actions: it backed up `.env` and wrote
new values into `BYBIT_ACCOUNTS_JSON`. It returned `need_restart=true`, but the
UI did not perform or verify that restart. Consequently, “credentials replaced”
was storage truth, not running-process truth.

## New transaction contract

The replacement flow now:

1. validates the candidate key against Bybit before modifying `.env`;
2. requires `ContractTrade: Order, Position`;
3. refuses keys with any Wallet/transfer/withdraw permission;
4. queries live USDT linear positions with the candidate key;
5. creates a private backup and atomically replaces exactly one account;
6. restarts automatically only when the account is flat;
7. requires a fresh bot heartbeat and fresh `auth OK` after the env write;
8. rolls back the env and restarts the old configuration if apply verification
   fails;
9. writes only redacted metadata and a one-way credential fingerprint;
10. feeds the receipt to both the API Keys web page and onboard AI context.

The interactive fallback is:

```bash
cd /root/by-bot
.venv/bin/python scripts/rotate_bybit_credentials.py --account main
```

Secrets are requested through hidden interactive input and never passed in
command-line arguments.

## Current key security posture

- Expiry: `2026-11-06T08:43:37Z`.
- Required contract permissions: present.
- Wallet/withdraw permissions: absent.
- IP restriction: absent (`ANY IP`).
- Additional enabled scopes: Derivatives, Options, Spot.

Recommended owner-side hardening for the next key: bind it to the VPS public IP
and keep only the minimum contract permissions needed by the bot. This is not a
runtime blocker today because withdrawal permission is absent, but it reduces
the blast radius of credential theft.

## Deployment truth

This was a targeted live deploy because the server repository remains behind
the development branch and has unrelated server-side modifications.

- Existing live versions were backed up under
  `state/deploy_backups/api_rotation_20260806/`.
- Server-modified web/index and AI-context files were merged rather than
  overwritten.
- Only `trading-journal-web.service` was restarted after the control-plane
  deployment.
- `bybot.service` remained active after the already completed credential apply.
- Post-deploy `/ping`, direct Bybit position query, bot service state, and safe
  rotation receipt all passed.

