# OLD ATT1: приостановка только новых входов — предложение владельцу

Статус: PREPARED_NOT_EXECUTED, 2026-10-02. Это не переключение NEW на деньги.

**Историческое предложение14:55UTC; позже владелец разрешил его выполнение.**
Фактическая пауза15:36:43UTC с broker postchecks и сохранённым сервисом:
`ATT1_OLD_ENTRY_PAUSE_EXECUTED_2026_10_02.json`. Команды ниже сохранены как история,
не инструкция повторно применить pause/resume. NEW orders остаются OFF.

Прямой подписанный broker GET14:55:22UTC:0 linearUSDT positions/0 open orders,
полная пагинация. OLD PID492970 сохранён, trade_on=true/dry_run=false.
Public NEW PID1584802 RUNNING,0 sessions/open/broker/order calls.
Breaker snapshot:21-day lookback,5 trades,net -1.0271USDT,winrate40%; это
диагностический агрегат, не полный независимый ledger/account PnL.

Readonly pause wiring14:57:20UTC подтверждён на VPS: ATT1 entry вызывает
hot-read `_operator_strategy_entry_allowed('att1')` до генерации входа.
Модуль `bot/operator_strategy_controls.py` SHA256
`a61dde4fae0fa4a32c8680de4279fb2d306725842cb1c81a19b099dba6dddad3`
совпадает с просмотренным локальным источником. Default control path
`/root/by-bot/runtime/operator_strategy_controls.json`, отсутствует, без symlink;
override не найден в воспроизведённой current-files startup цепочке. Это не
интроспекция mutable process environment. Entry source SHA c8ca2c32 unchanged.

При явном GO владельца сначала обновить broker/control/source truth. Применить
штатный `pause` в существующем control plane, сохранив любые другие sleeve keys:

```bash
cd /root/by-bot
/root/by-bot/.venv/bin/python3 -B -c 'from bot.operator_strategy_controls import pause; print(pause("att1", source="owner_codex_20261002", reason="Owner-approved new-entry hold pending NEW execution gate"))'
```

Не отправляет ордера, не закрывает позиции, не трогает SL/TP, не останавливает
bybot.service, не меняет env/стратегию/риск/Alpaca/public shadow. При malformed
control state штатный writer откажется его перезаписывать. После записи проверить
`snapshot()`/`is_paused('att1')`, original service PID, свежий heartbeat и broker
truth. Сохранить receipt записи и фактическую границу применения. Если вход уже
был в работе до pause, возможен поздний fill: не объявлять pause мгновенным drain.
Control damage/missing state fail-open: нужен postcheck, не считать это hard kill.

Rollback только по решению владельца: штатный `resume('att1')` с сохранением
остальных keys; это снова разрешает входы. Не удалять state или менять crontab.
В этом цикле ни `pause`, ни `resume`, ни financial cutover не выполнены.

NEW authenticated adapter — GET-only evidence/reconciliation, SEND_ENABLED=false.
Broker replay binding также требует send_enabled=false. Эти компоненты не дают
автономный money runner. Existing migration plan требует exclusive entry owner,
fresh absolute-USDT risk/daily/notional caps, minqty rejection, native protection,
cost/finality recovery и последующее отдельное разрешение на финансовое исполнение.
Frozen2–3 clean prospective filled-terminal gate не отменён вопросом о раннем LIVE.

Private originals: `.private/continuation_20261002/att1_money_question_truth.json`
и `pause_prereqs.json`; не публиковать account/balances/raw order IDs/env evidence.
