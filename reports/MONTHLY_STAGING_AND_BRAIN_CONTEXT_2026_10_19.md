# Monthly staging / фактическая обвязка Brain — 19 октября 2026

## DONE / TESTED

Владелец явно разрешил передачу проверенного Monthly-кандидата на свой VPS
64.226.73.119 в отдельную неактивную папку для серверных проверок. Это разрешение
на code-only staging; standing financial GO, выбор active версии и запуск units
оно не создаёт. Предыдущий auto-review transfer blocker закрыт этой операцией.

- Точные44 source pins повторно сверены локально. **165 exact tests PASS**,34
  candidate imports/0 checkout fallback. Повторный прогон не прибавляется к
  предыдущим165. **51 targeted Brain/Elder tests PASS** — отдельная граница
  проверки, не51 денежных или проспективных событий.
- Загружены только44 файла и manifest в
  `/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-348690be65466d3c/app`.
  Material SHA256 `348690be65466d3cfc34c7c31875b65907a43f338b189613e0fe888c61b14582`.
- Независимый серверный GET: все hashes совпали;43 Python AST разобраны,
  дополнительных файлов0, imports/code execution0. Это проверка доставки и
  синтаксиса, **не server runtime rehearsal/автономная торговля**.
-77 protected static pins и original lock inode813893 сохранены. NET manager
  timer/NET DAY monitor active/enabled; SHOP inactive/disabled до и после.
  Broker requests/writes0, financial units changed0, active pointer changes0,
  owner grants created0. Actual NET opening protection13:30UTC/readback13:35UTC
  ещё впереди и этим snapshot не доказаны.

[Staging](evidence/monthly_staging_20261019/staging.json),
[независимый readback](evidence/monthly_staging_20261019/server-readback.json),
[проверки](evidence/monthly_staging_20261019/verification.json),
[операционный snapshot](evidence/monthly_staging_20261019/ops-before.json).

## Brain: что фактически продолжается

Проверены существующие Mac source hash chains `opportunities.jsonl` и
`decisions.jsonl`, без запуска Brain, чтения outcomes или изменения Claude files.
На момент проверки:22448 opportunity rows,68878 decision rows; из последних
1534 относятся к BRAIN_V2_DET. Последняя запись —19Oct07:13:51.529UTC.
Остальные политики: BASELINE_V1/BRAIN_V1/HEDGE_V1 по22448 записей.
Это свежие source facts; они не доказывают непрерывную работу демона, независимые
сделки, causal freshness каждой feature или пользу для денег.

В published `PREREG_BRAIN_V2_DET_2026_10_17.md` сравнение после выравнивания
унаследованных позиций начинается31Oct14:00UTC. Нынешние V2 записи относятся к
прогреву и не превращаются в prospective economic PASS при сегодняшнем импорте.
[Фактические source hashes/counts](evidence/monthly_staging_20261019/brain-current-source.json).

### Новый точный blocker ежедневной передачи

Existing receiver содержит8 ранее принятых receipts. Полный catchup с исходной
границы17Oct13:52 возвращает **BLOCKED / receiver_capacity** до append:
6136 projected receipts против4096;28196655 bytes против8388608.
Свободного места достаточно; проблема — контракт ограниченного receiver, не диск.
Все8 прежних receipts, bytes, hash, inode и mtime сохранены. Нельзя выдавать
источник с68878 решениями за6136 уже доставленных production-shadow receipts.

Следующий ограниченный P1 — безопасная непрерывная поставка через существующий
read-only journal: versioned retention/rotation/cursor с доказанным restart/replay,
без пропусков, дубликатов, обрезания producer chain или второго Brain. Простое
увеличение cap и ручная фильтрация неудобных событий не являются acceptance.
Новый финансовый журнал и денежные полномочия не нужны.
[Фактический preflight/no-mutation receipt](evidence/monthly_staging_20261019/brain-catchup-preflight.json).

## Пила, отскоки, hedge: факты research, не обещания

Прочитан опубликованный origin `1407fbf64178d92f2d121e1f2a114665c1b1c4e0`;
research judges/PnL не запускались.

| Компонент | Фактический статус / роль | Следующий полезный gate |
|---|---|---|
| Context / Brain regimes | Общие режимные labels и Shadow решения существуют. В опубликованном72-pair исследовании6 timing confirmations,0MONEY_PASS | Сравнивать BASELINE/Brain на тех же возможностях, расходах и капитале; filter полезен только после net evidence |
| RANGE_MR WFO | FAIL, published19979 model trades, mean−0.1235R; не доказанная прибыльная торговля пилы | Не повторять подбор на использованной истории для спасения версии |
| KANAL_OTSKOK | Crypto long/short NEGATIVE в опубликованном отчёте | Не включать в money queue; другой механизм требует собственной prereg |
| LIQ_OTSKOK_4H_V2 | Отдельная гипотеза ликвидационного потока; existing source/data delivery, economic gates OPEN | Frozen warmup до28Oct08:35UTC;≥200 events/≥20days/≥15coins, по dossier не ранее17Nov; raw records не события/не money PASS |
| Elder | Hedge-only; standalone KILL. Local f1 clarification принят без изменения hedge geometry | Actual causal context/risk/instrument,≥30prospective и frozen parity/delay/restart/ETS2M gates; затем bounded owner packet |

Published evidence: [общий research delta](https://github.com/Brokenbass90/by-bot/blob/1407fbf64178d92f2d121e1f2a114665c1b1c4e0/research_lab/ROADMAP_VKLAD_RESEARCH_2026_10_19.md),
[режимы/денежный судья](https://github.com/Brokenbass90/by-bot/blob/1407fbf64178d92f2d121e1f2a114665c1b1c4e0/research_lab/ITOG_FABRIKA_VOROTA_V2_1_V2_2_2026_10_18.md),
[RANGE WFO receipt](https://github.com/Brokenbass90/by-bot/blob/1407fbf64178d92f2d121e1f2a114665c1b1c4e0/research_lab/data/factory_v3/WFO_RANGE_MR_rezultat.json),
[канальный отскок](https://github.com/Brokenbass90/by-bot/blob/1407fbf64178d92f2d121e1f2a114665c1b1c4e0/research_lab/ITOG_FABRIKA_KANAL_OTSKOK_2026_10_18.md),
[LIQ dossier](https://github.com/Brokenbass90/by-bot/blob/1407fbf64178d92f2d121e1f2a114665c1b1c4e0/research_lab/dosie/ZAGOTOVKA_DOSIE_LIQ_OTSKOK_4H_V2.md).

## REMAINING / статус дельта для Claude

Monthly code staging DONE/UNSELECTED. Automatic actual broker cost-finality
producer, one production applying runner/handoff/rollback и concrete standing
packet всё ещё P0. Server syntax/source parity не закрывает эти функции.
KITY SPENT/ORDERS_OFF, NET/SHOP/стратегии/финансовые полномочия сохранены.
Brain source продолжает записи; receiver catchup BLOCKED_CAPACITY с точной
причиной и без потери старых receipts. Режимные filters остаются Shadow.
Claude не отправлялось сообщение; его research code/KARTA/VOROTA не менялись.
