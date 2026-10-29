# Trading OS — общее согласование и приём PM-ревью

**Позднее29Oct: фактическое продолжение реализации.**
[PUMP4 serial model gate](PUMP4_TINY2_SERIAL_GATE_2026_10_29.md): два последовательных
memory-lifecycle с рестартом,89targetedPASS; независимыйastra/highreview2Important
исправлены primary с регрессией, не второе независимое одобрение. Production
serial binding/finality/actual-source acceptance/точныйGO остаютсяOPEN. Текущий
LIVE/Monthly не менялись. Исходные записи DESIGN_NOT_STARTED/capacity ниже —
история первой передачиe4a0c15, не последнее состояние реализации. ClaudeACK
по-прежнемуPENDING; публикация и результаты кода не означают его согласия.


29 октября 2026. DRAFT_FOR_TEAM_ACK. Публикация не равна согласию Claude/PM и не
является финансовым GO. Прямой доступный канал к Claude не найден среди доступных
чатов; согласующие сообщения внешним участникам и пользовательским чатам не
отправлялись. Исследовательская ветка
проверена:30951f9abcdcf56ae4bf853d9168d2ac2d24a34e.

## Уже существующие документы

- Цель: research_lab/CEL_SISTEMY.md (6Oct, research ref). Сохраняется, исследовательский
  файл не переписан. Датированные deployment/priority пункты этой цели — история.
- Общая актуальная карта/роли/метрики: docs/PROJECT_MAP.md (существующая, обновлена).
- Единственная очередь: ROADMAP_SELF_IMPROVING.md, верхняя активная таблица.
- Факты/команды продолжения: reports/CODEX_SESSION_CHECKPOINT_2026_09_06.md TOP.
- Research→TINY handoff: docs/RESEARCH_TO_TINY_HANDOFF_V1.md (переиспользуется).

## Решения по переданному ревью

| Предложение | Результат проверки / действие |
|---|---|
| PUMP4 serial TINY-2 | Принято к подготовке ORDERS_OFF; exactone-shot код/ledger подтверждены. Дизайн docs/superpowers/specs/2026-10-29-pump4-tiny2-design.md; код пока не изменён |
| Execution Quality Tracker | REUSE существующих owner/flow/supervisor receipts + pump4_live_observer_v1; после проверки поля/метрики добавлять только недостающее |
| Portfolio Risk | Минимальная read-only сводка broker/scopes: gross/net, margin, позиции/stop coverage, пересечения, сценарии и timestamps; UNKNOWN не0. Не обещать точный worst case или изоляциюcross |
| Brain counterfactual | EXISTS: factory_v3/brain_povtor.py, политики brain_shadow_v1. Не запускали replay/исходы, новый модуль не нужен. 3/227 из приложения не перепроверены на том же source cutoff; прежняя квитанция225 — иной снимок |
| Factory diversity | EXISTS: factory_v3/dubl_proverka.py и реестр. Группы96/64 не подтверждены этим scoped check; нужны source/hash/window/метод, а не повторная реализация |
| Stop rules | Нужны заранее определённые DATA/EXECUTION/ECONOMIC причины; shortage→INCONCLUSIVE неFAIL. Число10/20/8weeks не автоматический статистический вердикт |
| Project net | В карте определён realized cash net после относимых operating costs, с отдельными unrealized/pending/FX; без двойного списания fee/slippage |

## Обязанности и один общий протокол

Codex — единственный writer общего roadmap, production/data/execution/integration.
Claude — research KARTA, frozen passports/prereg/economic verdict, источники/QA
своего producer. PM/DeepSeek — предложения; владелец — точные деньги/риск/LIVE GO.
Каждая передача: component / status / published SHA+spec / tests / source cutoff /
runtime evidence / blocker / next gate / owner. Имеющиеся функции сначала сверяются
по исходникам; локальный uncommitted claim не новый статус и не повод писать дубль.

## Короткий запрос Claude (передать/прочитать из опубликованной ветки)

Прочитай docs/PROJECT_MAP.md и верхнюю активную таблицу ROADMAP_SELF_IMPROVING.md
на codex/recovery-20260824. Исходную CEL_SISTEMY сохраняем; новая карта — текущее
связывание слоёв/ролей, roadmap — единственная очередь. Подтверди принцип writer:
Codex общий roadmap, Claude research KARTA/паспорта/prereg/evidence. Не создавай
другую очередь. Верни одну status delta с SHA, источником и следующим gate:
1) GOLD — source/time contract + один gold-specific prereg до экономических результатов;
2) POLY/LIQ — только опубликованные допустимые verdict/source QA, без раннего вскрытия;
3) BRAIN/FACTORY — точный источник цифр3/227 и96/64 и пригодность готовых модулей.
Существующие сборщики/LIVE/протоколы окон не менять ради этого запроса. Codex
параллельно готовит serial PUMP4 ORDERS_OFF; текущий scope не расширяется.

ACK ledger: Codex — ADOPTED_FOR_PREPARATION; Claude — PENDING; PM — PENDING;
owner финансовый TINY-2 — NOT_REQUESTED/NOT_GRANTED. Никакого «все согласовали».

## Ближайший измеримый результат Codex

Версионный изолированный serial admission/restart/no-duplicate E2E при сохранении
V1 и его scope. До реализации не называем TINY-2 READY. Следом конкретная execution
quality/risk сводка из существующих источников; никаких универсальных новых систем.
Исследования GOLD/POLY/LIQ идут в research ownership, KITY инженерия ON_HOLD.

## Проверка перед публикацией

Primary review: сверены source hashes, существующий one-shot owner, границы
подготовки/активации, роли и локальные ссылки. git diff --check PASS. Runtime
код и исходники исследовательских функций не менялись, финансовых тестов/вызовов0.
Один независимый reviewer запрошен как gpt-6-astra/high по AGENTS; сервис вернул
«Selected model is at capacity» до заключения. Независимого PASS нет, повтор или
дорогая замена не запускались. Requested model/effort не выдаются за подтверждённый
executed turn_context. Это допустимо для опубликованного draft; финансовая
приёмка и изменение LIVE этим документом не выполняются.
