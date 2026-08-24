# ATT1/SBR1 research ↔ live adapter parity

Дата заморозки: 2026-08-20. Authority: research-only, zero orders, zero risk,
no promotion authority. Запечатанный период 2025-10…2026-06 не читается.

## Выбранный контракт

Выбрана **новая live-геометрия**: широкий ATR-стоп строится внутри стратегии,
а TP1/TP2 заново строятся от фактического широкого риска с объявленными RR.
Старая исследовательская арифметика, где уже готовый стоп умножался после
генерации сигнала, а прежние цели сохранялись, не является доказательством
этого контракта. Её PnL нельзя использовать для допуска в shadow или live.

ATT1 и SBR1 проверяются раздельно. Для каждой ноги research-adapter и
live-adapter обязаны прочитать одни и те же pre-sealed bytes и записать по одной
нормализованной строке на каждую оценку бара. Схема задаётся
`research_lab/adapter_parity.py`.

## Gate

`adapter_parity.py` обязан завершиться ненулевым кодом, если есть хотя бы одно:

1. отсутствующее поле, дублированный ключ или проглоченное исключение;
2. разные data/config/source hash;
3. несовпавшая оценка `(symbol, bar_ts, side)` или coverage ниже 99%;
4. разница raw signal count больше 10%;
5. entry/SL/TP расходятся больше чем на один exchange tick;
6. различаются доли TP/runner, time-stop, cooldown, regime или drop reason;
7. различаются детерминированный outcome или net R после одного cost-contract.

Все несовпадения сохраняются в отчёте. PASS comparator-а доказывает только
паритет двух адаптеров на заявленных данных; он сам по себе не разрешает деньги.

## Fail-closed amendment 2026-08-23

Независимый аудит понизил первоначальный результат до
`COMPONENT_PARITY_PASS / LIVE_CALLER_PARITY_BLOCKED`. До следующего прогона
фиксируются дополнительные условия:

1. BTC EMA200 один раз seed-ится с начала непрерывного окна и затем обновляется
   каузально; повторное наблюдение того же H1 не обновляет EMA второй раз.
2. ATT1 cooldown `96 × M5` означает восемь часов wall-clock, а не 96 вызовов
   H1-scheduler. SBR1 меняет cooldown только на новом закрытом H1.
3. Защитный стоп округляется наружу до exchange tick; цели заново строятся от
   этого frozen stop. Market/fractional fill может быть вне tick.
4. Research и live-shaped ветви отдельно строят fill, outcome, context и
   receipt. Передача research receipt в live emitter запрещена.
5. Ledger содержит фактический replay `exit_ts_ms`; stop-gap исполняется по
   худшему open, а stress включает adverse funding `1 bps / 8h` дополнительно
   к fees/slippage.
6. Source closure включает общие `live_kline_utils.py` и `signals.py`. Хэши
   каждого нормализованного ledger сохраняются в parity report.
7. Этот runner всё ещё моделирует idealized `closed H1 → next M5 open` на
   major8 и не проверяет production caller, intended wide universe, portfolio
   slots/correlation/exposure либо брокера. Поэтому даже зелёный comparator
   не открывает sealed window и не выдаёт money authority.

Следующий gate: default-off production caller parity и prospective zero-order
shadow с durable simulated decision/fill/exit ledger. Настоящие broker fills
возможны только в отдельной owner-approved minimum-notional canary. Запечатанный
период открывается один раз лишь после исправленного frozen portfolio scorer,
полного manifest и независимой проверки; старый `read_sealed.py` не используется.
