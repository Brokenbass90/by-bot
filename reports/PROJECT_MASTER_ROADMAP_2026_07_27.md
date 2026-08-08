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
| XSEC | risk-zero shadow, 4 решения | survivorship/PIT, funding, fill/cost, Sharpe formula | 10–15 чистых решений interim; 20–30 final | N10 около 4 августа; N20 около 14 августа; N30 около 24 августа при daily cadence |
| Event universe V2r2 | terminal: 1h/4h FAIL, 24h BLOCKED_DATA | aggregate negative; 24h incomplete | new short-only prereg with PIT regime/beta, no threshold reuse | discovery preserved; no money |
| Event retest long | causal identity есть | 8 data/performance/additivity contracts | frozen scorer, затем только risk-zero shadow | 1–3 недели, если coverage достаточна |
| Pump exhaustion short | frozen research | нужна новая post-window выборка | N≥40, sealed holdout N≥10 без retune | 2–5 недель по событиям |
| Funding arb | low-priority paper | 12 clean cycles, 2 wins, median -0.1671%, p25 -0.2238% | N20/N30 post-cutover, p25>0, median>0, annual floor≥8% | 8 cycles remain to initial gate |
| Funding positioning V4 | historical maker gate PASS to shadow | queue position and prospective fill lifecycle | public 72h shadow, then N20 | first lifecycle receipt 1–3 days |
| Alpaca | SAFE_HOLD + shadow, 6 уникальных решений | Basic connector 3/3, но exact exit/parity не закреплены | PIT materializer + exact broker-parity shadow | 20 решений около 3 недель при daily cadence |
| FX/CFD | research-only; public swap contract materialized | `.pro` commission unknown; prior H4 families failed | sealed D1 carry+trend and new H4 base/stress | first new verdicts after harness side-swap repair |
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

29 июля публичный OANDA swap contract снял data-blocker для исторического
этапа. KYC, utility bill и депозит не требуются до demo/live execution.
Финансирование обязано моделироваться отдельно по long/short, а неизвестная
комиссия `.pro` покрывается обязательным stress-arm.

Первые два ATT1 bounded исследования уже terminal:

- seasonality hour filter — `FAIL`, live filter unchanged;
- combined A3/fixed-3R — `FAIL`; current champion was stronger at every cost
  scenario and remains unchanged.

### P3 — инфраструктура

1. Canonical strategy/module/claim matrices (Claude Package A audited
   PARTIAL/BLOCKED; archive moves remain uncommitted).
2. LevelSnapshotV2 design и trade→decision→geometry provenance.
3. Portfolio combiner на trade ledgers с three-slot constraints.
4. AI truth freshness, proposal audit trail и bounded restart только
   research-only supervisors.

Недельный supervisor проверяет состояние каждые 12 часов. Он может продолжать
или восстанавливать только research-only процессы; live risk/env/deploy остаются
запрещены без отдельного receipt.

Аудит Package A 28 июля выявил, что заявленный “ASB1 long” является
`alt_support_bounce_v1/BOUNCE1`, а не live ASB1. Сохранённые цифры считаются
exploratory: окна пересекаются, power недостаточна и `risk_mult=0` не создаёт
virtual trade lifecycle. Поэтому архивные переносы не коммитятся, а следующий
bounded implementation — отдельный BOUNCE1 decision/fill/exit shadow ledger и
untouched prereg.

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
- N30 и gate выше разрешают bounded step `0.10 → 0.15` без повторного
  вопроса владельцу; следующий шаг до `0.20` требует ещё одного чистого
  live-review;
- переход к сумме `$500–1000` не происходит одним шагом: сначала ограничение
  риска на сделку, затем несколько ступеней с live execution health.

Standing owner authorization от 28 июля распространяется только на маленькую
ступень после заранее записанного gate. Она не разрешает повышать риск ради
частоты, обходить OOS/shadow, менять signal/universe или включать новый money
sleeve без deploy receipt.

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

## 14. Checkpoint 28 июля 11:48 UTC

- Claude package принят частично и пересобран через независимые receipts:
  `reports/CLAUDE_PACKAGE_ACCEPTANCE_2026_07_28.md`.
- Autoresearch теперь логирует raw search counts; effective independent trials
  не подменяются количеством соседних grid rows. Significance toolkit покрыт
  focused tests, DSR остаётся advisory до честного dependence contract.
- XSEC V4 прошёл дешёвый family landscape: `36/36` положительных вариантов,
  median `+35.86%`, champion 75th percentile. PIT work оправдан, capital
  по-прежнему запрещён.
- Alpaca исторический proxy локализовал дефект в shared exit. SPY gate полезен,
  но текущая полная модель отрицательна. Calendar-hold arm сильно лучше на
  recent survivor proxy, однако требует distant safety stop, PIT и untouched
  replay. SAFE_HOLD сохранён.
- BOUNCE1 не является ASB1; virtual lifecycle всё ещё следующий crypto repair.
- Архивные moves и graph prototype не приняты: сначала registry/reference map
  и visual/provenance gates.
- Direct Bybit truth: service active, equity `$1020.10`, positions empty,
  query OK. Live risk/signal/universe не менялись.

## 15. Crypto expansion audit 28 июля

- Claude regime-book arithmetic independently reproduced:
  `+11.08 / +8.70 / +1.71`, but verdict is `SHADOW_GO / MONEY_NO_GO`.
  Two windows have only 31–37 trades and BOUNCE1 was tuned on the same
  windows. Expanded alt universe materially lowers PF; losing DOT is retained
  in shadow to prevent symbol cherry-picking.
- Config collision removed: slope-break uses canonical `ASLB1_*`,
  support-bounce uses `BOUNCE1_*`; `ASB1_*` is legacy fallback only.
- BREAKDOWN now has a separate fail-closed capital regime gate. A stale,
  missing, bull or neutral overlay cannot silently authorize the short sleeve.
- BOUNCE1 has a persistent risk-zero decision/fill/partial-target/exit ledger
  and an eight-symbol frozen shadow config. No broker calls or live risk.
- Massive Stocks Basic is already configured and reverified 3/3. No owner
  purchase or new key is required for the next Alpaca PIT prototype.
- Live server Git HEAD is still `f7ed011`, but the dirty monolith already
  contains the later signal-level geometry code. No new position has created a
  geometry snapshot yet, so live visual proof and a reproducible deploy receipt
  remain pending. Web replay remains a prototype until it consumes the same
  immutable trade geometry receipt.

## 16. Control-plane and funding checkpoint 28 июля

- The two-layer D1/H4 regime detector, allocator, decision bus, health monitor,
  cross-sectional ranker and exposure gate already exist. The missing layer is
  competitive slot assignment: live allocator remains `disabled/approved_env`
  and does not award the three slots by expected after-cost value.
- Added a deterministic priority-router library. It ranks immutable candidates
  by expected net R discounted by evidence, regime fit, live health, execution,
  cost stress and symbol rank; it cannot create edge or authorize money.
- Live wiring stays risk-zero until ATT1, BOUNCE1, BREAKDOWN and XSEC emit a
  common parity-checked candidate schema and ledger replay improves the
  portfolio versus first-signal-wins.
- Regime builders no longer write the shared `ASB1_ALLOW_*` direction keys:
  slope-break uses `ASLB1_*`, support-bounce uses `BOUNCE1_*`.
- BOUNCE1 server/local SHA mismatch is explained by this prefix-only change.
  The server file equals the exact pre-isolation Git version and legacy-env
  replay parity is unchanged; a full re-tune is not required.
- Funding positioning V2 repaired percentile ties, overlap, funding cashflows,
  PIT regime and beta diagnostics. The result is not terminal: 8h maker proxy
  remains mildly positive after beta, while longer holds look stronger but
  require a three-slot untouched V2.1 and incremental ATT1/BREAKDOWN replay.
- Hour-of-day seasonality remains `FAIL` for filtering: 52.6% of shuffled
  controls produce an equally strong best-hour illusion.

## 17. Dynamic-universe, FX-cost and observability checkpoint 29 июля

- Funding Positioning V4 now has two isolated prospective shadows: the frozen
  eight-symbol control and a causal 16-symbol dynamic-liquidity challenger.
  Dynamic selection uses listing age, turnover, spread and funding-history
  coverage only; it never ranks on signal or PnL. First review is N20 closed
  lifecycles, estimated at 5–10 days.
- Cross-exchange funding paper is N12 with 2 wins, median `-0.1671%` and five
  open cycles. At current cadence N20 is expected around 31 July–1 August. The
  automatic standalone-sleeve retirement rule remains binding.
- Public OANDA costs are now executable in the V2 harness with signed,
  side-specific daily swap cashflows. No KYC/deposit is required for the
  historical phase. New D1/H4 runs must use a fresh preregistration rather than
  mutating old SHA-pinned receipts.
- Onboard AI context now receives a conservative technology inventory.
  `tested_static_runtime_not_observed` is discovery evidence, not a promotion
  claim. The web has a read-only Book Status API/page for sleeve health and
  gate counts.
- Direct live truth remains flat and healthy. ATT1 is enabled; the last entry
  was 24 July and current silence is explained by cooldown plus valid
  no-signal geometry. No live money mutation was made.
- Canonical operational handoff:
  `reports/RECOVERY_EXECUTION_UPDATE_2026_07_29.md`.

## 18. Strategy promotion queue checkpoint 30 июля

Добавлена единая машинно-проверяемая очередь:

- `configs/research/strategy_promotion_queue_20260730.json`;
- `reports/STRATEGY_PROMOTION_QUEUE_2026_07_30.md`;
- `scripts/validate_strategy_promotion_queue.py`.

Очередь не создаёт live authority и фиксирует `capital_authorized=false`.
Текущие пять risk-zero supervisor занимают WIP полностью; длинная шестая
задача не стартует до bounded/terminal receipt.

Порядок следующего запуска:

1. первый свободный WIP — FX D1 carry+trend;
2. второй — BOUNCE1 virtual lifecycle;
3. отдельный short-slot — BREAKDOWN regime V2;
4. после D1 base receipt — FX H4 break/retest;
5. затем exact BTC/ETH midterm pullback.

Crypto очередь содержит 11 физических кандидатов, FX/CFD — 6. Это не
17 будущих money sleeves: очередь заранее фиксирует, какие кандидаты являются
feature/data probes, какие могут стать самостоятельным sleeve, и какой receipt
обязан существовать до следующей стадии.

Dynamic universe определяется отдельно для каждой стратегии. Funding и XSEC
уже используют причинные eligibility rules; BOUNCE/BREAKDOWN требуют
level-quality eligibility, owner-volume setup — volume inflow, pump exhaustion
— новый movers cohort. BTC/ETH midterm core не расширяется сегодняшним списком
альтов; PIT-major expansion остаётся отдельным challenger.

## 19. Anticrisis and self-healing checkpoint 8 августа

- ATT1 calendar expiry removed under standing owner approval. Live remains
  short-only, risk 0.10 and the same eight-symbol universe. Fresh cohort starts
  2026-08-08; previous mixed accounting cannot be used to scale it.
- BOUNCE1 BTC/ETH exact replay produced 3/3 positive windows and 41 trades.
  It is deployed as prospective risk-zero shadow; N20 and exact
  geometry/source/config parity remain binding before a money decision.
- Funding-positioning has 42 closed outcomes and promising central tendency,
  but fails concentration because BLESS contributes about 69% of total net.
  A separate post-N42 frozen 16-symbol cohort is now running from N0; its
  20–30 new outcomes are the next falsification.
- XSEC v3 remains no-go interim (4/11 positive, aggregate markout negative).
  SQB1 offset-1 and all legacy FX price-only families are terminal for their
  current formulations, not for the wider themes.
- Alpaca remains SAFE_HOLD. Fractional stop-replace payload is fixed, but a
  market-open broker acceptance receipt, broker-fill reconstruction and one
  exact rotation are required before staged capital expansion.
- A unified proposal-only project-audit registry now joins deterministic
  static checks, all-strategy liveness, technology reachability and bounded
  Ollama/Qwen review. First registry has only 6 actionable findings after
  noisy-rule suppression; 187 additional records are inventory triage, not
  proven defects. Full liveness refresh is running, then the cheap cycle runs
  every six hours.
- Next foundation increment is strategy failure phenotypes plus an isolated
  patch/test queue. The self-healing path is observe → reproduce → patch in an
  isolated branch → parity/OOS tests → reviewed targeted deploy. Local AI is
  never allowed to mutate live risk or orders directly.

Current handoff: `reports/ANTICRISIS_STATUS_AND_NEXT_HANDOFF_2026_08_08.md`.
Audit contract: `reports/SELF_HEALING_AUDIT_PIPELINE_2026_08_08.md`.
