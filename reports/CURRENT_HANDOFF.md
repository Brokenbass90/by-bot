# Текущий handoff

Обновлено: 2026-08-31.

Единая точка продолжения:

`reports/CODEX_SESSION_CHECKPOINT_2026_08_31.md`

Каноническое дерево и ветка:

- `bybit-bot-recovery-20260824`;
- `codex/recovery-20260824`;
- verified pushed Task 5 code floor:
  `482a536f1b734361c42720744243465b3f033a69`.

Task 5 canonical migration закончен и запушен. Последний factual запуск был
только dry-run: `NOT_CONFIRMED`, `legacy_stop=[]`, authorization отсутствует.
Ни live, ни ордера, ни риск, ни screen-сессии не менялись.

Следующая очередь:

1. XSEC PIT V5 Task 1 — shared deterministic controls and frozen 36-arm family.
2. Параллельно Bull Continuation Tasks 2 и 3 — event detector и execution model.
3. Canonical Station Task 6 — status/audit gate, без live migration.
4. Затем Bull frozen contract, XSEC PIT preflight и public-only closed-symbol
   data acquisition. До данных XSEC обязан остаться `BLOCKED_DATA_OR_PARITY`.

Старое `bybit-bot-clean-v28` активно меняется. Не использовать там
`git add -A`, не удалять `.git/index.lock`, `_snimki`, `_to_delete` или backups.
Уникальные изменения переносить в каноническое дерево только изолированными
группами после secret scan и tests.

Перед любым live-утверждением заново сверять Git, deployed hashes, service,
heartbeat и broker positions/orders/fills. Этот файл не является текущей
broker-выпиской.
