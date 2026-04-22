# Project Map

## Goal
- Build a crypto + Alpaca trading system that survives regime changes.
- Use multiple sleeves, not one universal strategy.
- Let control-plane decide when sleeves should be on, reduced, paused, or blocked.
- Promote sleeves to live only after honest validation, then keep improving the rest.

## Core Layers

### 1. Live Bot
- File: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/smart_pump_reversal_bot.py`
- Responsibility:
  - live market data
  - order placement
  - open-trade management
  - per-sleeve entry loops
  - Telegram/operator messages

### 2. Control Plane
- Regime:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_regime_state.py`
  - outputs market phase and strategy overrides
- Router:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_symbol_router.py`
  - chooses symbol baskets per sleeve
- Allocator:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_portfolio_allocator.py`
  - translates regime + router + health into final sleeve enable flags and risk haircuts
- Watchdog / health:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/check_control_plane_health.sh`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/control_plane_watchdog.py`

### 3. Research / Validation
- Static portfolio runner:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/backtest/run_portfolio.py`
- Dynamic system replay:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_annual.py`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_dynamic_crypto_walkforward.py`
- Autoresearch / sweeps:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/run_strategy_autoresearch.py`
- Project-wide health/reporting:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/build_project_doctor_report.py`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/live_vs_backtest_monitor.py`

### 4. Operator / AI
- Runtime snapshot:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/operator_snapshot.py`
- Telegram/web AI truth layer:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/bot/deepseek_overlay.py`
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/web/routes/ai_routes.py`

### 5. Web Surface
- API:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/web/routes`
- Mirror sync:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/scripts/sync_web_live_mirror.sh`

## Truth Sources
- Live heartbeat:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/bot_heartbeat.json`
- Regime:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/regime/orchestrator_state.json`
- Router:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/router/symbol_router_state.json`
- Allocator:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/control_plane/portfolio_allocator_state.json`
- Strategy health:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/configs/strategy_health.json`
- Project doctor:
  - `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/runtime/project_doctor/latest.txt`

## Promotion Policy

### Canary Gate
- `360d confirm`
- recent `WF`
- recent `2025 + 2026 YTD`
- if good: reduced-risk canary/live

### Standard Gate
- `2022 / 2023 / 2024 / 2025 / 2026 YTD`
- `WF`
- if good: fully validated sleeve/package

## Current Lanes

### Current strong live base
- `ATT1`

### Best next candidate
- `ASB1`

### Candidate, not yet cleared
- `breakdown_v1`

### Repair / rewrite lanes
- `Elder v3`
- `inplay_breakout`
- `midterm_v3`
- `bounce1`
- `HZBO1`

## Immediate Work Pattern
1. Validate sleeves individually.
2. Validate packages statically.
3. Validate the same package through dynamic control-plane replay.
4. Promote only what survives recent windows.
5. Move failed ideas into repair lanes instead of forgetting them.
