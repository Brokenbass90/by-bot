# Settlement/execution v3 — research MVP audit

Дата фиксации: `2026-07-21`. Статус: **local research-only**, без private API, cron migration, ордеров, капитала или доходностного вердикта.

## Зачем создан отдельный v3

Legacy cross-exchange funding v2 invalidated: его 228 cycles не имеют достаточной settlement, taxonomy, lineage и execution достоверности. V3 не продолжает этот журнал и не наследует его цифры; будущая выборка начинается с нуля.

## Зафиксированный контракт

- один последовательный supervisor и atomic/idempotent receipts;
- asset/venue/settlement metadata и полная lineage;
- причинный порядок `predicted funding -> validation books -> entry books -> settlement`;
- freshness/skew gates и fail-closed при нарушении времени;
- funding P&L только как `leg quantity × exact settlement mark × actual public rate`;
- conflicting duplicate settlement rate/mark блокируется;
- manifest хеширует runner и весь исполняемый package, включая storage/supervisor;
- bad/incomplete cycles не допускаются в descriptive ROI.

## Аудит и тесты

Независимый аудит нашёл три P1: неверную базу funding P&L, неполную causal chronology и неполный code manifest. Все три исправлены. `11` focused tests PASS, `py_compile` PASS; полный проект после исправлений — `1507` tests PASS. В пределах заявленной research-only модели оставшихся P0/P1 нет.

## Что это пока не умеет

- ingest ожидает pre-normalized local public bundles; provenance-bound collector ещё нужен;
- комиссии являются conservative assumptions, а не account-specific fill receipts;
- нет authenticated fills, margin, maintenance/liquidation, transfers и real two-leg recovery/legging;
- ROI только описывает корректно собранную research-выборку и не является прогнозом дохода;
- старый прогноз `$5–15/month per $1000` остаётся отозван.

## Следующие ворота

1. Freeze code/config hashes этого MVP.
2. Построить public collector с provenance для predicted funding, validation/entry books и exact settlement marks.
3. Собирать fresh cycles from zero.
4. Только после устойчивого net result под stress costs проектировать paper execution. До этого API-ключи и капитал не требуются.

Основные файлы: `configs/preregistered/settlement_execution_v3_research_v1.json`, `scripts/run_settlement_execution_v3.py`, `scripts/settlement_execution_v3/`, `tests/test_settlement_execution_v3_station.py`.
