# Brain fixes: bounded production dependency check

Research commit **c80712ca824fe6bd1b3534ab4030a85811ddc3bd** is an ancestor of
the observed origin research/fabrika-v1 **3ed9b64969886583f7a51119962d6d9b5f4baf89**.
Verified using git ls-remote, cat-file, merge-base and versioned diff; no merge.
Claude's 64-test claim and line-availability percentages were not rerun here and
are not evidence of better returns.

## Money paths

| Path checked | Evidence | Verdict |
|---|---|---|
| Monthly candidate | Accepted 53-source manifest; actual runner AST closure 43 files | NO_IMPACT |
| Frozen PUMP4 V1 | pump_fade_v4r.py → signals.py/package initializer: 3 files | NO_IMPACT |
| KITY execution | Accepted 24-source safety manifest; micro CLI closure 5 files; batch service closure 18 files | NO_IMPACT |
| Selected LIVE NET manager | systemctl ExecStart → manager-wrapper.py → maintenance-only control-v1.py → pinned overlays/app imports, 40 files; all static pins valid | NO_IMPACT |

None of these checked closures imports a changed Brain/market-structure module.
NET was inspected by read-only AST/file checks, not by running its controller.
Zero broker requests, remote writes or unit changes in this dependency check.
This is scoped NO_IMPACT, not a claim about every possible future caller or every
other strategy in the repository. Generic persisted regime-state fields are not
the same dependency as bot.regime_hmm.

## Actual other callers and behavior risk

| Caller / function | Dependency and use | Effect if deliberately promoted |
|---|---|---|
| strategies/pump_exhaustion_unwind_short_v1.py::freeze_pre_event_highs | sloped_level(require_unbroken=True), structural signal eligibility | Changed line validity may change eligible signals; **different strategy from frozen PUMP4 V1** |
| bot/fx_setups_v2.py::_break_levels / sweep_reclaim_bounce_v2 | sloped_level; regime_probs; elder_bias, setup construction/filtering | Potential entry changes |
| bot/range_filter.py::range_state | classify_channel, range eligibility used by callers | New diagnostics separate flat/sloped; degradation handling changes failure behavior |
| bot/adaptive_context.py::get_adaptive_context | classify_channel → adaptive_params → build_context | Changes levels/tolerances when the consuming strategy enables adaptive context |
| bot/fx_context.py::build_fx_context | regime_probs and elder_bias, context information | Downstream consumers decide whether informational or a gate |
| bot/smart_grid.py::grid_plan; bot/range_scanner.py::score_instrument | classify_channel/regime_probs, grid eligibility/ranking | Potential plan/ranking changes |
| research_lab/factory_v3/brain_shadow_v1.py | opportunity_v2, research decision/outcome journal | New append-only outcome-correction API; no selected money caller found |

The sloped-level diff also changes the default validity scan to begin at the
first pivot; last_pivots is optional. Do not treat the entire patch as an
unchanged-default refactor. HMM missing-data gating becomes fail-closed; Elder
history/MACD validation and adaptive volatility priority also change behavior.
No changes from c80712c were copied to the execution checkout or deployed.

## Immutable files for external review

These links show the **research version at c80712c**, not the selected LIVE code:

- [regime_orchestrator.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/regime_orchestrator.py)
- [regime_hmm.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/regime_hmm.py)
- [range_filter.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/range_filter.py)
- [market_context.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/market_context.py)
- [elder_filter.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/elder_filter.py)
- [regime_side_gate.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/regime_side_gate.py)
- [strategy_regime_gate.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/strategy_regime_gate.py)
- [adaptive_context.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/adaptive_context.py)
- [risk_manager.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/bot/risk_manager.py)
- [brain_shadow_v1.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/research_lab/factory_v3/brain_shadow_v1.py)
- [opportunity_v2.py](https://github.com/Brokenbass90/by-bot/blob/c80712ca824fe6bd1b3534ab4030a85811ddc3bd/research_lab/factory_v3/opportunity_v2.py)

Priority remains Monthly cost handoff → PUMP4 execution/TINY acceptance. This
check neither promotes research nor creates financial authority.
