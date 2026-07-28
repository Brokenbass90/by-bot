# Master roadmap торговой станции

Дата фиксации: 2026-07-27
Локальный baseline: `5ee2713` до текущего пакета
Статус: единственный актуальный roadmap. Старые roadmap и chat prompts — история,
а не руководство к live-действиям.

## 1. Куда мы идём

Цель — не одна «идеальная» стратегия, а станция из 3–6 независимо доказанных
рукавов:

- один среднесрочный core;
- один relative/market-neutral sleeve;
- 1–2 тактических crypto sleeves;
- 1–2 event/FX/equity sleeves;
- общий allocator максимум на три одновременно открытые позиции;
- автоматическое понижение риска и остановка новых входов при деградации;
- повышение live-риска только после воспроизводимого receipt и ручного
  разрешения.

Законченная система умеет собирать причинные данные, повторять backtest тем же
execution contract, вести shadow, запускать маленький canary, измерять реальное
исполнение и заменять деградировавший sleeve. Она не обещает положительный
результат каждого месяца и не создаёт edge из отсутствующей рыночной
неэффективности.

## 2. Иерархия правды

Для live-фактов порядок такой:

1. прямой ответ брокера/биржи;
2. свежий heartbeat и процесс сервиса;
3. deploy receipt с хешами;
4. локальный Git;
5. AI snapshot и текстовые отчёты.

`strategy-flags=True`, наличие файла или красивый backtest не доказывают, что
рукав получает реальные деньги.

## 3. Денежная правда на момент фиксации

- Bybit: сервис активен, прямой запрос показал отсутствие позиций; equity около
  `1020 USDT`.
- ATT1 short-only — единственный денежный crypto sleeve, `risk_mult=0.10`.
- ATT1 не выключается календарём и не повышается автоматически.
- Alpaca — `SAFE_HOLD`: существующие ABBV/SCHW защищены брокерскими стопами;
  новая ротация не разрешена.
- XSEC, event, funding, FX/CFD и новые crypto families — без реальных ордеров.
- Funding paper теперь имеет 7 чистых post-cutover циклов после привязки ROI
  calculator к `opened_at >= 2026-07-27 10:53 UTC`: `0` wins, median
  `-0.1930%`, p25 `-0.2308%`; standalone economics остаётся отрицательной.
- 27 июля найден двойной локальный funding supervisor. Старый процесс
  остановлен; спорный интервал до cutover не используется для promotion.

## 4. Портфельная архитектура

| Слот | Назначение | Допустимые кандидаты |
|---|---|---|
| A | максимум одна среднесрочная позиция | BTC/ETH MIDTERM; позже PIT-major challenger |
| B | тактический/relative | ATT1, break-retest, XSEC |
| C | тактический/event | exhaust, sweep, event, FX/equity при независимом капитале |

Allocator обязан ограничивать:

- общий open risk;
- число позиций (`max=3`);
- одинаковую сторону и beta-кластер;
- overlap одного символа;
- корреляцию sleeves;
- конфликт среднесрочного и краткосрочного риска.

Цель `0 красных месяцев` измеряется на портфеле и на untouched OOS. Это не
условие перебора параметров: оптимизация именно под отсутствие красных месяцев
создаёт переобучение. Обязательные метрики — CAGR/annualized after-cost return,
число красных месяцев, худший месяц, max drawdown, recovery time, PF, sample
size и вклад каждого sleeve.

## 5. Единая лестница допуска

1. **Preregistration**: гипотеза, universe, costs, split, exit и gate фиксируются
   до просмотра результата.
2. **Causal backtest**: PIT universe, `known_at`, delistings/corporate actions,
   costs/funding/slippage и воспроизводимый trade ledger.
3. **Stress/OOS**: side split, regime split, walk-forward и отрицательные
   контроли.
4. **Risk-zero shadow**: реальные сигналы, отказы, latency, fill/non-fill и
   lifecycle без ключей/ордеров.
5. **Tiny canary**: только отдельное разрешение владельца.
6. **Scale ladder**: маленькими ступенями после live sample и execution health.

AI может собирать данные, диагностировать, ранжировать прошедшие gate и снижать
риск. AI не может сам повышать риск, менять сигнал, universe или открывать новый
денежный sleeve.

## 6. Активные контуры и ближайшие решения

| Контур | Сейчас | Блокер | Следующий gate | Реалистичный ориентир |
|---|---|---|---|---|
| ATT1 short champion | live tiny-canary `x0.10` | малая live-выборка | N20 — review; N30: net>0, PF≥1.20, DD≤3R, 0 incidents | N20 середина августа; N30 начало сентября при прежней частоте |
| ATT1 A3/3R | completed FAIL | at 11 bps: 3/4 folds, 4 red months, DD 17.46%; worse than champion | do not forward; preserve evidence | terminal 28 июля |
| ATT1 seasonality | completed FAIL | hour 21 UTC discovery не повторился | сохранить evidence; live filter не менять | terminal 28 июля |
| XSEC | risk-zero shadow, 3 решения | survivorship/PIT, funding, fill/cost, Sharpe formula | 10–15 чистых решений interim; 20–30 final | N10 около 4 августа; N20 около 14 августа; N30 около 24 августа при daily cadence |
| Event universe V2r2 | collector | ожидаемая coverage около 75%, не 100% | deadline 28 июля 18:19 UTC; frozen scorer | 29–30 июля PASS/FAIL/BLOCKED_DATA |
| Event retest long | causal identity есть | 8 data/performance/additivity contracts | frozen scorer, затем только risk-zero shadow | 1–3 недели, если coverage достаточна |
| Pump exhaustion short | frozen research | нужна новая post-window выборка | N≥40, sealed holdout N≥10 без retune | 2–5 недель по событиям |
| Funding arb | low-priority paper | 7 clean cycles, 0 wins, отрицательная distribution; duplicate incident | N20/N30 post-cutover, p25>0, median>0, annual floor≥8% | первичный gate только по фактическим циклам |
| Alpaca | SAFE_HOLD + shadow, 5 уникальных решений | Basic connector 3/3, но 9 exact-parity artifacts не закреплены; performance не считается | PIT materializer + exact broker-parity shadow | 3–10 дней на parity repair; 20 решений около 4 недель |
| FX/CFD | research-only | 9-family: 0 PASS; H4 stress 16/16 отрицательные | не rerun; новые prereg daily carry+trend и H4 families | 3–14 дней на новые sealed verdicts после реализации |
| LevelSnapshotV2 | design/parity infrastructure | нельзя скрытно менять ATT1 | design → replay parity → отдельный challenger | 1–3 недели |
| Web levels/reports | geometry snapshot уже сохраняется | нужна полная trade→decision→level связь | parity audit и visual regression | 2–7 дней |
| AI operator | observer/proposal-only | truth freshness, retry/model errors | verified context, bounded tools, audit trail | непрерывно; authority не расширять |

Ориентиры — сроки получения доказательства, не обещание promotion или прибыли.

## 7. Целевой пакет стратегий

### Crypto

- ATT1: sloped breakout continuation, long/short отдельно.
- Level rejection/bounce: horizontal и sloped отдельно.
- Break-and-retest: horizontal и sloped, long/short отдельно.
- Impulse breakout: expansion long/short.
- Exhaustion: pump fade short и dump exhaustion long.
- Sweep/reclaim: ложный вынос и возврат.
- Liquidity density: reaction/follow при наличии качественного L2/tape.
- MIDTERM: BTC/ETH H4/D1 trend/pullback; PIT-major challenger отдельно.
- XSEC: relative strength/weakness с PIT universe.
- Event: unlock, funding/OI positioning и редкие causal events.

Elder, seasonality, funding и OI по умолчанию являются фильтрами/features, а не
денежными sleeves, пока отдельный OOS не докажет обратное.

### Equities / Alpaca

- защищённый hold текущих позиций;
- PIT momentum/sector rotation;
- PEAD/event family;
- overnight/intraday decomposition;
- broker-native stop/trailing parity;
- только fractional-compatible исполнение при малом капитале.

Покупать Massive Starter/Developer сейчас не требуется. Сначала используется
Basic; платный тариф рассматривается только если конкретный data blocker
доказан receipt.

### FX/CFD

- D1 carry + trend;
- H4 breakout/retest;
- H1/H4 momentum;
- regime mean reversion;
- XAU как отдельный cost/volatility contract.

Каждый инструмент получает broker-specific spread, commission, swap,
contract-size и session model. До появления practice broker contract возможен
backtest, но не достоверный demo/live verdict.

## 8. Недельный execution plan: 27 июля — 2 августа

### P0 — целостность и live safety

1. Устранить двойной funding process; зафиксировать cutover incident.
2. Выпустить targeted equity fail-closed + ATT1 telemetry contract только
   против текущего серверного baseline.
3. Проверить direct-flat, heartbeat, DRY_RUN, money sleeves, ATT1 universe/risk
   и source SHA до/после.
4. Не копировать целиком drifted core и не делать `git pull` на live.

### P1 — завершить уже оплаченные временем исследования

1. Event V2r2: дождаться deadline, посчитать coverage и запустить frozen scorer.
2. XSEC: продолжать shadow; исправлять methodology только новой версией, не
   переписывать ledger.
3. Funding: один supervisor, post-cutover cohort, low-priority budget.
4. Alpaca: материализовать PIT/corporate actions/delisting и закрыть 9
   exact-parity blockers; Basic connector уже прошёл 3/3.
5. FX: сохранить 9-family/16 stress FAIL как baseline; неизменённо не
   перезапускать.

### P2 — новые bounded исследования

1. ATT1 sealed seasonality/filter study.
2. ATT1 A3/3R exact production replay.
3. Полный owner volume setup:
   dynamic volume universe → level/retest → measured entry → volume exit.
4. После Package A: token unlock data-availability probe.
5. FX D1 carry+trend prereg и H4 breakout/retest prereg.

Первые два ATT1 bounded исследования уже terminal:

- seasonality hour filter — `FAIL`, live filter unchanged;
- combined A3/fixed-3R — `FAIL`; current champion was stronger at every cost
  scenario and remains unchanged.

### P3 — инфраструктура

1. Canonical strategy/module/claim matrices (Claude Package A, WIP=1).
2. LevelSnapshotV2 design и trade→decision→geometry provenance.
3. Portfolio combiner на trade ledgers с three-slot constraints.
4. AI truth freshness, proposal audit trail и bounded restart только
   research-only supervisors.

Недельный supervisor проверяет состояние каждые 12 часов. Он может продолжать
или восстанавливать только research-only процессы; live risk/env/deploy остаются
запрещены без отдельного receipt.

## 9. Stop/retire правила

- Funding standalone sleeve: после N20 отрицательные p25/median или annualized
  ниже 8% → retire standalone; сохранить collector/features/execution code.
- Любой sleeve: causal/PIT defect → результат invalid, не «почти PASS».
- Красивый aggregate при провале одной стороны → стороны разделяются.
- Stress costs уничтожают edge → не продвигать, чинить execution или менять
  горизонт.
- Дубликат процесса, ledger race или неполный manifest → quarantine interval.
- Недостаток событий/данных → `BLOCKED_DATA`, а не ослабление gate.
- Retired означает сохранить доказательства и переиспользуемые компоненты, а не
  удалить идею или данные.

## 10. Когда можно увеличивать деньги

ATT1:

- N20 даёт только review;
- N30 и gate выше позволяют обсудить `0.10 → 0.15/0.20`;
- переход к сумме `$500–1000` не происходит одним шагом: сначала ограничение
  риска на сделку, затем несколько ступеней с live execution health.

XSEC/Alpaca/FX/event:

- сначала shadow и account-specific costs;
- затем tiny canary;
- капитал не выдаётся по headline backtest.

При капитале около `$1500` даже сильная система не превращается безопасно в
прожиточный доход сразу. Ближайшая цель — доказать несколько независимых edges,
сохранить капитал и получить воспроизводимую основу для масштабирования.

## 11. Что требуется от владельца

Сейчас для crypto research, XSEC, event, funding paper и Massive Basic — ничего.
Не присылать trade keys.

Позже:

- Massive API key хранится только локально в `.env`, не в чате/Git;
- OANDA practice либо MT5 specification нужны для точных FX/CFD costs;
- два trade-only API без withdrawal и средства на двух биржах нужны только
  после paper PASS;
- owner-label pack потребует ручной разметки 30 ослеплённых графиков.

## 12. Канонические документы

- `PROJECT_MASTER_ROADMAP_2026_07_27.md` — этот roadmap.
- `PROJECT_CANONICAL_INDEX_2026_07_27.json` — машинная карта.
- `WEEKLY_RESEARCH_QUEUE_2026_07_27.md` — операционная неделя.
- `TARGET_CRYPTO_STRATEGY_FACTORY_2026_07_27.md` — целевая crypto-архитектура.
- `CLAUDE_TASK_STRATEGY_FACTORY_VALIDATION_2026_07_27.md` — bounded задание
  Claude; сначала только Package A.
- immutable release/research receipts — доказательства, а не roadmap.

## 13. Supersession map

Без удаления помечаются историческими:

- `ROADMAP_V2_2026_06_30.md`;
- `ROADMAP_V3_TECH_STACK_2026_06_30.md`;
- `ROADMAP_V4_2026_07_01.md`;
- `ROADMAP_TIMELINE_2026_07_04.md`;
- `ROADMAP_WHERE_WE_ARE_2026_06_30.md`;
- `CRYPTO_PORTFOLIO_RECOVERY_PLAN_2026_06_26.md`;
- `ROADMAP_ALPACA_INTRADAY_2026_06_15.md`;
- старые `NEXT_CHAT_START_PROMPT_*`, canonical indexes и recovery checkpoints.

Файлы не перемещаются в грязном worktree до отдельной reference-map проверки.
`PROJECT_STATE_LEDGER.md` остаётся append-only историей и не является roadmap.
