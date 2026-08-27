# Фазовый портфель: от двух кандидатов к управляемой системе

Обновлено: 2026-08-27. Статус: архитектурный и исследовательский план; этот
документ не меняет live-конфиг, риск, ордера или money authority и не открывает
зарезервированные данные.

## Executive Summary

- **Заморозка ATT1/SBR1 не останавливает стратегии.** Она фиксирует один точный
  контракт для проверяемого эксперимента. Действующий ATT1 tiny-контур,
  широкие zero-risk тени и Alpaca protection продолжают жить в рамках уже
  выданных полномочий.
- **Конечный продукт — не десять одновременно торгующих алгоритмов.** Это
  библиотека из десяти раздельно доказанных рукавов, из которой причинный
  режимный слой допускает уместные стратегии, а аллокатор выбирает только
  независимую комбинацию в пределах общего stop-risk и корреляции.
- **Сегодня существуют два главных крипто-кандидата, защищаемый Alpaca-контур,
  исследовательский funding-кандидат и XAU-зацепка.** Остальные рукава ниже —
  новые гипотезы или переиспользование механизмов отклонённых старых версий.
  Наличие кода не считается доказательством доходности.
- **Следующие 30 дней не должны быть ожиданием.** Сначала получается быстрый
  диагностический вердикт по ATT1/SBR1; параллельно готовятся две независимые
  крипто-гипотезы, Alpaca lifecycle, XAU demo journal и Pattern Atlas v2. Если
  ATT1/SBR1 не проходят, точные конфигурации закрываются без спасательного
  тюнинга, а вычислительный слот сразу переходит плану B.

## Как портфель принимает решение

```text
проверенные данные
  -> причинный режим (trend/range/volatility/liquidity)
  -> раздельные strategy sleeves
  -> собственный admission gate каждого sleeve
  -> exposure/correlation gate
  -> allocator общего stop-risk
  -> execution + биржевые стопы
  -> broker/runtime auditor
```

Режим не создаёт сигнал и не «угадывает рынок»: он только допускает или
запрещает уже доказанный рукав. Аллокатор не исправляет слабую стратегию:
стратегия сначала самостоятельно проходит исторический и prospective gate.
ИИ/Ollama может искать аномалии и предлагать опыты, но не может менять стадию,
риск или ордер.

### Общий контракт допуска

Для новых гипотез минимальный исторический пакет одинаков: причинные закрытые
свечи, фиксированные universe/параметры, next-open исполнение, base и stress
costs, хронологические folds с embargo, breadth/LOSO, концентрация, просадка и
заранее выбранный baseline или time-matched random control. Исторический PASS
разрешает только zero-risk shadow. Деньги требуют caller parity, полного
lifecycle, broker reconciliation, чистой prospective выборки и отдельного
release receipt.

## Десять рукавов и их реальные стадии

| # | Рукав и класс | Фаза / сторона / горизонт | Текущий статус | Что уже можно переиспользовать | Следующий исторический gate | Следующий live gate | Главные конфликты экспозиции |
|---:|---|---|---|---|---|---|---|
| 1 | **ATT1 flat-down short** — существующий кандидат | боковик с уклоном вниз; short; H1-сигнал, до 336 ч | tiny money существует на старом контракте; live-native кандидат и regime gate исследовательские, без нового money authority | persisted BTC H1 regime, caller receipts, exact geometry adapter, ON/OFF replay, fixed-51 evidence path | зарезервированный OOS-диагностический прогон с известной контаминацией, base/stress и замороженными thresholds; не называть его pristine proof | exact current caller, fill/stop/time-stop replay, exposure gate, prospective shadow; затем отдельный tiny release | не суммировать с bear-trend short на том же символе; общий BTC/alt beta и short stop-risk |
| 2 | **SBR1 flat-up long** — существующий кандидат | боковик с уклоном вверх; long; H1, до 168 ч | fixed-51 zero-risk shadow и детерминированный random control; money authority отсутствует, admitted решений пока нет | live-native adapter, causal regime, fixed-51 coverage manifest, hash journal | тот же ограниченный OOS-диагностический пакет; затем prospective сравнение с control, минимум 50 закрытых решений для окончательного вывода | caller/fill/stop parity, slots/exposure replay и отдельная tiny-canary авторизация | конфликтует с range-long и bull-trend long на одном символе; не дублировать long beta |
| 3 | **Bull trend continuation / pullback long** — новая приоритетная гипотеза | устойчивый H4/D1 uptrend; long; H1/H4, дни–недели | новой frozen версии нет; старые midterm/event наработки не дают promotion authority | event IDs, horizontal LevelSnapshot, causal H1/H4 aggregation, BTC leader features, order/fill adapters | один prereg: тренд до входа → импульс → первая контролируемая коррекция/retest; отдельный BTC/ETH и fixed-alt cohort, time control, base/stress | zero-risk shadow с фактической задержкой и гэпами; затем один tiny slot | не включать одновременно с SBR1/range-long на том же активе; общий long beta и кластер альткоинов |
| 4 | **Bear trend continuation / correction short** — новая гипотеза | устойчивый H4/D1 downtrend; short; H1/H4, дни–недели | готовой доказанной ноги нет; ATT1 не является её заменой | causal regime, sloped/horizontal snapshots, break/retest primitives, execution adapters | отдельный prereg с первой коррекцией после подтверждённого downside break; без инверсии или ретюнинга ATT1 | zero-risk shadow и caller parity; money только после совместного replay с ATT1 | взаимоисключение/priority rule с ATT1; общий short beta, squeeze и gap risk |
| 5 | **Horizontal range rejection** — новая сторона-раздельная гипотеза | чистый range; long от поддержки / short от сопротивления; M15/H1, часы–дни | дизайн; старые generic range/FX reversion версии были отрицательны | horizontal LevelSnapshot, first-retest, level age/touches, causal regime, order-block annotations | long и short считать раздельно; level-quality ablation, random-time/control-level baseline, costs и overlap | shadow только при подтверждённом range; hard-off при expansion/trend | противоположен trend/volatility sleeves; одна позиция на symbol-level episode |
| 6 | **Volatility expansion + breakout/retest** — независимая гипотеза после отказа v1 | сжатие → expansion; стороны раздельно; M15/H1, 6–72 ч | старый horizontal breakout-long 72h получил `NO_PROMOTION`; повторять или спасать его нельзя | Pattern Atlas, event universe, LevelSnapshot, impulse/retest features, M5 execution | новый причинно отличный контракт: expansion quality + first retest, фиксированный horizon и контроль; не повтор старого breakout-only | zero-risk event journal, fill probability/adverse selection и cluster cap | взаимоисключение с range mean-reversion; массовые одновременные сигналы требуют event-cluster limit |
| 7 | **Exhaustion → CHoCH reversal** — новая редкая гипотеза | истощение тренда и подтверждённый слом; против прежнего тренда; M15/H1, часы–дни | старый pump-unwind был `NO_PROMOTION`; TD Sequential/imbalance — только features | event tape, MFE/MAE forensics, CHoCH/BOS primitives, TD/exhaustion annotations | prereg требует сначала exhaustion, затем causal structure break; сравнение с продолжением тренда и time control, жёсткий multiplicity budget | редкий low-risk shadow; денежный режим только после stop-first/gap stress | запрещён до фактического ослабления incumbent trend; противонаправленная позиция не должна маскировать hedge |
| 8 | **Funding/basis market-neutral** — существующий research-кандидат | любой directional regime при исполнимом спреде; hedged long/short; 8–24 ч | V3 `p70/16h` допущен только к research shadow; новые forward mean/median зависят от хвостов и концентрации; cross-exchange v2 инвалидирован | public venue metadata, funding ledgers, three-slot selector, fee/funding accounting, L2/tape collectors | свежая frozen cohort с actual settlement, maker fill/adverse selection, p25/median, LOSO и concentration; никаких старых денежных прогнозов | двухногий atomic/recovery paper lifecycle, margin/liquidation/transfer kill switches; только затем canary | directional beta должна быть около нуля; collateral, venue, stablecoin и simultaneous-leg risk считаются отдельно |
| 9 | **Alpaca monthly adaptive long-or-cash** — существующий защищаемый контур | месячная momentum/regime selection; long или cash; дни–месяц | SAFE_HOLD: защита старых позиций работает; новые покупки заморожены; challenger остаётся diagnostic | adaptive selector, fill-relative stop, monotonic floor, 15m health auditor, default-off whole-share profile | точный frozen replay на PIT/XNYS/corporate actions/delistings, gap stress и сравнение current profile с challenger | полный prospective `signal → actual fill → protection → rearm → management → exit`; затем one-slot tiny canary | equity beta и overnight gap; капитал/слоты Alpaca не смешивать с crypto allocator без общего risk budget |
| 10 | **XAU/FX multi-timeframe trend/session** — существующая зацепка, новая версия | D1/H4 regime → H1 structure → M15 entry; long/short отдельно; часы–дни | zero-order paper core готов; старый XAU session breakout/retest лишь diagnostic (`N=13`), Bullwaves ingestion и money authority отсутствуют | immutable XAU M5, session breakout/retest, gap/cost journal, MT5-safe setup, LevelSnapshot/order-block features | новый XAU prereg с account-specific spread/swap/news; session baseline как reference, trend/range/reversal раздельно | read-only Bullwaves/MT5 demo journal + random control, затем paper orders только после identity/cost parity | USD/rates/news, overnight/weekend gap и broker-specific margin; XAU не объединять с generic FX до отдельной корреляционной проверки |

**Классификация важнее количества.** Рукава 1–2 — текущие главные crypto
кандидаты. Рукава 8–10 имеют работающие исследовательские компоненты, но не
money proof. Рукава 3–7 — новые bounded hypotheses; старые отклонённые версии
разрешают переиспользовать инфраструктуру, но не результаты.

## Что именно делает оркестратор и аллокатор

Оркестратор получает только причинное состояние, рассчитанное до сигнала:
направление/наклон тренда, расстояние от EMA/структуры, volatility state,
liquidity/data-health и freshness. Он создаёт список допустимых рукавов, а не
сам вход.

Аллокатор работает после сигналов и применяет пять обязательных ограничений:

1. один активный episode/position на символ и сторону;
2. лимит общего stop-risk и отдельный лимит на рынок/брокера;
3. correlation/cluster cap для одновременных altcoin или event-сигналов;
4. запрет конфликтующих режимов, например range-reversion вместе с expansion;
5. приоритет доказательности: live-proven > prospective > shadow; hypothesis
   без money authority всегда получает ноль денежного веса.

Это означает, что появление десяти рукавов не увеличивает риск автоматически.
В конкретный момент портфель может держать ноль, один или несколько
действительно независимых допущенных рукавов.

## Pattern Atlas v2: научный поиск фигур без индикаторной свалки

У лаборатории уже есть Pattern Atlas v1: `20,372` причинных траекторий и
`8,840` time-controls. Его единственный breakout-long lead затем провалил
отдельный costed scorer, поэтому v2 должен задавать новые вопросы, а не
перебирать настройки старого победителя.

Следующий атлас фиксирует **эпизод до результата**:

- тип и возраст уровня: horizontal в первой версии; causal sloped, order block
  и imbalance только после отдельных point-in-time passports и исправленного
  non-overlap/control engine;
- число касаний, время между ними и остаточная ширина зоны в ATR;
- длина/скорость импульса, breakout distance и объёмное расширение;
- первый retest: глубина, задержка, wick/body acceptance, reclaim/failure;
- bounce count и длина удержания до повторного теста;
- causal trend/range/volatility regime и ликвидность на момент решения;
- исходы на `6/24/72/168/336h`: return, MFE, MAE, time-to-MFE и false-break;
- time-matched и regime-matched random controls, overlap/concentration и
  multiple-testing ledger.

Первый проход — описательная статистика пути без P&L-продвижения. Только один
или два заранее объявленных независимых lead получают отдельный costed
next-open scorer. Это позволяет изучать рынок быстро, но не выдавать красивую
фигуру за торговое доказательство.

## 30-дневная последовательность без пассивного ожидания

### Дни 1–3: получить поворотный вердикт

1. Закрыть metadata-only preflight зарезервированного ATT1/SBR1 diagnostic:
   точный M5 input manifest, frozen one-shot runner и независимая audit-команда.
2. Не открывать строки до отдельного разрешения владельца. После разрешения —
   один запуск, один audit, заранее заданные PASS/FAIL/INCONCLUSIVE.
3. Зафиксировать эту таблицу рукавов и exposure graph как versioned registry.

Инженерная цель третьего дня — готовность к решению по точным ATT1/SBR1
контрактам. Это не календарное обещание: если точного M5-манифеста или
независимого аудита нет, контур остаётся fail-closed и публикует конкретный
blocker вместо чтения данных обходным путём.

### Дни 4–7: развести ветку PASS и план B

- При диагностическом PASS: подключить candidate contract только в default-off
  zero-risk caller, выполнить exact fill/stop/time-stop и joint exposure replay.
- При FAIL: закрыть точную конфигурацию без повторного поиска на увиденном окне;
  сохранить adapters/regime/data и немедленно освободить вычислительный слот.
- Независимо от результата: заморозить один bull-trend continuation prereg и
  Pattern Atlas v2 ontology; завершить Alpaca month-end lifecycle manifest.

### Дни 8–14: две новые независимые дорожки

1. Прогнать bounded bull-trend long и bear-trend short на development history
   с фиксированными сторонами, costs, folds и controls.
2. Запустить XAU/Bullwaves read-only demo journal после безопасной проверки
   identity/token; ордеров нет.
3. Проверить Alpaca exact current-profile lifecycle, gap stress и default-off
   whole-share profile. Один удачный старый trailing exit не заменяет цикл.

### Дни 15–21: закрыть фазовые дыры

1. Пререгистрировать long/short horizontal range rejection.
2. Пререгистрировать один причинно новый volatility expansion/retest контракт;
   старый breakout-72h не повторять.
3. Пересчитать funding shadow по actual settlements, maker fills,
   adverse-selection и concentration.
4. Собрать portfolio ledger, где все рукава переводятся в общий R и имеют
   timestamped occupancy/exposure.

### Дни 22–30: проверить связку, а не только одиночные стратегии

1. Replay causal orchestrator ON/OFF для каждого surviving рукава.
2. Replay allocator с stop-risk, cluster/correlation и broker caps; сравнить с
   простым equal-risk baseline.
3. Запустить только прошедшие кандидаты в zero-risk shadow с controls и единым
   auditor; отклонённые рукава архивировать с reason code.
4. Tiny canary возможна лишь для рукава, у которого отдельно PASS исторический
   контракт, live parity, lifecycle и explicit owner release. Календарная дата
   сама по себе разрешением не является.

## План B, если ATT1 и/или SBR1 не проходят

FAIL не означает ещё месяцы ремонта. В день результата применяется заранее
определённый маршрут:

1. точная failed-конфигурация получает `RETIRED/REFORMULATE`, а не новый grid;
2. её generic infrastructure — causal regime, adapters, controls, ledgers —
   остаётся общей платформой;
3. первый свободный слот получает bull-trend continuation long, потому что он
   закрывает текущую фазовую дыру и механически отличается от ATT1/SBR1;
4. второй слот получает Pattern Atlas v2, который ищет независимые эпизоды;
5. XAU demo и Alpaca lifecycle продолжаются параллельно как другие рынки;
6. если новые directional гипотезы не проходят, усиливается neutral lane
   (funding/basis), но только после execution-aware evidence.

Запрещено исключать проигравшие монеты, менять stop/hold или выбирать новый
режим после просмотра reserved результата. Новая формулировка получает новый
prereg и новые данные; иначе это маскировка провала.

## Открытые решения владельца

- Отдельное разрешение на одноразовый reserved diagnostic после полного
  preflight; текущий документ его не даёт.
- Утверждение максимального общего portfolio stop-risk и broker/market caps до
  подключения аллокатора к деньгам.
- Подтверждение Bullwaves demo identity после ротации MT5 token.
- Отдельное решение о one-slot Alpaca tiny canary только после полного
  prospective lifecycle.

## Ограничения и источники

- Зарезервированный период ATT1/SBR1 уже имеет известные следы доступа другими
  экспериментами; будущий прогон классифицируется как
  `RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION`, а не pristine sealed proof.
- ATT1 regime ON/OFF улучшил presealed stress и уменьшил drawdown, но это не
  разрешение включить режим в текущем money caller.
- BTC-подгруппа ATT1 выглядит положительно, ETH — отрицательно в текущем
  post-hoc presealed срезе; малые `N` и post-hoc разбиение запрещают ручной
  blacklist или отдельный тюнинг.
- XAU session breakout/retest имеет лишь `N=13`; funding и Alpaca результаты
  также остаются diagnostic/shadow до своих gates.

Основные проверенные источники:

- [PROJECT_STATE_AND_EXECUTION_PLAN_2026_08_26.md](PROJECT_STATE_AND_EXECUTION_PLAN_2026_08_26.md)
- [CURRENT_PROJECT_ROADMAP.md](CURRENT_PROJECT_ROADMAP.md)
- [CODEX_SESSION_CHECKPOINT_2026_08_24.md](CODEX_SESSION_CHECKPOINT_2026_08_24.md)
- [ATT1/SBR1 reserved diagnostic preflight](receipts/ATT1_SBR1_RESERVED_OOS_PREFLIGHT_2026_08_27.json)
- [ATT1/SBR1 presealed economics](../research_lab/results/att1_sbr1_presealed_economics_diagnostic_20260823/receipt.json)
- [ATT1 regime ON/OFF replay](../research_lab/results/att1_major8_regime_replay_presealed_v1_20260826/receipt.json)
- [BTC/ETH ATT1 attribution](../research_lab/results/att1_btc_eth_presealed_diagnostic_v1_20260827/receipt.json)
- [Pattern Atlas v1 preregistration](PATTERN_ATLAS_V1_PREREG_2026_07_15.md)
- [Funding V3 audit](FUNDING_POSITIONING_V3_AUDIT_2026_07_28.md)
- [Cross-exchange funding v2 forensic verdict](CROSS_EXCHANGE_FUNDING_V2_FORENSIC_VERDICT_2026_07_21.md)
- [XAU base summary](../research_lab/results/xau_intraday_flat_baseline_v2_20260813/base/summary.md)
- [XAU stress summary](../research_lab/results/xau_intraday_flat_baseline_v2_20260813/stress/summary.md)
