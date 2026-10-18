# Alpaca Monthly58 — доставка одинаковых данных и диагностический отбор

18 октября 2026. **DONE / DATA_ONLY**: действующий Monthly source → его же daily
view → frozen ranking/selection → immutable VPS export → фактический импорт Claude.
19 октября после закрытия — отдельный будущий снимок, пока **PENDING**, не PASS.
Финансовая активация Monthly не выполнена; NET и отмена SHOP сохранены.

## Что доставлено

- `research_lab/alpaca_monthly_data_parity_v1.py`: представление существующих данных,
  проверка целостности/часов/покрытия, повторяемый ranking и диагностический отчёт.
- `scripts/export_alpaca_monthly58_daily_v1.py`: FILE_ONLY worker; принимает только
  исходный capture с квитанцией действующего Monthly source. Независимо пересобирает
  его source identity оригинальным пинованным compiler и сверяет с исходным seal.
- `scripts/pull_alpaca_monthly58_daily_v1.py`: явный SCP pull, проверка до публикации,
  create-exclusive файлы и seal последним. Повторный импорт не изменяет файлы.
- Реальный снимок **16 октября**, source available **17 октября 13:37:17.337 UTC**,
  впервые доставлен Claude **18 октября 16:25:04.862 UTC**. Это исторический прогрев
  и диагностика, не проспективное решение 16 октября.

Фактический каталог Claude:
`bybit-bot-clean-v28/research_lab/data/alpaca_monthly58_daily_v1/`.
Файлы `2026-10-16.json`, `.diagnostic.json`, `.diagnostic.md`, `.delivery.json`.
Его код/KARTA/VOROTA не изменялись; сообщения Claude не отправлялись.

Universe строго **57 инструментов + SPY**, **QQQ исключён**. Точный список и SHA:
[source_provenance.json](evidence/alpaca_monthly_data_parity_20261018/source_provenance.json).
Universe SHA `d88f7598819afa8b2cc2fabec197f45a7bcd9dfb8f50d30c1bf2698d671295fa`.
Actual VPS data SHA `e165f362866d739e5be0d8fb2e8b0aa185538e759358cb8b3419b360a4b7bc7e`.

## Семантика цен и доказанная эквивалентность

Существующий fetcher: Yahoo hourly, `interval=1h`, `period=2y`,
`auto_adjust=False`, `prepost=False`. Существующий aggregator берёт UTC day:
first open / max high / min low / last close / sum volume. Calendar проверяет
реальные RTH opening timestamps, DST и сокращённые сессии; последний hourly бар
может иметь длительность 30 минут. Daily close — close последнего захваченного
RTH hourly бара, **не доказанная SIP official closing auction**.

`auto_adjust=False` выключает клиентское применение коэффициента Adj Close/Close.
Это не свидетельство полностью сырой истории до всех split: сохраняется vendor
OHLC как получен; второе split-преобразование, дивидендный total-return factor,
rebasing и заполнение пропусков здесь отсутствуют. Point-in-time восстановление
corporate actions **NOT_PROVEN**; оно не требуется для сравнения одного и того же
снимка. Основание: фактический fetcher и
[yfinance auto_adjust/parse_quotes](https://github.com/ranaroussi/yfinance/blob/main/yfinance/utils.py),
[параметры price history](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html).

На VPS сейчас yfinance **1.2.0**, его observed utils SHA сохранён. Версия библиотеки
именно в момент первоначального capture не записана — **UNKNOWN**, а не установленный
факт. Нужная для paired control идентичность доказана через неизменяемые исходные
файлы/их hashes, source receipt и те же преобразования; Yahoo с SIP не смешиваются.

JSON roundtrip через существующий reader, полный исходный history против экспортных
260 дней: те же выбранные symbols, порядок ranking и решения. Пересчитанные float
metrics между Python runtimes сравниваются с явно заданными `abs_tol=rel_tol=1e-12`;
bars/file hashes, symbols/order, причины и boolean-решения — точные. Это политика
сверки метрик, не изменение frozen selector, threshold или финансового sizing.

Часы разделены: raw hourly open timestamps, session date/close, фактическое получение
source, первое получение Claude. Более поздний импорт не становится ранним решением.
Hashes обеспечивают целостность, а не подпись против злоумышленника, заменившего все
данные и все seals. Доверие к происхождению — известный SSH host, пинованный source
worker и сверка с его принятой квитанцией.

## Покрытие — без скрытых пропусков

Экспортировано **260 sessions × 58 symbols**, 105095 hourly rows в окне.
**Последние 200 полностью покрыты по всем 58**, включая timestamps. Более старые
неполные сессии сохранены с флагами:

- 28 ноября 2025: последний получасовой бар отсутствует у всех 58;
- 24 декабря 2025: последний получасовой бар отсутствует у всех 58;
- 9 октября 2025: отсутствует один час у REGN.

Минимум полностью проверенных дней на инструмент — **257**, не 260. Данные не
дорисованы. Пропуск в необходимом core200 даёт fail-closed отказ; эти старые флаги
не влияют на текущие 200/80/28/20 lookbacks, что подтверждено source/selection parity.
Любому другому эксперименту, использующему старые неполные дни, требуется явная
собственная политика качества; этот экспорт не выдаёт ему автоматический PASS.

## Диагностика закрытия 16 октября

[Все 57 health ranks, допуски и причины отказа](evidence/alpaca_monthly_data_parity_20261018/2026-10-16.diagnostic.md),
[метрики/режимы/гипотетические версии JSON](evidence/alpaca_monthly_data_parity_20261018/2026-10-16.diagnostic.json).

| Гипотетический Monthly pick | Вес | Close |
|---|---:|---:|
| SHOP | 40.65% | 169.51 |
| ABBV | 25.78% | 285.38 |
| ADSK | 21.46% | 239.93 |
| MSFT | 12.11% | 528.95 |

SPY200 gate TRUE; Monthly calendar due FALSE. Это **гипотетический** отбор вне
месячного исполнения. Cash/positions не читались: `UNKNOWN_NOT_READ_DATA_ONLY`.
SMA50 — наблюдение, не новый veto. `FINAL_SET_*` причины описывают ограничения
относительно конечного набора, не добавляют алгоритм отбора.

Weekly показана только на том же Monthly58 snapshot как общий selector: тот же
кандидатный набор, максимум один гипотетический новый вход (SHOP). Это не полный
портфельный replay действующей Weekly/Dynamic59 и не новый её backtest. Реальная
покупка SHOP **остаётся отменённой владельцем**.

## VPS и ежедневная доставка

Отдельный DATA_ONLY каталог:
`/opt/bybot-research/alpaca-monthly58-daily-20261018/candidate-50690ccc723cc2df/app`.
47 source files: прежние 44 пинованных E2E files + три новых файла. Сохранён старый
frozen Dynamic helper из `d205f8f`, не подменён текущим EventReselection helper.
Material SHA `50690ccc723cc2df73241e2319f0c4d849e8856159ee81a3a8f207f24f6d6aac`;
spec SHA `b736b443f40f32c5fd16bccafc4e09a1d91c41b1835ca9c1123bf1a2ebb701a5`.

`alpaca-monthly58-data-export.timer` **enabled/active**, каждые 5 минут в13..23UTC
по будням. Сервис не имеет IP-доступа (`AF_UNIX`, `IPAddressDeny=any`), работает с
файлами существующего source; не получает broker profile или route для заявок.
Первый реальный export занял 41.574s; повтор дал `ALREADY_SEALED_DATA_ONLY`.

Исходный Monthly source timer сохранён. До закрытия+20мин worker отвечает NOT_DUE;
после закрытия ждёт именно capture нужной сессии и её исходный accepted source seal.
Незавершённый новый capture не скрывает старые завершённые. Catchup компилирует
исторический capture на его собственное время завершения, проверяя его <= real now,
без подмены actual import/decision time. 16 октября нельзя переименовать в19-е.

Локальный heartbeat **`monthly58-daily-data-delivery`**, ACTIVE, ежедневно23:40
Asia/Nicosia. Доставляет недостающие seals, проверяет старые hashes, догоняет после
сна Mac. При штатном неизменном состоянии молчит; при новом сбое сообщает, ничего
не перезапускает. Первый действительный отчёт19Oct должен быть доставлен отдельно
после close20:00UTC и source >=20:20UTC. Mac может задержать локальную доставку во
сне; серверный экспорт от Mac не зависит. Existing `19-net-ibit` не изменялся.

Actual SCP повтор подтверждён: `already_imported=true`, data SHA прежний,
mtime первого seal **не изменился**. [Receipts](evidence/alpaca_monthly_data_parity_20261018/import_replay_verification.json).

## TESTED / review / ограничения

**19 targeted PASS**, отдельно те же **19 PASS на точном 47-file candidate**, 25
source imports, **0 checkout fallback**. Эти числа не складываются в38. Полный
repo suite не запускался. Реальный sealed market fixture включён в regression.
Проверены contamination, source clocks, immutable/replay/hash conflict, старые
пропуски/core200 отказ, historical restart, незавершённый capture и19Oct waiting.

Один независимый `gpt-6-astra/high` review; фактические model/effort проверены по
runtime metadata. 0 Critical, 4 Important: cross-runtime float, unfinished capture,
historical as-of, provenance binding. Все исправлены с RED→GREEN checks; второй
независимый review после исправлений не заявляется. Financial signoff отсутствует.
[Review](evidence/alpaca_monthly_data_parity_20261018/review.json),
[verification](evidence/alpaca_monthly_data_parity_20261018/verification.json),
[exact tests](evidence/alpaca_monthly_data_parity_20261018/exact_tests.xml).

Deployment receipt: **77 исходных static pins сохранены**, account lock inode813893
прежний, NET manager/DAY timers active, SHOP disabled/inactive. **0 broker requests,
0 broker writes, 0 financial-unit changes**. Активированы только новые DATA units.
[Deployment](evidence/alpaca_monthly_data_parity_20261018/deployment.json).

## Следующие реальные gates

1. **19Oct13:30UTC /16:30Cyprus**: фактическая NET DAY protection;
   **13:35UTC /16:35Cyprus** независимый readback. Сегодняшний snapshot не доказывает
   будущую защиту. SHOP не включать. Существующий монитор и heartbeat сохранены.
2. **19Oct после close**: отдельный actual source/report19 + IBIT prospective QA;
   Massive остаётся PENDING до настоящей сверки. Никаких backdated PASS.
3. **Monthly деньги**: E2E candidate1bd171f завершён ORDERS_OFF.30Oct actual closed
   selection/risk → отдельный точный personal OWNER GO →2Nov14:30–14:35UTC при fresh
   account/cost/finality/NET-flat/single-manager gates. CASH/NO_SEND допустимы.
4. **KITY**: safety candidate48020edd staged UNSELECTED; spent policy не повторять.
   Нормальный hold и экономический допуск не доказаны, нового paid retry нет.
5. **Elder**: прочитано локальное уточнение6a618d2 (f1 контракта остаётся0.55,
   producer0.50 становится informational). Origin всё ещё **31ccd113**; применять
   неопубликованный контракт нельзя. Следующий gate — публикация/versioned intake,
   затем тесты информационного mismatch, неизменных остальных geometry checks и
   causal context/risk/instrument. Producer и окно900 не менять, outcomes не читать.
6. **ATT1**: опубликованный contemporaneous control1c595cf: n1200/16days,
   diff−0.0006R/t−0.08, **ECONOMIC_FAIL**. Убран из денежной очереди; все старые
   engineering/evidence сохранены. Research board4129fed уже указатель на одну
   execution board — прежнее `pending pointer` исправлено.

Эта поставка не меняет frozen стратегию, риск, финансовые разрешения или LIVE.
