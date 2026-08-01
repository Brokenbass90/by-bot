# Очередь новых стратегий — 2026-07-30

Статус: каноническая операционная очередь для crypto и FX/CFD.
Машинный контракт:
`configs/research/strategy_promotion_queue_20260730.json`.

## Ответ владельцу

Да, портфель расширяется. Но очередь теперь строится не по числу файлов и не
по максимальному backtest-проценту. Приоритет определяется четырьмя вещами:

1. качество и причинность данных;
2. независимость от уже имеющихся sleeves;
3. близость к проверяемому prospective lifecycle;
4. возможность пройти затраты и исполнение на доступном капитале.

Текущий лимит — пять долгих research-supervisor одновременно. Все пять слотов
заняты полезными risk-zero процессами. Новые задания не теряются: они получают
условие автоматического старта после terminal/interim receipt, а не запускаются
шестым конкурирующим процессом.

## Очередь запуска crypto

| № | Кандидат | Роль | Сейчас | Следующий доказательный шаг | Самый ранний money-review |
|---:|---|---|---|---|---|
| 1 | XSEC PIT V5 | relative/market-neutral | shadow, N5 | N10 + PIT/fill/cost receipt | середина–конец августа |
| 2 | Funding Positioning V4 | derivatives event | 72h FAIL economics, N11; bounded continuation active | N20; mean/median must turn positive | 3–8 августа review |
| 3 | Dynamic Funding Positioning | dynamic derivatives event | N12 BLOCKED_DATA audit: only COTI/BANK, 62.96% concentration | continuity/outlier audit, then N20 control | после audit/frozen review |
| 4 | BOUNCE1 virtual lifecycle | tactical long | code exists, evidence weak | exact SHA + untouched prereg + virtual fills/exits | после N20 shadow |
| 5 | BREAKDOWN regime V2 | tactical bear | code/regime gate exist | bear OOS + bull control + exit ladder | после N20 shadow |
| 6 | BTC/ETH Midterm Pullback V4 | slow core | old evidence non-independent | standalone ledger + walk-forward + funding stress | после N20 shadow |
| 7 | Owner Volume-Level Setup | owner tactical edge | three parts not integrated | volume universe → level/retest → entry → volume exit | event-driven |
| 8 | Pump Exhaustion Short V2 | event short | old viewed events | new N40 + sealed N10 | 2–5 weeks evidence |
| 9 | Sweep/Reclaim V2 | countertrend event | fragmented probes | horizontal/sloped × long/short physical tests | after level harness |
| 10 | OI Divergence | feature/event | data absent | causal OI collector + overlap with Funding | several weeks |
| 11 | Token Unlock | orthogonal supply event | calendar absent | known-at source/coverage probe | coverage-dependent |

### Важная динамика подбора монет

Dynamic universe не должен быть одним универсальным списком:

- XSEC ранжирует всю причинно допустимую кросс-секцию;
- Funding использует listing age, funding history, turnover и spread;
- BOUNCE/BREAKDOWN используют ликвидность плюс пригодность уровней;
- owner volume setup сначала выбирает приток объёма;
- pump exhaustion выбирает только новый movers cohort;
- midterm core остаётся BTC/ETH, PIT majors — отдельный challenger.

Так стратегии получают подходящую поверхность, но не выбирают монеты по
будущему PnL.

## Очередь FX/CFD

| № | Кандидат | Горизонт | Почему именно он | Следующий gate |
|---:|---|---|---|---|
| 1 | D1 Carry + Trend | D1 | **FAIL 2026-08-01:** stress annualized −0.98%, 10/20 красных месяцев | сохранить как отрицательный контроль; не продвигать |
| 2 | H4 Break + Retest | H4 | **FAIL 2026-08-01:** stress −24.26%, 22/25 красных месяцев, 0/4 положительных folds | не подбирать эту реализацию после просмотра результата |
| 3 | H4 Momentum | H4 | следующий независимый кандидат после двух terminal FAIL | sealed standalone OOS + portfolio additivity |
| 4 | H4 Regime Mean Reversion | H4 | противовес трендовым ногам | range-only OOS и catastrophic trend control |
| 5 | XAUUSD D1/H4 | D1/H4 | отдельный commodity CFD | отдельная арифметика pip/contract/swap и stress |
| 6 | SPX500/NAS100 CFD | D1/H4 | потенциальный equity-index sleeve | сначала broker contract/session/financing data |

OANDA KYC и депозит не нужны для первых пяти исторических исследований.
Публичный swap contract уже есть. Индексные CFD пока честно
`BLOCKED_DATA`, а не «почти готовы».

## Последовательность при освобождении WIP

1. Первый свободный FX-слот — H4 Momentum; D1 Carry + Trend и H4 Break + Retest уже terminal FAIL.
2. Второй — BOUNCE1 virtual lifecycle.
3. Первый свободный short-slot — BREAKDOWN regime V2.
4. После H4 Momentum — H4 Regime Mean Reversion с заранее замороженным range gate.
5. После освобождения measurement harness — BTC/ETH Midterm Pullback V4.

Cross-exchange funding при отрицательном N20 освобождает слот, но его scanner
и данные сохраняются. Funding Positioning и XSEC не останавливаются ради новых
идей до их ближайшего bounded receipt.

## Общая основа, которая не перетестируется с нуля

Повторно используются:

- causal/PIT universe snapshot;
- side/regime split;
- costs/funding/slippage contract;
- decision/fill/exit ledger;
- negative controls, LOSO и concentration;
- parameter/source SHA;
- общий allocator на три слота;
- breaker, exposure и health rails.

Новая стратегия тестирует собственный сигнал и совместимость с этой основой,
а не переписывает всю станцию. Изменение общей технологии сначала проходит
replay на сохранённых ledgers нескольких sleeves; только затем создаёт новую
версию execution contract.

## Что не запускается

- новый Elder как отдельный sleeve;
- внутридневной FX с движением меньше спреда;
- старый same-venue cash-carry;
- новые grid/scalper варианты с тесным стопом;
- AI auto-apply или автоматическое повышение live-риска;
- оптимизация специально под ноль красных месяцев.

Цель нуля красных месяцев оценивается только как результат объединения
независимых untouched OOS ledgers, а не как параметр подгонки.
