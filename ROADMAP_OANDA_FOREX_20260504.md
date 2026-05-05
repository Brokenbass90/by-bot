# Roadmap — OANDA Forex/CFD launch
**Дата:** 2026-05-04
**Контекст:** пользователь принесёт API через ~неделю.

## Pre-API (сейчас) — что готово

| Компонент | Готовность |
|---|---|
| `forex/engine.py` — backtest engine с spread+swap | ✅ |
| `forex/strategies/` — 19 стратегий (5 production-ready по аудиту) | ✅ |
| `forex/oanda/client.py` — REST API wrapper (250 строк) | ✅ Claude 2026-05-04 |
| `forex/oanda/bridge.py` — signal→order с idempotency (200 строк) | ✅ Claude 2026-05-04 |
| `scripts/run_forex_backtest.py` — CLI runner | ✅ |
| `forex/mt5/` — MT5 bridge (alternative) | ✅ |

## Day 0 (когда пользователь принесёт OANDA API)

### Шаг 1 — конфигурация (5 минут)
```bash
# .env additions:
OANDA_API_TOKEN=<from OANDA Account Settings>
OANDA_ACCOUNT_ID=<typical: 001-001-XXXXXXX-001>
OANDA_ENV=practice  # сначала paper
FOREX_RISK_PCT=0.005
FOREX_MAX_POSITIONS=3
FOREX_LEVERAGE=10
FOREX_DRY_RUN=1  # в начале — log only
```

### Шаг 2 — smoke test client (5 минут)
```bash
cd ~/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate
python3 forex/oanda/client.py
# должно показать account_summary + EUR_USD pricing
```

Если работает — credentials OK.

### Шаг 3 — bridge dry-run smoke (5 минут)
```bash
python3 forex/oanda/bridge.py
# должно: Ready: True, Bridge dry_run=True
```

## Day 1-3 — Backtest top-5 strategies на годовом окне

```bash
# для каждой из top-5 (по FOREX_19_STRATEGIES_AUDIT_20260504.md):
for strat in bb_mean_reversion_v3 london_open_breakout_v2 trendline_break_bounce_v1 \
             liquidity_sweep_bounce_session_v1 ema_trend_pullback_v2; do
  for pair in EURUSD GBPUSD USDJPY; do
    FX_SYMBOL=$pair \
    FX_CSV_PATH=data_cache/forex/${pair}_M5.csv \
    FX_SPREAD_PIPS=1.2 \
    bash scripts/run_forex_pilot_smoke.sh --strategy $strat --days 365
  done
done
```

Acceptance gate (для перехода в paper canary):
- Annual net > +200 pips
- PF ≥ 1.4
- Max DD ≤ 80 pips
- ≥ 50 сделок

## Day 4-10 — Paper canary live на OANDA practice

```bash
# в .env:
OANDA_ENV=practice
FOREX_DRY_RUN=0  # реально размещаем ордера на paper account
```

Запустить отдельный bridge-loop процесс для forex (аналогично crypto bot):
```bash
nohup python3 scripts/run_forex_live_bridge.py \
  --strategies bb_mean_reversion_v3,london_open_breakout_v2 \
  --pairs EURUSD,GBPUSD \
  --check-interval-sec 60 \
  > logs/forex_paper_canary.log 2>&1 &
```

(`scripts/run_forex_live_bridge.py` — нужно написать как обертку, ~150 строк, отложено пока нет API).

7 дней наблюдаем:
- Бот размещает ордера? (`oanda` web UI должен показать paper trades)
- TG-уведомления приходят?
- log пишется?
- PnL > 0 реалистично за 7 дней?

## Day 11+ — Real $200-500 на топ-1 стратегии

Если paper canary показал устойчивый плюс:
```bash
# .env:
OANDA_ENV=live
OANDA_API_TOKEN=<live-API-token, не practice!>
OANDA_ACCOUNT_ID=<live account ID>
FOREX_RISK_PCT=0.0025  # урезаем риск для real
FOREX_MAX_POSITIONS=1  # одна позиция за раз для начала
```

Запускаем только 1 стратегию (победитель из аудита) на 1 паре (наиболее-предсказуемой — обычно EURUSD).

30 дней live:
- Если PF live ≥ 1.3 → расширяем до 2-х стратегий
- Если PF live < 1.0 → пауза, диагностика

## Day 30+ — расширение портфеля

Постепенно:
- 2-я стратегия: добавить вторую из top-5
- Дополнительные пары
- Поднять FOREX_RISK_PCT с 0.0025 до 0.005
- Поднять FOREX_MAX_POSITIONS с 1 до 3

Realistic outcome через 60 дней live: $500 на OANDA → $530-580 (5-15% за 2 месяца).

## Critical safety

- НИКОГДА не запускать с `FOREX_DRY_RUN=0` без 7 дней paper smoke
- НИКОГДА не поднимать leverage > 10:1 без 30 дней live evidence
- При DD > -8% за неделю — pause, диагностика
- API ключ live ≠ paper, не путать

## Что писать когда работает

`docs/JOURNAL.md` каждую неделю:
- Сколько сделок на OANDA за неделю
- Net pips per pair
- PF rolling 30d
- Свежие проблемы

## Файлы которые я подготовил для этого

- `forex/oanda/client.py` ✅
- `forex/oanda/bridge.py` ✅
- `FOREX_19_STRATEGIES_AUDIT_20260504.md` ✅ — top-5 ranking
- `docs/JOURNAL_CLAUDE_20260504.md` ✅ — текущий статус

## TODO для Codex (когда вернётся)

- Написать `scripts/run_forex_live_bridge.py` (обёртка вокруг bridge для постоянного loop) — без этого мы не запустим OANDA live
- Добавить forex cron entries в `setup_server_crons.sh`
- Написать `forex/oanda/streaming.py` для real-time pricing (текущий REST poll = задержка)

## Ожидаемый результат через 60 дней после старта OANDA

- Crypto Bybit canary v2.1+: 8-12%/мес stable
- Funding-carry passive: +0.5-1.5%/мес
- OANDA forex (1-2 strategies live): +2-5%/мес
- **ИТОГО: 10-18%/мес на portfolio** = пользовательский target вдоль нижней границы

С leverage 5x на crypto через 4-6 месяцев → 15-25%/мес возможно.
