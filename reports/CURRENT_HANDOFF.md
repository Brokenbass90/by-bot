# Текущий handoff

Обновлено: 2026-09-01. Работать только в каноническом дереве
`bybit-bot-recovery-20260824`, ветка `codex/recovery-20260824`. Перед этим
документом код Research Conveyor V1 находится на запушенном commit
`62c34504d93ec4fa4b1cd9454ea5a9e8b09a5e19`; документационный commit меняет
HEAD отдельно.

## Research Conveyor V1

Конвейер — это честная research-only очередь, а не автоторговля. Его точная
authority:

`research_only_no_live_risk_order_promotion_or_private_api_authority`

Executable manifest:
`configs/research/research_conveyor_v1.json`, current `manifest_sha256` (SHA-256 of
the canonical JSON payload, not raw file bytes)
`ca007dfba56d01aaf559a46c7086614c46f1a56266f6c4653b312232016616b0`.

Канонический preflight receipt:
`runtime/research_conveyor/manual_20260901_v5/terminal_receipt.json`, embedded
self-hash
`561e54eef1610cfcb4529b476365835e56502e180fb1d0f273d5dcc6bb8a6630`.
Preflights v1–v4 are superseded evidence; do not treat them as the current
manifest receipt.

Он зафиксировал 10 terminal receipts: 3 `BLOCKED_DATA_OR_PARITY`, 7
`BLOCKED_ADAPTER`, ноль phase receipts, logs и adapter launches. Это корректный
readiness result: не называть его backtest, diagnostic pass или доказательством
доходности. Начальная очередь не имеет `RUNNABLE` карт.

Manual CLI — только из canonical root, и каждый раз с новым путём, которого
ещё не существует: runner откажется от любого уже существующего пути, даже
пустого.

```bash
python3 scripts/run_research_conveyor.py \
  --config configs/research/research_conveyor_v1.json \
  --run-dir runtime/research_conveyor/manual_<UTC_UNIQUE>_preflight \
  --preflight
```

Есть `--dry-run`, `--preflight` и `--run`. Первые два никогда не запускают
адаптер. `--run` может запускать только reviewed `RUNNABLE` card с четырьмя
hash-bound фазами; сейчас таких карт ноль. `BLOCKED_*` — допустимый terminal
verdict. Даже `PASS_DIAGNOSTIC` означает только прохождение четырёх research
фаз; он не даёт promotion, shadow, paper, money, live, broker, order, private
API или risk authority. Scheduler/LaunchAgent/cron не установлен.

Research Conveyor отличается от Station v3: Station v3 resume-ит тот же
immutable `run-id`; Conveyor запрещает любой уже существующий `run-dir`.
Receipts и
authority этих двух систем не взаимозаменяемы. Для rollback не удалять и не
перезаписывать receipts: сохранить evidence и не запускать новую итерацию.

Граница безопасности важна: Conveyor authority — policy + receipt contract, не
OS sandbox. Runner использует `shell=False`, очищенное окружение, hash-bound
reviewed script paths и process-group-bounded timeout для cooperative reviewed
adapters. Это не adversarial process-tree containment и не обещает остановить
враждебный дочерний процесс вне reviewed execution assumptions. Текущий
preflight безопасен фактически: `RUNNABLE=0`, adapters launched=0. Будущий
`--run` разрешать только после отдельного review, доказывающего отсутствие
network/private/live/broker/order/risk side effects у adapter, и после запуска
adapter через Station v3 isolation либо независимо reviewed equivalent,
предотвращающий process/session spawn. Synthetic adapters только для тестов и
не могут сделать production card `RUNNABLE`. У compliant reviewed adapter
external rollback не ожидается. Если side effect всё-таки возникнет, это
incident: сначала reconciliation внешних систем, потому что receipts сами
ничего не откатывают.

## Ближайшая техническая очередь

1. XSEC: общий deterministic control и data-parity contract; до verified
   histories всех closed+active PIT contracts остаётся `BLOCKED_DATA_OR_PARITY`.
2. Bull Continuation: frozen detector и execution adapter с четырьмя фазами.
3. XAU: независимый causal data/cost parity, затем adapter.
4. Только после каждого отдельного scoped commit + tests + manual receipt +
   independent review соответствующая карта может стать `RUNNABLE`.

Task 1–3 Conveyor verification: 72 passed, `py_compile` PASS, `git diff
--check` PASS. При будущих runnable adapters помнить границу V1: runner
hash-bind-ит adapter script и ограничивает допустимые roots, но это не заменяет
отдельный code review и техническую isolation-границу самого adapter.

## Сохранённые факты Task 5 и live caution

Проверенный и запушенный Task 5 code floor:
`482a536f1b734361c42720744243465b3f033a69`. Последний factual запуск — только
dry-run: `NOT_CONFIRMED`, `legacy_stop=[]`, authorization отсутствует. В этой
сессии Task 5 не мигрировал live, не менял order/risk/money authority и не
останавливал legacy screen sessions.

Alpaca `SAFE_HOLD` — только snapshot последнего canonical checkpoint, а не
свежая выписка брокера. Перед любым live утверждением заново сверить Git,
deployed hashes, service, heartbeat и прямые broker positions/orders/fills.
Этот handoff не является текущей broker-выпиской.

Старое `bybit-bot-clean-v28` активно меняется. Не использовать там `git add
-A`, не удалять `.git/index.lock`, `_snimki`, `_to_delete` или backups.
Уникальные изменения переносить только изолированными группами после secret
scan, tests и review.
