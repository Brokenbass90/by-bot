# Ускоренная фабрика стратегий — 2026-08-02

## Что не обнулилось

Месяц ATT1 не выброшен. Валидны signal decisions, market data, broker fills,
entry geometry и закрытые lifecycle после broker reconciliation. Найденный
qty-step defect затрагивал внутреннюю оценку остатка после partial TP, а не
право стратегии на сигнал. DOT/LTC остаются в статистике.

Отдельный вопрос — качество разрешённого расстояния до линии. Это новая
single-variable проверка, а не перезапуск всей стратегии и не новый нулевой N.

## Новая скорость работы

Воронка разделена на четыре скорости:

1. **Часы:** VectorBT/NumPy проверяют 100–1000 вариантов как necessary-condition
   prefilter. Красивые train-результаты без OOS выбрасываются сразу.
2. **1–3 дня:** train-only Optuna/pruning для семейств, переживших первый слой.
   OOS не используется как objective; сохраняются planned/evaluated trials.
3. **Дни:** native event-driven replay с PIT, costs, LOSO, regimes, negative
   controls, source/params SHA и immutable ledger.
4. **Недели только для победителей:** prospective shadow и tiny canary.

Live-месяц больше не должен быть первым местом, где обнаруживается отсутствие
базовой экономики.

## Первая массовая crypto-волна

Завершён `vectorbt_crypto_prefilter_20260802`: 170 вариантов, восемь монет,
следующий-open execution, base 8 bps round-trip и stress 18 bps. Семейства:

- EMA trend continuation, long/short отдельно;
- z-score regime-agnostic reversion, long/short отдельно;
- Donchian breakout, long/short отдельно;
- liquidity sweep/reclaim, long/short отдельно;
- pump/dump exhaustion reversal, long/short отдельно.

Отбор финалистов выполняется только на chronological train. На OOS идут три
замороженных кандидата каждого семейства. Даже OOS-победитель не получает
promotion: сначала он переносится в native engine.

### Первый результат фабрики

- EMA trend, Donchian, z-reversion и sweep/reclaim дали красивые train-лидеры,
  но развалились на OOS; они остановлены за часы, без месяца live-ожидания.
- Семейство `dump exhaustion reversal long` прошло discovery OOS у 3/3
  train-frozen arms даже при 18 bps stress costs. Широкий arm был положителен на
  7/8 символах.
- Native replay подтвердил положительный общий эффект у 3/3 arms и сотни
  сделок, но строгий gate вернул `FAIL_NATIVE_ROBUSTNESS`: один из четырёх
  временных блоков отрицателен почти по всей ширине, а concentration limit не
  выдержан.
- Кандидат не удалён: он переведён в задачу causal regime discriminator. Это
  не разрешение на shadow или деньги; просмотренный OOS больше не называется
  untouched.

## Очередь native crypto-кандидатов

1. ATT1 entry-distance ablation — улучшение живой ноги без смены идеи.
2. BOUNCE1 exact-SHA virtual lifecycle — ближайший tactical long.
3. BREAKDOWN regime V2 — short только в доказанном bear-контексте.
4. BTC/ETH Midterm Pullback V4 — медленный независимый core.
5. Owner Volume-Level Setup — volume universe → level/retest → volume exit.
6. Dump Exhaustion Reversal Long — regime repair после успешной общей экономики.
7. Pump Exhaustion Short V2 — только новый frozen movers cohort.
8. Sweep/Reclaim V2 — horizontal/sloped × long/short как четыре гипотезы.
9. XSEC PIT — relative sleeve, если prospective markouts восстановятся.
10. Funding Positioning — frozen terminal и dynamic LOSO/concentration.
11. OI divergence — сначала причинный collector.
12. Token unlock supply events — только known-at calendar.

Elder, grid и тесный scalping не удаляются как идеи навсегда, но не получают
бюджет до новой причинной версии, меняющей прежний доказанный failure mode.

## Новая FX/CFD-волна

Четыре старых price-only реализации закрыты, но рынок не закрыт. Следующие
семейства должны менять источник edge:

1. cross-pair relative strength / currency basket residual;
2. session carry и London/New York inventory transfer;
3. rate-differential surprise, а не статический carry;
4. commodity-FX linkage для AUD/CAD/JPY;
5. отдельный XAU D1/H4 contract;
6. SPX500/NAS100 overnight/session continuation после financing contract;
7. volatility expansion after compression with session and cost gates;
8. cross-market risk-on/risk-off allocation.

Для каждого семейства сначала 20–100 дешёвых arms; финальный verdict выдаёт
только event-driven OOS со spread, commission, swap, gaps и session closures.

## Open-source contract

Создан отдельный `.venv-research` на Python 3.12:

- VectorBT `1.1.0` — массовый research-only prefilter;
- Optuna `4.9.0` — train-only search/pruning;
- live VPS и core dependencies не изменены;
- внешние библиотеки не имеют API keys, order/risk/env authority;
- финальный сигнал всегда повторяется собственным causal engine.

## Операционный ориентир

Первый crypto prefilter уже завершён; освобождённый слот отдан single-variable
ATT1 entry-distance ablation. Цель ближайших 7 дней — получить Funding N20,
XSEC N10, ATT1 ablation и prereg режима для dump exhaustion, затем отдать
следующий native слот BOUNCE1. Цель 2–6 недель — не «обещанные 3 стратегии», а минимум один новый
tiny-canary либо честный terminal FAIL с немедленной передачей слота следующему
кандидату. Одновременно продолжаются Alpaca adaptive и новая FX-фабрика.
