# Codex session checkpoint — 2026-08-20

> Исторический checkpoint. Актуальная точка продолжения:
> `reports/CODEX_SESSION_CHECKPOINT_2026_08_22.md`.

## Superseding completion update — 2026-08-20 15:48 UTC

Этот раздел **заменяет противоречащие ему оперативные факты ниже**. Старые
разделы сохранены как история аудита, а не как текущая broker truth.

### Alpaca: protection-only исправление уже в live

- На VPS атомарно выложен только контур защиты; новые входы, закрытие stale и
  mid-month rotation остаются выключены режимом `SAFE_HOLD`.
- Deployed SHA256:
  - `scripts/equities_alpaca_paper_bridge.py` —
    `1237fafbe73930eb5c3a0b53f4d2e426539c4f463086e02c4eae942a78c14ae1`;
  - `scripts/alpaca_protective_exit_manager.py` —
    `3239014036c8126e52e8deba5b29080624caf0cc631acd80bb7f7ba76097256e`.
- Исправленный контракт учитывает реальное ограничение Alpaca: fractional
  equity stop остаётся `DAY`, whole-share stop использует `GTC`. Ночной
  re-arm теперь берёт не сырой HWM, а подтверждённый брокером accepted floor,
  проверяет lifecycle до мутации и после действия сверяет точные qty/TIF/floor.
- Focused release suite: `53 passed`; полный Alpaca suite: `128 passed` и один
  ожидаемый FAIL старого frozen prereg hash, потому что защищённый source
  намеренно изменился. Старый prereg hash не переписывался.
- Live manager завершился `rc=0`; реальный bridge-run завершился `rc=0` и
  `protection_gate_status=PASS`. На 15:47 UTC прямой broker GET показывает:
  - ABBV `qty=0.135734866`, entry `247.55`, DAY stop `257.37` на полный объём;
  - SCHW `qty=0.563776973`, entry `101.552`, DAY stop `108.20` на полный объём;
  - equity `$490.05`, cash `$391.47`, protection coverage `2/2`.
- Обязательный последний gate — прямой broker readback после 20:30 UTC:
  истёкшие DAY-стопы должны быть переармированы не ниже `257.37/108.20`, а не
  снова в `235.17/96.47`. До этой проверки ночной дефект не объявляется
  окончательно закрытым.
- Снимать `SAFE_HOLD` сегодня запрещено: bridge всё ещё мог бы купить устаревший
  July-31 cohort `SNOW/MSFT/MA` в середине цикла, хотя проверенный контракт —
  completed month signal -> next session open. Первый чистый prospective cycle:
  сигнал на закрытии 2026-08-31, входное окно 2026-09-01. До new-money canary
  также обязательна ротация Alpaca credentials; значения ключей нигде не
  переносить в отчёты или Git.

### Storage и сбор данных восстановлены

- Локально на 15:46 UTC свободно `57,146,548 KiB` (около `54.5 GiB`), выше
  research disk-floor `50 GiB`.
- Wide M5 collector снова работает: `98/137` symbol status receipts уже имеют
  `state=complete`; некоторые отсутствующие у Bybit тикеры корректно дают
  нулевое число строк, поэтому receipt count не равен числу полезных рядов.
- Alt24 order-book density collector имеет `status=collecting`, 24 символа,
  `public_only=true`, `order_capability=false`; текущий файл около `1.5 GiB`.
- На VPS удалены только 13,340 заранее захешированных gitignored cache-файлов
  из точного manifest; evidence/runtime/equities/forex не затрагивались. Затем
  8 завершённых raw L2 partitions сжаты функцией с обратной распаковкой и
  SHA-проверкой; replay validation `4/4 PASS`.
- VPS L2 BTC/ETH снова собирает: heartbeat 15:47 UTC имеет
  `status=collecting`, оба book snapshots synced, `public_only=true`,
  `order_capability=false`, storage allowed, config SHA256
  `1d8943b7968054d6cde41ccf42b08031df91102aa40b450d1e21c56176b24810`.
  Свободно `9,952,216 KiB`; tape использует около `518 MB` при cap `2 GiB` и
  floor `5 GiB`.

### Следующие engineering gates

- ATT1/SBR1: внедряется отдельный pure parity/rebase contract. Денежной власти
  он не получает; после тестов ещё нужны live emitters и повторный frozen rerun.
- Alpaca entries: внедряется write-once cycle manifest с точным XNYS calendar,
  common as-of, 5-minute entry window, hash bindings и deterministic
  `client_order_id`; к bridge он пока не подключается.
- Order blocks: текущий 12-cell результат остаётся diagnostic FAIL_CLOSED.
  Найден governance defect: раннер физически декодировал цельные NPZ с
  reserved rows до timestamp filter, хотя holdout-метрики не вычислял. Новый
  `OrderBlockSnapshotV1` строится как causal context без права создавать ордер.

## Итог

Проект движется, но стадия остаётся **recovery + verified research**, а не
готовая много-ножевая торговая станция. Bybit live жив; второй crypto money
sleeve не разрешён. Alpaca — защищённый SAFE_HOLD pilot. MT5 manual-signal
контур безопасно подготовлен, но заблокирован до ротации утёкшего локального
MCP token. Web position console принят и проверен.

## Прямая live-проверка

- VPS: `bybot.service=active`, `trading-journal-web.service=active`.
- Bybit signed broker GET: `retCode=0`, открытых позиций `0`.
- `runtime/bot_heartbeat.json`: age около 14 секунд, `trade_on=true`,
  `dry_run=false`, `open_trades=0`, `regime=bull_trend`, WS guard inactive.
- Alpaca broker GET: equity `$490.13`, cash/BP `$391.47`, позиции ABBV и SCHW,
  broker stop coverage `2/2`. Стопы **не фиксируют прибыль**:
  `ABBV entry=247.55, stop=235.17` (`-5.00%` от входа) и
  `SCHW entry=101.552, stop=96.47` (`-5.00%` от входа). При исполнении ровно
  по stop, без gap/slippage, общий результат этих двух позиций относительно
  входов был бы около `-$4.55`; от проверенных текущих цен до стопов можно
  отдать около `$12.04`. Никакие ордера в этой сессии не изменялись.
- Alpaca entry authority остаётся выключенной:
  `ALPACA_SEND_ORDERS=0`, `ALPACA_ALLOW_NEW_ENTRIES=0`.

Это snapshot, не вечная истина; перед любым live-изменением проверяется заново.

## Принято и проверено

### Web

Commit `37d50a8` принят: multi-position broker-truth console, видимый timeframe,
stale/conflict handling и безопасная отрисовка. Focused web tests: `28 passed`.
Полное встраивание standalone page в основной SPA ещё не завершено.

### MT5 manual-signal contour

Commits `4e41339`, `a3c04c5`, `0487b6c` сохранены локально. Контур:

`Telegram/web text -> deterministic parser -> fresh quote/stale guard -> risk
calculation -> account allowlist -> owner confirmation -> one-use token ->
execution -> broker reconciliation -> journal`.

Fail-closed восстановлен: execution default OFF, live нельзя включить env-флагом,
account allowlist пуст по умолчанию, direct close/BE endpoints выключены, journal
не считает исчезнувшую позицию закрытой без broker history. Seven direct safety
scripts PASS. `.env` mode `600`, нового token в нём пока нет.

Пример EURUSD корректно разбирается. При midpoint `1.16830` RR целей примерно:
TP1 `0.72R`, TP2 `1.06R`, TP3 `1.41R`, TP4 `2.56R`. Перед demo нужен фиксированный
exit-policy на канал; иначе отчёт поставщика и реальное исполнение будут разными.

### ATT1/SBR1 parity

Старая research-геометрия признана неэквивалентной live: research умножал уже
готовый стоп и сохранял старые цели; live строит широкий ATR stop и новые цели.
Выбран новый live-native contract; прежний PnL не даёт promotion authority.

Добавлены:

- `research_lab/adapter_parity.py` — fail-closed comparator normalized ledgers;
- `research_lab/prereg/PREREG_ATT1_SBR1_ADAPTER_PARITY_2026_08_20.md`;
- `tests/test_adapter_parity.py`.

Gate сравнивает data/config/source hashes, evaluation coverage, entry/SL/TP,
TP/runner fractions, time stop, cooldown, regime/drop reasons и deterministic
outcome/net R. Focused ATT1/SBR1/parity suite: `37 passed`.

Отдельный найденный стык: после фактического fill fixed TP/SL могут быть
восстановлены относительно fill, но runner targets пока остаются абсолютными.
Это должно войти в live-adapter ledger и не позволяет считать старый replay
эквивалентным исполнению.

## Research continuity

Supervisor сейчас подтверждает 6 здоровых research-only jobs плюс отдельный
ATT1 limit-paper screen. Предыдущее число `12` больше не считать текущим.
Материальные состояния:

- Inplay prospective ETH остаётся `N=0`, orders/risk authority отсутствуют.
  Но текущий `status.json` одновременно пишет `raw_signal_count_lookback=0`,
  тогда как предыдущий startup receipt сообщал `32/40/62/81`. До повторного
  hash-bound startup parity это конфликт `NOT_CONFIRMED`, а не доказанная
  рыночная тишина.
- ATT1 limit paper: `N=3`, maker fills `2/3`, mean saving `+2.48 bps`; это
  позитивный механизм, но выборка не разрешает live.
- Wide Bybit M5 materialization дошёл до `69/137`, около `757 MiB`, sealed
  holdout не читался. Процесс сейчас не движется: disk guard остановил запись.
- XSEC v3 shadow обновляется ежедневно, orders sent false.
- Funding shadow: 34–36 closed trials в текущих frozen summaries. Средние
  положительные, но одна версия имеет отрицательную медиану и до 89% positive
  concentration; promotion запрещён до tail/concentration audit.
- Три L2/tape collector и alt24 density штатно остановлены storage guard:
  свободно около `53.06 GB` при floor около `53.69 GB`. Старые завершённые
  JSONL уже сжаты; штатная verified compression нашла `0` дополнительных
  завершённых файлов. Guard не обходить. Дни с coverage около 86% остаются
  неполными и не годятся для итоговых выводов.

## Независимая проверка ордерблоков Claude

Commit `76fc63c` находится локально поверх parity commit и **не запушен**.
Статическая проверка `orderblock.py` и `run_ob.sh` прошла; в data root ровно
137 H1 bundles. Локальный log воспроизводит 12 ячеек: возврат в order-block
лучше контроля «просто уровень» в 9/12, но хуже случайного входа в 8/12
(не 9/12, как было написано в пересказе). Ни одна конфигурация не проходит
заранее заявленное условие одновременно на обоих окнах.

Этот результат пока `FAIL_CLOSED`, а не окончательный запрет семейства:

- log игнорируется Git и не имеет passport/hash receipt;
- сделки допускают перекрытие (`HOLD=60`, блокировка только на 15 баров);
- control B может выбрать событие/возврат за границами назначенного окна;
- нет continuity/PIT/concentration checks, uncertainty и multiple-test gate;
- `docs/PRAVDA.md` в commit `76fc63c` не изменён, несмотря на заявленный текст.

После ремонта измерения разрешён отдельный prereg для **impulse continuation**.
Возврат-в-зону нельзя отправлять в shadow/live по текущему результату.

## Что НЕ готово

- Денежная crypto-книга: только ATT1 tiny canary. SBR1 — research candidate,
  не подключён к monolith; Inplay prospective N0; XSEC/funding shadow only.
- Исследовательский портфель ATT1+SBR1 архитектурно полезнее текущего live
  (две стороны/два режима), но **не доказанно лучше**: его исторические цифры
  получены до обнаружения research/live geometry mismatch.
- `bot/exposure_gate.py` имеет тесты, но не подключён к monolith.
- `regime_orchestrator.py` существует, но не реализует согласованный H1
  BTC/EMA200 flat-up/flat-down contract для ATT1/SBR1.
- Decision bus у ATT1 default OFF; SBR1 wiring отсутствует.
- Alpaca entry-relative challenger: proxy `25.65% annualized`, DD `14.36%`,
  40 trades, audit arithmetic PASS, но exact live contract false и PIT/corporate
  actions/paper lifecycle gates не закрыты.
- XAU: данные готовы (87,439 M5; 7,291 H1, pre-holdout), доказанной стратегии нет.
- FX/CFD: money authority отсутствует; сначала XAU frozen replay, затем
  portability на EURUSD/GBPUSD и broker-cost calibration.

## Следующий порядок

1. Освободить минимум 1 GiB безопасно (verified archive/cache cleanup с
   receipt), не снижая disk floor; затем возобновить wide M5 и L2/tape.
2. Реальные research/live emitters для normalized parity ledger; исправить
   fill/runner target rebasing и добиться comparator PASS.
3. Перепрогнать ATT1 short flat-down и SBR1 long flat-up на выбранной
   live-native геометрии, одинаковых издержках и pre-sealed bytes.
4. Подключить exposure gate и H1 EMA200 regime labels только в zero-risk shadow;
   затем повторить portfolio allocator replay.
5. Alpaca: exact paper lifecycle replay entry-relative challenger. До PASS
   SAFE_HOLD не снимается.
6. Повторить Inplay startup frequency gate с hash-bound config и устранить
   конфликт `32/40/62/81` против текущего lookback `0`.
7. XAU: одна frozen session breakout/retest base/stress; news blackout —
   отдельный challenger, не подгонка основной руки.
8. MT5: owner rotates token, заполняет explicit account allowlist; затем один
   demo signal и reconciliation. Никаких реальных денег на первом запуске.
9. Завершить wide M5, затем Inplay multi-symbol replay без изменения frozen ETH
   prospective contract.
10. Исправить измеритель order-block controls, провести passported rerun и
    отдельно предрегистрировать impulse-continuation, не меняя старый результат.

## Условные сроки, не обещания

- 1–2 engineering days: parity emitters + corrected ATT1/SBR1 rerun.
- 2–4 engineering days: Alpaca paper lifecycle parity и XAU first frozen replay.
- 1–2 weeks: решение о bounded Alpaca micro-canary, только если paper PASS.
- 3–6 weeks: возможный второй crypto money sleeve после parity, shadow и owner gate.
- 6–12 weeks: агрессивный сценарий 3–4 crypto legs; отрицательные результаты
  могут увеличить срок, поэтому дата не заменяет gates.

## Git/security blocker

Локальный HEAD: `76fc63c`, его безопасная основа включает parity commit
`2f0c2a9`; ветка `ahead 6, behind 2`. Remote содержит старый commit с MT5 token
и расходится с safe history. Сначала token rotation, затем требуется отдельное
явное разрешение владельца на `git push --force-with-lease`. Обычный push сейчас
не подходит. Все работы Claude за четыре дня проверенными/запушенными считать
нельзя: проверена критическая цепочка и отдельно `76fc63c`, но не сотни WIP.

В грязном worktree сейчас около `374` записей Claude/legacy. Они не удалены и
не попали в тематические commits. `signal_copy/app.py` и
`signal_copy/test_journal.py` снова изменены после принятого fail-closed commit,
поэтому терминал Claude надо переаудировать до запуска. `.git/index.lock`
открыт активными приложениями; его не удалять и не коммитить поверх текущей
работы. Владение зонами закреплено в `docs/ACTIVE_WORK_OWNERSHIP.md`.

## С какой точки начинает следующий чат

1. Прочитать этот файл целиком и считать его единственным актуальным checkpoint.
2. Снять свежие broker/service/Git/disk факты; старые числа не объявлять live.
3. Не трогать стопы Alpaca без отдельного owner решения; сначала проверить
   effective GTC/protective-manager deployment и paper lifecycle parity.
4. Закрыть storage blocker, затем вернуть wide M5/L2 collectors.
5. Закрыть ATT1/SBR1 parity и только после corrected rerun разрешать zero-risk
   shadow. Старые `+86.7R` и `2.63R/month` не использовать как прогноз денег.
6. Аудировать свежий terminal WIP Claude и MT5 token rotation gate.
7. Не открывать sealed holdout 2025-10..2026-06 без нового явного разрешения.
