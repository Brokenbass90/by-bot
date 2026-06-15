# Codex to Claude — 2026-06-15

## Status

- Local deps: `pip install -r requirements-dev.txt` completed.
- Local tests: `228 passed`.
- Server tests after targeted deploy: `99 passed, 1 warning` (`passlib` deprecation only).
- Server snapshot refreshed: `reports/SERVER_SNAPSHOT_latest.{json,md}` at `2026-06-15T08:34:31.790670Z`.
- Secrets check: snapshot uses allowlist + recursive redaction; no unredacted secret-like keys found.
- Repo hygiene: `configs/web_config.json` remains `skip-worktree`; do not stage it.

## Server live state

- `open_trades=0`, `trade_on=True`, `dry_run=False`.
- `regime=bull_trend`, `bybit_msgs=275743` in exported snapshot; post-test heartbeat reached `bybit_msgs=282111`.
- `risk_per_trade_pct=0.44`, `orch_global_risk_mult=0.55`, `allocator_global_risk_mult=0.80`.
- `NO_ENTRY_HOURS_UTC=[]`.
- Real live journal path on server: `runtime/live_trade_events.jsonl`.
- Local mirror copy refreshed to `runtime/live_mirror/live_trade_events.jsonl`.
- Last trade event: `2026-06-13 18:00:15 UTC`, `flat_resistance_fade`, `LTCUSDT`, pnl `+0.17396262`.
- No trade events in the last 24h, so Telegram "no trade events" is honest.

## Runtime strategies

Runtime config from heartbeat, which is more important than raw `.env`:

| sleeve | enabled | runtime risk_mult |
|---|---:|---:|
| `midterm` | true | 0.0 |
| `att1` | true | 0.0 |
| `flat` | true | 0.3 |
| `breakdown` | true | 0.0 |
| `ivb1` | true | 0.25 |
| `bounce1` | true | 0.0 |
| `asb1_slope_break` | false | 0.0 |
| `hzbo1` | false | 0.0 |
| `elder` | false | 0.05 |

Raw safe `.env` has many `ENABLE_* = 1`, but allocator/regime runtime config currently zeroes or disables several sleeves. Use heartbeat runtime config for live truth.

## P&L by sleeve

Output from `scripts/pnl_by_sleeve.py` / snapshot recent journal:

| sleeve | pnl | trades | W/L |
|---|---:|---:|---:|
| `alt_inplay_breakdown_v1` | -2.4170 | 15 | 4/11 |
| `att1_trendline_touch` | -1.2827 | 7 | 1/6 |
| `range` | -0.9227 | 1 | 0/1 |
| `flat_resistance_fade` | +0.3234 | 2 | 2/0 |
| `bootstrap` | +0.7451 | 1 | 1/0 |

Total recent realized: pnl `-3.5539`, fees `0.6632`, trades `26`, W/L `8/18`.

## Alpaca bake-off, bear 2022 OOS

Command, local and server:

```bash
python backtest/alpaca_bakeoff_wf.py
```

Period: warm-up `2021-01-01..2023-01-01`, evaluation `2022-01-01..2023-01-01`, 19 cached symbols including SPY, 10 bps round-trip fee/slippage, capital `$1000`, max positions `4`.

| variant | return | PF | WR | trades | DD | negative months | worst month |
|---|---:|---:|---:|---:|---:|---:|---:|
| `STATIC_TOP4_21D` | -32.26% | 0.219 | 31.8% | 22 | 35.37% | 6/12 | -15.15% |
| `V39_EVENT_CLOSE` | -23.47% | 0.415 | 45.5% | 44 | 27.66% | 6/12 | -9.41% |
| `V39_OHLC_SPY200_GATE` | -23.43% | 0.257 | 25.0% | 24 | 24.83% | 6/12 | -11.93% |
| `V40_EVENT_DRAFT` | -15.34% | 0.413 | 41.0% | 39 | 19.68% | 6/12 | -9.26% |
| `V40_STATIC_TOP4` | -15.93% | 0.250 | 41.2% | 17 | 22.31% | 5/12 | -10.12% |
| `ADAPTIVE_V1_GATED` | -6.54% | 0.280 | 33.3% | 12 | 2.23% | 2/11 | -6.11% |
| `ADAPTIVE_V1_UNGATED_CONTROL` | -15.27% | 0.541 | 44.4% | 36 | 18.30% | 6/11 | -7.29% |

Verdict: `alpaca_adaptive_v1` gated is the current bear-capital-protection champion, but it is not an income champion yet because PF remains below 1. Use it as Alpaca stabilizer/paper candidate, not as a large live allocation. v39/v40/static fail bear OOS.

## Crypto efficiency smoke

Server command:

```bash
PYTHONPATH=. python backtest/crypto_efficiency_backtest.py
```

Results are smoke-only: cached OHLC, no fees/slippage, low trade counts.

| probe | trades | win% | avg win R | avg loss R | expectancy R | PF |
|---|---:|---:|---:|---:|---:|---:|
| ASB1 SOLUSDT | 10 | 50.0 | 3.67 | -1.00 | 1.336 | 3.67 |
| ASB1 LINKUSDT | 9 | 22.2 | 6.02 | -1.00 | 0.561 | 1.72 |
| ASB1 ADAUSDT | 9 | 33.3 | 2.44 | -1.00 | 0.145 | 1.22 |

Verdict: positive research signal for ASB1, but not enough for live risk increase. Keep ASB1 in shadow/research until fee/slippage WF and live additivity are proven. HZBO1 and Elder should remain OFF.

## Telegram honesty

Critical live claims are consistent with server state: auth/equity mode, `DRY_RUN: OFF`, `open_trades=0`, no recent trade events, and `bull_trend` regime.

Weak point: strategy health section in Telegram can still refer to stale `configs/strategy_health.json`. The digest warns about staleness, but it should be upgraded to prefer `runtime/strategy_health_report.json` or label old snapshots as historical.

## Errors / blockers

- Fixed exporter compatibility: `dt.UTC` replaced with `dt.timezone.utc`.
- Server Python is actually `3.12.3`, not `3.10.12`, but the compatibility fix is still correct.
- No remaining server test errors after targeted deploy.
- 2020 equities bear/COVID data is not yet in the local/server cache. Current honest table covers 2022 bear only.

## Follow-up deploy: web/AI visibility + proof-of-life

Deployed additively to server:

- `bot/code_access.py` and `bot/ai_tools.py`: read-only source/code-map access for the on-board AI. Secret-like paths and `.env` are refused; secret-like assignments are redacted.
- `scripts/build_ai_codemap.py`: generated `reports/AI_CODEMAP.{json,md}`.
- `scripts/proof_of_life.py`: compact live pulse from `SERVER_SNAPSHOT_latest`.
- `web/static/operator_console.html`.
- `web/main.py`: `/operator-console` static route.
- `web/routes/data_routes.py`: authenticated read-only operator/AI APIs: `/api/heartbeat`, `/api/pnl`, `/api/strategy-catalog`, `/api/ai/tools`, `/api/ai/pulse`, `/api/ai/codemap`, `/api/ai/code/list|read|search`.

Safety note: connection/key write APIs from the HTML console are deliberately not implemented. The page is useful for visibility, but secret-store writes need a separate design.

Server checks:

- `trading-journal-web` restarted only; live trading bot was not restarted.
- `/ping` = 200, `/operator-console` = 200, unauthenticated `/api/heartbeat` = 401.
- Server full pytest after deploy: `118 passed, 1 warning`.
- Latest full local pytest after additive work: `247 passed`; latest targeted local tests for this follow-up: `22 passed`.

Proof-of-life:

- Server exporter refreshed snapshot at `2026-06-15T12:23:31.328663Z`.
- `scripts/proof_of_life.py --tg --send` sent a control Telegram successfully: `TG send ok`.
- Added cron:

```cron
15 */3 * * * /bin/bash -lc 'cd /root/by-bot && set -a && source .env && set +a && .venv/bin/python3 scripts/proof_of_life.py --tg --send >> logs/proof_of_life.log 2>&1' # proof_of_life_tg_codex
```

Latest pulse:

```text
ALIVE | regime=bull_trend | feed OK | open=0
risk/trade=0.44% | maxpos=3 | block=False
LIVE sleeves: flat=0.3, ivb1=0.25
recent P&L: -3.554 over 26 trades
```

## Crypto fee/slippage WF with ladder compare

Deployed `backtest/ladder_exit.py` + `backtest/crypto_efficiency_wf.py` and ran bounded server WF:

```bash
PYTHONPATH=. .venv/bin/python3 backtest/crypto_efficiency_wf.py --max-rows 60000
```

| sleeve | symbol | 0bps | 10bps | 20bps |
|---|---|---:|---:|---:|
| ASB1 long | SOLUSDT | +1.34R PF3.67 n10 | +1.08R PF2.66 | +0.83R PF2.03 |
| ASB1 long | LINKUSDT | +0.56R PF1.72 n9 | +0.29R PF1.29 | +0.01R PF1.01 |
| ASB1 long | ADAUSDT | +0.14R PF1.22 n9 | -0.07R PF0.91 | -0.29R PF0.70 |
| ARF1 short | SOLUSDT | -0.63R PF0.26 n7 | -0.85R PF0.19 | -1.06R PF0.13 |
| ARF1 short | LINKUSDT | -0.43R PF0.44 n8 | -0.67R PF0.31 | -0.90R PF0.24 |
| ARF1 short | ADAUSDT | +0.47R PF1.65 n14 | +0.25R PF1.28 | +0.03R PF1.03 |

Ladder compare:

- SOL ASB1: single +1.34R PF3.67 vs ladder +0.96R PF2.92 at 0bps; single +1.08R PF2.66 vs ladder +0.71R PF2.08 at 10bps.
- LINK ASB1: single +0.56R PF1.72 vs ladder +0.54R PF1.76 at 0bps; both thin but survive near 10bps.
- ADA ASB1: fails after fees/ladder; do not promote.

Verdict: ASB1/SOL is the cleanest fee-resilient pocket. ASB1/LINK is thin. ASB1/ADA is not fee-safe. ARF1 short only has a possible ADA pocket; SOL/LINK fail this window. This supports symbol-specific shadow/canary design, not a broad package risk increase yet.

## Alpaca paper status

Alpaca paper is already running on server cron:

- `ALPACA_SEND_ORDERS=1`
- candidate env: `/root/by-bot/configs/alpaca_v38_hybrid_top4_candidate.env`
- effective monthly capital: `$500`
- current paper positions in log: `AMD`, `GE`, `LLY`, `SNOW`
- broker protection active: stop orders exist/rearmed for all held names in the paper log.

Important: this does not mean real `$500` is ready today. The bear-2022 WF says `alpaca_adaptive_v1` is the best capital-protection candidate, but still has PF `< 1` in 2022. Treat Alpaca as paper/stabilizer until it passes live-paper evidence: 4-8 weeks, enough closed decisions, protection clean, and live-paper behavior matching the harness.
