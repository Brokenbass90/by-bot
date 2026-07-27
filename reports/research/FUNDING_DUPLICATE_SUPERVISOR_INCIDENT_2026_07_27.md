# Funding paper duplicate-supervisor incident

Дата обнаружения: 2026-07-27
Влияние: только локальный risk-zero research, не live trading.

## Факт

Один и тот же `scripts/run_cross_exchange_funding_shadow_loop.sh` писал в общий
`runtime/arb` двумя процессами:

- старый orphan, старт `2026-07-26 07:45 local`, PID `52261`;
- новый контролируемый screen `cross_arb_shadow_20260727`, старт
  `2026-07-27 12:52 local`, PID `31553`.

Старый PID `52261` и его parent `52259` остановлены. Screen supervisor оставлен
активным. После проверки остался один процесс.

## Последствия

- двойной polling не ускоряет число независимых 24-hour lifecycle cycles;
- одновременная запись могла менять marks/validated snapshots в разном порядке;
- закрытые циклы и оценки, затронутые overlap, нельзя использовать для
  promotion без отдельной проверки;
- live Bybit/ATT1 и Alpaca не затронуты.

## Quarantine

Overlap window: примерно `2026-07-27T09:52Z` —
`2026-07-27T10:53Z`. Promotion sample после инцидента должен либо:

1. доказать на уровне cycle timestamps, что конкретный цикл не зависел от race;
2. либо использовать только cycles, открытые после cutover.

До materialization post-cutover cohort `capital_authorized=false`.

## Prevention

- single-instance directory lock/PID ownership добавлен в supervisor; второй
  запуск проверен и завершается с code `73`;
- stale-lock recovery намеренно fail-closed: сначала ручная проверка owner;
- JSON state заменяется через durable temporary file + atomic `os.replace`;
- сохранять `supervisor_instance_id` и `cycle_opened_at` в ledger;
- проверять PID uniqueness в 12-hour research heartbeat;
- не запускать новый loop, если уже существует cron/screen с тем же state path.
