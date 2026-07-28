# Crypto expansion — deploy preflight 2026-07-28

Verdict: `TARGETED_DEPLOY_REQUIRED / FULL_PULL_FORBIDDEN`

## Prepared and pushed

- local/origin branch: `codex/dynamic-symbol-filters`;
- prepared head: `f600f2280d921c8dbedde60679ceafbe7a23939d`;
- BOUNCE1 risk-zero shadow lifecycle is implemented;
- BREAKDOWN fail-closed regime capital gate is implemented;
- slope-break and support-bounce env prefixes are isolated;
- independent backtest reproduction is recorded in
  `reports/research/CRYPTO_REGIME_BOOK_INDEPENDENT_AUDIT_2026_07_28.md`;
- non-slow test lane: `1538 passed, 54 deselected`;
- focused shadow/regime/prefix tests: `41 passed`;
- chart/geometry tests: `15 passed`.

## Direct live truth

Checked read-only on `64.226.73.119:/root/by-bot`:

- deployed Git HEAD: `f7ed0116a5f5`;
- `bybot` service: active;
- direct Bybit equity: approximately `1020.01 USDT`;
- direct Bybit open positions: none;
- current overlay: ATT1 enabled, BOUNCE1 disabled, BREAKDOWN disabled;
- live checkout has many tracked and untracked changes.

No live risk, strategy universe, real order or service state was changed.

## Level visualization truth

The live monolith already contains the position-geometry and honest chart
integration even though its Git HEAD predates that work. This is therefore a
dirty/manual deployment, not a reproducible Git receipt.

There are no files yet in `runtime/position_geometry`: no new position has
created a geometry snapshot since the feature was installed. The code path is
locally covered by 15 tests, but live visual confirmation remains pending the
next qualifying entry or an explicit synthetic, broker-free chart smoke test.

## Why a normal pull/restart was not performed

The server checkout is materially dirty. Replacing the monolith or pulling the
whole branch could overwrite unrelated operator/Claude changes and could change
the behavior of the owner-approved ATT1 canary. That would violate the bounded
deployment contract.

## Safe next deployment

Build a targeted package containing only:

1. `bot/strategy_shadow_ledger.py`;
2. `bot/strategy_regime_gate.py`;
3. isolated prefix changes in the two strategy modules;
4. minimal monolith hunks for BOUNCE1 shadow and BREAKDOWN gate;
5. the risk-zero BOUNCE1 env overlay.

Before restart:

- patch a copy of the current server monolith, not the repository baseline;
- run `py_compile` and focused tests against that copy;
- prove the effective ATT1 config/universe/risk hash is unchanged;
- prove BOUNCE1 effective risk is exactly zero;
- prove BREAKDOWN effective risk remains zero;
- back up only the exact files being patched.

After restart:

- verify direct broker positions and protection;
- verify ATT1 owner authorization and effective risk are unchanged;
- verify BOUNCE1 ledger initializes with `broker_calls=false`;
- write a targeted deploy receipt with before/after hashes.

