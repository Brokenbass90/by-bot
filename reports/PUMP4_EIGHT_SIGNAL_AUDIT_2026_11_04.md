# PUMP4: восемь кандидатов — фактические стадии, 4 ноября2026

Утверждение «LIVE-DATA не видела ни одного raw-сигнала» неверно: все8 найдены в
исходных VPS publication и независимых original observations; содержимое совпало.
Все8 canonicaldecisionID перепроверены, source_pins совпали с frozenV1 и
локальными фактическими SHA стратегии. Это8 raw-сигналов, не8 допустимых/упущенных сделок и не подтверждённая прибыль.

| Кандидат / решение не раньше UTC | Публикация после закрытия | Первая доказанная преграда |
|---|---:|---|
| 1000PEPE,28Oct16:00 |36.862с|До начала первого scope28Oct18:09:38.340UTC|
| TUT,28Oct16:00 |37.154с|До начала первого scope|
| HYPE,30Oct18:00 |15.767с|Финансовые receipts: OBSERVATION_BOUND|
| XPL,31Oct10:00 |8.286с|OBSERVATION_BOUND|
| ESP,31Oct10:00 |30.506с|OBSERVATION_BOUND|
| HEI,31Oct11:00 |45.026с|OBSERVATION_BOUND|
| GWEI,1Nov02:00 |37.631с|OBSERVATION_BOUND|
| SIREN,3Nov03:00 |2.482с|03:00:15.697UTC: ENTRY_SOURCE_STALE; далее coverage blocked|

Publication timestamp снимается до окончательной fsync-публикации индекса;
эти offsets не отдельное историческое доказательство доступности индекса owner.

SIREN: сигнальная свеча открылась02UTC, решение не раньше03UTC. Raw-фильтры
пройдены, сигналshort сохранён. Первые финансовые receipts:03:00:01 waiting,
03:00:15.697 BLOCKED_NEW_INPUTS/PUMP4_RUNNER_ENTRY_SOURCE_STALE, затем ожидание
публикаций; с03:01:36.006 CURRENT_HOUR_COVERAGE_UNVERIFIED. Census134/134complete,
122/134within60, no disconnect. Итого есть ДВЕ реальные преграды, а не отсутствие сигнала.

ENTRY_SOURCE_STALE —5-секундная свежесть source_ms/available_ms свежей HTTPS-проверки,
отдельная от60-секундного окна. Исходные HTTPS captures этой неуспешной попытки
в данном evidence отсутствуют: неизвестно, какой timestamp/этап дал превышение.
Нельзя объявлять причиной только DATAlateness или менять5s/60s. Следующий bounded
PUMP-шаг — read-only измерить весь fresh-HTTPS→replay→freshness-check путь и сохранить
тайминги/ответы. На основании текущих receipts задним числом его не восстановить.

Для пяти старых кандидатов независимые финансовые receipts за соответствующие
минуты подтвердили OBSERVATION_BOUND старого reader. Сценарий «детектор не находит»
не подтвердился; архивный дефект и позже свежесть/полнота блокировали admission.

В выбранном immutable candidate проверен actual hash execution_plan: стоп ×4,
доли0.40/0.60, первые две цели0.9/1.8 сигнальногоR; третья цель не используется.
Это реализация плана, не доказательство фактических fills/rounding/PnL. Исследовательские
+0.35R не становятся реальной прибылью; максимум1entry не превращается в8сделок.

Новый bound-key проверен существующим pinned GET-helper4Nov12:26:09.914UTC:
sameaccount=true/exactVPSIP=true/key_no_fixed_expiry=true/expiry_ms0. Financial
owner3669955/active/NRestarts0 сохранён. Предупреждение legacy main из12:00UTC
указывает6Nov,1.9дня — это другой configuration binding, не выбранный PUMP4key.
Не требуется снова загружать ключ PUMP4 на основании этого сообщения. Старую
конфигурацию не меняли/предупреждение не выключали; потребители legacy требуют
отдельной read-only инвентаризации до её отзыва/ротации.

[Санитизированные SHA/receipt timestamps](evidence/pump4_eight_signal_audit_20261104/actual-stage-audit.json).
Полные ответы приватно .private/pump4_candidate_audit_20261104. Ни финансовых
команд, ни рестартов, ни смены стратегии/ключей/лимитов/GO не выполнено.
Полный30-дневный census не заявлен: это ограниченная проверка8 предоставленных
кандидатов. Частота0.9/сутки на2025 — отчёт Claude, здесь не пересчитывалась;
выборка только закрытых исходов не равна полному потоку всех сигналов.
