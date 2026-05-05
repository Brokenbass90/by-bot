# Арбитраж + Плечо план — путь к 10-30% в месяц
**Дата:** 2026-05-04
**Автор:** Claude
**Контекст:** пользователь хочет 10-30% в месяц (=120-360% годовых). Чисто directional крипта-стратегии без leverage реалистично 60-100% годовых. Нужны дополнительные edge'ы.

## TL;DR

Три параллельных трека к высокой доходности:

1. **Funding-rate арбитраж** — низкий risk, edge 12-30% годовых по historical data Bybit, требует ~1-2 недели разработки.
2. **Cross-exchange spot↔perp basis arbitrage** — средний risk, edge 8-25% годовых, требует API на 2-х биржах + ~3-4 недели разработки.
3. **Аккуратное плечо после устойчивой работы canary** — мультипликатор к directional. Только после 2 месяцев стабильного PF ≥ 1.4 в live.

Итого если все три работают: directional 70% + funding 20% + basis 15% = ~105% годовых **без плеча**, и 200%+ с плечом 2.5x. Это и есть target пользователя.

---

## 1. Funding-Rate Arbitrage (приоритет №1 — самая дешёвая в разработке)

### Идея

На Bybit perpetual swaps каждые **8 часов** trader'ы платят/получают **funding rate**. Если funding > 0 → longs платят shorts (рынок перегрет лонгами). Если funding < 0 → shorts платят longs (рынок перегрет шортами).

**Edge:** удерживать market-neutral позицию, которая **просто собирает funding**:
- Если funding > +0.01% → SHORT perp + LONG спот → получаешь funding с шорта, цена-нейтрален
- Если funding < −0.01% → LONG perp + SHORT спот → получаешь funding с лонга

Bybit historical: funding на BTCUSDT в среднем ~+0.01% в 8h (≈3 раза/день) ≈ +11% годовых passive yield, на altcoins может доходить до +50-100% годовых в pump-фазах.

### Реализация

**Шаг 1:** Сборщик funding rate (5 мин кода).
```python
# scripts/fetch_funding_rates.py
# каждые 5 мин запрашивает /v5/market/funding/history для топ-20 perp
# пишет в runtime/funding_rates.jsonl
```

**Шаг 2:** Стратегия `funding_arb_v1`:
- Если funding > FUNDING_ENTRY_THRESHOLD (default +0.02%) → открываем SHORT perp + ждём
- Через 30 минут до funding payment проверяем что funding всё ещё > threshold → если нет, закрываем
- Получаем payment, удерживаем ещё 8h цикл если funding всё ещё положительный
- Если volatility вырастает (move > 2 ATR) → выйти из позиции (стоп от ушедшего pnl)

**Шаг 3:** Hedge — ОПАСНЫЙ момент.
Идеально — иметь spot позицию противоположной стороны. На Bybit Unified можно использовать spot wallet, но это требует:
- Двойного капитала (spot + margin)
- Или derivatives ↔ derivatives hedge (в будущем)

**Минимальная версия — naked funding harvest без hedge:**
- Только когда funding extreme (|funding| > 0.05%)
- С коротким time-horizon (один payment cycle)
- С tight ATR stop
- Это уже наш `funding_rev` рукав по сути, но с другим focus: не reversion price, а capture funding

Edge: 5-15% годовых, low DD (≤ 2-3%). Хорошо как passive overlay.

### Acceptance gate
- 365d backtest: net ≥ +5%, max DD ≤ 4%, sharpe ≥ 1.5
- WF-22: ≥ 14/22 окон pass
- Live shadow 30 дней с реальным funding tracking

### Стоимость и время
- Code: ~3-4 часа (`scripts/fetch_funding_rates.py` + `strategies/funding_arb_v1.py`)
- Backtest: 30 мин
- Acceptance: 30 дней shadow
- API calls: ~$0 (Bybit funding history бесплатный)

---

## 2. Cross-Exchange Spot↔Perp Basis Arbitrage (приоритет №2)

### Идея

Spot price и perpetual price должны быть равны. Когда они расходятся (basis), есть edge:
- Если **perp > spot** на > 0.1% → SHORT perp + LONG spot → ждём конвергенции
- Когда basis нормализуется (или funding payment) → закрываем обе ноги, фиксируем profit

Особенно работает на altcoins, где basis может расходиться на 0.3-1%+ в момент pump'а.

### Реализация

Нужна **вторая биржа** с spot trading. Bybit имеет spot, но обычно basis arb делают cross-exchange:
- Bybit perp ↔ Binance spot
- Bybit perp ↔ Coinbase spot

**Сложности:**
- Withdrawal fees (для balance) — не вариант для < $10k
- API на 2-х биржах + reconciliation
- Latency: если позиция открывается с задержкой > 1 сек, basis может закрыться прежде чем мы вошли

**Проще: same-exchange spot↔perp.** На Bybit:
- Открыть SHORT perp BTCUSDT + LONG spot BTC одновременно
- Ждём когда perp price упадёт relative to spot → закрываем обе

### Edge
Реалистично 8-15% годовых на крупные крипты, до 25% на altcoin'ах в активные периоды.

### Acceptance gate
- Backtest на 90d funding+basis combined: net ≥ +8%, max DD ≤ 5%
- Live shadow 14 дней с paper-tracking
- Реальный live deploy с маленьким объёмом ($200 на ноге = $400 нотионала)

### Стоимость и время
- Code: ~10-15 часов (двухбиржный bridge сложнее чем funding harvest)
- Backtest infrastructure: ~5 часов (нужна синхронизация spot/perp candles)
- Acceptance: 14-30 дней

---

## 3. Плечо — roadmap

### Текущее состояние
- `BYBIT_LEVERAGE=3` на main account (`.env` строка 17)
- `risk_pct=0.01` (1% риск на сделку)
- Эффективное плечо: 3 × 1% = 3% капитала под риском на сделку при leverage 3x

### Когда поднимать
**Жёсткое правило:** плечо поднимается ТОЛЬКО когда live PF за 60 дней ≥ 1.40 на минимум 100 сделок.

| Этап | leverage | risk_pct | условие |
|---|---|---|---|
| Сейчас | 3x | 1.0% | live canary v2.1, ждём первых сделок |
| После 30d live PF≥1.3 | 3x | 1.0% | проверяем устойчивость |
| После 60d live PF≥1.4, ≥100 trades | 5x | 0.8% | первый scale-up |
| После 120d live PF≥1.4 + Phase 3 monitor работает | 7-10x | 0.6% | максимум для крипты |

При плече 5x с risk_pct=0.8% — каждая сделка рискует 4% от depo с волатильностью 20% относительно небольших движений. На 100 сделках с PF 1.4 ожидание ~30-40% prof, но max DD до 12-15%. Психологически выдерживаемо для $1000+, не для $100.

### Что НЕ делать
- Не поднимать leverage > 3x на $100 депозите. Один drawdown 20% = $20 потери = 20% от total. Это не масштабируется.
- Не поднимать leverage до того, как Phase 3 monitor (live_vs_backtest_monitor.py) работает. Без него ты не увидишь degradation вовремя.
- Не поднимать leverage и risk_pct одновременно. Что-то одно.

---

## Реалистичный путь к 10-30%/мес

| Месяц | действие | ожидаемая доходность |
|---|---|---:|
| Май 2026 | canary v2.1 deploy, первые 30 дней live data | 1-3% (calibration) |
| Июнь 2026 | + ASB1 promote (если bull_chop держится) + funding_arb_v1 backtest | 4-7% |
| Июль 2026 | + funding_arb_v1 live shadow, начать basis arb backtest | 6-10% |
| Август 2026 | + leverage 5x (если live PF держится) + funding_arb_v1 в live | 10-18% |
| Сентябрь 2026 | + basis arb live shadow | 12-22% |
| Октябрь 2026 | basis arb live + Phase 3 auto-apply | 18-30% |

К октябрю 2026 = 6 месяцев → реалистично выйти на target пользователя.

**На пути к этому:** $500 deposit становится $500 × (1.05)^6 ≈ **$670** к октябрю при простом compounding 5% в месяц. Если в августе достигнем 12%, то $500 → $500 × 1.05² × 1.07² × 1.12 = **$735** к Сентябрю. Это для понимания: **сложный процент работает, но медленнее чем кажется**.

Чтобы $500 стало $2000 к концу года — нужно держать 30% в месяц. Это max наш realistic optimistic plan. Реалистичный — **$500 → $1000 за 6 месяцев** при 12-15%/мес после развёртывания всех 3 треков.

---

## Что я могу сделать сам без Codex

1. ✅ Прямо сейчас — пишу `scripts/fetch_funding_rates.py` (короткий, 50 строк)
2. ✅ Прямо сейчас — пишу `strategies/funding_arb_v1.py` (концепт версия 200 строк)
3. ✅ Прямо сейчас — backtest spec для funding_arb_v1
4. После пуша — Codex запускает на сервере, мы смотрим результаты

basis arb и leverage management — это сложнее и требуют live data. Делать после funding_arb стабильно работает.

---

## Что блокирует прогресс

1. **Push commit `8447d00`** — без этого canary v2.1 не попадёт в live. Сделай у себя `git push origin codex/dynamic-symbol-filters`.
2. **Свежий cache** до 2026-05-04 — для acceptance backtest на bull_chop window. Codex или я можем скачать.
3. **Codex недоступен 2 дня** — что блокирует server-side acceptance test и deploy. Я могу подготовить всё, deploy сделается когда Codex вернётся (либо ты руками).

Я в это время делаю: funding_arb_v1 концепт + код, pass 2 code-review, ночной локальный backtest для acceptance v2 vs v2.1, дополнительные strategies на хорошие идеи.
