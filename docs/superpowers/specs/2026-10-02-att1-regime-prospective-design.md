# ATT1: причинно доступные regime receipts перед сравнением политик

Дата: 2026-10-02. Статус: **DRAFT — owner review pending; не реализовано**.
Это первый этап нового исследовательского контура, не разрешение на LIVE,
не preregistration прибыльности и не глобальный bull/bear/range router.

## Цель и ближайший результат

Владелец хочет ограничить входы неподходящим режимом рынка и довести существующие
стратегии до автономной работы с доказанным результатом после расходов.
Первый проверяемый вопрос: можем ли мы связать каждую prospective возможность
ATT1 с валидным BTC regime receipt, действительно доступным **до решения**?

Результат этапа — append-only исследовательский архив режима и проверяемый
availability audit всех событий скана. Он показывает coverage и конкретные
причины UNKNOWN; он не выносит вердикт о доходности фильтра. Следующий этап
сравнения политик допускается только отдельным замороженным протоколом.

## Проверенные ограничения

- NEW public timing epoch уже работает с driver97239996/core26b14571/profile79d23e38.
  На снимке14:29:12UTC:51/51 скан,50 NO_SIGNAL,1 stale HFT,0 sessions/open,
  broker/order calls0. Исправление ещё не проверено на новой заполненной позиции.
- OLD caller по текущим файлам конфигурации defaultOFF. Его default source
  manifest и regime input отсутствуют в `/root/by-bot`; updater пишет в другой
  каталог `/opt/bybot-research/live-caller-parity`. Отсутствие caller journal
  ожидаемо при OFF и само по себе не доказывает неисправность writer.
- Закрытая BTC14:00 свеча записана updater в14:03:06.841UTC. Текущий public
  скан51 имён завершён между14:00:23.369 и14:02:13.126UTC. Это не полная история
  availability, но конкретный поздний файл нельзя считать доступным раньше его
  записи. Сейчас нет независимого immutable архива первого наблюдения receipt.
- Существующий gate допускает ATT1 только при `flat_down`: deviation от BTC H1
  EMA200 в диапазоне [-2%,0%). `below_band` тоже запрещён. Это не эквивалент
  «любой медвежий рынок» и не классификация тренда каждой монеты.
- Public admission ведёт active/cooldown по символу. Выкинуть часть baseline
  trades недостаточно для независимой политики: освобождённый symbol/cooldown
  может разрешить другие будущие входы. Portfolio slots/capital OLD здесь
  не моделируются. Общей полной ленты book observations для таких новых holds нет.

Источник фактов: `reports/ATT1_REGIME_GATE_READINESS_2026_10_02.json`.

## Выбор подхода

1. Включить существующий OLD caller: сейчас непригодно — missing inputs,
   возможная блокировка входов и новая финансовая политика.
2. Пометить старые сделки последним BTC tip: непригодно — availability не
   доказана, возникает lookahead, меняется counterfactual admission.
3. **Рекомендуется:** отдельный prospective archive и causal availability audit,
   затем отдельный протокол сравнения. Это ближайший этап, определённый ниже.

## Архив режима и граница доверия

Отдельный defaultOFF процесс читает только фактический updater receipt; не
вызывает брокера и не делает network fetch. Один writer пишет в отдельный
research runtime, не в авторитетный lifecycle journal. Consumer не меняет
ATT1 driver/coordinator/profile, updater, OLD env, cron или текущую timing epoch.

Для каждого нового receipt архивируется полный исходный blob с byte SHA256,
проверенными receipt/state hashes и declared schema; source path, deployment
pins, reader epoch, UTC wall timestamp окончания чтения, monotonic read interval,
closed-H1 cutoff и sequence/hash-chain. Проверяются тип/размер/owner/mode0600,
symlink/hardlink, полное атомарное чтение и стабильность file identity.
Hash и freshness — разные проверки. Ошибка чтения/валидации также фиксируется.

`first_observed_ms` — момент окончания **этого** успешного чтения, нижнюю
историческую границу доступности он не доказывает. Startup существующий tip
помечается BOOTSTRAP; доступность ранее запуска архиватора UNKNOWN. Нельзя
восстанавливать timestamp из mtime или менять его задним числом. Wall-clock
rollback/jump и неопределённая синхронизация часов приводят к CLOCK_UNKNOWN;
monotonic sequence не заменяет UTC сравнение с decision clock. Конкретные
resource/clock bounds и security implementation определяются в плане до запуска.

## События ATT1 и причинный join

Отдельный reader читает законченные immutable prefix сканов текущей public epoch,
проверяет canonical hash-chain/уникальность и сохраняет identity исходного
события. Append не переписывает baseline и не чинит повреждённый input.
Сохраняются все51 имён: NO_SIGNAL, stale/error/rejected, candidates, admitted,
nonfills. Denominator не сужается до filled trades или gate-allowed observations.
План фиксирует expected inventory: reader epoch × каждый наступивший H1 cutoff
× frozen51 symbols, с явными частичными startup/shutdown окнами. После заранее
заданного completion allowance отсутствующее событие остаётся MISSING_SCAN или
UNRESOLVED_SCAN в coverage denominator. Эти строки принадлежат только аудиту:
не создаём baseline SCAN, signal или gate decision. Позднее найденный исходный
event добавляется отдельным разрешением omission, не переписывает старую запись.

Для signal-bearing события нужны materialized signal/closed-H1 inputs,
data/instrument/source hashes и времена фактического получения. SCAN timestamp
означает завершение скана, не обязательно момент admission: для admitted
используется исходный intent submit_ms и его точные source dependencies.
Signal hash нельзя без проверки считать именем файла blob. Если событие отказа
не содержит восстановимого decision cutoff, оно сохраняется с UNKNOWN_CUTOFF.
Для NO_SIGNAL/error допускается только descriptive scan-time annotation;
это не simulated gate decision и не trade outcome.

Для валидного admission/candidate cutoff выбирается только receipt, который
архиватор уже прочитал до cutoff и который относится к той же закрытой H1
свече. Возраст от candle close до cutoff <=300000ms; существующий2s market
freshness gate остаётся отдельной неизменной проверкой. Поздний receipt не
исправляет более ранний UNKNOWN. Если input найден только после события,
результат NOT_PROVEN_AVAILABLE, даже если свеча формально закрыта и hash верен.

Результаты join: ALLOW_FLAT_DOWN, BLOCK_OTHER_REGIME, UNKNOWN_MISSING,
UNKNOWN_STALE, UNKNOWN_CUTOFF, NOT_PROVEN_AVAILABLE, INVALID_INPUT,
CLOCK_UNKNOWN. Availability/invalid outcomes нельзя считать полезной селекцией
рынка. Existing updater minute03 остаётся как есть: сначала измеряем доступность
и при необходимости отдельно проектируем supply ordering; baseline не задерживаем.

## Разделение инженерной проверки и edge

Engineering acceptance: чистое воспроизведение из immutable inputs, все события
учтены ровно один раз, timestamps/hashes доступны, поздние/invalid inputs не дают
ALLOW, источник/authority baseline не изменены. Полнота opportunity tape и доля
доступных regime inputs публикуются, включая UNKNOWN; нулевая availability
означает BLOCKED_DATA_SUPPLY, а не победу фильтра.

Никакого прибыльного PASS, target sample или выбора порогов после просмотра PnL
на этом этапе. Даже2–3 clean public terminals проверяют эксплуатацию, не net edge.
Для сравнения потребуется заморозить estimand, sample/power, costs, multiple-look
rules и termination. Candidate ведёт собственные per-symbol admission/cooldown
состояния, с исходными frozen правилами, и получает полную causal ленту наблюдений
для candidate-only holdings. При отсутствии ленты честный verdict BLOCKED;
не синтезируем2s исполнение из OHLC. Portfolio/capital policy — отдельный scope.

## Изменения, проверки и эксплуатация следующего этапа

После review документа план должен назвать точные archive/reader modules,
schemas/config paths, source closure, security/resource bounds и rollback.
До deployment обязательны byte/inode quotas архива, запас свободного места
**выше** текущего baseline guard536870912bytes и ограниченная incremental работа
reader, без повторного чтения полного растущего журнала на каждом poll. При
достижении лимита/reserve или заранее заданного baseline-health stop condition
автоматически приостанавливается только audit collection, с сохранением evidence.
Нельзя остановить/перезапустить public baseline или удалить архив ради свободного
места. Проверка free-space выполняется до записи и учитывает максимальный append.
Targeted fixtures: поздний/same-cutoff/stale режим, future/open bar, mutated hash,
перезапуск/duplicate/partial prefix, потерянный blob, unknown cutoff/clock,
missing scan/partial-hour coverage, byte/inode/reserve/health suspension,
проверка всех исходных51 результатов без нового lifecycle writer.

Сначала local candidate + fixtures + read-only replay **новых** audit envelopes.
Deployment оценивается отдельно, defaultOFF; остановка архиватора прекращает
только сбор нового аудита. Архив и UNKNOWN сохраняются. Исходные timing epoch,
2s, freshness, стратегия, admission, risk и financial flags остаются неизменны.
Никакие sealed/consumed outcomes не читаются и не пересчитываются.

Порядок после этого этапа: ATT1 causal evidence → независимое prospective
сравнение → решение по конкретному admission gate. Затем существующий Elder
(его третий экран уже есть), bull/range leads и Factory по их отдельным gates.
Alpaca остаётся на текущем manager; следующая DAY проверка05.10 по broker truth.
