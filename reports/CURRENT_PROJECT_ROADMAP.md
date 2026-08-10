# Текущий roadmap проекта

Обновлено: 2026-08-10 18:55 UTC. Это стабильная точка входа между чатами.
Датированные отчеты остаются журналом, но при конфликте планов сначала читать
`CURRENT_HANDOFF.md`, затем этот файл и только потом старые roadmap.

## Emergency execution update — 18:55 UTC

ATT1 временно не может начать clean cohort: DOT fill исполнился уже за TP1 и
расширил stop risk в `2.64x`. Исправление stale/current/fill contract готово и
прошло focused tests, но монолит не перезапускается при открытой позиции.
Затем старый live-код допустил ADA fill с расширением риска `1.56x`. Поэтому
первый P0 gate теперь не пассивное ожидание, а горячая остановка только новых
ATT1-входов командой `/strategy_pause att1 execution_fix_release`. Сопровождение
и broker stops текущих позиций сохраняются. После broker flat — три прямые
проверки flat и atomic release; resume только после полной сверки release.

Обе incident-сделки и все события до release receipt исключаются из N20. При
наблюдаемом темпе ATT1 `9 сделок / 21 день` двадцать чистых сделок займут около
`47 дней` после release, то есть реалистичный decision window для
`risk 0.10 -> 0.25` — конец сентября 2026, а не 2–3 недели. Ускорение возможно
только если фактическая чистая частота вырастет примерно до одной сделки в день.

Gate `0.10 -> 0.25`:

1. exact release/hash/service/broker receipt и ни одного execution incident;
2. golden backtest-live size/entry/stop/TP parity;
3. 20 clean closed trades одной post-fix cohort, без contamination;
4. cohort `netR >= +2`, `PF(R) >= 1.20`, peak-to-trough `<= 5R`;
5. broker ↔ runner ↔ owner ↔ accounting reconciliation без unresolved conflict.

## Six-day autonomous research lane — RUNNING

- downloader: top-150 current surviving Bybit contracts, 5m from 2023;
- explicit limitation: survivor/turnover-biased discovery universe, promotion
  forbidden;
- queue: ATT1 current/shallow, horizontal break long/short, support reclaim
  strict/relaxed, squeeze long/short;
- design: 3 chronological pre-2025 windows × base/stress costs = 48 cases;
- every varied strategy handle passes executable preflight;
- every run uses next-open execution, coverage gate, R metrics and audit;
- 2025-10..2026-06 holdout is code-blocked from reading;
- host idle sleep блокируется ограниченным шестью сутками `caffeinate` assertion;
  это не защита от power loss, reboot или network outage;
- status: `reports/research/six_day_crypto_pipeline_20260810/status.json`.

This lane searches a second leg and failure mechanisms. It cannot promote a
strategy, change risk or touch a broker.

Визуальная архитектура и promotion flow:
`reports/CODEX_PROJECT_VISUAL_MAP_2026_08_10.md`.

## Решение после сравнения планов

План Клода правильно начинает с экономики ноги: издержек, качества входа,
избирательности, карточек эджа и поиска рабочей long-ноги. Антикризисный план
Codex правильно ставит раньше них операционную истину: broker truth, безопасный
release, reconciliation, чистые когорты и независимую проверку. Итоговый порядок:

1. не потерять капитал и доказать, что live исполняет именно тот код;
2. сделать измерения воспроизводимыми и независимыми;
3. улучшать экономику каждой ноги одним изменением за эксперимент;
4. только затем давать капитал нескольким независимым контурам;
5. отображать ту же истину в Web, Telegram и AI-ассистенте.

Цель не «запустить побольше стратегий», а получить несколько независимых
контуров, в каждом из которых есть минимум две отдельно доказанные ноги,
понятные издержки, ограничения риска и механизм автоматического отключения.

## Нулевая шкала статусов

- `PROCESS_OK`: процесс жив и выпускает свежие receipts.
- `MEASURED`: есть корректный результат на заявленном окне.
- `REPRODUCED`: результат повторен независимым способом или движком.
- `SHADOW`: работает на текущем рынке без права ордеров.
- `CANARY`: имеет явно ограниченное право на минимальный риск.
- `MONEY`: прошел promotion gates и имеет капитал.

`PROCESS_OK` никогда не подменяет `MONEY`, а положительный shadow PnL не
считается заработком счета.

## P0. Безопасность и операционная истина — сейчас

### P0.1 RUNNER TP1 dependency bundle — DONE

- bundle собран из Git revision `c5eba1ccb244584bb432dd902d22599290fca900`;
- архив SHA256 `5c7b4be781aed95b5df9f9f2a38b5912b70a1d523ade7896806b329490702e46`;
- server-Python import и bounded no-order startup smoke прошли вне live;
- direct Bybit flat подтвержден до остановки, после остановки и после старта;
- шесть файлов заменены атомарно, пять отсутствовавших зависимостей добавлены;
- live manifest `6/6 PASS`, service и heartbeat восстановлены;
- money authority не расширена: ATT1 short-only, `risk_mult=0.10`.

Следующий контроль: периодически сверять live manifest/deployed receipt, service,
heartbeat и прямого брокера; Git-коммит сам по себе не считать деплоем.

### P0.2 Retest3 research-integrity — REPAIRED, RESULT NOT PROVEN

Старый ladder был no-op: экспортировал неиспользуемую переменную. Скрипт теперь
передает реальную ручку `IRV3_STOP_BUFFER_ATR`, выполняет preflight четырех
разных конфигураций и запрещает интерпретацию, если stop distributions не
различаются. Старые результаты изолированы новыми тегами.

Дешевый 90d smoke честно заблокирован: две конфигурации дали ноль сделок, две —
по одной. Это доказательство работы fail-close, но не результат стратегии.
Следующее действие — differentiating smoke на достаточном окне после
освобождения одного из пяти исследовательских слотов.

### P0.3 Alpaca protective exits — LIVE RECEIPT PASS, MONITORING REQUIRED

На сервере обнаружены действующие protective-only authority и cron каждые 15
минут. Последовательно исправлены два broker-contract дефекта: fractional
`qty` больше не отправляется в PATCH, а stop-price округляется вниз на
разрешенную Alpaca сетку (2 decimals при цене >= `$1`, 4 ниже `$1`). Staged
server-Python smoke и 26 focused tests прошли.

2026-08-10 14:44 UTC Alpaca приняла replace SCHW `96.47 -> 105.03`, точный
защищенный qty `0.563776973`, статус нового ордера `new`. Прямое broker-read:
equity `$485.87`, cash `$391.27`, ABBV/SCHW, stop coverage `2/2`; SCHW stop
находится примерно на `+3.42%` к entry до gap/slippage. ABBV пока не достигла
порога arm и сохраняет stop `235.17`. Новых покупок, ротаций и market-close не
было; SAFE_HOLD сохраняется.

Оставшийся риск: дробные equity stop-ордера имеют `DAY`, поэтому защита зависит
от ежедневного rearm и polling; stop/trailing не устраняет overnight gap risk.
Автоматический cron 14:45 UTC уже перечитал новый stop `105.03` и корректно
вернул `hold/no_material_stop_raise` без повторного PATCH. Следующие проверки:
rearm на следующей сессии, freshness alert и восстановление HWM после рестарта.
Для будущих входов отдельно сравнить fractional DAY с whole-share
GTC/native-trailing контрактом.

Routine PAPER HOLD/dry-run Telegram отключен по умолчанию в paper-launcher;
paper broker receipts и логи сохранены. Отдельные live/actionable сообщения не
отключались.

### P0.4 Грязная рабочая область — INVENTORIED, TRIAGE OPEN

Read-only inventory на HEAD `c5eba1c`: `1,138` paths (`27` tracked changes,
`1,111` untracked). Крупные классы: `429` document/metadata, `344` reports,
`100` archive/backup, `61` manual-code candidates, `29` runtime/log и `14`
secret/env-looking names. Контент секретов не печатался. Подробный порядок —
`reports/WORKTREE_CLEANUP_PLAN_2026_08_10.md`.

До owner/reference/test triage массово не удалять и не архивировать. Работа
Клода и параллельные research artifacts считаются чужими до доказательства
обратного. Первый безопасный выигрыш — вынести bulk data/runtime и backups из
code checkout по manifest, затем разбирать 61 code candidate малыми batches.

## P1. Control plane — неделя 1–2

### P1.1 Broker ↔ runner ↔ owner ↔ accounting reconciliation — PURE CORE READY

`bot/position_reconciliation.py` теперь строит единый deterministic receipt из
четырех position views, проверяет freshness, broker stop, qty/side/strategy,
missing и duplicate/hedged rows. Stale/malformed source означает глобальный
fail-close новых входов; локальный конфликт блокирует только затронутый символ,
не мешая защитному TP/SL и runner management. Совместный focused suite:
`18 passed`.

Открытый gate: материализовать четыре runtime adapters, durable receipt и
подключить `entry_allowed()` ко всем реальным submit paths отдельным релизом.
До этого pure core — проверенный контракт, но не live protection. Incident
должен попадать в очередь `finding -> reproduction -> patch -> tests -> deploy`.

### P1.2 Backtest ↔ live sizing parity — CORE WIRED, EXCHANGE LAYER OPEN

Live stop-percent sizing теперь проходит через тот же pure
`bot/risk_sizing_contract.py`, что и backtest fixed-R sizing. Golden fixtures
доказывают одинаковые pre-round notional и effective risk для uncapped,
notional-capped и reject cases, включая геометрию DOT. Остается проверить
exchange qty-step/min-qty rounding, fees, partial fills и запрет legacy-DCA.
Любое расхождение — fail-fast, не предупреждение.

### P1.3 Clean cohort registry

Каждая правка signal/sizing/execution/accounting начинает новую когорту с code
SHA, config hash, data version и timestamp. ATT1 promotion использует только
чистые post-fix сделки; старые contaminated события сохраняются как evidence.

### P1.4 Maker execution shadow и slope shadow

- ATT1/BREAKDOWN: frozen post-only grid, fill/nonfill markout, opportunity cost,
  adverse selection, symbol/time folds;
- ATT1 slope `0.7`: только shadow, поскольку порог выбран на просмотренном окне;
- не включать maker в деньги по одному улучшению комиссии.

### P1.5 `sloped_break_retest_v1` — UNIT FIX DONE, REACHABILITY OPEN

Повторная проверка показала, что пункт старого roadmap уже частично устарел:
`_retest_expiry_ms()` переводит секунды в миллисекунды, а два contract tests
проходят; последняя история файла указывает на commit `2d04e3f`. Повторно чинить
код не нужно. Остались reachability proof, bounded smoke, geometry receipt и
shadow gate; старые нулевые результаты до unit fix не использовать как приговор.

### P1.6 Alpaca selection/exit exact parity

Текущий live — SAFE_HOLD старых ABBV/SCHW, а adaptive shadow выбирает
SNOW/BAC/PANW/CRWD. Это разные cohort и не доказательство работы одной стратегии.
Старые красивые v38 цифры не совпадали с intended live contract по universe,
70% exposure, weighting, exit и daily MTM. Новый preregistered diagnostic
`alpaca_honest_diagnostic_v1_20260810` уже исправляет next-open, единый cash
ledger, fractional qty, hard weight cap, per-fill costs, retained positions,
deployable fractional stop/ratchet proxy и daily drawdown.

Первый результат после независимой проверки арифметических invariants:

| окно / arm | 5 bps/side | 10 bps/side | daily DD stress | статус |
|---|---:|---:|---:|---|
| 2022 v38 successor + SPY200 | `-2.75%` | `-2.89%` | `4.00%` | bear edge не доказан |
| 2024-05..2026-04 v38 successor + SPY200 | `+31.88%` | `+30.16%` | `7.84%` | promising diagnostic |
| 2022 Adaptive V1 + SPY200 | `-5.38%` | `-5.63%` | `6.58%` | bear edge не доказан |
| 2024-05..2026-04 Adaptive V1 + SPY200 | `+20.66%` | `+18.75%` | `4.94%` | lower-DD diagnostic |

Старое v38 `+50.77% / DD 2.28%` больше не является рабочей оценкой: новый
cash-aware replay дает ниже доход и выше честную дневную просадку. Средняя
реальная экспозиция v38 получилась лишь `26.6%`, потому что cash, hard cap,
защитные выходы и reentry blocks больше не скрываются нормализацией до 100%.
В live bridge найден и исправлен тот же sizing-defect: прежний cap 60% затем
повторно нормализовался и мог стать 100%. Теперь остаток остается cash; текущий
SAFE_HOLD не затронут, поскольку new entries выключены. Focused suite `34 PASS`.

Validator: `16/16` result invariants, `6/6` source pins и `8/8` cost-stress
monotonicity PASS. Data quality всё ещё `NEEDS_REVISION`: universe survivor-only,
XNYS ledger не authoritative, corporate actions/delistings и broker cost bundle
не pinned, daily proxy не воспроизводит 15-minute HWM path; XYZ имеет лишь
`63.9%` покрытия двухлетнего окна из-за своей более короткой истории. Forward
с 2026-08-03 не читался. Поэтому promotion остается `BLOCKED_FAIL_CLOSED` до
PIT/input bundle, второго engine и трех sealed monthly forward cycles.

## P2. Исследовательский завод — неделя 2–6

### P2.1 Карточка эджа для каждой ноги

Единый `strategy_edge_report`: вход signal/next-open/limit; выход MFE/MAE и
отданный ход; отбор по измеримым признакам; gross edge, costs, net edge,
uncertainty, data/PIT coverage и failure phenotypes. Один эксперимент меняет
только один рычаг.

Порядок: liveness -> ablation -> edge card -> one-change experiment ->
preregistered fold -> independent replay -> shadow -> canary.

### P2.2 Независимый replay

VectorBT — быстрый prefilter, causal harness — основной исследовательский
движок, LEAN или второй независимо реализованный engine — сверка ключевых
кандидатов. Два движка не должны разделять одну и ту же реализацию signal/exit.

### P2.3 Анализ отрицательных сделок по фенотипам

Кластеризовать по regime, slope, geometry, liquidity/spread, fill path,
markout, symbol age, volatility, funding/basis и времени. LLM может назвать
кластер и предложить тест, но не имеет права объявлять причинность или promotion.

### P2.4 Данные и честные окна

150–200 perpetual symbols с listing dates, 5m history с 2023-01 и funding
history в parquet. Любой тест хранит data hash, coverage, exclusions и PIT
ограничения. Holdout squeeze `2025-10..2026-06` не расходовать на другие ноги.

### P2.5 Long family и slot arbitration

Приоритет поиска: `inplay -> breakout -> continuation -> retest`, потому что у
книги нет доказанной long-ноги. `strategy_priority_router` сначала проверяется
в shadow на opportunity cost; не подключать к live только по старому aggregate.

### P2.6 Load-aware night queue

Пять постоянных research loops остаются `5 healthy / 0 degraded`. Load-aware
очередь `research_backlog_guard_20260810` завершила два risk-zero fixed probes,
без broker calls и live authority. USDJPY H1 полностью заблокирован cost gate:
`feeR=0.515 > 0.35`, сделок не симулировали. На H4 лучшие диагностические
строки: EURJPY trend pullback `+3.366R` (13 сделок, 2/4 positive folds), GBPUSD
trend pullback `+1.732R` (9, 3/4), USDJPY breakout/retest `+1.321R` (10, 2/4),
EURUSD breakout/retest `+1.221R` (4, 2/4). Все `preflight=false`: это очередь
для prereg reproduction с fresh bid/ask, swap и news exclusions, не promotion.

## P3. Несколько контуров дохода — неделя 3–12+

| Контур | Сейчас | Следующий falsifiable gate | Условие капитала |
|---|---|---|---|
| Crypto directional | ATT1 `CANARY 0.10`; остальные zero-risk | clean N20/N30, maker/slope shadow, size parity | по ступеням `0.10 -> 0.25 -> 0.50`, только после gates |
| Crypto long/retest | research-integrity repaired, edge не доказан | liveness + geometry + independent folds | отдельная доказанная нога, затем shadow/canary |
| Funding/basis | два `PROCESS_OK` shadow; capital false | concentration, adverse selection, realistic costs, frozen N20–30 | только reproduced net edge |
| XSEC market-neutral | `PROCESS_OK`, risk zero | outlier-resistant/median analysis, costs, independent replay | только stable folds и broker-ready controls |
| Alpaca equities | SAFE_HOLD + verified daily diagnostic: v38 recent `+30.16%`, 2022 `-2.89%` stress | PIT/XNYS/corp-actions/cost bundle, second engine, sealed Aug-Nov forward | текущий cap не расширять; SAFE_HOLD не ротировать по proxy |
| FX/CFD medium-term | USDJPY H1 rejected by cost gate; H4 has four thin diagnostic leads, all preflight false | prereg H4 reproduction, fresh bid/ask+swap/news, chronological OOS | сначала shadow/demo; money только после stable folds и broker-cost parity |
| Arbitrage/volatility | inventory/research only | executable quotes, transfer/borrow/funding risks, kill switches | отдельный canary после end-to-end shadow |

Желаемое состояние: в каждом денежном контуре минимум две независимо
проверенные стратегии/ноги. Но недоказанная нога не является диверсификацией:
она отнимает слоты и добавляет неизвестный риск.

## P4. Web, Telegram и AI — параллельно после P1 truth model

Один источник состояния для Web/TG/assistant: broker positions/equity,
protected exposure, money sleeves, strategy authority, deployed revision,
heartbeat freshness, reconciliation conflicts и research-only статус.

AI/Ollama индексирует весь несекретный код по path/SHA/chunk, извлекает source
и свежие receipts, отвечает `NOT_CONFIRMED` при stale/conflict. AI предлагает
finding и experiment, но не получает credentials, право ордера или изменение
риска. Web/TG ручные действия требуют подтверждения и immutable receipt.

## Метрики движения

1. число ног с reproduced net edge на независимом окне;
2. число clean live lifecycles с broker/runner/accounting parity;
3. защищенная экспозиция и число reconciliation conflicts;
4. maker fill rate, nonfill opportunity cost и adverse selection;
5. число findings, прошедших reproduction, а не число сырых предупреждений;
6. число денежных контуров с отдельной authority и kill switch.

Сроки — окна получения доказательств, не обещание доходности.
