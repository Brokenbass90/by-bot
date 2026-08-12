# Текущий roadmap проекта

Обновлено: 2026-08-11 17:08 UTC. Это стабильная точка входа между чатами.
Датированные отчеты остаются журналом, но при конфликте планов сначала читать
`CURRENT_HANDOFF.md`, затем этот файл и только потом старые roadmap.

## Latest reprioritization — 2026-08-11 17:08 UTC

1. **ATT1:** сохранять tiny canary `0.10`; считать только сделки после release
   `475745108b5e`. Перед повышением риска: exact parity + N20 clean + cohort
   gates. Сегодняшние DOT/ADA положительны, но contaminated.
2. **Second crypto leg:** построить fixed `inplay_breakout ETH 0.75/24h`
   risk-zero collector. Не включать в monolith до отдельного shadow contract;
   maker-entry тестировать как challenger, не default.
3. **Neutral crypto:** продолжать XSEC forward shadow; funding dynamic/frozen
   начали новую clean epoch после карантина перекрывающихся legacy trials.
4. **Research integrity:** reserved holdout больше не раскрывать; любой explicit
   symbol mismatch и timeout fail-close; каждое число несет cutoff/passport.
5. **BTC-state:** один prereg interaction test для support bounce/strong-up;
   не превращать descriptive table в live switch.
6. **Alpaca:** SAFE_HOLD ABBV/SCHW сохранять; закончить live-contract backtest
   parity перед новыми среднесрочными деньгами. PAPER intraday отделять в TG.
7. **FX/CFD:** четыре terminal fail не перезапускать; следующий gate — XAUUSD
   contract/cost validation. Index CFD остается blocked-data.
8. **AI/research:** пять supervisor screens продолжают proposal/risk-zero
   работу. AI не имеет secrets/order/risk authority; тяжелый новый run только
   после освобождения WIP и с preregistration.

Очередь `configs/research/strategy_promotion_queue_20260730.json` снова валидна:
`13 crypto`, `6 FX/CFD`, `active=4/max=5`, `capital_authorized=false`.

## Update 2026-08-11 — что изменилось и что делать дальше

### Завершено сейчас

1. **ATT1 execution release:** atomic revision `475745108b5e` находится в live,
   broker flat, service/heartbeat живы. Clean N20 начинается только после этого
   receipt; DOT/ADA положительны, но contaminated.
2. **Автономная матрица:** terminal `48/48`; ни одного money-кандидата.
   Reserved holdout не читался.
3. **Лаборатория отрицательных сделок:** первая reproducible версия готова.
   Она отличает negative gross edge от cost-killed edge, строит exit-path и
   market/context buckets, а AI получает только proposal packet.
4. **Скрытый universe contract:** стандартная ручка добавлена в
   `inplay_retest_v3`, preflight теперь обязан доказать различие universe.
5. **XSEC shadow integrity:** maturity, entry attribution и anomaly gate
   добавлены без broker/order authority.

### Новые измеренные границы

- **ATT1 major-only:** остается единственной money-canary, но еще не доказана
  clean live cohort. Не экстраполировать на весь рынок.
- **ATT1 wide:** `823` trades, gross `+19.34R`, costs `48.11R`, net `-28.77R`,
  `t=-0.99`; отклонена как широкий контур.
- **Squeeze long 2023H2:** `620` trades, gross `-40.37R`, costs `90.97R`, net
  `-131.34R`, `t=-6.74`; отклонена в текущем виде. Причина не сводится к fees.
- **XSEC:** `SHADOW`, zero risk; forward evidence еще не накоплена.
- **Alpaca:** live SAFE_HOLD/protective-exit contour, но стратегия selection
  остается diagnostic, не доказанным источником дохода.

### Следующие P0/P1 — без календарного простоя

1. **Live truth loop:** на каждом цикле reconcile broker ↔ runner ↔ owner ↔
   accounting; конфликт символа fail-closes только новые добавки, protection
   продолжает работать.
2. **Clean ATT1:** собирать N20, одновременно завершить exact
   backtest↔live parity для rounding/fees/partial fills. Gate риска остается
   `20 clean closed`, `netR>=+2`, `PF>=1.20`, drawdown `<=5R`, zero unresolved
   execution conflicts; ориентир при прежней частоте — конец сентября.
3. **Second-leg lane A — XSEC:** держать V3 в shadow, ежедневно валидировать
   maturity/markout attribution/anomalies. До forward sample капитал нулевой.
4. **Second-leg lane B — retest/level reaction:** провести differentiating
   wide-universe smoke после освобождения compute slot; затем time/symbol OOS.
   Для возвратных сетапов maker моделировать отдельно; импульсным breakout
   maker не навязывать из-за adverse selection.
5. **Negative lab experiments:** preregister три отдельных falsification-теста:
   delayed/confirmed entry для `entry_failed_fast`; state-aware entry для
   `stopped_no_reversal_yet`; exit redesign для `gave_back_profit`. Не смешивать
   три изменения в одном варианте и не читать reserved holdout.
6. **Data lane:** после освобождения слота расширить public funding history и
   получить PIT-aware equities daily universe. Текущие 8-symbol funding data и
   yfinance/survivor equity data недостаточны для финального вердикта.
7. **Elder:** построить один contract manifest V2/V3 и replay на одинаковом
   universe/data/cost/exits; обе версии остаются risk zero до результата.
8. **AI/graph analysis:** AI имеет read-only timestamped snapshots, OHLC cards,
   regime probabilities и proposal-only findings. Он не включает модули, не
   меняет risk и не отправляет ордера. Visual pattern claim обязан иметь
   machine reproduction и preregistered test.

### Что не считать прогрессом

- `141 symbols downloaded` — это coverage, не edge и не live activation.
- `85 modules indexed` — inventory coverage, не доказанная полезность.
- старый красивый backtest без exact universe/weights/exits/cost contract;
- один положительный shadow markout или две contaminated live сделки;
- AI-объяснение причины без воспроизводимого finding и source receipt.

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

## Recovery session — 2026-08-12 07:50–08:15 UTC

### Live truth и последняя сделка

Direct Bybit read после закрытия подтвердил flat и equity
`1022.06789312 USDT`. Последний DOTUSDT short: average entry `0.7944`, average
exit `0.78884968`, qty `75.9`, broker closed PnL `+0.35517723 USDT`. Позиция
сначала получила breakeven, затем биржевой trailing stop; ручного закрытия,
submit/cancel или изменения риска в этой сессии не было. Текущая authority не
расширялась: ATT1 short-only `risk_mult=0.10`, effective risk около `0.044%`
equity на сделку.

Actual DOT order теперь имеет golden sizing receipt:
`reports/evidence/ATT1_DOT_ORDER_SIZE_PARITY_20260812.json`. Shared fixed-R
contract дал тот же pre-round notional и после qty-step `0.1` ровно тот же
submitted qty `75.9`; `5/5 PASS`. Для будущих live events добавлена non-secret
телеметрия `sizing_contract`, но monolith с этой телеметрией не деплоился.

### Что из работы Claude принято, а что отозвано

- MPL — идея принята, но исходный holdout-контракт был неисполняемым и
  неоднозначным. Он пересобран: exact `[2025-10-01, 2026-07-01)`, next-15m-open,
  no-overlap, causal liquidity/slippage, time-matched random control, exact 62
  symbols, input integrity, write-once manifest/result. Изолированный bundle
  готов, focused tests `6 PASS`, immutable local commit `2811242`. Холдаут не
  вскрыт: push этого commit заблокирован security review до явного разрешения
  владельца на конкретный Git remote/branch.
- Inplay `+0.2352R` отозван: `research_lab/path_sim.py` видел close сигнального
  5m бара и входил по тому же close. Исправлено на next-open и conservative
  stop-first; `2 PASS`. До causal pre-holdout replay shadow не запускать.
- XSEC `Sharpe 0.65` — сильный research lead, не `ГОТОВО К ДЕНЬГАМ`: clean
  symbol-holdout имеет слабый `t=0.60`, funding cashflows ещё не включены, а
  closed-contract PIT universe не восстановлен. Modern keys в старом JSON
  quarantined; сценарий использует только pre-holdout search.
- Два заявленных live-багa про runtime env и отсутствие try/except не
  воспроизведены: open `TradeState` хранит stop/runner fields, async signal и
  runner pulse уже имеют exception boundaries. Код live по этим утверждениям
  не менялся.

### Данные и лаборатория

- Bybit funding/listing archive: `137/137`, `413,356` observations, `0` failed,
  public/read-only. Integrity PASS, но PIT `NOT_READY`: provider inventory
  содержит `936 Closed`, тогда как OHLC/funding set выбран из текущих 137.
- Alpaca/Massive PIT candidate pool: `1000` symbols, resumable, GET-only,
  текущий прогресс сохраняется в
  `research_lab/data/alpaca_pit_daily_v1/status.json`. Добавлен независимый
  validator hashes/timestamps/delist dates и membership intervals. Он может
  доказать PIT только внутри выбранного пула и fail-close запрещает называть
  current-liquidity selection полным историческим PIT universe.
- Bybit L2: BTC/ETH, ONDO, public trades и новый density denominator по `24`
  альтам собираются непрерывно. На 08:15 UTC alt24 имел `4,999` observations,
  `5.3 MB`, public-only, order-capability false, storage guards green.
- Audit registry loop закрыт полями confirmation evidence/resolution note и
  fail-closed validator: `298` total, `211` current, `3` actionable, `0`
  lifecycle violations.
- Шестидневный wide rerun больше нельзя называть завершённым успешным:
  текущий status `48/48`, но `24` cases invalid после исправления universe
  contract. Ранее terminal `complete` относится к старому узкому контракту.

### $1,000 mechanical matrix — не прогноз

Canonical artifact:
`reports/analytics/trading_recovery_20260812/report.html` и machine-readable
`artifact.json`.

| sleeve | mechanical evidence | допустимость |
|---|---:|---|
| ATT1 current tiny canary | `$1,008.86` | только перевод старого narrow anchor при 0.044% risk; не forecast |
| XSEC | no estimate | старые 7.5–9.5% отозваны: same-close execution; funding/PIT unresolved |
| Alpaca monthly | `$971–1,141` | bear/recent survivor proxies; SAFE_HOLD cap не расширять |
| FX H4 basket | `$1,007–1,031` | 1–7 trades/variant, all preflight false; не использовать для allocation |
| MPL/inplay | no estimate | executable accepted replay отсутствует |

Эти строки нельзя складывать как обещанную portfolio return. Новый money sleeve
не продвинут; продвижение этой сессии — достоверность измерений, данные и
готовые gates.

### Следующий порядок

1. Получить явное разрешение push `2811242` в указанный remote/branch и только
   затем один раз вскрыть MPL V3 holdout.
2. Дождаться `1000/1000` Alpaca, запустить независимый validator и repaired
   monthly replay; текущий сбор займёт часы, аналитика 1–2 рабочих дня.
3. Построить funding-adjusted XSEC и closed-contract PIT universe; затем
   prospective shadow, а не money.
4. Выполнить causal pre-holdout replay inplay; shadow только если переживёт.
5. Продолжать ATT1 clean cohort: при наблюдаемой частоте N20 ориентировочно
   около 47 календарных дней после release, не искусственно ускорять риском.

Дополнительный causal-аудит после записи матрицы нашёл в XSEC тот же дефект,
что в inplay: веса рассчитывались по завершённому daily close и доходность
начиналась с цены этого же close. Поэтому сохранённые `7.5–9.5%` больше не
являются даже research-сценарием. Добавлен pure contract
`research_lab/xsec_causal_contract.py`: next-day-open entry, open-to-open hold,
фактические crossed funding cashflows со знаком `-weight*rate`, fail-close при
отсутствующей исполнимой цене. Отдельный физический pre-holdout funding archive
до `2025-10-01` запущен public-only; основной sealed outcome не читается.

## Continuity receipt — 2026-08-12 08:29–08:38 UTC

- Пять supervisor jobs подтверждены текущим status как `5 healthy / 0
  degraded`: Alpaca adaptive shadow, XSEC shadow, funding dynamic/frozen и
  project audit. Три локальных public Bybit tape-контура свежие и продолжают
  запись: BTC/ETH `2.19 GB`, ONDO `849 MB`, micro-trades `368 MB`; у всех
  `public_only=true`, `authentication=false`, `order_capability=false`,
  disk guards green. Alt24 density также жив: `8,092` observations.
- Изолированный `/root/research-l2` на сервере подтверждён read-only:
  heartbeat `collecting`, lag `1 ms`, BTC/ETH snapshot synchronized,
  `921.9 MB` tape при cap `2 GiB`, свободно `7.2 GB` при guard `5 GiB`.
  Storage guard не переопределялся.
- Найдена причина двух молча завершавшихся запусков daily pre-holdout:
  direct-file import не видел пакет `scripts`. После исправления CLI и focused
  suite `11 PASS`; архив дневных Bybit bars завершён `137/137`, `0 failed`,
  end-exclusive `2025-10-01`, `sealed_holdout_rows_decoded=0`.
- Независимый funding validator сначала корректно fail-closed, затем в нём
  исправлена собственная zero-observation ошибка для контрактов, запущенных
  после границы окна. Повторная проверка: integrity PASS, `213,109` funding
  observations, но verdict `INTEGRITY_PASS_PIT_NOT_READY`, 26 coverage warnings
  и survivorship unresolved. Это не разрешает promotion.
- Один write-once XSEC causal V1 завершён с валидным passport
  `63201839a44f06710840526f49c076bf632b921b97a751eb8e99aaa0b45f8971`.
  Verdict `REJECT`: base 15 bps `+9.08%` total / `3.81%` CAGR / Sharpe `0.41` /
  DD `25.72%`, но 2023 `-7.80%`, одна phase `-11.18%`; stress 30 bps
  `-5.82%` total / `-2.54%` CAGR. Красных месяцев `15/31` base и `17/31`
  stress. Старый XSEC shadow остаётся только процессным наблюдением, не ногой с
  доказанным net edge.
- Alpaca PIT daily materialization продолжает GET-only сбор: на 08:37 UTC
  завершены первые 133 из 1000, failures `0`. Direct Bybit position checker
  один раз подтвердил broker flat (`open_position_count=0`). Это не deploy gate:
  live monolith не перезапускался, risk/order state не менялся.

## Superseding recovery update — 2026-08-12 11:05 UTC

Полная сводка и приоритеты находятся в
`reports/PROJECT_STATE_AND_RESEARCH_REPORT_20260812.md`. Этот раздел заменяет
устаревшие выше формулировки «MPL не вскрыт» и «Inplay ждёт causal replay».

- MPL V4/V3 вскрыт один раз после freeze/push: обе руки `REJECT`, independent
  audit PASS. Текущую формулировку закрыть, капитал/shadow не давать.
- Causal Inplay ETH replay на физически изолированном pre-holdout input:
  `N=455`, `3/4` positive folds, median `+0.1705R`, один fold `-0.4602R`.
  Вердикт только `CAUSAL_VIABLE_SHADOW_ONLY`.
- Prospective public-only Inplay collector запущен в screen
  `research_inplay_prospective_20260812`; local research supervisor теперь
  `6/6 healthy`. Collector не имеет authentication/order/risk authority.
- Dirty worktree разобран read-only на `176` code candidates: 15 test-backed,
  118 evidence-backed/reproduce, 16 referenced/review, 27 quarantine. Ничего
  не удалено; ATT1 live-risk diff не принят без reproduction.
- Alpaca PIT progress на срезе `783/1000`, failures `0`; честный v38 replay
  только после validator. Spot Bybit pre-holdout: 67 symbols с данными из 74
  поддерживаемых, 46,742 bars; частичное покрытие не скрывать.
- Server Bybit checker вернул broker flat (`retCode=0`, positions `0`). Local
  checker key expired и отдельно требует replacement. Server L2 collector:
  collecting, lag `2ms`, tape `1.31GB`, free `6.4GB` при guard `5GB`.
- Focused suite: `41 passed`. Live monolith, orders и risk не менялись.
