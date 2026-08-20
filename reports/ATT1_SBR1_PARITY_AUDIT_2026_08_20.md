# ATT1/SBR1 simulation-vs-live parity audit — 2026-08-20

## Technical summary

**Decision: `NO-GO` for live promotion of the ATT1/SBR1 candidates.**

- `ATT1_MAX_STOP_PCT=0.25` restores ATT1 raw signal density on the 137-symbol pre-sealed universe: 4,678 candidate signals versus 4,612 in the current-parameter baseline (`+1.43%`). This proves only that the stop-width validator no longer removes most entries.
- The historical simulator and the proposed live configuration do not create the same trades. The simulator widens the whole precomputed stop and keeps the original targets; the live strategy widens only its ATR component and recomputes targets from the wider risk.
- ATT1 cooldown, the missing BTC H1 EMA200 flat-regime gate, SBR1 partial exits/runner, and SBR1 live wiring introduce additional independent parity failures.
- The reported historical edge is therefore a research hypothesis, not reproducible live evidence. Decision bus, edge monitor, live parameters, risk, and slot limits must remain unchanged until the parity gate below passes.

No sealed-period rows were read. No live API, broker, order, deploy, decision-bus, edge-monitor, or money-authority action was performed.

## Scope and definitions

Audit base: Git `ba83c8bceaf7` plus an unrelated dirty worktree belonging to the user/other agents. Python: `3.13.5` from `.venv`.

The full-universe comparison used all 137 H1 `.npz` files in `research_lab/data/h1`. Every input was filtered by the existing immutable boundary `ts < 1759276800000` before strategy evaluation. `raw signals` means successful `maybe_signal(...)` results of the requested side. `median stop` is `abs(entry - sl) / entry * 100` over those raw signals.

The comparison does **not** measure fills, exchange rounding, portfolio risk gates, slot contention, fees, partial exits, runner outcome, time exits, or PnL. It must not be used as a release gate by itself.

## Raw signal survival passes only after the ATT1 cap repair

| Strategy/configuration | Raw signals | Median stop | Change versus strategy baseline |
|---|---:|---:|---:|
| ATT1 current-parameter baseline | 4,612 | 1.8127% | — |
| ATT1 wide stop, old cap | 1,544 | 4.2532% | −66.52% |
| ATT1 wide stop, `MAX_STOP_PCT=0.25` | 4,678 | 7.8288% | +1.43% |
| SBR1 current-parameter baseline | 2,176 | 2.4260% | — |
| SBR1 proposed parameters | 2,177 | 7.2884% | +0.05% |

Interpretation: the 25% ATT1 cap is necessary for the proposed wider stops, and both proposed configurations satisfy the narrow `≤10% raw-count difference` check. They do not satisfy trade-geometry or outcome parity.

The existing 25-symbol verifier independently produced:

| ATT1 configuration | Raw signals | Median stop |
|---|---:|---:|
| Current-parameter baseline | 865 | 2.04% |
| Wide stop, old cap | 178 | 4.92% |
| Wide stop, `MAX_STOP_PCT=0.25` | 867 | 8.60% |

## The historical and live candidates have different geometry

`research_lab/research_machine.py` and `research_lab/orchestrator.py` first request a normal signal, then multiply the complete distance from entry to the already-generated stop. Existing TP prices remain unchanged. The live strategy instead applies `ATT1_SL_ATR_MULT` or `SBR1_SL_ATR_MULT` while constructing the signal and derives TP prices from the resulting wider risk.

On the first 25 pre-sealed symbols, 906 comparable ATT1 short signals showed:

| Geometry | Median stop | P10 stop | P90 stop | Effective TP1 RR | Effective TP2 RR |
|---|---:|---:|---:|---:|---:|
| Historical research ×6 transform | 12.0839% | 6.5120% | 21.5264% | 0.2000 | 0.4167 |
| Proposed live-env construction | 8.5277% | 4.8198% | 14.6241% | 1.2000 | 2.5000 |

This is a definition mismatch, not sampling noise. The old ATT1 PnL cannot validate the proposed live-env strategy. SBR1 has the same stop/target construction mismatch.

## Other binding parity failures

1. **ATT1 cooldown has different units in practice.** `ATT1_COOLDOWN_BARS_5M=96` is decremented once per strategy call, while the monolith calls ATT1 approximately every 55 minutes. This is close to 96 hours, not eight hours. Research forces the value to eight calls.
2. **ATT1 `min_rr` is applied before the research stop transform.** In normal live construction, TP2 is created at 2.5R, making the 1.15 minimum effectively tautological. The historical ×6 transform reduces effective TP2 RR to 0.4167 but does not rerun the validator; an exact live reproduction would be rejected unless this contract is explicitly changed.
3. **`min_r2` is material.** On the 25-symbol sample, ATT1 moved from 865 to 2,260 signals with `min_r2=0`; SBR1 moved from 477 to 856. ATT1 waives R² for exactly two pivots, but the filter remains binding on larger fits.
4. **SBR1 exit fractions differ.** Live emits fractions `0.50, 0.30`, leaving a 20% runner. Research closes the entire remaining 50% at TP2. If both targets trade, research realizes 1.85R before costs while live realizes 1.33R plus an unresolved 0.20 runner: at least a 0.52R modeled-payoff mismatch before the runner outcome.
5. **SBR1 daily-limit scope is not global.** Strategy state is held per instance; the research verifier creates one instance per symbol. The current `max_signals_per_day=2` therefore behaves per symbol/day despite the cross-symbol description. In the 25-symbol sample it was not binding (477 with and without the cap), but its intended scope remains undefined for live wiring.
6. **The required flat-regime filters are absent from live code.** Neither ATT1 flat-down (`−2% ≤ BTC H1 close/EMA200−1 < 0`) nor SBR1 flat-up (`0 ≤ d < 2%`) is implemented with a last-closed-bar and freshness contract.
7. **SBR1 is not wired into the live monolith.** The existing generic `SLOPED_ENGINE` is a different strategy and cannot be treated as SBR1 evidence.
8. **Current ATT1 runtime evidence is incomplete.** The runtime contract omits the allowlist, 12-slot setting, flat-regime value/timestamp, global position/risk limits, and decision-bus/edge-monitor flags. A matching current hash would not prove the requested configuration.
9. **The 12-slot proposal is not execution-parity safe.** Portfolio caps, same-direction limits, minimum-quantity fallback, reservations, and open-risk checks can remove live signals and are not modeled by the verifier. The standalone exposure gate is not sufficient evidence of monolith wiring.

## Sensitivity checks

On the first 25 pre-sealed symbols:

| Check | Baseline signals | Changed signals | Result |
|---|---:|---:|---|
| ATT1 `MIN_RR=0` | 865 | 865 | Not binding in normal live geometry |
| ATT1 `MIN_R2=0` | 865 | 2,260 | Material limiter |
| SBR1 daily cap removed | 477 | 477 | Not binding in this window |
| SBR1 `MIN_R2=0` | 477 | 856 | Material limiter |
| SBR1 cap removed and `MIN_R2=0` | 477 | 857 | R² drives almost all of this change |

## Reproduction commands

Existing 25-symbol verifier:

```bash
python3 research_lab/verify_live_config.py
```

Full 137-symbol calculation using the same pre-sealed `run(...)` function:

```bash
.venv/bin/python -c 'import glob; from research_lab.verify_live_config import CASES,DATA,run; fs=sorted(glob.glob(DATA+"/*.npz")); print(f"files={len(fs)}"); [(lambda r: print(f"{name}\t{r[0]}\t{r[1]:.4f}"))(run(mod,cls,pfx,side,env,fs)) for name,mod,cls,pfx,side,env in CASES]'
```

Targeted parity/wiring tests used before the follow-up fix:

```bash
.venv/bin/python -m pytest -q tests/test_att1_runtime_contract.py tests/test_att1_live_wiring.py tests/test_exposure_gate.py tests/test_sloped_break_retest_v1.py tests/test_strategy_shadow_ledger.py tests/test_runner_state_fill_sync.py tests/test_runner_state_restore.py
```

Result: `33 passed in 0.32s`. These tests do not cover the mismatches listed above.

SLOPED sizing-contract regression and adjacent tests after the one-line fix:

```bash
.venv/bin/python -m pytest -q tests/test_sloped_sizing_contract.py tests/test_order_size_parity.py tests/test_strategy_pause_contract.py tests/test_att1_post_ack_safety.py tests/test_att1_rounding_diagnostics.py tests/test_sloped_break_retest_v1.py tests/test_sloped_break_retest_v2.py tests/test_sloped_break_retest_v3.py
```

Result: `19 passed in 1.13s`.

Final combined targeted validation:

```bash
.venv/bin/python -m pytest -q tests/test_att1_runtime_contract.py tests/test_att1_live_wiring.py tests/test_exposure_gate.py tests/test_strategy_shadow_ledger.py tests/test_runner_state_fill_sync.py tests/test_runner_state_restore.py tests/test_sloped_sizing_contract.py tests/test_order_size_parity.py tests/test_strategy_pause_contract.py tests/test_att1_post_ack_safety.py tests/test_att1_rounding_diagnostics.py tests/test_sloped_break_retest_v1.py tests/test_sloped_break_retest_v2.py tests/test_sloped_break_retest_v3.py
.venv/bin/python -m py_compile smart_pump_reversal_bot.py tests/test_sloped_sizing_contract.py research_lab/verify_live_config.py
git diff --check -- smart_pump_reversal_bot.py
```

Result: `50 passed in 1.32s`; compilation and targeted diff check passed.

## Next falsifiable parity harness

The next gate must compare two dry-run adapters over the same pre-sealed bytes: the research adapter and the live-signal/live-execution adapter. First choose and preregister exactly one geometry:

- **Historical reproduction:** widen the complete baseline stop and preserve original targets; or
- **New live geometry:** construct the wider ATR stop and recalculate targets at nominal RR, then discard the old PnL claim and rerun research.

Both adapters must emit one normalized row per evaluation with at least:

`symbol, bar_ts, side, signal_id, entry, sl, tp1, tp2, tp_fracs, runner_fraction, time_stop, cooldown_state, regime_value, regime_bar_ts, validator/drop_reason, config_hash, source_hash, data_hash`.

The harness must exit non-zero unless all of these preregistered assertions pass:

1. identical data hashes, timestamps, universe, side, and cutoff; zero swallowed exceptions;
2. raw signal-count difference ≤10% and matched `(symbol, bar_ts, side)` coverage ≥99%;
3. for matched signals, entry/SL/TP equality within one exchange tick after the same rounding path;
4. exact equality of TP fractions, runner fraction, time stop, cooldown transitions, regime decision, and every validator/drop reason;
5. exact equality of deterministic trade outcomes and R-return after the same fees/slippage contract;
6. all unmatched rows exported with reason codes; no unexplained drop is allowed.

Only after this harness passes may the selected candidate be rerun on the pre-sealed research window. A subsequent shadow configuration must use zero money authority, a new sleeve/spec identity, complete runtime contract, and paper/shadow outcome ledger. Decision bus and edge monitor should not be enabled merely because raw counts match.

## Follow-up code correction

The generic SLOPED post-submit sizing contract referenced undefined `effective_att1_risk_mult`. The sizing calculation immediately above already uses `SLOPED_RISK_MULT`; the contract now records that same value. `tests/test_sloped_sizing_contract.py` statically verifies the correct symbol and prevents ATT1 risk state from leaking back into the SLOPED function.

This correction does not wire SBR1, enable SLOPED, change risk, place orders, or alter ATT1/SBR1 live parameters.
