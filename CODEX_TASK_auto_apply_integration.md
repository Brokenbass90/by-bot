# Codex Task: Wire auto_apply_params.env into live bot loading

## Context

`scripts/auto_apply_research_winner.py` (new module) generates
`configs/auto_apply_params.env` with the best autoresearch-validated parameters.
This file needs to be loaded by the bot so params take effect without restart.

## Tasks

### Task 1: Load auto_apply_params.env at bot startup

In `smart_pump_reversal_bot.py` (or wherever `.env` files are loaded at startup),
add loading of `configs/auto_apply_params.env` **after** the main `.env` and canary
config — so auto-applied params override the base config:

```python
# Existing loading (approximate, adjust to actual code):
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "configs" / "core3_live_canary_20260410.env", override=True)

# ADD THIS:
_auto_apply = ROOT / "configs" / "auto_apply_params.env"
if _auto_apply.exists():
    load_dotenv(_auto_apply, override=True)
```

The file may not exist on a fresh deploy — that's OK, skip gracefully.

### Task 2: Add auto_apply_params.env to AllowlistWatcher hot-reload

The AllowlistWatcher currently watches `configs/dynamic_allowlist_latest.env`.
Extend it to also watch `configs/auto_apply_params.env`:

Find the AllowlistWatcher class (likely in `bot/allowlist_watcher.py` or similar).
It should call `load_dotenv` on `auto_apply_params.env` on every reload cycle,
same as it does for `dynamic_allowlist_latest.env`.

### Task 3: Add --dry-run smoke test to setup_server_crons validation

After installing crons, run:
```bash
python3 scripts/auto_apply_research_winner.py --dry-run
```
and confirm it exits cleanly.

### Task 4: Add auto_apply_params.env to .gitignore

This file is machine-generated. Add to `.gitignore`:
```
configs/auto_apply_params.env
runtime/auto_apply_log.jsonl
runtime/auto_apply_current_params.json
```

## Definition of Done

- `auto_apply_params.env` params are visible in bot's os.environ after startup
- AllowlistWatcher hot-reloads them without restart
- Dry-run exits 0
- File added to .gitignore
