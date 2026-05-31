# Codex Hotfix — 2026-05-27 — Sweep Configs Repaired

**Opus repaired three sweep configs that were broken in the 2026-05-26 session.**
Codex can now run Block 1 of `CODEX_HANDOFF_2026_05_26_v3.md` as written.

---

## What was broken

The previous Claude session created three sweep configs with the **wrong JSON schema** — they wouldn't parse:

| File | Bug 1 | Bug 2 | Bug 3 |
|---|---|---|---|
| `package_att1_rsi_relax_v1.json` | `"grid": [...]` (list) | `"pass_criteria"` (wrong key) | no `score_weights` |
| `package_bear_brc1_v1.json` | `"grid": [...]` | `"pass_criteria"` | no `score_weights` |
| `package_bull_asc1_longs_v1.json` | `"grid": [...]` | `"pass_criteria"` | no `score_weights` |

`scripts/run_strategy_autoresearch.py::_iter_grid` expects `grid: Dict[str, list]` and reads `constraints` + `score_weights`. Running any of the three above would crash on the very first call with `AttributeError: 'list' object has no attribute 'keys'` and produce zero candidates.

Two other configs (`package_asb1_slope_break_v1.json`, `package_elder_ema_v1.json`) had the correct grid shape but were missing `score_weights`, so ranking would have been trivial; combo counts in their descriptions were also wrong (54 vs actual 108).

---

## What Opus changed

For all five files:

- `grid` is now `Dict[str, list[str]]` (correct shape)
- `pass_criteria` renamed to `constraints` with runner-recognized keys: `min_trades`, `min_profit_factor`, `max_drawdown`, `min_net_pnl`, `max_negative_months`, `max_negative_streak`
- `score_weights` block added (same shape as `arf1_filter_v1.json`)
- For `package_bear_brc1_v1.json`: added `ENABLE_BRC1_TRADING=1`, `BRC1_RISK_MULT=0.08`, `BRC1_MAX_OPEN_TRADES=1` to `base_env` for clarity (backtest uses `--strategies` CLI but explicit env helps diagnostics)
- Corrected combo counts in ASB1 and Elder descriptions (54 → 108)
- Added `_notes.fix_history` to each file

**No params, no symbol allowlists, no grid values were changed.** The predecessor's intent is preserved; only the schema is fixed.

---

## Verified combo counts (Opus, 2026-05-27)

| Sweep | Combos | Description |
|---|---|---|
| `package_att1_rsi_relax_v1.json` | 36 | 4 × 3 × 3 |
| `package_bear_brc1_v1.json` | 81 | 3 × 3 × 3 × 3 |
| `package_bull_asc1_longs_v1.json` | 27 | 1 × 3 × 3 × 3 |
| `package_asb1_slope_break_v1.json` | 108 | 3 × 3 × 3 × 2 × 2 |
| `package_elder_ema_v1.json` | 108 | 3 × 2 × 2 × 3 × 3 × 1 |
| **Total queue** | **360** |  |

Smoke-test (Opus, 2026-05-27): all five configs parse cleanly through `_load_spec`, `_iter_grid`, `_grid_size`, `_command_context`, `_score_candidate`. Command templates resolve fully (no `{}` placeholders left). Empty-summary candidate correctly fails with `trades<N;net<0.0` reason.

---

## What you need to do (no changes from the original handoff)

```bash
# Block 0 first (regime reset, web restart, cron) — unchanged
python3 scripts/reset_regime_neutral.py
supervisorctl restart web
# crontab as per CODEX_HANDOFF_2026_05_26_v3.md

# Block 1 sweeps — run sequentially, check ranked_results.csv after each
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_att1_rsi_relax_v1.json
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_bear_brc1_v1.json
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_bull_asc1_longs_v1.json
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_asb1_slope_break_v1.json
.venv/bin/python3 scripts/run_strategy_autoresearch.py --spec configs/autoresearch/package_elder_ema_v1.json
```

Note the runner spec flag is `--spec <path>`, not a positional arg as written in some handoff snippets.

Acceptance gate unchanged: `PF > 1.591 AND DD <= 7.0 AND trades >= 50 (or 40/60 per file).`

---

## Related Opus deliverable

Full audit + 4-phase roadmap to self-sufficient / self-healing / self-improving trading system: see `OPUS_AUDIT_2026_05_27.md`.
