# ATT1/SBR1 reserved OOS diagnostic — результат 2026-08-29

## Итог

Одноразовый diagnostic с известной контаминацией был авторизован владельцем и
запущен ровно один раз. После создания durable claim и декодирования всех
входов runner завершился `FAIL_CLOSED_AFTER_CLAIM` из-за ошибки суммаризатора:

`AttributeError: 'tuple' object has no attribute 'get'`.

Авторизация потреблена. Повторный запуск v1 запрещён и не выполнялся. Live,
broker, private API, ордера, риск и money authority не затрагивались.

Независимый failure-forensic audit подтвердил неизменность входов и всех 16
частичных scorer-артефактов, exact inventory, research/live parity, причинность
accounting и отсутствие денежного воздействия. Формальная попытка остаётся
технической неудачей; восстановленные ниже метрики являются offline forensic
диагностикой и не превращают её в успешный one-shot.

## Предварительно замороженный вывод

| Нога | Режим | Raw / accepted | Sum R | PF | Первая / вторая половина R | Max DD R | Вывод |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| ATT1 | base | 76 / 61 | +21.3471 | 1.7921 | +20.6843 / +0.6629 | 8.5150 | — |
| ATT1 | stress | 76 / 61 | +19.5021 | 1.7030 | +19.8393 / **−0.3372** | 8.8512 | `FAIL_CLOSED` |
| SBR1 | base | 16 / 16 | −3.3131 | 0.6418 | −0.9452 / −2.3679 | 5.1562 | — |
| SBR1 | stress | 16 / 16 | −3.6881 | 0.6080 | −1.1314 / −2.5567 | 5.2649 | `INCONCLUSIVE_LOW_N` |

ATT1 показывает сильный суммарный результат, но почти весь он находится в
первой хронологической половине. Заранее заданное условие требовало строго
положительный результат в обеих половинах base и stress. Вторая stress-половина
равна `−0.337197R`, поэтому продвижение запрещено независимо от положительного
общего `+19.502091R`.

SBR1 имеет только `N=16`, что ниже порога `N>=40`, и отрицательна в обеих
половинах, base и stress. Формальная классификация — `INCONCLUSIVE_LOW_N`, но
никакого положительного сигнала для продвижения текущей геометрии нет.

## Что именно сломалось

`read_jsonl()` возвращает словарь, ключами которого являются tuple
`(symbol, bar_ts, side)`. В `_summarize_ledgers()` runner передал сам словарь в
`chronological_symbol_occupancy()`, поэтому цикл получил tuple-ключ вместо row и
позже вызвал `row.get(...)`.

Минимальная будущая техническая правка: передавать `live.values()`. Она не даёт
права повторить consumed v1. Если когда-либо понадобится формальный v2, он
должен иметь новый output path, claim, config и отдельную owner authorization,
а v1 должен остаться byte-for-byte неизменным.

## Forensic accounting

- окно: `[2025-10-01T00:00:00Z, 2026-07-01T00:00:00Z)`;
- классификация: `RESERVED_OOS_DIAGNOSTIC_WITH_KNOWN_CONTAMINATION`;
- reserved inputs: `8/8`, `628,992` строк;
- causal bootstrap inputs: `8/8`, `1,334,016` строк;
- частичные output-артефакты: `16/16`, все SHA совпадают;
- research/live byte parity: PASS;
- normalized base/stress comparator parity: PASS для всех четырёх ячеек;
- live/broker calls: `0/false`;
- private API calls: `0`;
- orders created/changed: `0`;
- money authority: `false`;
- promotion authority: `false`.

## Идентичности

- source commit до запуска: `686298722f08ab1cc278854f8bbe97abfa59555b`;
- authorization commit: `9baa5f8`;
- authorization ID: `owner-authorization-20260829T080646Z-6862987`;
- config SHA: `6f4b3b2e5387cf7755617ec0a68ae4e63d4b6cc502332c755eb795117e7eab96`;
- input manifest SHA: `8f82bb7f6e5fad56e78acb4e9ffe567d2cf045c7901a7e1744a4ad5d12b7434c`;
- runner SHA: `9194e5c1e5841ebe9df579b0a15eb4a7fc27ecad3028d2a71eb2af69198b16b4`;
- original post-audit SHA: `da72992ee68c653a4c16274c8f4559caab211217d89e2f9bcd99e8e1b113b9b8`;
- one-shot claim SHA: `3f3dcf0decaa8352608c2204e9805494ac7fa3d1b17544dd4b95175080a179cb`;
- terminal failure receipt file SHA: `cc128cd201ea5568fc225b1ad945767613b7743321f74713da65b55f7b9d4e67`;
- terminal receipt canonical self-hash: `b667841b5444d15ed08c954a1a8c2d2a1897470b8b3471188b3e0a01e7347e73`;
- failure-forensic receipt self-hash: `f2f75cead491dc375b7f68c63fe521ba8ef5b3de1bc0ec7027d62f7ab2a0f7a2`.

## Проверка пакета

- финальное независимое ревью: `Spec PASS`, `Code-quality PASS`;
- failure-forensic suite: `26 passed`;
- post-authorization regression suite: `64 passed, 2 deselected`;
- две deselected проверки являются только pre-execution контрактами и требуют
  физического отсутствия authorization; удалять уже потреблённую authorization
  ради их запуска запрещено;
- до authorization тот же полный Task 1–3 suite проходил `66/66`;
- `py_compile`, CLI fresh-versus-tracked receipt equality и
  `git diff --check` прошли;
- secret scan добавляемого пакета совпадений не нашёл.

## Решение и следующий falsifiable шаг

1. Не повышать ATT1-риск и не подключать к деньгам новую геометрию по этому
   результату. Отдельно исследовать временную деградацию без подбора параметров
   на уже просмотренном окне.
2. Не продвигать текущую SBR1. Поставить её текущую геометрию в quarantine либо
   сформулировать новую заранее зарегистрированную long/continuation-гипотезу.
3. Не тратить новую owner authorization на механический rerun v2: forensic
   экономика уже дала ответ `no promotion`. Исправление суммаризатора сохранить
   для будущих независимых пакетов.
4. Переключить основной исследовательский ресурс на заранее объявленный Plan B:
   bull-continuation и XSEC PIT rebuild. Каждый кандидат проходит новый
   preregistration и не использует этот OOS для тюнинга.

Это не доказательство будущей доходности и не разрешение на сделки. Это быстрый
и полезный отрицательный gate: потенциально опасное продвижение остановлено до
капитала, а следующая гипотеза может быть проверена без месяцев ожидания live.
