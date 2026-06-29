# Codebase audit & cleanup plan — 2026-06-29

Author: Claude (central). Honest read: the project is **far less "junk" than it feels**.
The mess is mostly artifacts and documents, not broken code.

## Health summary (good news first)
- **Code compiles clean**: 0 syntax-broken files across all 89 strategies + `bot/`.
- **Strategies are disciplined**: of 89, only **1 is truly orphaned** (`att1_v2_live`
  — referenced nowhere). The other 12 "unwired" ones are referenced in scripts/tests
  (planned future arms: pair_stat_arb, smart_grid, basis_arb, funding_hold, RMR1, TPB1…).
- **Secrets are safe**: `.env` is gitignored and not tracked; untracked `.env` files
  are non-secret canary configs.
- **Big caches are gitignored**: `backtest_runs` (1.9G) and `data_cache` (1.2G) are
  local-only — safe to prune without touching git history.
- New foundation code added this session is unit-tested: 27 tests green
  (`strategy_breaker`, `market_context`, alpaca guard/trailing).

## Where the clutter actually is
| Area | Finding | Impact |
|---|---|---|
| Disk | `backtest_runs` 1.9G + `data_cache` 1.2G = ~3.1G local artifacts | wastes space; slows file ops |
| Docs | 84 `.md` in repo root (+106 untracked `.md`), 1.3M | hard to find the current truth |
| Git | 179 untracked files (106 md, 22 py, 22 json, 14 env) | new code/docs uncommitted |
| Dead code | 1 orphaned strategy (`att1_v2_live`) | trivial |
| Tests | venv is macOS-only → unusable in Linux/CI; deps not pinned for sandbox | can't run full suite portably |

## Prioritized plan

### P0 — git hygiene (do first, non-destructive)
- Commit the new tested modules (`bot/strategy_breaker.py`, `bot/market_context.py`,
  their tests, the canary config, the new reports). Right now valuable work is untracked.
- Triage the 22 untracked `.py` and 22 `.json` — commit the keepers, gitignore generated ones.

### P1 — document the truth, archive the rest (needs your OK to move files)
- Keep ~6 canonical entry docs in root (PROJECT_MAP, latest CODEX/CLAUDE handoff,
  EXTERNAL_AUDIT_BRIEF, DEV_PLAN, this audit). Move the other ~78 dated `.md` into
  `docs/archive/YYYY-MM/`. Nothing deleted, just filed.
- Create one `README.md` "start here" index pointing to the canonical docs.

### P2 — reclaim disk (needs your OK; safe because gitignored)
- Prune `backtest_runs`: keep the latest N runs + any referenced by `baselines/` and
  current configs; delete the rest (likely ~1.5G reclaimed).
- `data_cache` (1.2G): regenerable; keep if you run frequent local backtests, else prune.

### P3 — portability / CI
- Pin a `requirements.txt` that installs in a clean Linux venv so the full test suite
  (~280 tests) runs in CI / this sandbox, not just on your Mac.
- Remove the single orphaned `att1_v2_live` (or wire it if intended).

## What I can do safely right now (on your word)
1. Stage + commit the new tested code and reports (P0) — reversible via git.
2. Move the doc sprawl into `docs/archive/` + add a README index (P1) — reversible.
3. Generate an exact prune list for `backtest_runs` for you/Codex to review before
   any deletion (P2) — I will not delete without explicit confirmation.

No deletions have been made. Disk pruning and doc moves wait for your go-ahead.
