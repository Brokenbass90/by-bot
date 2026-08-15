# Утренняя recovery-сессия — 15 августа 2026

Обновлено: 2026-08-15 04:50 UTC.

## Итог

За ночь не появилась вторая подтверждённая денежная нога, но сделан большой
инженерный шаг: устранено ещё одно ложное сравнение ATT1, перспективное
улучшение Alpaca перенесено из proxy в выключенный реальный bridge, а первый
эксперимент прошёл полный tamper-evident lifecycle. Это не «ещё месяц сначала»:
live ATT1 остаётся на `N5/20`; заново и правильно пересчитан только исторический
контракт, который раньше использовал не тот восьмой символ.

Никаких заявок, отмен, ручных закрытий, изменений риска, deploy или restart в
этой сессии не выполнялось. Запечатанный период `2025-10..2026-06` не читался.

## ATT1: live и история больше не смешиваются

| Слой доказательств | Факт | Решение |
|---|---:|---|
| clean live forward | N5, +2.950R, PF(R) 3.289 | tiny canary оставить |
| exact live major8 baseline | 557 сделок, -15.654R, PF 0.960 | не продвигать |
| exact live major8 pivot challenger | 402 сделки, -13.611R, PF 0.944 | `DECISION_REJECTED` |

Точная восьмёрка live: BTC, ETH, SOL, ADA, LINK, LTC, DOT, SUI. Старое
corrected-сравнение подменяло LTC на AVAX. LTC после исправления оказалось
крупнейшим минусом challenger (`-12.094R`), SOL `-9.419R`, ETH `-7.239R`;
ADA, DOT, LINK и SUI положительны. Значит проблема не решается общим
`pivot-sequence` фильтром. Следующий честный шаг — анализ отрицательных
фенотипов и заранее заданная symbol/market-mechanism гипотеза, а не выбор
победителей после просмотра.

Live cohort не сбрасывается из-за backtest verdict. Повышение `0.10 → 0.25`
остается запрещено до N20, net `>=2R`, PF `>=1.20`, DD `<=5R`, zero conflicts,
паритета и прямой проверки effective risk.

Источники: `reports/evidence/ATT1_LIVE_LIFECYCLE_20260814.json`,
`research_lab/results/att1_live_major8_corrected_preholdout_v1_20260815/result.json`,
`independent_audit.json`, `reports/evidence/EXPERIMENT_LIFECYCLE_20260815.json`.

## Что проверено из последних работ Claude

В git нет нового отдельного коммита Claude поверх `5cc1b39`. Полезная идея из
`research_lab/trial_ledger.py` принята по смыслу, но файл не принят в основу:
он терпимо читает повреждённые строки, не связывает approval с content hash и
не закрывает повторный result. Вместо этого создан
`research_lab/experiment_lifecycle.py` с жёсткими стадиями и SHA256-цепочкой.

Большой worktree не признан мусором и не удалён. Ранее классифицировано `163`
code-кандидата: `5` test-backed, `115` evidence/reproduction, `16` review,
`27` quarantine. Это очередь проверки, а не одна поставка. В текущий commit
попадают только файлы этой сессии и доказательные receipts.

## Sloped V3: что именно провалилось

Это стратегия пробоя и ретеста наклонной, не отскок и не весь класс наклонок.
Контракт использует подтверждённую 4h pivot-line, break, первый 15m retest,
delayed reclaim и последующий BOS. Causal-review не нашёл очевидного lookahead,
same-bar fill или незакрытых pivot. Результат: `18` сделок, `-5.371R`, PF(R)
`0.521`; short `-4.497R`, long `-0.874R`.

Поэтому V3 не «чинится» случайным стопом или ещё одним timing knob. Две
следующие фальсифицируемые гипотезы:

1. upstream break quality: displacement/close acceptance на 4h до ретеста;
2. отдельная long continuation-механика BTC/ETH, не зеркальная копия short.

Не больше двух рук в одном pre-reg batch; затем поправка на множественные
проверки и независимый аудит.

## Inplay: ожидание не равно простой

Collector healthy, current code SHA совпадает с замороженным reference, но
prospective остаётся `N0`. После старта зарегистрировано 787 отказов:
`impulse_weak=547`, `no_breakout_side=144`, `impulse_body_weak=96`. На четырёх
старых 35-дневных срезах тот же код давал `0.91–2.31` raw signals/day, что при
повторении режима соответствовало бы примерно `13–33` дням до N30. Но текущий
наблюдаемый темп равен нулю, поэтому выдавать дату N30 как обещание нельзя.

Решение: контракт не ослаблять; проверить freshness/coverage входных баров и
продолжить prospective. Переписывать правила можно только как новую версию с
новой предрегистрацией, а не задним числом.

Источник: `reports/evidence/INPLAY_CADENCE_20260815.json`.

## Alpaca: улучшение дошло до реального bridge, но не до live

Entry-relative challenger на clean-962 proxy дал `25.65%` annualized, DD
`14.36%`, PF `1.837`, 40 сделок и 5 красных месяцев из 25; stress почти не
ухудшил результат. Арифметика прошла независимую проверку.

В `scripts/equities_alpaca_paper_bridge.py` добавлен default-off путь:

- дождаться broker fill и `filled_avg_price`;
- сохранить абсолютную signal-time risk distance;
- перенести её на фактический fill;
- только затем поставить protective stop;
- fail-close для bracket, отсутствующей fill price и незащищённого входа.

Флаг `ALPACA_ENTRY_RELATIVE_STOP_ENABLE` выключен. Live не менялся. Focused
Alpaca/lab/XAU suite: `50 passed` в итоговом наборе.

Почему ещё SAFE_HOLD: clean subset не является полным point-in-time universe,
есть 24 конфликта bars-after-delist, не закрыты corporate actions, официальный
XNYS calendar, broker lifecycle/cost calibration и свежая prospective selection
cohort. Реалистичный следующий gate — paper lifecycle replay за 2–4 инженерных
дня. Bounded micro-canary можно обсуждать через 1–2 недели только после PASS и
явного принятия владельцем остаточного PIT ограничения.

Источник: `reports/evidence/ALPACA_EXACT_READINESS_20260815.json`.

## Лаборатория: сделано и осталось

Реализовано:

- единый experiment ID;
- hash-bound owner approval;
- SHA prereg/spec/preflight/passport/result/audit;
- глобальная append-only SHA256 chain;
- проверка артефактов при аудите;
- fail-close на порче, повторе, нарушении порядка и nonzero audit;
- атомарный audit receipt.

Первый lifecycle имеет 9 записей, целостность и артефакты прошли, финал —
`DECISION_REJECTED`. Это важный успех: лаборатория смогла не только запустить,
но и доказуемо отклонить собственную гипотезу.

Осталось: 4 idea cards не связаны с experiment IDs; nightly scheduler receipt
протух примерно на 2244 часа; 30 старых approvals остаются name-only. Текущий
вердикт поэтому честно остаётся
`PARTIAL_PIPELINE_NOT_SELF_IMPROVING_CLOSED_LOOP`.

## Overnight-данные

- Research station: `6/6 healthy`, у всех research-only и no order authority.
- Funding dynamic: 13 closed, 2 open, median `-127.8 bps`, positive
  concentration `57.4%`.
- Funding frozen: 11 closed, 2 open, median `-162.1 bps`, positive
  concentration `82.2%`.
- Положительная mean при отрицательной median — признак редкого хвоста, а не
  устойчивой ноги. Деньги не подключать.
- XAU Dukascopy: 30 completed, 26 empty, 32 quarantined; guard остановил
  дальнейшее накопление корректно.

## XAU: маршрут разблокировки

OANDA v20 официально поддерживает M5 и выдаёт до 5000 свечей на страницу, но
нужны account и bearer token. Resumable SHA-bound materializer уже реализован
в `scripts/materialize_xau_oanda_preholdout.py`: страницы и status атомарны,
resume проверяет SHA, токен не пишется, sealed range отвергается до сети.
Offline preflight прошёл; сеть без токена не запускалась. HistData перечисляет
XAUUSD в бесплатном архиве и остаётся
fallback; перед использованием нужно проверить timezone, gaps, duplicates,
price side и лицензию на overlap с уже валидной частью Dukascopy.

Текущий quarantine guard не обходить. Следующий результат — не стратегия, а
полный pre-holdout data receipt; затем frozen XAU session-break/retest replay.

## Следующий рабочий пакет

1. Alpaca paper parity и exact protection lifecycle.
2. Idea card → lifecycle bridge и свежий bounded scheduler receipt.
3. Inplay cadence/data-path audit без изменения контракта.
4. Две заранее объявленные crypto-long/upstream-break руки.
5. Funding tail/concentration и exact fee decomposition.
6. Запуск готового OANDA XAU M5 downloader либо HistData validation adapter.
7. Следующий маленький dirty-workbench batch с reproduction receipts.

До минимальной целевой станции всё ещё далеко: одна tiny crypto canary вместо
3–4 ног, Alpaca защищена, но не полноценна, FX/XAU только в data/research.
Однако с этой сессии ложный положительный результат стало существенно сложнее
пронести в live, а полезный challenger Alpaca уже имеет безопасный путь из
исследования в paper parity. Это реальное приближение, не ожидание.
