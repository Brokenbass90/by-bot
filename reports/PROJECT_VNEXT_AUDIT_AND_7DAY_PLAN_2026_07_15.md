# Project vNext audit and seven-day recovery plan — 2026-07-15

## Executive decision

Проект не заблудился, но долго смешивал три разные вещи: наличие кода, красивый backtest и разрешение рисковать деньгами. Каркас уже достаточно богатый; главный дефицит — parity, неизменяемые входы, исполнение и честные ворота. Поэтому основа не переписывается целиком. Она сжимается до пяти контуров: `truth -> data -> research -> shadow -> money`, а каждый компонент теперь имеет одно машинно-читаемое состояние в `configs/project_capability_registry_v1.json`.

Денежная правда на 2026-07-15:

| Контур | Фактическое состояние | Решение |
|---|---|---|
| Bybit crypto | сервис active, fresh heartbeat, broker flat; только `ATT1 short-only`, `risk_mult=0.10` | оставить tiny canary до явного review 20 июля; не ускорять и не масштабировать |
| Alpaca | monthly v38, `SAFE_HOLD`; `ABBV/ABNB/GE/SCHW`; broker stop quantity coverage `4/4`; новые входы выключены | защита работает, но стратегия не доказана; exact-parity replay до новой ротации |
| Cross-exchange arb | 174 закрытых shadow-цикла: mean `-0.0314%`, median `-0.1049%`, p25 `-0.1907%`, WR `33.3%` | `NO-GO`, не пополнять вторую биржу |
| Bybit spot+perp cash-and-carry | исторический strict screen только `1.1–1.8%` annualized и `NO-GO`; public-data paper core теперь есть, но daemon/real cycles отсутствуют | достроить collector/quantization/recovery; текущий публичный XRP snapshot — лишь lead, не edge |
| FX/CFD | V2 отрицателен во всех шести side-specific sleeves; V3 заблокирован данными/news/account-cost contract | research only; деньги и API исполнения пока не нужны |

Это не пессимизм. Это наконец корректная стартовая линия, от которой прогресс нельзя подменить случайной цифрой.

## Что обнаружено и исправлено сегодня

### Внутренний AI, web и Telegram

- Причина ложного сообщения «бот offline четыре дня» подтверждена: web AI читал неполное и старое live mirror. Прямой VPS на 16:28 UTC: `bybot.service=active`, `trade_on=true`, `dry_run=false`, `open_trades=0`, режим `bull_chop`.
- AI context теперь выбирает самый свежий direct/mirror artifact, имеет жёсткие age gates и при stale truth отвечает `UNKNOWN`, а не придумывает offline, позиции или live-рекомендации.
- Mirror sync теперь атомарный, защищён от одновременно запущенных копий и выдаёт bundle manifest. Реальная синхронизация завершилась: `31` файла, `2` необязательных отсутствуют, critical failures `0`.
- Внутреннему AI добавлен capability registry: он видит не только стратегии, но и их `stage`, physical side, authority, известные пробелы и следующий gate.
- AI env mutation/deploy/rollback физически помещены в quarantine. AI остаётся observer/proposal-only; setup card или мнение модели не может стать ордером.
- Heartbeat теперь публикует исчерпывающую authority-карту всех `21` исполнимых strategy flags. Web и Telegram сверяют текущую карту, risk contract и cached AI context; при stale/mixed/semantic/risk mismatch рекомендации блокируются.
- `/ai_code` больше не читает `configs/` вообще, поэтому ignored broker/env credentials не могут уйти внешнему AI; дополнительные Telegram packs исключаются после `900` секунд.
- Web login page локально загружается нормально и больше не показывает `Unauthorized` до ввода. Успешный password+TOTP replay без данных владельца не заявляется.
- Финальный полный regression после независимого safety-review: `1334 passed`.
- Safety package targeted-deployed under `ai_truth_aaf57f1_20260715`: nine SHA256 matches, exact backup, three direct-flat confirmations before core restart, web restart/ping PASS, ATT1-only `0.10`, AI truth blockers empty and `.env` unchanged. Research/strategy/FX files were excluded.

### Alpaca

- Исправлена ошибка drawdown в diagnostic adaptive bakeoff: старая функция начинала peak с первой сохранённой точки и игнорировала падение от initial capital.
- Заявление `max DD 2.2%` для gated-adaptive 2022 отозвано. На имеющихся редких rebalance endpoints минимум `8.205%`; истинная внутримесячная просадка неизвестна, потому что daily MTM отсутствует.
- Сам gated-adaptive в 2022 дал `-6.54%`, PF `0.280`, N `12`. Кроме того, он использует same-close вход и 21-session шаг, поэтому это diagnostic, а не кандидат в live.
- Текущий live не gated-adaptive. Это monthly v38 в `SAFE_HOLD`, equity `$486.77` по post-action broker receipt, четыре позиции и четыре точно покрывающих stop order; `SBUX` осознанно не куплен из-за `allow_new_entries=false`.
- Официальная Alpaca поддерживает broker trailing stops, но они являются отдельными orders и превращаются в market order при срабатывании; fractional режим имеет ограничения. Поэтому текущая комбинация exact broker stops + software HWM protection сохраняется до parity replay.

### ATT1

- Код формально реализует то, что заявляет: confirmed H1 close, swing pivots, touch/rejection, short-only runtime, stop/partial/BE/trail.
- AI называл часть входов нелогичными не из-за сломанного backtest engine, а из-за слабого геометрического контракта: при двух pivots `R²=1` автоматически; обязательных `unbroken interval`, first retest, minimum respects и bounded overshoot нет.
- Последние пять broker-accounted закрытий текущего canary: `2` прибыльных, `3` убыточных, суммарно около `+0.15 USDT`; это лучше старого отрицательного потока, но sample слишком мал для edge.
- Вывод: execution path не выглядит сломанным, entry geometry и edge остаются недоказанными. Baseline не правится post-hoc; отдельный geometry challenger preregistered до просмотра outcome.

### Research

- Claude Research Station действительно отработала `107` вариантов за `3:11`: ATT1 `36`, level fade `54`, pump `12`, пять classics по одному default. Один `impulse_breakout` прошёл IS, затем провалил forward и OOS; survivors `0`.
- Это полезный diagnostic prototype, но не новая фабрика edge: mutable-largest-cache selection, повторное использование OOS, отсутствие multiple-testing correction, выброшенные причины финальных провалов и отсутствие live/backtest parity.
- Расширять её слепо до десятков тысяч вариантов запрещено. Karpathy `autoresearch` полезен организационным принципом — один изменяемый объект, фиксированный бюджет, сравнимый metric — но официальный проект оптимизирует nanochat на одной NVIDIA GPU, а не торговые стратегии. Прямое копирование не подходит.
- Вместо бесконечного grid создан `Pattern Atlas v1`: hash-pinned dev13, шесть заранее зафиксированных H1 гипотез (horizontal breakout / failed break / rejection; long и short отдельно), next-H1-open outcomes 6/24/72/168h, 120 дней sealed holdout. Discovery завершён: `20,372` gross-path observations, source hashes PASS. Байты sealed tail прочитаны только для проверки SHA256; строки holdout не декодировались, не оценивались и не использовались.
- Единственный достойный follow-up lead — `horizontal_breakout_long @72h`: N `909`, mean `+54.5 bps`, excess к time-control `+91.0 bps`, 10/13 symbol means положительны и largest symbol share `7.9%`. Но median `-49.2 bps`, hit rate `48.0%`, p25 `-442.6 bps`: результат fat-tail и не является готовым входом. Следующий шаг — один заранее замороженный sealed-holdout + costed exit/event-retest contract; остальные 23 cells не спасать post-hoc.
- Replayable public tape продолжает собираться: ONDO depth-50+trades и шесть publicTrade streams, около `838 MB` суммарно на контрольной точке. Первый календарный полный UTC-день станет доступен после закрытия и сжатия 15 июля; данные 14 июля начались только в 06:28 UTC и являются частичным днём.

## Арбитраж: шанс и правильное место в очереди

Арбитраж стоит держать в приоритете, но только Bybit same-exchange `long spot + short perp`. Он убирает направленную дельту, но не basis drift, funding flip, liquidation/margin, four-fill cost и риск временной одной ноги.

Свежий public scan 15 июля нашёл один screening lead: `XRPUSDT`, текущий positive funding `0.01% / 8h` (простая annualization `10.95%`), mark-index basis около `-0.0449%`, достаточные turnover/OI. Это не ожидаемая доходность: ставка может смениться, четыре fill и basis могут съесть месяцы carry. Исторический baseline XRP дал около `3.43%` net-on-notional за 365 дней при упрощённой cost-модели, а более строгий basket/stress screen был только `1.1–1.8%` и завершился `NO-GO`.

Правильные ворота:

1. Public-data paper shadow, никаких private keys или orders.
2. Persistence минимум через три завершённых funding observation до simulated entry.
3. Четыре исполнимых fill, fees, slippage, funding settlement, basis P&L, delta drift и funding-flip exit.
4. Первые `10` cycles проверяют механику, не edge.
5. Edge review только после `>=30` cycles, `>=3` coins, положительных stressed median и p25, без концентрации и двухногих ошибок.
6. Только после PASS — отдельный live executor с idempotency/reconciliation и canary `$25–50` на ногу.

Реалистично: `1–2` рабочих дня на paper engine; `1–3` недели на первые 10 циклов; `3–8` недель на 30+. Сейчас оставлять капитал на Bybit можно, но переводить дополнительные деньги или включать withdrawal permission не нужно.

Механическое ядро paper shadow уже собрано и проверено: default disabled, только public GET, никаких ключей/private/order endpoints; три завершённых funding observations, four-fill adverse execution, fees, settlement timing, basis/delta/funding guards и checksummed idempotent ledger. Synthetic fixture специально завершился около `-$0.431` на `$100` каждой ноги после издержек — это подтверждает, что прибыль не рисуется автоматически. До реального paper clock ещё нужны durable collector/open-cycle state, instruments quantization, L2 walk и recovery.

## Лучшая форма Alpaca и как извлечь больше

Путь к большей прибыльности — не сделать monthly чаще. Нужно проверить четыре физически сравнимых варианта на одной механике: static top4, regime-gated top4, gated+adaptive sizing, cash control. Для всех нужны calendar-month signal, next-session-open fill, PIT universe/corporate actions, costs, daily MTM, общий stop/trailing engine и broker-fill parity.

Только после этого можно честно проверять улучшения:

- regime gate как защита, а не оптимизация дохода;
- volatility/cluster budgeting;
- turnover-aware replacement threshold;
- market/sector breadth overlay;
- software HWM versus broker trailing как A/B exit;
- ensemble monthly momentum + event sleeve, не смешивая intraday ledger.

Срок: `2–4` рабочих дня на исправленный replay после materialization входов; затем `4–8` недель paper-forward для решения о снятии SAFE_HOLD. Старые `+50–63%` и PF `6+` остаются selected historical evidence, а не годовым обещанием.

## Семидневная исполнимая очередь

### 15–16 июля

- опубликовать AI truth gate, mutation quarantine, capability registry и Alpaca drawdown erratum;
- разобрать завершённый Pattern Atlas receipt и до доступа к holdout заморозить только один bounded `horizontal_breakout_long_72h` follow-up;
- закончить pure cash-and-carry paper engine и deterministic fixtures;
- сохранить live risk без изменений.

### 17–18 июля

- материализовать missing Alpaca parity artifacts и frozen four-arm replay;
- разобрать интересные Pattern Atlas cells только как новые prereg hypotheses;
- валидировать первый полный UTC tape day и начать imbalance/density feature contract без performance claims.

### 19–20 июля

- ATT1 review по broker-reconciled logical trades; решение: continue tiny / pause / retire;
- freeze geometry challenger с минимум тремя pivots/respects, unbroken interval, first retest и отдельным short-only identity;
- Bybit API key: статус `ok`, expiry `2026-08-12`, плановая ротация до `2026-08-05`.

### 21–22 июля

- FX V3 input contract: repaired immutable M5, pinned news coverage, account-specific spread/commission/financing; затем только первый prereg diagnostic;
- если cash-and-carry engine готов, начать public paper clock; никаких реальных ордеров;
- обновить web/TG control surfaces из capability registry, чтобы UI не называл research/live одним словом.

## Реалистичные временные рамки

- Alpaca replay verdict: несколько рабочих дней; решение по live mode — после 4–8 недель forward.
- Второй crypto risk-zero shadow: июль, если Pattern Atlas/event-long закроет data/runner gates; tiny money — не раньше августа и только после PASS.
- Три независимых money sleeves: август–октябрь как условный диапазон, не обещание; два кандидата должны реально пережить OOS и shadow.
- FX/CFD первые новые честные V3 цифры: 1–3 недели после фиксации data/news/cost contract; broker canary существенно позже.
- Microstructure: первые исследования после 7–14 дней tape, promotion-grade вывод — после 60–90 дней.

## Что от владельца нужно сейчас

- Не добавлять капитал под арбитраж и не открывать ручные сделки по setup cards.
- Оставить Mac включённым и с интернетом для tape/Pattern Atlas; текущий keep-awake уже активен.
- До 5 августа безопасно ротировать Bybit API key; секреты в чат не присылать.
- Для FX позже предоставить только название/тип реального счёта и точный fee/spread/financing schedule; сами credentials для backtest не нужны.

## Source hierarchy

При конфликте: direct broker/exchange -> fresh runtime receipt -> targeted deploy receipt/SHA -> immutable prereg research -> human-reviewed registry/checkpoint -> AI interpretation. Красивое сообщение AI или selected backtest никогда не выше свежего брокерского факта.

Внешние первичные ссылки: [Bybit funding calculation](https://www.bybit.com/en/help-center/article/Funding-fee-calculation), [Bybit instruments/fundingInterval API](https://bybit-exchange.github.io/docs/v5/market/instrument), [Alpaca order and trailing-stop contract](https://docs.alpaca.markets/us/docs/orders-at-alpaca), [Karpathy autoresearch](https://github.com/karpathy/autoresearch), [Freqtrade lookahead analysis](https://docs.freqtrade.io/en/stable/lookahead-analysis/), [NautilusTrader backtesting](https://nautilustrader.io/docs/latest/concepts/backtesting/).
