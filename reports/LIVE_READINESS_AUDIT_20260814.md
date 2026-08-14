# Ревизия готовности к live — 14 августа 2026

## Короткий итог

В live по-прежнему готова только tiny-canary ATT1 short. Это не означает, что
вся работа бесполезна: Inplay, XSEC и funding действительно собирают forward,
Alpaca защищена, L2/tape копятся, а лаборатория быстро отклоняет неверные
механизмы. Но второй денежной ноги на этом срезе нет.

Прямая read-only проверка в 15:02 UTC: Bybit flat, сервис active. Никаких
ордеров, отмен, ручных закрытий, повышения риска или деплоя во время ревизии не
было.

## Что готовится к live

| Контур | Реальная стадия | Главное доказательство | Что блокирует деньги |
|---|---|---|---|
| ATT1 short | tiny live `0.10` | clean N5, `+2.950R`; historical corrected `-2.468R/393` | N20, reconciliation, historical robustness |
| Inplay ETH | fixed prospective shadow | collector fresh, N0, code parity exact | нет forward-сигнала и доказанного net edge |
| XSEC | daily research shadow | свежий orderless decision | PIT/funding/next-open, концентрация и forward |
| Funding/carry | shadow + data repair | 10 dynamic и 9 frozen closes | отрицательные медианы, концентрация, слабая two-leg экономика |
| Sloped break/retest | rejected | V2 `-2.739R`, V3 `-5.371R` | механизм не прошёл даже development |
| Alpaca | protected SAFE_HOLD | GTC protection; entry-relative proxy `25.65%/14.36% DD` | exact live replay и PIT/sector parity |
| XAU | сбор данных | 12/1734 дней обработано | текущая скорость неприемлема, нужен другой источник/режим загрузки |

## ATT1 и буллран

ATT1 не обязана минусить только потому, что рынок растёт. В corrected history
bucket с ростом BTC за 30 дней более 10% дал `+1.263R/91`, neutral
`+5.572R/252`; основной минус оказался в сильном падении BTC:
`-11.356R/35`. Это exploratory разрез, не готовый фильтр.

Но операционный риск реален: live-контракт short-only, прямого bull-regime
блокиратора внутри ATT1 нет. Есть реактивный breaker по уже полученным убыткам.
Лонговый код в стратегии существует, но доказанного long-аналога и live
authority нет. Правильный следующий тест — отдельная long continuation/retest
нога и отдельно frozen impulse/bear guard для шорта; простая инверсия ATT1
запрещена как ложный аналог.

## Что показал разбор 393 отрицательных/положительных исходов ATT1

- ETH: `-8.313R/43`, SOL: `-8.267R/60`; ADA, LINK и SUI положительны.
- Horizontal-resistance geometry: `-15.296R/166`; descending trendline часть
  компенсирует этот провал.
- Вход ближе `0.5 ATR` к линии: `-24.699R/141` — потенциальный механический
  фенотип, но порог нельзя брать в live с того же окна.
- Bear `<-10%/30d`: `-11.356R/35`, тогда как bull и neutral около нуля/в плюсе.

Следующая проверка должна взять ровно один механизм, заморозить его и проверить
на disjoint окне. Удалять ETH/SOL или включать режимный фильтр по этому же
разрезу нельзя — это будет hindsight selection.

## Лаборатория: что реально работает и чего нет

Сейчас здоровы `6/6` supervised research-only jobs и четыре публичных
microstructure collectors. AI idea intake принимает полные карточки и не имеет
ордера/risk authority. Но closed-loop пока не завершён:

1. четыре idea cards не связаны явными ID с prereg/spec/passport/result;
2. nightly historical scheduler имеет протухший status примерно на 2231 час;
3. 30 approved specs привязаны только к имени файла, а не к SHA256;
4. AI не генерирует безопасно проверенный strategy code автоматически.

Поэтому вердикт: `PARTIAL_PIPELINE_NOT_SELF_IMPROVING_CLOSED_LOOP`. Следующая
модернизация — lifecycle ledger, hash-bound approval, обязательные preflight и
passport, затем автоматический запуск только уже существующего bounded-кода.
ИИ может предлагать гипотезы и анализировать результаты, но код остаётся через
review/tests; live остаётся только через owner approval.

## Динамический подбор монет

Он реален и частично уже существует. Есть IVB1 rolling train→OOS selector,
Inplay dynamic-selector и общий live market scanner. Но IVB1-проверка честно
провалилась: лучший policy имел 4 folds, только 2 положительных, median
`-1.28`, aggregate PF `0.365`. Общего promotion-grade API пока нет.

Новая версия должна быть отдельной для каждой стратегии и выбирать universe
только из прошлых данных на месячной границе: liquidity/listing age/spread,
частота именно её сетапа и стабильность; затем universe замораживается на
следующий месяц. Нельзя каждый раз оставлять исторически прибыльные монеты —
это и есть переобучение.

## Грязный хвост

Обновлённый недеструктивный аудит нашёл 163 code-кандидата:

- 5 test-backed;
- 115 evidence-backed, требующих reproduction;
- 16 referenced, требующих review;
- 27 unreferenced quarantine candidates.

В первой очереди: shared portfolio engine, XSEC reference, backtest auditor,
sweep-reclaim, old sloped research, trial ledger и Alpaca validator. Удаление
будет только после reference map и отдельного quarantine receipt. Большая часть
остальных 500+ entries — данные, отчёты, логи, backup и результаты, поэтому
цифра 163 не противоречит общему dirty count.

## Решения этой сессии

- Sloped V3 отклонена и не идёт в shadow/live.
- ATT1 tiny-canary сохраняется; TP2 и live geometry не меняются.
- Alpaca HWM, re-entry и TG dedupe state теперь сохраняются атомарно локально;
  это не деплой и не разрешение новых входов.
- Inplay, XSEC, funding и L2/tape продолжают orderless сбор.
- Server L2 лечится компрессией с SHA/decompression verification. Для будущей
  выгрузки на Mac правило такое: copy → hash verify → retention receipt →
  только затем удаление server source; простое `scp && rm` запрещено.

Источники: `reports/evidence/LIVE_READINESS_MATRIX_20260814.json`,
`reports/evidence/ATT1_NEGATIVE_PHENOTYPES_PREHOLDOUT_20260814.json`,
`reports/evidence/ATT1_BULL_REGIME_AND_LOSS_AUDIT_20260814.json`,
`reports/evidence/RESEARCH_PIPELINE_AUDIT_20260814.json`,
`reports/evidence/DIRTY_RESEARCH_WORKBENCH_AUDIT_20260814.json`.
