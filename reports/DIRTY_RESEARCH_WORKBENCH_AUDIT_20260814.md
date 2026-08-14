# Аудит грязной исследовательской рабочей области

Проверено code-кандидатов: **163**. Ничего не удалено и не перемещено.

## Сводка

| категория | количество |
|---|---:|
| `evidence_backed_needs_reproduction` | 115 |
| `referenced_needs_review` | 16 |
| `test_backed_candidate` | 5 |
| `unreferenced_quarantine_candidate` | 27 |

## Первая очередь разбора

| score | категория | путь | tests | evidence | live-risk |
|---:|---|---|---:|---:|---|
| 43 | `test_backed_candidate` | `backtest/run_portfolio.py` | 4 | 35 | no |
| 27 | `evidence_backed_needs_reproduction` | `research_lab/xsec_v3_reference.py` | 0 | 8 | no |
| 19 | `evidence_backed_needs_reproduction` | `scripts/audit_backtest_run.py` | 0 | 6 | no |
| 17 | `evidence_backed_needs_reproduction` | `research_lab/sweep_reclaim.py` | 0 | 10 | no |
| 16 | `evidence_backed_needs_reproduction` | `research_lab/sloped_break_retest.py` | 0 | 6 | no |
| 15 | `evidence_backed_needs_reproduction` | `research_lab/trial_ledger.py` | 0 | 4 | no |
| 15 | `test_backed_candidate` | `scripts/validate_swing_alpaca.py` | 1 | 3 | no |
| 15 | `evidence_backed_needs_reproduction` | `strategies/sc1_live.py` | 0 | 5 | no |
| 15 | `test_backed_candidate` | `strategies/sloped_break_retest_v3.py` | 1 | 2 | no |
| 13 | `test_backed_candidate` | `research_lab/hypothesis_memory.py` | 1 | 1 | no |
| 13 | `evidence_backed_needs_reproduction` | `research_lab/level_dca_v1.py` | 0 | 3 | no |
| 13 | `evidence_backed_needs_reproduction` | `research_lab/xsec_v2_run.py` | 0 | 4 | no |
| 12 | `evidence_backed_needs_reproduction` | `research_lab/l2_density_edge.py` | 0 | 4 | no |
| 12 | `evidence_backed_needs_reproduction` | `research_lab/liquidation_cascade.py` | 0 | 3 | no |
| 12 | `evidence_backed_needs_reproduction` | `research_lab/options_expiry.py` | 0 | 4 | no |
| 12 | `evidence_backed_needs_reproduction` | `research_lab/xsec_eventfilter.py` | 0 | 3 | no |
| 12 | `evidence_backed_needs_reproduction` | `strategies/smart_grid_v1.py` | 0 | 5 | no |
| 11 | `evidence_backed_needs_reproduction` | `bot/loso_concentration.py` | 0 | 4 | no |
| 11 | `evidence_backed_needs_reproduction` | `research_lab/strategy_liveness_probe.py` | 0 | 2 | no |
| 11 | `evidence_backed_needs_reproduction` | `research_lab/vol_regime_filter.py` | 0 | 4 | no |
| 10 | `evidence_backed_needs_reproduction` | `research_lab/entry_ladder.py` | 0 | 3 | no |
| 10 | `evidence_backed_needs_reproduction` | `research_lab/equity_gap_drift.py` | 0 | 3 | no |
| 10 | `evidence_backed_needs_reproduction` | `research_lab/equity_overnight.py` | 0 | 3 | no |
| 10 | `evidence_backed_needs_reproduction` | `research_lab/fetch_daily_history.py` | 0 | 3 | no |
| 10 | `evidence_backed_needs_reproduction` | `research_lab/heat_selector.py` | 0 | 3 | no |
| 10 | `evidence_backed_needs_reproduction` | `research_lab/station_tsm_v2_holdout.py` | 0 | 4 | no |
| 10 | `evidence_backed_needs_reproduction` | `research_lab/strategy_census.py` | 0 | 2 | no |
| 9 | `evidence_backed_needs_reproduction` | `research_lab/funding_squeeze_v2.py` | 0 | 2 | no |
| 9 | `evidence_backed_needs_reproduction` | `research_lab/level_dca_v2_midterm.py` | 0 | 3 | no |
| 9 | `evidence_backed_needs_reproduction` | `research_lab/negative_control.py` | 0 | 1 | no |
| 9 | `evidence_backed_needs_reproduction` | `research_lab/station_sloped_v1.py` | 0 | 3 | no |
| 9 | `evidence_backed_needs_reproduction` | `research_lab/station_tsm_v1.py` | 0 | 3 | no |
| 9 | `evidence_backed_needs_reproduction` | `scripts/portfolio_13symbols.sh` | 0 | 3 | no |
| 8 | `evidence_backed_needs_reproduction` | `backtest/funding_carry_maximizer.py` | 0 | 3 | no |
| 8 | `evidence_backed_needs_reproduction` | `backtest/portfolio_combiner.py` | 0 | 3 | no |
| 8 | `evidence_backed_needs_reproduction` | `backtest/red_month_doctor.py` | 0 | 3 | no |
| 8 | `test_backed_candidate` | `research_lab/att1_negative_phenotypes.py` | 1 | 0 | no |
| 8 | `evidence_backed_needs_reproduction` | `research_lab/forward_horizon_study.py` | 0 | 2 | no |
| 8 | `evidence_backed_needs_reproduction` | `research_lab/pump_spike_fade.py` | 0 | 2 | no |
| 8 | `evidence_backed_needs_reproduction` | `research_lab/tsm_shadow_local.py` | 0 | 3 | no |
| 8 | `evidence_backed_needs_reproduction` | `scripts/att1_negative_control.sh` | 0 | 4 | no |
| 8 | `evidence_backed_needs_reproduction` | `scripts/render_levels.py` | 0 | 3 | no |
| 7 | `evidence_backed_needs_reproduction` | `research_lab/bounce_or_break.py` | 0 | 2 | no |
| 7 | `evidence_backed_needs_reproduction` | `research_lab/build_h1_bundle.py` | 0 | 2 | no |
| 7 | `evidence_backed_needs_reproduction` | `research_lab/fetch_movers_5m.py` | 0 | 2 | no |
| 7 | `evidence_backed_needs_reproduction` | `research_lab/guard_calibration.py` | 0 | 2 | no |
| 7 | `evidence_backed_needs_reproduction` | `research_lab/horizontal_break_retest.py` | 0 | 2 | no |
| 7 | `evidence_backed_needs_reproduction` | `research_lab/pairs_statarb.py` | 0 | 3 | no |
| 7 | `evidence_backed_needs_reproduction` | `research_lab/station_movers_v1.py` | 0 | 2 | no |
| 7 | `evidence_backed_needs_reproduction` | `research_lab/validate_xsec_v2.py` | 0 | 2 | no |

## Правило зачистки

Сначала воспроизводимость и reference-map, затем отдельный commit или карантин. Массовое удаление по возрасту/имени запрещено.
