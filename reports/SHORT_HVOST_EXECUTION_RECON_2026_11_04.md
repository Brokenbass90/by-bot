# SHORT_HVOST: ограниченная read-only проверка исполнения,4Nov2026

**BLOCKED для заявленного пакета $50 SHORT + равный BTC hedge.** Это техническая
разведка до экономического PASS, не новый исполнитель или финансовый допуск.
LIQ — следующая NOT_ASSESSED; Absorption — после неё NOT_ASSESSED.

Входы Claude зафиксированы SHA в [inputs](evidence/short_hvost_execution_20261104/inputs.json).
34 исхода/t=1.26 — данные его отчёта; Codex judge/PnL/producer не запускал.
Фактически сняты56 публичных Bybit GET, в том числе10 стаканов каждого инструмента
за4Nov17:48:25–17:48:54UTC (19:48Cyprus). Выбор3примеров: последние tail decision
records AKE/ACE/BLESS из двух названных shadow ledgers, не selection по доходности.
Это не вся вселенная и не новые своевременные сигналы; решение AKE было04:02UTC,
ACE/BLESS00:02UTC. Доставку сигнала к будущему исполнению сейчас не доказали.

| Инструмент | Минимальный легальный номинал по captured ask | Шаг qty | P90 displayed spread+depth круга | Current funding / interval |
|---|---:|---:|---:|---:|
| AKEUSDT |5.2440|100|9.135bps|-0.253312% /4ч|
| ACEUSDT |5.0052|0.1|8.045bps|+0.005028% /4ч|
| BLESSUSDT |5.07842|10|15.596bps|+0.005% /4ч|
| BTCUSDT |80.3472|0.001|0.01245bps|−0.000805% /8ч|

Все4 Trading/linear USDT perpetual/minLeverage1. Для alt замерялся размер около50,
для BTC — его легальный минимум0.001, поскольку50нелегальны. P90 — nearest-rank
на10кратких снимках, без комиссии/funding/latency/будущего выхода. Это НЕ приёмка
порога60bps на своевременных сигналах и не доказательство fill. Request RTT174–522ms.
Actual account fee rate UNKNOWN: private fee GET не выполнялся. В расчёте ниже
5.5bps/сторону — явно сценарий, а не измеренная персональная ставка.
AKE funding уже отрицательный: short платит. Нельзя считать будущий funding доходом
по старому положительному сигналу;8последних public funding settlements сохранены.

## 1. Конкретный блокер BTC-лота

BTC minOrderQty/qtyStep=0.001 при ask80347.2: minimum80.3472USDT. На hedge50
округление вниз даёт0, вверх80.3472 — больше разрешённого равного номинала.
Для общей hedge150: floor0.001=80.3472 (недохедж46.44%), ceil0.002=160.6944
(перехедж7.13%). Допуск mismatch/агрегация и распределение общего hedge не заданы.
При заданном $50/равном hedge точного исполнимого пакета нет. Codex не заменял
BTC perp спотом, не повышал $50 и не вводил новый допуск округления.

## 2. Капитал — расхождение исходного пакета

ВариантB27Oct прямо объясняет200 как150 маржи alt1× +50 маржи BTC150 при3×.
Пакет28Oct и краткое поручение не проговаривают это плечо BTC одинаково явно.
Если обе ноги1×:150+150=300 только модельной IM до комиссий/funding, без ошибки
BTC-округления. Если alt1×/BTC3×:200 IM, но у BTC другой риск ликвидации.

Сценарий, НЕ безопасный минимум: при неизменном номинале150+150 и fee0.00055
круг обеих ног стоит0.33. Статические current funding caps за16ч: AKE4 +ACE4
+BLESS8 +BTC0.999 =16.999. Получается317.329 при1×/1× до дополнительного резерва.
Это не персональная fee, не прогноз funding и не верхняя граница при росте цен,
смене caps/interval, задержке выхода или gap. Будущий funding может менять знак.
Уникальный безопасный минимум UNKNOWN; exact50пары сейчас BLOCKED независимо от
пополнения. Маржу нельзя одновременно считать свободным резервом второго входа.

Коррелированный stress: все alt+80%, BTC−20% →120+30=150 убытка до расходов
при nominal150+150. Это50% от модельных300. BTC не страхует idiosyncratic squeeze
и не гарантирует компенсацию шортов. Потеря обеих isolated margin может затронуть
весь выделенный капитал; формула старого пакета «не более150» не включает BTC.
Никакой новый loss budget/маржинальный резерв этим расчётом не утверждён.

## 3. Стоп +80% — не гарантия максимального убытка

По актуальной опубликованной формуле, при extra margin0/MM deduction0 и без fee
short1× liquidation ratio≈2/(1+MM). В samples MM2%/4%: +96.078%/+92.308%,
запас над stop+80% около16.078/12.308п.п. Формула1+IM−MM в старом документе
завышает запас. Реальные fees/funding и Mark price требуют отдельной сверки.
Выход точно на+80% стоил бы40 на short50. Сценарий price1.8×1.05=1.89
даёт44.5 потери (=89%, НЕ84%); это тоже не bound на исполнение.
Liquidation определяется MarkPrice; trigger basis стопа в пакете не закреплён.
Market может исполняться частично/отменяться в IOC/slippage protection. При гэпе
оба порога могут быть пересечены до выхода; ноль срабатываний в H1 истории не
доказывает защиту. Auto-add margin, funding debit и защита BTC-ноги не приняты.

## 4. Отказ одной ноги и существующие gates

Существующие source/account identity, fresh quotes, lot checks, send-once,
original account lease, immutable receipts и closed-cost finality переиспользуемы.
Но действующий PUMP запрещает isolated (flat_account требует REGULAR_MARGIN),
держит max_positions=max_entries=1 и frozen plan168h/.4+.6. Это не готовый
контракт трёх short16h с общей BTC-ногой. UTA marginMode — account-level;
менять его рядом с действующим PUMP или запускать второго владельца нельзя.

Нет принятого порядка двух fills, допуска частичного hedge, срока удержания
незахеджированной ноги, защиты BTC, распределения aggregate hedge/funding,
сценария unknown ACK и утверждённого аварийного unwinding. До этого no entry;
не вслепую повторять вторую заявку. Будущая версия должна сохранить одного owner
и заранее ограничить действия при частичном fill/отказе, затем независимый readback.
Это перечень стыков существующего кода, не поручение строить новую архитектуру.

Итог: **BLOCKED** — BTC grid, leverage/capital ambiguity, incompatible selected
scope/margin/lifecycle и отсутствующий двухногий failure contract. Account-specific
fees/custody, signal-time p90 и точный безопасный капитал UNKNOWN. Экономический
PASS отсутствует. LIQ/Absorption остаются в очереди, outcomes не открывались.

[Измерения/формулы](evidence/short_hvost_execution_20261104/measured-recon.json),
[воспроизводимый расчёт](evidence/short_hvost_execution_20261104/analyze-capture.py),
[ограниченное review](evidence/short_hvost_execution_20261104/independent-review.md).
Документация: [instrument lots](https://bybit-exchange.github.io/docs/v5/market/instrument),
[account margin mode](https://bybit-exchange.github.io/docs/v5/account/set-margin-mode),
[liquidation formula](https://www.bybit.com/en/help-center/article/UTA-Trading-Rules-Liquidation-Process),
[market/IOC](https://bybit-exchange.github.io/docs/v5/order/create-order),
[position stop](https://bybit-exchange.github.io/docs/v5/position/trading-stop).
