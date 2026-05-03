# Alpaca $500 Deploy Plan — 2026-05-03

## TL;DR

Можно деплоить $500 на Alpaca **в течение 1-2 недель**, не блокируя по trailing-stop. Bracket-orders с фиксированным TP+SL на стороне Alpaca уже работают (`equities_alpaca_paper_bridge.py:427-429`). Это базовая защита капитала. Trailing — улучшение, не блокер.

## Что есть СЕЙЧАС

### v38 hybrid top4 — best Alpaca кандидат
- Файл: `configs/alpaca_v38_hybrid_top4_candidate.env`
- Эвиденс: OOS +27.95% / PF 7.85 / WR 86.7% / DD −2.28% / **15 сделок за год**
- Особенность: monthly compounder, не income engine. Для $500 это даёт ~$11/мес среднего профита, при 1-2 сделках/месяц.
- Risk на сделку: `risk_pct=0.005` (0.5%), значит на $500 = $2.50 на trade.

### Bracket-orders — ЕСТЬ
```python
# scripts/equities_alpaca_paper_bridge.py:418-431
"order_class": "bracket",
"take_profit": {"limit_price": ...},
"stop_loss":   {"stop_price":  ...},
```

Это значит **Alpaca брокер автоматически закрывает позицию** при достижении SL или TP, даже если бот падает или интернет отключился. Это базовая защита.

### Что НЕ работает
- Trailing-stop (динамический SL, который двигается за ценой) — реализован только симуляторно в monthly bridge, не на стороне брокера.
- Intraday/swing layer (income engine с 5+ сделок в неделю) — пока нет рабочего.

## Roadmap для $500 (поэтапный, по убыванию риска)

### Stage 0 — текущий paper canary (проверка ещё 7 дней)
- Запустить v38 hybrid top4 на paper с теми же $500-эквивалент
- Проверить: bracket-orders реально закрываются как ожидается
- Проверить: дневная отчётность в TG приходит
- Проверить: monthly rebalance работает (1 числа месяца)
- **Acceptance:** 7 дней без incidents, минимум 1-2 trade

### Stage 1 — реальный $500 deploy с conservative size
- env: `ALPACA_PAPER=0`, `MAX_POSITION_PCT=0.20` (max $100 на одну сделку из $500)
- Bracket order class активен (default уже)
- `MONTHLY_SL_PCT=0.08` (8% loss → force close)
- `risk_pct=0.005` (0.5% от equity = $2.50)
- TG-уведомления на каждую сделку
- **Daily check pre-market:** что ничего не зависло, что balance корректный
- **Acceptance:** 30 дней live без потери > 5%, PF live ≥ 1.5

### Stage 2 — добавить income layer (после Stage 1 успеха)
- Параллельно к v38 monthly запустить **intraday/swing** на отдельный account_id или sub-bot
- Кандидаты: `swing_strict` (PF 1.34, 77 trades/24m) или `intraday_v3` (нужен повторный тест после смены данных)
- Risk: $100 из $500 на этот layer ($25/сделка max)
- **Acceptance:** 30 дней live, PF ≥ 1.3 на 50+ сделок

### Stage 3 — добавить trailing-stop (улучшение, не блокер)
- Реализовать через Alpaca `trailing_stop` order type. Нужно изменить bridge: после TP1 partial exit заменить static SL на trailing с `trail_percent=2.0` или `trail_price=ATR*1.0`.
- Это даёт +5-15% PF на тех же сигналах через захват extended moves.
- **Acceptance:** A/B test paper 30 дней с/без trailing на same signals.

## Какую версию использовать для real money?

| version | PF | Trades/y | Recommendation |
|---|---:|---:|---|
| v38 hybrid top4 | 7.85 | 15 | **Stage 1 default** — самый чистый |
| v38 more active research | 4.54 | 21 | Только после Stage 1 успеха, как 2-я нога |
| swing_strict | 1.34 | 39 | Stage 2 income layer кандидат №1 |
| swing_classic | **−32%** | сломан | НЕ используем |
| intraday_v3 | unknown | unknown | Нужна свежая валидация перед использованием |

## Риски и mitigation

| риск | mitigation |
|---|---|
| Brokerage gap (overnight halt) | bracket order стоит в Alpaca → автозакрытие |
| Бот упал ночью | bracket order работает независимо |
| Stop-hunt на тонком стоке | `MAX_POSITION_PCT=0.20` ограничивает worst-case loss |
| API key утечка | IP whitelist + 2FA на Alpaca |
| Earnings overnight surprise | `_filter_earnings` уже есть в bridge — фильтрует |
| Нерезидент проблемы / KYC | Alpaca paper → Alpaca real нужна верификация. Если не проходишь — рассмотреть IBKR / TradeStation |

## Первая команда после approval

```bash
# 1. Подтвердить paper работает 7 дней без incidents
tail -n 100 logs/equities_alpaca_paper_bridge.log

# 2. Сделать backup текущего .env
cp .env state/env_backups/.env.before_alpaca_real_$(date +%s).bak

# 3. Поменять paper → real в .env
# ALPACA_PAPER=0
# ALPACA_KEY=<real key>
# ALPACA_SECRET=<real secret>
# ALPACA_BASE_URL=https://api.alpaca.markets

# 4. Smoke test через одну ручную команду (placement → cancel)
python3 scripts/equities_alpaca_paper_bridge.py --dry-run

# 5. Restart cron-job или service
systemctl restart alpaca-bridge
```

## Что улучшить долгосрочно

Если Alpaca реально торгует и приносит $11-50/мес с $500 — пополняй. При $5000 возможна:
- v38 + swing_strict + intraday_v3 = 3 одновременных layers
- PF expectations 4-6 weighted, ~30-40% годовых
- Реалистично выйти на ~$150-200/мес чистыми

Без интрадей-слоя monthly v38 в одиночку не даст «доход кормильца» — он compounder, не income.

## Что я НЕ делаю в ночь

- Не меняю код Alpaca bridge без явного approval
- Не перевожу paper → real
- Не вкладываю real money

## Время

- Stage 0 (7 days paper smoke) — пассивно, надо просто подождать
- Stage 1 deploy (real $500) — 1 час твоей работы при ОК со Stage 0
- Stage 2 (income layer) — 1-2 недели разработки + 30 дней проверки
- Stage 3 (trailing) — 1 неделя разработки + A/B test
