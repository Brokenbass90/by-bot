# News Filter Spec

## Goal

Reduce avoidable losses around high-impact macro/news events by applying a reproducible
code-level blackout and severity filter before signal execution.

This is not an "AI decides if news is scary" layer. The base layer must be deterministic.

## Scope

Phase 1:
- Forex
- Gold / macro-sensitive instruments
- Optional later extension to equities earnings / CPI / FOMC / NFP

Phase 2:
- Crypto-specific event calendar
- Headline severity overlay

## Architecture

### 1. Event Store

Canonical local file:
- `runtime/news_filter/events_latest.csv`

Columns:
- `event_id`
- `ts_utc`
- `country`
- `currency`
- `instrument_scope`
- `title`
- `impact`
- `source`
- `blackout_before_min`
- `blackout_after_min`
- `notes`

`instrument_scope` examples:
- `FX:USD`
- `FX:JPY`
- `FX:USD,JPY`
- `METALS:XAUUSD`
- `EQUITIES:ALL`

### 2. Decision Layer

Single function:
- `is_news_blocked(symbol, ts_utc, strategy_name) -> (blocked: bool, reason: str)`

Inputs:
- symbol
- timestamp
- strategy
- current event store
- strategy-specific policy

Outputs:
- deterministic allow/block
- human-readable reason for logs / Telegram

### 3. Policy Layer

Config-driven rules:
- block all entries inside blackout
- optionally allow exits / stop management
- different policies by market and strategy

Examples:
- `trend_retest_session_v1` on FX: block entries 20m before / 30m after high-impact USD/JPY events
- XAU breakout: block entries 30m before / 45m after high-impact USD events
- equities swing: no intraday block, but earnings blackout handled separately

## Event Classes

Phase 1 mandatory:
- FOMC
- CPI
- NFP
- central bank rates
- GDP
- PMI
- unemployment

Impact levels:
- `high`
- `medium`
- `low`

Default behavior:
- block only `high`
- optionally log `medium`

## Instrument Mapping

Examples:
- `EURUSD` -> EUR, USD
- `GBPJPY` -> GBP, JPY
- `XAUUSD` -> XAU, USD
- equities index-sensitive layer -> USD macro only

## Runtime Behavior

When blocked:
- no new entry
- no averaging
- no canary promotion
- existing open positions continue normal risk management

Optional Telegram message:
- only first block per symbol/event window
- avoid spam

Example:
- `NEWS BLOCK GBPJPY trend_retest: BOJ high impact, blackout until 2026-03-10 12:00 UTC`

## Data Ingestion

Preferred sources:
- structured macro calendar feed
- local normalized CSV snapshot

Do not make execution depend on live scraping.

Execution layer should read local event snapshot only.

## Phase 2: Headline Severity Overlay

Optional AI-assisted layer:
- parse headline feed
- classify severity into `ignore/watch/block`
- only allowed to tighten the deterministic filter, not relax it

This avoids non-reproducible "model whim" blocking.

## Backtest Plan

1. Build historical event dataset for major macro events.
2. Replay existing FX candidates with and without blackout.
3. Compare:
- stress return
- drawdown
- monthly positive share
- trade count
- average slippage around events

Pass condition:
- lower DD / tail losses without destroying too much edge

## Deliverables

Phase 1:
- `news_filter.py`
- local event CSV contract
- env/config policy
- Telegram block reporting
- backtest toggle for historical event blackout

Phase 2:
- headline severity worker
- strategy-specific severity routing
