# Polymarket: первые полные автоматические модельные циклы,4Nov2026

**FIRST_REAL_FULL_MODEL_CYCLES_VERIFIED.** Три сигнала одного матча Buriram–Kashima
автоматически сопоставлены с будущими официальными resolutions16:07:30/16:08:04UTC;
join сохранён16:11:53–54UTC (18:11Cyprus). Нет нового сервиса или ручного replay.
По первым двум ID592477… иce56… модельный net после captured fee estimate:
3.9666667 и3.1885155 на budget100 каждый; третий1e82… —2.9427835. Это неactualPnL.
Независимо перепроверены все3parent manifests/files/after-fsync anchors, raw SHA
официального ответа, exactcondition/tokens/payouts, порядок времён и арифметика net.
Три рынка одного матча не три независимых возможности; SPORTS-before-final не
доказан. real_fill=false,actual_fees/net=null. V2 остаётся контрольным FAIL-правилом.

Снимок4Nov17:56UTC:9complete measurements/3joins/2BLOCKED. По двум отказам не
создана новая попытка; один captured book имеет NO_ASK_AT_LIMIT, другой complete
fresh measurement не получен. Это неопределённость исполнимости, не нулевая цена.
V3по последнему штатному hook WAITING_REAL_SIGNAL. Новый E2 код не разрабатывался.

[Проверка полных циклов](evidence/poly_cycle_e2_20261104/official-joins-20261104.json),
[reproduction](evidence/poly_cycle_e2_20261104/verify-official-joins.py).
Денежного допуска/экономическогоPASS по этим результатам нет. Ниже — более ранние
измерения и приёмка V3 witness, сохранённые как датированная история.

---

# Polymarket: два настоящих E2 измерения и V3 source witness —4Nov2026

**FIRST_REAL_SIGNALS_MEASURED / FUTURE_OFFICIAL_OUTCOME_PENDING.**
Новый сигнал E2 `592477964f4c96c66c32290e` автоматически обработан4Nov13:42:23UTC.
Market6627581, Buriram United–Kashima Antlers, Under2.5: signal13:42:23.322,
consumer first observation after fsync13:42:23.563, actual measurement13:42:23.960.
Оба token REST books и feeSchedule сохранены; выбранный ask0.96, book age1ms,
модельный бюджет100, displayed-depth VWAP0.96, оценка комиссии0.20.
Это новый своевременно прочитанный сигнал, не replay истории. Независимое
доказательство, что матч ещё не завершился, отсутствует; official join PENDING.

Второй сигнал `ce56e3243a151baec5a0697e` того же матча (Both Teams to Score)
автоматически обработан уже новым bundle13:50:53UTC, exit0 в13:51:08UTC.
Исходная quote0.96; displayed-depth VWAP0.9675810474 на model100, fee estimate0.162.
Это фиксируемое ухудшение доступной цены, а не реальное проскальзывание fill.
Два разных рынка одного матча не засчитаны как независимые возможности.
Проверены исходные строки, SHA всех manifest files и отдельные after-fsync anchors.
Повторный hook сохранил прежние measurement, joined0/order_posts0.

## V3: независимая проверка готовых пяти строк

Вход SHA64fabe4ea75257784790edc81879bcc9e9fe1a0a543a8279cbf0e21230ed79f5,
5строк из `V3_SVIDETEL_ISTORIYA_31_10_03_11.jsonl`. Producer/judge не запускались.
Все5 проверены собственным verifier: allowlisted path, sealed compressed/raw hash,
полный newline prefix/seq/epoch, native local import receipt, exact frame hash,
monotonic/receive clocks, gameId/score/period/clock, доступность до signal_ms.
**У4/5 импорт позже старой book timestamp.** Это отдельно отмечено
score_available_before_book=false. signal_ms относится к сухому прогону4Nov,
поэтому5/5 — компонентная проверка provenance, не историческая исполнимость,
не E2/live-сигналы и не экономический PASS. Claimed first_seen не объявлен
независимым внешним timestamp; SPORTS FINAL/fill не доказаны.

## Установленная совместимая версия

Файл producer V3 и E2 manifest проверены по подтверждённому владельцем SHA
cb6c6bd18d46a8d61be7ab0e8e44e5a0e28ad896004457efbb206f2b34a9d04a.
Прежний consumer корректно выдавал PRODUCER_DRIFT; после проверки bytes обновлена
только собственная закреплённая версия ORDERS_OFF consumer. Producer/hook неизменны.
Новый immutable runtime manifest
4e276ab0474dbcfcf80912add06fc6410bf88271cc268c4ffb6d871761509b8e,
launcher36240f94cdca19b7e26eaef62d7c3e947d10ae00fcf3ee0cfa680060a64e7fcb.
Старый bundle и launcher backup сохранены; замена собственного launcher атомарная.
Установка13:50:12UTC, ручной GET-only check CYCLE_CHECKED, затем реальный
автоматический вызов13:50:53 подтвердил работу с прежним состоянием/без дублей.
V3 пока WAITING_REAL_SIGNAL. Нового сервиса, ордеров, кошельков, keys/env нет.

157 целевых dependency tests PASS (96Poly+61PUMP); RED сохранены. Один ограниченный
независимый astra/high review нового diff: PASS, подтверждённых P0/P1/P2 нет,
reviewer12targetedPASS. Полный project suite не запускался.

## Следующая граница

Существующий hook сам проверяет official resolution и сохранит model outcome
с первоначальным signal ID/manifest. Полный цикл пока PENDING; старое правило
V2 остаётся контрольным источником, снятым с денежной очереди. Ни два измерения,
ни будущий модельный net не дают TINY/LIVE или основания обещать прибыль.
Для текущей ORDERS_OFF работы пополнять Polymarket не требуется.

Доказательства: [первое измерение](evidence/poly_cycle_e2_20261104/first-real-e2-measurement.json),
[новый автоматический hook](evidence/poly_cycle_e2_20261104/witness-actual-hook.json),
[пять witness](evidence/poly_cycle_e2_20261104/v3-witness-check.json),
[runtime](evidence/poly_cycle_e2_20261104/witness-runtime.json).
