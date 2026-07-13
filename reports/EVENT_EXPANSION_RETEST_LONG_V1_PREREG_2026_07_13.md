# Event Expansion Retest Long v1 — phase-0 preregistration

> Historical freeze: не переписывать. Текущий causal authority —
> `reports/EVENT_EXPANSION_RETEST_LONG_V1_PHASE1_FREEZE_2026_07_13.md`.
> После усиления LevelSnapshot старый phase-0 hash preflight ожидаемо mismatch;
> performance/live по-прежнему запрещены.

Дата фиксации: 2026-07-13 10:32 UTC
Статус: **BLOCKED_RESEARCH_MECHANICS**
Performance: **PERFORMANCE_FORBIDDEN**
Live/broker/risk: **LIVE_FORBIDDEN**, `risk_pct=0`

Фактический phase-0 preflight 13 июля прошёл проверку identity:
`integrity_pass=true`, все pinned source/test/data hashes совпали. При этом он
правильно сохранил девять обязательных блокеров и не вычислял performance.

## Что зафиксировано

Это не бэктест и не разрешение на прогон. Phase 0 фиксирует уже проверяемую
каузальную механику и заранее объявляет данные, комиссии и будущие ворота до
появления performance-capable runner.

- implementation HEAD: `f07dd012810d55028d238fe5d6780e591768bb64`;
- отдельная физическая сторона: `long_only`;
- `LevelSnapshot v1`: только горизонтальный H1/H4 resistance -> flip support;
- наклонные уровни намеренно отложены в отдельный versioned contract;
- уровни не перерисовываются после возникновения event;
- обязательный порядок: closed H1 expansion -> более поздний closed M15 hold / первый retest -> более позднее M15 bullish structure confirmation -> следующий M5 open;
- same-bar collapse, future access, повторный retest, duplicate event/plan ID запрещены;
- exact closed-bar aggregation M5 -> M15/H1/H4 уже добавлена и hash-pinned, но ещё не соединена с event FSM единым оркестратором.

Полный машинный контракт:
`configs/preregistered/event_expansion_retest_long_v1_20260713.json`.

## Identity и качество данных

Phase-0 preflight сверяет SHA256 исходников, зависимости, тесты и текущий
immutable dev-manifest без импорта торгового кода и без вычисления доходности.

- dev13 manifest:
  `data_cache/immutable/pump_exhaustion_unwind_short_v1_720d_20260711/manifest.json`;
- SHA256: `f1f425e8822a5a8de56676fb24f257982d4c5fb33e254a328dc2b8243aedffd8`;
- окно: `[2024-07-15T00:00:00Z, 2026-07-05T00:00:00Z)`;
- исходный grain: M5;
- dev13: 1000PEPE, ADA, AVAX, BNB, BTC, DOGE, ETH, ONDO, SOL, SUI, TAO, WIF, XRP.

Этот manifest ранее создан для другого исследования. Его M5-бары пригодны как
зафиксированный development input, но название/история manifest не дают новому
long-рукаву никакого performance-доказательства. Dev13 имеет только право на
проверку mechanics и отдельную отчётность, не на promotion.

External8 фиксируется заранее без замены монет по результату:
`FIL, UNI, ETC, ICP, TRX, TON, MNT, IMX`. Корректная роль —
**strategy-untouched historical replication**, а не доказуемо untouched рынок:
исторические данные могли быть доступны в других контурах проекта. Настоящей
untouched выборкой станет только prospective-период после полного runnable
freeze и push; задним числом объявлять данные prospective запрещено.

## Почему performance сейчас запрещён

Preflight обязан вернуть следующие блокеры:

1. нет hash-pinned performance runner;
2. нет интегрированного H1-expansion / M15-retest / M5-next-open оркестратора и conformance-тестов;
3. нет замороженного exit simulator;
4. нет исполняемой cost/funding модели с receipts;
5. нет external8 M5 manifest;
6. нет point-in-time metadata external8;
7. нет liquidity/tradability manifest external8;
8. нет funding history external8;
9. нет same-window ATT1 reference: daily returns, trades, occupancy и equity.

Наличие чистой FSM или smoke-test не заменяет эти артефакты. Следующий runnable
freeze должен быть отдельным коммитом до первого доступа к результатам.

## Замороженные будущие условия

Стоимость на сторону:

- base: fee 6 bps + slippage 2 bps;
- stress: fee 10 bps + slippage 5 bps;
- funding credit = 0; debit = `max(actual debit, 5 bps)` на funding event;
- отсутствие funding data = fail closed.

Sizing: equity `$100`, risk `0.5%`, notional cap `$30`, максимум 4 позиции в
портфеле и 1 на символ.

Будущая оценка использует четыре фиксированных 150-дневных fold в первых 600
днях, 7-дневный embargo после границ и финальный 120-дневный holdout. Все ворота
обязательны одновременно:

- base PF >= 1.35; stress PF >= 1.25; stress N >= 60;
- каждый fold N >= 8; минимум 3/4 fold net-positive; median fold PF >= 1.10;
- holdout stress N >= 12, netR > 0, PF >= 1.10;
- conservative stress DD <= 8%; duplicate IDs = 0; invalid/censored = 0; long purity = 100%;
- dev13 traded/positive >= 7/4; external8 >= 6/4;
- top-positive-net concentration <= 30%;
- worst LOSO stress PF >= 1.05, netR > 0, DD <= 10%;
- с ATT1: |daily correlation| <= 0.35, |downside correlation| <= 0.45, co-loss Jaccard <= 0.40;
- в худшем из `ATT1_FIRST` / `EVENT_LONG_FIRST`: сохранить >= 70% long trades,
  combined net >= ATT1 net + 25% standalone long net, DD <= 1.10x ATT1,
  return/DD >= 1.10x ATT1, worst month не хуже ATT1 более чем на 0.50 п.п.

Даже полный PASS не включает live автоматически: сначала отдельный review,
shadow/demo и новое разрешение риска.

## Воспроизводимая проверка

```bash
python3 scripts/preflight_event_expansion_retest_long_v1.py
pytest -q tests/test_preflight_event_expansion_retest_long_v1.py
```

Ожидаемый здоровый phase-0 результат — integrity PASS при одновременном
`BLOCKED_RESEARCH_MECHANICS / PERFORMANCE_FORBIDDEN`. Любое несовпадение хеша,
cohort, cost или gate добавляет critical blocker и возвращает ненулевой код.
