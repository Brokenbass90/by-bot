# Active work ownership

Обновлено: 2026-08-20. Цель — не допустить повторения параллельной перезаписи
одних и тех же файлов двумя агентами.

| Зона | Владелец изменений | Правило передачи |
|---|---|---|
| live monolith, risk/execution, broker reconciliation | Codex | Claude передаёт finding/spec, но не правит эти файлы параллельно |
| `signal_copy/` (MT5 execution and journal) | Codex | Claude передаёт parser/UI proposal отдельным diff или commit |
| `web/routes/position_routes.py`, `web/static/position.html` | Codex | новый UI batch сначала инвентаризируется и тестируется |
| parity/release gates and deploy receipts | Codex | только exact hashes и fail-closed gates |
| research hypotheses, prereg drafts, negative analysis | Claude | не имеет order/risk/promotion authority |
| dirty legacy inventory | совместный review, один writer за batch | никаких массовых delete/move без manifest и reproduction receipt |

Перед сменой владельца текущий автор обязан записать HEAD, список изменённых
файлов, тесты и незавершённый gate. Чужие незакоммиченные изменения не
форматируются, не архивируются и не добавляются в тематический commit.
