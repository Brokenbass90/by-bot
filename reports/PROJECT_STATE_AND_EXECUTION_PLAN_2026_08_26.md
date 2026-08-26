# Торговая станция: фактическое состояние и путь к рабочей системе

Снимок: **2026-08-26 17:05 UTC**. Каноническое дерево:
`bybit-bot-recovery-20260824`, ветка `codex/recovery-20260824`.

## Короткий вывод

Главный инженерный блокер этой сессии закрыт: `LIVE_CALLER_PARITY` получил
`PASS` для **default-off, zero-risk research candidate** по всем пяти заявленным
пунктам. Код production caller развёрнут в реальном монолите, но feature-флаг
выключен, поэтому риск, геометрия, слоты и ордера не менялись. Запечатанный
период не открывался.

Это ещё не означает, что текущая денежная ATT1 воспроизводит исследовательскую
конфигурацию. Напротив, отдельный аудит намеренно фиксирует
`FAIL_EXPECTED_MONEY_CONFIG_UNCHANGED`. Теперь разрыв измерен и путь к его
закрытию воспроизводим; до сегодняшнего дня он был смешан с несколькими
несовместимыми поколениями кода.

## Пять ворот LIVE_CALLER_PARITY

| Ворота | Результат | Что доказано | Чего не разрешает |
| --- | --- | --- | --- |
| P1 persisted causal BTC H1/EMA200 | PASS, live zero-risk timer | Закрытая H1-свеча и EMA200 сохраняются между рестартами, state 0600, fail-closed | Не меняет денежный regime gate |
| P2 real caller receipts | PASS, код live и default-off | ATT1 signal/no-signal/exception связаны с hash-bound receipt; SBR1 связан с live wrapper/shadow caller | Не включает receipt gate в денежном потоке |
| P3 ATT1 regime ON/OFF replay | COMPLETE, presealed only | `flat_down` gate улучшил base/stress и сильно снизил DD на major-8 | Не является sealed или prospective доказательством |
| P4 fixed-51 evidence coverage | PASS, server runtime | Обе тени реально проходят фиксированные 51 символов, ноль ордеров | Не расширяет денежную вселенную |
| P5 verify_live_config | PASS для кандидата | Frozen research contract воспроизводим | Текущий money config отдельно FAIL и не менялся |

Главный release receipt:
`reports/receipts/LIVE_CALLER_PARITY_RELEASE_2026_08_26.json`.

Post-release deployment receipt:
`reports/receipts/LIVE_CALLER_PARITY_P2_DEPLOYMENT_2026_08_26.json`.

Финальная hash-bound перепроверка после reconciliation/deploy:
`reports/receipts/LIVE_CALLER_PARITY_FINAL_VERIFICATION_2026_08_26.json`.

## Что фактически сделано 26 августа

### Код и Git

- Реализовано causal persisted BTC H1/EMA200 состояние и hourly server timer.
- Привязаны ATT1 production-caller receipts ко всем исходам: signal,
  no-signal, exception. Исключения больше не маскируются как отсутствие сигнала.
- SBR1 live wrapper и zero-risk caller связаны с тем же decision contract.
- Добавлен fixed-51 runtime manifest для ATT1/SBR1.
- Реализован `verify_live_config` с отдельным verdict для research candidate и
  текущего money process.
- Выполнен major-8 ON/OFF replay без чтения sealed rows.
- Сведены две версии монолита: сохранены серверные исправления low-sample WS,
  честная маркировка rule-based operator и default-off платный DeepSeek; добавлен
  parity caller, sizing receipt и честные timeframe labels графиков.
- Все эти изменения отправлены в `origin/codex/recovery-20260824`.

Коммиты критического пути:

- `b7c53a2` — persisted causal BTC regime;
- `a389628` — fixed-51 и config gates;
- `5bbc904` — ATT1 production caller receipts;
- `b54c7fe`, `e25b98d` — server timer и deployment closure;
- `59cf3d4` — zero-risk release gate;
- `5286673` — causal ATT1 regime replay;
- `8b287ea` — reconciliation серверного и Git-монолита.

### Серверный deploy P2

- Server monolith SHA-256:
  `8e8ccea73fa94d1d4d262b0d3d1415159637b3a463a81c8b132a15bb1ff9585d`.
- Rollback-копия старого монолита:
  `/root/by-bot/deploy_backups/live_caller_p2_20260826T170117Z/`.
- Перед deploy: 107 targeted tests PASS, включая 18 reconciliation/caller
  tests; после пересборки всех связанных receipts итоговый focused suite:
  **216 passed**. `py_compile` PASS.
- На VPS: dependency import PASS, staged monolith import PASS, deployed hashes
  совпали.
- `ATT1_CALLER_RECEIPT_ENABLE` отсутствует в env и поэтому остаётся `False`.
- Caller journal после рестарта отсутствует — ожидаемое доказательство default-off.
- `DEEPSEEK_OPERATOR_USE_API=0` и
  `DEEPSEEK_OPERATOR_TRADE_REVIEW_ENABLE=0` подтверждены в окружении процесса.

## Прямая live-истина после deploy

### Bybit

- `bybot.service`: active/running, PID `3157366`, `NRestarts=0`.
- Heartbeat после рестарта: fresh, `trade_on=true`, `dry_run=false`,
  `open_trades=1`, `regime=bull_chop`, `ws_guard_active=0`, `last_error=null`.
- Direct broker GET до и после рестарта совпал:
  `ETHUSDT Sell 0.01`, entry `2449.16`, биржевой stop `2491.34`.
- Deploy не создал, не отменил и не изменил ордера.

### Широкие тени

- ATT1 fixed-51 journal: `2295` событий, `0` admitted.
- SBR1 fixed-51 journal: `2688` событий, `0` admitted.
- Последний общий BTC causal regime: `above_band`; последние решения обеих ног
  были no-signal/regime-ineligible, authority zero-risk.
- Это не доказательство эджа и не доказательство поломки. Это подтверждение, что
  timers, coverage, causal timestamps и journals работают. Входы не надо
  искусственно ослаблять ради количества.

### Alpaca

Прямая broker truth на `17:05 UTC`:

- account ACTIVE, equity `$487.77`, cash `$452.33`;
- ABBV: `0.135734866`, entry `247.55`, price `261.11`, unrealized `+$1.840565`;
- полный sell stop: `257.65`, status `new`, TIF `day`.

Псевдотрейлинг **динамический**, а не одноразовый. Manager на каждом цикле
смотрит новый high-water mark и поднимает floor, если новый рассчитанный уровень
выше сохранённого. Он не имеет права опускать floor. Если акция просто колеблется
ниже старого максимума, стоп закономерно не двигается; новый максимум снова
подтянет его.

Текущий floor ABBV гарантирует положительный gross относительно входа при
обычном исполнении, но не гарантирует цену исполнения: дробная акция требует
DAY stop и остаётся под overnight gap/slippage risk. SCHW уже дал реальное
доказательство этого ограничения: рассчитанный stop был `110.52`, а заполнение
после гэпа произошло около `108.00`. Храповик работал, но брокерская цена не
обязана совпасть со stop trigger.

Новые Alpaca-покупки остаются `SAFE_HOLD`, потому что ещё нет свежего полного
prospective цикла `signal → actual fill → protection → daily rearm → management
→ exit` для новой версии. Размораживать только по факту прибыльного стопа одной
старой позиции означало бы смешать защитную починку со свидетельством качества
stock selector.

## Что показал ATT1 regime replay

Окно `2024-03-01` — `2025-10-01`, sealed период не читался.

| Сценарий | N | PF | Sum R | Max DD R |
| --- | ---: | ---: | ---: | ---: |
| Base, gate OFF | 468 | 1.057 | +13.86 | 46.22 |
| Base, flat_down ON | 122 | 1.249 | +14.02 | 18.33 |
| Stress, gate OFF | 468 | 0.982 | -4.38 | 52.19 |
| Stress, flat_down ON | 122 | 1.162 | +9.37 | 19.04 |

Это сильный инженерно-исследовательский результат: причинный gate не просто
убрал сделки, а улучшил stress и уменьшил просадку. Но это всё ещё просмотренное
presealed окно. Денежный режим включается только после sealed/forward gate и
проверки exact current caller.

По монетам BTC не требует немедленной ручной настройки только потому, что были
убыточные сделки: в gate-on base BTC дал `+4.79R`, stress `+3.11R`. Слабее были,
например, ETH и DOT. Значит гипотеза «ATT1 сломана именно на BTC» текущими
данными не подтверждается; правильный объект следующего анализа — причинный
режим, концентрация и exact caller, а не ручной blacklist после нескольких
live-сделок.

## Ментальная модель конечной системы

Станция должна работать как замкнутый, но не самовольный цикл:

1. **Market/data layer** получает публичные свечи, стакан, сделки, funding,
   equity/Forex данные и проверяет пропуски, время и provenance.
2. **Regime layer** независимо описывает trend/range/volatility/liquidity и
   сохраняет причинное состояние между рестартами.
3. **Strategy sleeves** решают только свою задачу: ATT1 short flat-down, SBR1
   long flat-up, будущие trend continuation, range/order-block, XAU и т.д.
4. **Evidence lab** предрегистрирует гипотезу, запускает replay, random control,
   shadow и считает PF/DD/concentration/cost sensitivity.
5. **Orchestrator** включает только стратегии, допущенные для текущего режима.
6. **Allocator/exposure gate** распределяет риск между независимыми sleeves,
   ограничивает корреляцию, общий stop-risk и количество слотов.
7. **Execution layer** применяет биржевые фильтры, maker/market contract,
   фактический fill, stop/TP/runner и idempotent recovery.
8. **Live auditor** сверяет Git SHA, server hashes, process flags, heartbeat,
   broker positions/orders, risk и journals. Любое расхождение — fail-closed.
9. **Learning loop** предлагает кандидатов и находит аномалии, но не имеет money
   authority. Продвижение выполняется только через receipt + gate + owner release.

Это и есть динамичность: не ежедневная подгонка параметров по последней свече,
а автоматическое переключение уже доказанных sleeves, контроль деградации и
быстрое испытание новых гипотез вне денег.

## Что ещё НЕ готово

- Текущий ATT1 money caller не воспроизводит frozen geometry. В нём остаются
  прежние risk/stop/time-stop и regime/allocator gaps.
- `exposure_gate` ещё не подключён к реальному money path. Поэтому расширение
  слотов сейчас запрещено, несмотря на исторический capacity result.
- SBR1 не имеет money authority; широкая тень пока не дала admitted decision.
- Sealed период не открыт.
- Alpaca selector новой версии не прошёл полный prospective paper lifecycle;
  whole-share/native-trailing profile только следующий кандидат.
- XAU/Forex не подключён к Bullwaves demo ingestion и не имеет order authority.
- Polymarket, DeFi и новые индикаторы остаются research backlog.
- Самообучение пока proposal-only; нет безопасного автономного promotion loop.

## Следующий критический путь

### Следующая сильная сессия: SEALED_RELEASE_PREFLIGHT

Цель одной сессии — не придумывать новые стратегии, а подготовить одноразовое
открытие sealed периода:

1. повторно сверить clean Git, source/data/manifest SHA и server receipts;
2. доказать, что ни один sealed row ранее не декодирован;
3. заморозить exact ATT1/SBR1 configs, universe, costs и decision thresholds;
4. подготовить одну команду запуска и независимый audit command;
5. получить отдельное явное owner-разрешение на открытие;
6. только после разрешения прочитать sealed период ровно один раз.

Если sealed PASS: подключить candidate receipt в zero-risk caller, закрыть
`exposure_gate`, прогнать exact fill/stop replay, затем prospective shadow и
tiny canary. Если sealed FAIL: ноги не растягиваются на месяцы; в тот же день
они закрываются/переформулируются, а вычисления переходят к заранее
подготовленным 5m семействам. Это главный механизм компрессии времени.

### После sealed, отдельными пакетами

1. **Money integration gate:** regime caller, measured ATT1 geometry, time stop,
   exposure/correlation gate, allocator, exact order sizing receipt.
2. **SBR1 random control:** детерминированная контрольная лента рядом с основной
   до первого admitted решения; fixed-51 evidence universe остаётся неизменной.
3. **Alpaca:** frozen current-profile replay, gap stress, default-off whole-share
   paper profile, month-end prospective cycle, затем tiny canary.
4. **XAU:** Bullwaves/MT5 demo read-only ingestion, journal и random control;
   сначала H4/D1 regime + H1 structure + M15 execution, без ордеров.
5. **Новые crypto sleeves:** отдельные trend-long, range mean-reversion,
   order-block/imbalance continuation и volatility breakout — не один
   универсальный алгоритм.

## XAU/Forex: конкретная отправная точка

- Готов zero-order paper core `bot/xau_mt5_zero_order_paper.py`, 18 tests.
- Есть `87,439` presealed XAU M5 rows за `2024-07-08` — `2025-10-01`.
- Старый session breakout/retest baseline: `N13`, `+3.915R`, PF `1.73`; stress
  `+3.012R`, PF `1.526`, 3/4 folds. N слишком мал, preflight не даёт promotion.
- Round sweep и старый trend pullback были отрицательны.
- Следующий безопасный шаг — ротация MT5 token, точная demo identity Bullwaves и
  read-only signal/data tracker. Затем три предзарегистрированных семейства:
  trend continuation, range/order-block, reversal after distribution.
- Order blocks, imbalances, smart-money и TD Sequential являются features для
  ablation, а не самостоятельным основанием ставить деньги. TD Sequential
  полезнее сначала как annotation истощения тренда.

## Исследовательская лаборатория и Ollama

- Локальная research station на последней проверке: `6/6` supervised jobs
  healthy; сборщики продолжают писать публичные данные.
- Alt-24 orderbook collector накопил более `46k` наблюдений; trade collector
  имеет неполное покрытие и поэтому пока data-quality WARN, а не стратегия.
- Funding shadows имеют уже десятки закрытий, но положительный mean держится на
  хвостах/концентрации, median около нуля; money gate закрыт.
- ATT1 limit-paper `N3`, maker `2/3`, около `+2.48 bps` экономии — интересно,
  но выборка слишком мала.
- Inplay prospective сейчас отрицательный и не является кандидатом.

Ollama работает правильно как proposal-only auditor, но модельная отдача пока
скромная: deterministic audit нашёл actionable проблемы, qwen3:8b в последнем
цикле не добавил новых находок. Полезный следующий продукт после sealed
preflight — **Local Operator Digest**: скрипт собирает только свежие receipts,
heartbeat, broker-safe summaries и ошибки, а Ollama отвечает по этому короткому
контексту. Полный RAG на 20–50 тысяч чанков сейчас преждевременен.

На VPS qwen3:8b размещать не следует: сервер имеет примерно 1 CPU и 1 GB RAM,
а модель занимает около 4.9 GB. Она будет вытеснять торговый процесс. Запускать
на Mac и передавать на сервер только proposal/receipt безопаснее.

## DeepSeek и экономия токенов

Фоновые платные пути на live подтверждённо выключены. DeepSeek разумно оставить
только для ручного `/ai` или редкого явно запрошенного разбора с коротким
контекстом. Пополнять большой баланс до появления понятного usage receipt не
нужно; сначала добавить суточный счётчик requests/input/output tokens и жёсткий
budget breaker.

Распределение работы:

- **сильный Codex:** контракт, архитектура, live deploy, forensic reconciliation,
  sealed gate, денежные инварианты;
- **лёгкая модель/Claude:** замороженные прогоны, тесты, data QA, scoped commits,
  документация и reproduction receipts;
- **Ollama:** классификация логов и dirty findings, daily digest, поиск
  повторяющихся аномалий; никогда не money verdict;
- **детерминированные scripts:** регулярные health checks, hashes, broker truth,
  coverage и cost budgets.

## Polymarket, DeFi и новые идеи

Polymarket записан как `POLY1 research-only`: market/rules/settlement/fees,
liquidity, latency и causal paper replay; никакого wallet/private key/order до
отдельного gate. Правильный дизайн — не «LLM угадывает исход», а детерминированный
scanner mispricing/related-market inconsistency с LLM только для извлечения
условий resolution и поиска конфликтов.

DeFi ниже приоритетом до наличия качественных historical swaps и модели
fees minus impermanent loss. GMGN и внешние agent terminals не получают seed,
основной кошелёк или production authority.

Идеи order blocks, imbalance/FVG, smart-money, TD Sequential и среднесрочные
crypto sleeves не забыты. Каждая должна иметь causal definition, baseline,
random control, costs, concentration и multiple-testing budget. Количество
индикаторов само по себе не усиливает систему; усиливает только независимая
измеренная информация.

## Реалистичный горизонт

- Следующая сильная сессия: sealed preflight, без открытия данных.
- После явного разрешения owner: одноразовый sealed run занимает часы, а не
  месяцы, и даёт решение PASS/FAIL в тот же день.
- При PASS: 1–2 инженерные недели на money integration + zero-risk bake, затем
  только tiny canary по чистому gate.
- Alpaca: ближайший разумный milestone — один новый month-end prospective
  lifecycle; календарный срок нельзя заменить старой прибыльной позицией.
- XAU: 1–2 недели до качественного demo journal после выдачи точного безопасного
  доступа; money decision только после достаточной контрольной выборки.

Цель 4–5% в месяц можно оставить как product aspiration, но не как обещание или
основание привлекать `$5,000`. Сначала система должна показать воспроизводимую
доходность после costs, просадку, концентрацию и стабильность на независимых
данных; затем риск увеличивается ступенями, а не ожиданиями.

## Definition of done проекта

Станция считается реально рабочей не тогда, когда один бот совершает сделки, а
когда одновременно выполнено:

- Git SHA = server SHA = tested receipt;
- broker truth совпадает с internal state;
- каждая денежная нога имеет frozen contract, independent evidence и
  prospective lifecycle;
- regime/orchestrator/allocator реально находятся в caller path;
- общий exposure и correlation risk ограничены;
- stops/runner восстанавливаются после рестарта и проверяются auditor;
- research loop воспроизводим, а AI остаётся proposal-only;
- live economics после fees/slippage положительна и не держится на одной монете
  или одном хвостовом событии;
- любой сбой закрывает authority, а не угадывает продолжение.

На 26 августа фундамент для этого впервые собран в один проверяемый критический
путь. До полностью работающего портфеля ещё есть работа, но главный ответ больше
не требует пассивно ждать несколько месяцев: следующий поворотный вердикт можно
получить через sealed gate после одной подготовительной сессии и отдельного
разрешения владельца.
