# PUMP4: будущий capture ENTRY_SOURCE_STALE —4Nov2026

**LOCAL_ONLY / NOT_DEPLOYED.** Подготовлен минимальный patch существующих
selected_runner/runtime_sources/supervisor, без нового сервиса и без установки
в действующего финансового владельца. Исторический SIREN остаётся CLOSED_UNKNOWN.

При том же ValueError PUMP4_RUNNER_ENTRY_SOURCE_STALE capture содержит stage
(CANDIDATE_PUBLIC_PRECHECK/PRE_ACCOUNT/POST_ACCOUNT), decision_id, source_ms,
available_ms, check_ms, оба возраста, exact violated boundaries и по каждому
публичному ответу endpoint/request/receive/body.time/raw SHA. Raw body, account,
ключи и headers не копируются. selected_tick сохраняет capture в blocked result,
который действующий supervisor публикует как immutable receipt.

Сравнения 0..5000ms и окно max60000ms, порядок account GET, права, scope, STOP,
owner/lease и отсутствие resend не менялись. Тесты четырёх границ и propagation
в receipt проходят вместе с зависимостями. 61PUMP targeted PASS; независимый
ограниченный review PASS. Диагностический patch не доказывает исправления причины.
Выбор версии в LIVE потребует отдельной проверки изменённых financial source pins;
сейчас такой handoff/GO не выполнялся. NativePUMP/DATA/Monthly/Polymarket неизменны.
