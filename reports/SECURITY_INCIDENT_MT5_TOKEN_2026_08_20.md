# MT5 token incident — 20 August 2026

No secret value is recorded here.

## Facts

- A non-placeholder MT5 MCP token appeared in `signal_copy/config.py` during concurrent local work.
- Commit `5754ced` containing that value reached `origin/codex/dynamic-symbol-filters`.
- The active local branch was rebuilt from the last safe parent. Safe head before this incident note: `4e5558699df60abdd1f39555e97e1f496f3f883f`.
- The safe configuration reads the token only from `SIGCOPY_MT5_TOKEN`, defaults `SIGCOPY_EXECUTION_ENABLE` to `0`, has no default account login, and hard-disables live accounts.

## Required closure

1. Revoke the exposed MT5 MCP token in the terminal/provider UI.
2. Create a new token and store it only in local `.env`/secret storage.
3. With explicit owner authorization, replace the remote branch using `git push --force-with-lease` from the sanitized branch.
4. Verify by fresh clone that the exposed value is absent from all reachable commits.
5. Only then perform GET/read-only demo smoke; do not enable execution in the same step.

Status: `OPEN — ROTATION AND REMOTE HISTORY REWRITE REQUIRED`.
