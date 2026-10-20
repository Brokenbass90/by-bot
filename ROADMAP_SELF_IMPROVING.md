# Roadmap: Self-Improving Algobot / Trading OS

**ORIGINAL GOAL:** безопасная автономная мультистратегийная Trading OS: данные →
проверяемые гипотезы → независимое исследование → допуск → ограниченное исполнение →
защита → выход → сверка → диагностика и следующий разрешённый цикл. Factory ищет
экономические преимущества, Brain проверяет портфельную пользу. AI не получает
самостоятельного права менять LIVE, риск, судью или финансовые разрешения.

**Создан:**10.04.2026. **Актуализирован:**20.10.2026 — Monthly admission/server evidence + PUMP4 intake.
**CURRENT STATUS: PARTIAL.** Проверенные компоненты и репетиции существуют;
непрерывная автономная Factory и автономный денежный Monthly ещё не доказаны.
Это обновление исходного документа, не новый roadmap и не новый financial GO.

## Единственный roadmap и кто обновляет что

Каноническая версия — **этот путь в ветке `codex/recovery-20260824` репозитория
Brokenbass90/by-bot**. Старый файл в research-ветке не является отдельным актуальным
планом. Git-ветки и исторические документы не создают новых источников приоритетов.

| Документ / решение | Ответственный writer | Что обновляет | Когда |
|---|---|---|---|
| `ROADMAP_SELF_IMPROVING.md` | **Codex — maintainer и единственный интегрирующий writer** | Общие фазы, актуальные приоритеты, ownership, зависимости и acceptance; обе линии по evidence | После существенного PASS/FAIL/blocker/решения PM; research-изменения после проверки публикации и receipts |
| `research_lab/KARTA_PROEKTA.md`, research passports/registry | **Claude** | Исследовательские факты, prereg, попытки/данные, economic/forward verdicts; ссылки на общий roadmap | После существенного исследовательского результата; не дублирует финансовые разрешения и общую очередь |
| `research_lab/RESEARCH_TO_LIVE_BOARD.md` в recovery | **Codex** | Производная таблица research/execution/owner gates каждой стратегии | Вместе с соответствующей строкой roadmap; отдельную очередь приоритетов не создаёт |
| Checkpoint / START / MASTER в recovery | **Codex** | Короткий continuity pointer и фактическая дельта | После законченного инженерного блока |
| Приоритеты, change requests | **PM** | Причина смены порядка/направления, архитектурные ограничения | Явное решение с причиной; не автоматическая реакция на последние сделки |
| Финансовые пределы и активация | **Владелец** | Явный bounded GO по проверенному конкретному пакету | После technical acceptance; документ/исследовательский PASS не заменяет разрешение |

Claude сохраняет status delta в своей research-ветке: компонент → статус → SHA →
code/test/runtime evidence → blocker → next gate. Codex читает опубликованный ref,
проверяет delta и сам интегрирует общий roadmap/board. Пользователь не должен
переписывать сводки вручную. Нельзя одновременно править общий roadmap из двух
сессий; research code/KARTA/VOROTA Codex не редактирует. При расхождении источников
помечается UNKNOWN и фиксируется конкретное различие, а не выбирается удобная версия.

Распределение задано PM/владельцем в этой сессии. Claude подтвердил его в опубликованном
`research_lab/ROADMAP_VKLAD_RESEARCH_2026_10_19.md`, ref `1407fbf`:
Codex держит общий roadmap, research-копия OBSOLETE. Изменение самой KARTA ещё
не подтверждено. Для Claude:
старую формулировку KARTA «единый источник правды всего проекта» сузить до research
карты, добавить ссылку сюда; старые финансовые строки заменить ссылкой на execution
board. Изменение своей KARTA выполняет Claude, без переписывания истории.

## Реальная исходная точка и предел аудита

- Execution roadmap опубликован в `451ae69ace07335374d03ed99702ef3fb9c7f335`;
  инженерные receipts ниже сохраняют собственные SHA.
- Research origin на проверке19Oct07:14UTC:
  `1407fbf64178d92f2d121e1f2a114665c1b1c4e0` (`git ls-remote`).
- `3a349a3`, `82193fe`, `3e8f779` подтверждены предками опубликованного ref.
  **Publication blocker CLOSED; независимый непрерывный runtime acceptance не
  подтверждён.** Более новые локальные изменения не считаются опубликованными.
  Research не объединялся с production; judges/daemon не запускались Codex.
- Базовое сопоставление фаз выполнено19Oct. Аудит ограничен19–23Oct включительно
  (пять рабочих дней). Непроверенное к23Oct получает UNKNOWN с owner/следующим
  доказательством; автоматического продления и ожидания аудита для Money Lane нет.

Статусы: **IMPLEMENTED** — в явно указанной границе есть code + test + runtime
receipt; **PARTIAL** — одно звено или end-to-end применение не доказано;
**MISSING** — известная необходимая функция отсутствует; **OBSOLETE** — исторический
план больше не принят; **UNKNOWN** — фактическое подтверждение отсутствует.
Количество файлов/коммитов и наличие модуля не доказывают работающую систему.
Runtime receipt всегда датирован: вчерашняя проверка не является сегодняшним broker readback.

## Исходные фазы → фактическое состояние

| Фаза / ORIGINAL GOAL | CURRENT STATUS | Ответственный | Существующий code / test / runtime evidence | Blocker → следующий acceptance criterion | Настоящая зависимость |
|---|---|---|---|---|---|
| 1. Инфраструктура, здоровье, наблюдаемость | **PARTIAL**, прежнее общее «завершена» историческое | Codex | `research_lab/alpaca_monthly_notifications_v1.py`, `alpaca_day_monitor_v1.py`; notification tests; фактическая Telegram квитанция15223 в [Monthly E2E](reports/ALPACA_MONTHLY_E2E_COMPLETION_2026_10_18.md) | Общая поставка execution/Health/reporting ещё не принята как единый актуальный runtime → симптомы и восстановление проходят через существующие journal/Monitor без второго ledger | Реальное ownership/данные существующего manager; не новый Brain |
| 2. Безопасный денежный цикл, сначала Monthly | **PARTIAL**; pending-fee component/server fixture acceptance PASS | Codex | Existing Monthly manager/book/native finalizer; [20Oct receipt](reports/ALPACA_MONTHLY_PENDING_FEE_ADMISSION_2026_10_20.md):274local/274server exactPASS,4E2E receipts,0orders | Applying production entrypoint и actual NET handoff ещё OPEN; bounded pending estimate не final PnL. Следующий gate — один runner, затем handoff/rollback и owner-reviewed standing packet | Existing owner/cash/fees/native protection; Brain/Factory не блокируют |
| 3. Контролируемое улучшение, change control | **PARTIAL**; бесконтрольное auto-apply **OBSOLETE** | Codex + Claude | Существующие prereg/passports/source pins, execution receipts и versioned GO. Непрерывная автоматическая degradation→repair→review→release цепь **UNKNOWN** | Одна версия ухудшилась → воспроизводимый диагноз/CR/сравнение/rollback; никаких автоматических LIVE изменений по короткой серии PnL | Независимый review и owner-approved release; короткий PF сам по себе не причина повышать риск |
| 4. Factory: корректная автоматическая очередь | **PARTIAL**; default V2.2/денежный judge IMPLEMENTED в sandbox-границе research receipt | Claude | Published3a349a3 в origin1407fbf: `fabrika/fabrika.py`, `begun_h1.py`, `sudya_dengi.py`, `results/fabrika_v2_2_integ_20261019/integ_verdikty.jsonl`; research tests не запускались Codex | Publication CLOSED. Каталог простаивает с01Oct по опубликованному отчёту; непрерывный runtime **UNKNOWN** → штатный causal trace с нужными gates и точным terminal verdict | Существующая очередь/реестр и валидные данные; не новый framework/повтор старых verdicts |
| 4. AI proposer → prereg → evaluator → passport | **PARTIAL**;2reportedFAIL — технические примеры, не alphaPASS | Claude | Published82193fe/3e8f779 в origin1407fbf: `factory_v3/ai_formula_v1.py`, `ai_raund.py`, `fabrika/ai_formula_cikl.py`, `storozh.py`; Claude сообщает115factory tests, Codex их не запускал | Обе формулы составил Claude, не Ollama; hook в storozh.log не наблюдался; proposer/evaluator одного автора. Нужны actual Ollama proposal→verdict/hook trace и независимый review evaluator/registry; publication сам по себе этого не доказывает | Независимые окна/attempt budget; исчерпанное20/20 окно не становится новым из-за новой формулы |
| 4. Strategy passports и независимость | **PARTIAL** для непрерывного полного цикла | Claude | `factory_v3/reestr_v1.py`, `okna_proverka.py`, `avto_prodvizhenie.py`, `data/factory_v3/reestr_v1.jsonl`; component tests в research; полный актуальныйruntime **UNKNOWN** | Code+prereg+window+budget+judge pins связаны в одном проверяемом trace; автор не может менять судью после результата. Auto-prereg не доказывает неиспользованность данных | Протокол независимых данных и достаточная выборка; без повторного запуска spent judge |
| 5. Brain как проверяемый portfolio allocator | **PARTIAL**; added net value **INCONCLUSIVE** | Claude research; Codex read-only integration | Published7a80470:72pairs/6timing confirmations/0money; `fabrika/brain_rezhimy.py`; execution `brain_shadow_readonly_bridge_v1.py` и tests; [интеграция](reports/TRADING_OS_NEXT_GATES_DELIVERY_2026_10_17.md) | Нет доказанного incremental portfolio net value → paired fixed/equal-capital baseline, расходы/корреляция/кризисы; при недостатке независимых economic sleeves **BLOCKED_ECONOMICS** | Несколько допущенных независимых рукавов/проспективные decisions; режимный классификатор не заменяет экономику |
| 5. Multi-market масштабирование | **MISSING / DEFERRED**, исходная цель сохранена | PM + Claude + Codex | Отдельные существующие Alpaca/Bybit источники и frozen стратегии; общего разрешённого money allocator runtime нет | Закрыть первый reproducible net-accounted cycle и доказать второй sleeve до расширения капитала/бирж | Собственные economic/execution gates каждого sleeve, owner caps |
| Сквозные источники для новых исследований | **IMPLEMENTED** в узкой границе BIL/SGOV delivery; **PARTIAL** Polymarket/forward sources | Codex source; Claude QA/research | [92dd3f2:27tests+actualcopy](reports/RESEARCH_SOURCE_DELIVERY_2026_10_19.md); BIL2713/SGOV1606 all+split; Polymarket40markets/20752points; существующие LIQ/IBIT data workers | BIL: prereg overlay; Polymarket: полный согласованный census/lifetime/QA, не pilotPASS; IBIT Massive PENDING, raw LIQ не prospective event | Причинные timestamps, coverage/identity/cost contracts; не новые финансовые полномочия |
| Accounting / Reporting / Tax | **PARTIAL** financial accounting; полный tax assistant **MISSING / DEFERRED** | Codex accounting; Claude design | Existing `alpaca_dynamic_live_runtime_v1.py::finalize_costs`, Monthly book/Monitor; finality tests; [налоговый design](https://github.com/Brokenbass90/by-bot/blob/7a80470d0b928b8fbdf41d69d88570105d2803a4/research_lab/TAX_ACCOUNTING_OS_ROADMAP.md). Единого tax runtime нет | Сначала raw execution/cash/fees reconciliation и reporting из существующего журнала; полный налоговый продукт позже | Actual broker facts и классификация; не создавать второй источник финансовой истины |

Research пути в таблице относятся к sibling `bybit-bot-clean-v28` и соответствующему
Git ref. Локальный документ без публикации — publication blocker, не evidence PASS. Runtime Factory выше не проверялся запуском judge/демона.

## Одна короткая активная очередь

Нумерация здесь операционная: сохранение действующего выше delivery, затем один
главный пакет на исполнителя и максимум один независимый P1. Это не отменяет PM
порядок; аудит документа не блокирует реализацию.

| Slot / владелец | Работа сейчас | Закрывающий acceptance / следующее событие |
|---|---|---|
| **P0 Preserve — Codex** | NET20Oct: independent GET13:35UTC/16:35CY, actual DAY acceptance/coverage/ownership + notification receipt; SHOP остаётся отменён | До свежей квитанции **PENDING**, вчерашний PASS не сегодняшний. One-shot `net20-opening-broker-protection-readback` ACTIVE; новые financial/units permissions отсутствуют. Известный дефект доставки UNKNOWN/no-retry записан; источник ошибки и actual delivery проверяются отдельно от broker stop |
| **P0 Money — Codex** | Monthly pending-fee admission **COMPONENT_PASS**; следующий gate — existing manager applying tick в единственном production entrypoint → exact NET handoff/rollback → concrete standing packet | [20Oct evidence](reports/ALPACA_MONTHLY_PENDING_FEE_ADMISSION_2026_10_20.md):274local+274server PASS,51source/18test files,39imports/0fallback; frozen58 rotation→pending fees→replacement→stop/restart→finality. Candidate UNSELECTED,0real broker requests/writes. Full production CLI/handoff/standing GO ещё OPEN; reserve не выбран/увеличен |
| **NEXT Money — Codex** | **PUMP4 V1 после Monthly**, до менее перспективных crypto tasks; frozen adapter/state/reuse Bybit, ORDERS_OFF | [Published intake](reports/PUMP4_V1_EXECUTION_INTAKE_2026_10_20.md):origin88f42ac verified, frozen strategy matches2ea8d1f; research preregPASS ≠ executionPASS. A1–A6 NOT_RUN. Contract137 vs138 tracked NPZ → explicit versioned universe needed; seven cooldown duplicates remain independently unverified/UNKNOWN outcomes. Limits/r in USDT требуют отдельного owner GO; InPlay/V2 не задерживают V1 |
| **P1 Codex** | Существующие DATA_ONLY/journal доставки/QA; следующий bounded fix — Brain receiver capacity, без нового framework |19Oct source22448opps/68878decisions, V2=1534; catchup6136receipts/28.2MB превышает4096/8MiB, BLOCKED до append, старые8 сохранены. Независимый chain/prefix/key audit PASS в узкой границе предоставленных файлов; полный market census/feature PIT UNKNOWN. Нужна controlled continuity/restart/replay в существующем journal. Existing DATA timers поддерживаются; Polymarket global census не отнимает MoneyP0 |
| **P0 Research — Claude** | Один пакет Factory continuity: V2.2/default money judge + bounded AI proposal cycle + independent windows | Publication3a349a3/82193fe/3e8f779 CLOSED в1407fbf; следующий gate — единый causal automated trace с pins/budget/terminal verdict и независимый review; generator ещё manual/daemon stale не выдавать за полную автономию |
| **P1 Claude / Codex CR** | BIL/SGOV: опубликованный H5B_DEV_PASS и versioned change request | Research4587a34 входит в подтверждённый origin6826315. Нужны account type/settled cash/interest/actual costs и integration в одном account book; current Monthly отвергает чужой fund sleeve. Никакого GO из DEV_PASS |

**Сознательно отложено:** новый Polymarket bulk/global screen до dataset/prereg QA;
SEC/COT source после закрытия MoneyP0 и освобождения Codex P1; максимум три smart
selection гипотезы (SEC, AI top-8 ranking, daily ranking stability21/42) после
освобождения Claude P1. Сравнения — Monthly/momentum/random-within-setup/SPY на
одинаковых ограничениях, с зависимостью по акциям/времени и multiplicity.
Масштабирование, новые frameworks, массовая уборка, multi-account и полный tax
assistant не входят в первую monetary v1. KITY остаётся SPENT/ORDERS_OFF,
Elder сохраняет отдельные prospective/parity gates; количество2–3crypto strategies
и желаемая доходность не заменяют допуск.

**NET trailing — принятый research intake19Oct, BACKLOG после Monthly P0.**
Originresearch`d914fd2` подтверждён; H4 correction`60530b9` — его предок.
Проверенные варианты защиты Monthly имеют FAIL; дополнительная настройка на уже
использованной2016–2026 FROZEN. Ранние activation1.5/2/2.5 этим H4 не проверялись,
но новый подбор на той же истории не создаст независимого подтверждения.
Следующий research gate — prereg на действительно неиспользованных либо будущих
данных, без задержки Money Lane. Legacy NET5min quote-HWM и Monthly closed-daily/
next-session stop — отдельные модели. В activation-only сравнении trail3.5/minlock.5
постоянны;2%/2.5% — отдельная двухпараметрическая гипотеза, не изолированный эффект
активации. Точность stop fills/внутрибарного пути без данных UNKNOWN; оценивать весь
портфель/одинаковые входы/издержки и упущенное продолжение, не только закрытые winners.
[Диагностический receipt](reports/evidence/net_trailing_intake_20261019/receipt.json):
на сохранённом17:15UTC HWM315.505 **ни один** из четырёх порогов не активировался;
самый ранний требует315.89033. Это4pure-code checks, не backtest/economic/forwardPASS.
Новый эксперимент/AI-stop controller не запущен, frozen Monthly и LIVE неизменны.

**20Oct closure:** minimal pending-fee patch and its exact isolated server fixture
acceptance are complete. The26–29Oct target below still concerns the complete
production entrypoint/handoff acceptance, not a reason to wait before implementing
it. New financial scope/reserve and LIVE activation have not been issued.

### Рабочие сроки первой Monthly, без смены стратегии

| Дата / окно | Проверяемый результат | Граница обещания |
|---|---|---|
| До23Oct — инженерная цель | Законченный локальный ORDERS_OFF кандидат: automatic actual-cost producer → один applying runner → restart/lost-response/handoff/rollback evidence → конкретный standing packet | Срок разработки, не факт готовности или financial GO. Если actual fee source недоступен, назвать точный blocker вместо синтетического PASS |
| 26–29Oct — целевое окно приёмки | Точный серверный кандидат, disabled schedule, independent acceptance и решение владельца по bounded standing terms |19Oct owner разрешил code-only upload;44file348690be теперь VPS UNSELECTED, GET/hash/43AST PASS. Full applying runtime и activation ещё не приняты; финансового GO нет |
| 30Oct после actual close | Причинный закрытый снимок57+SPY и frozen Monthly selection | Закрытие по календарю —20:00UTC/22:00Кипр; сигнал/покупка не гарантируются |
| 2Nov14:30–14:35UTC /16:30–16:35Кипр | Ближайшее первоначально предусмотренное окно нового Monthly входа, если все actual gates и owner GO пройдены | CASH/NO_SEND допустимы; нет переноса даты, позднего входа или нового отбора по усмотрению инженера |

**Критическая зависимость до23Oct:** личное окно legacy NET exit2Nov14:30–14:35UTC
совпадает с первым окном Monthly. Должны быть доказаны actual exit/flat/orders,
fees/cash finality и единственное ownership до нового входа. Поздняя комиссия
может заблокировать именно это окно. Не закрывать NET раньше, не ослаблять
cost-finality и не обещать2Nov сделку ради даты; варианты изменения финансовых
условий выносятся только отдельным конкретным owner packet.

**Дополнение cost-source19Oct:** тот же конфликт применяется к обычной Monthly
rotation: продажа и замена в одном5min окне не совместимы с обязательной full-day
posted-fee finality перед любым новым entry. Next owner packet должен дать конкретный
versioned admission CR (возможный bounded pending-cost reserve, conservative loss
admission, unknown-cost stop) либо сохранить NO_SEND. Сейчас никакой резерв/GO/новый
лимит не выдан; net PnL остаётся PENDING до реальных assessments. Менять frozen
календарь или незаметно объявлять неизвестные расходы нулём нельзя.

**Крипто-checkpoint22–23Oct, не LIVE deadline:** KITY остаётся
ECONOMIC_INCONCLUSIVE/SPENT; crypto-only rescue — FAIL. Два weekly canary entry
receipts/C2 parity/C3 guard формируют исследовательский dossier, а не новый money
GO. Elder — hedge-only, ≥30 prospective hedge events и frozen parity/delay/restart
gates; текущая запись0prospective не является свежим пересчётом. При отсутствии
достаточных событий честная дата TINY неизвестна. Размер TINY не отменяет
экономический допуск; после PASS не добавлять произвольные недели ожидания.

## Уточнение20Oct: сроки исследований и существующие data blockers

Origin research `52094dd356cd0fd54c8e03b1201e420ef9606e3e` проверен через
`git ls-remote`; документы прочитаны из этого ref, research tests/judges Codex
не запускал. Очередь Monthly P0 → существующий независимый DATA_ONLY P1 сохранена.

- **H2b не является улучшением к ноябрьскому запуску.** Действующий prereg требует
  минимум18 **месячных** сигнальных дат с завершённым42-session исходом; ежедневные
  snapshots не увеличивают число независимых наблюдений. Более ранняя формулировка
  итогового отчёта про ежедневные даты не заменяет этот prereg. Monthly не ждёт H2b.
- **H6 trailing остаётся исследованием.** Identity318/318 и360/360 и разложение
  исторической отдачи — evidence о симуляторе/механике, не PASS ранней активации.
  Forward-когорты/22-session outcomes и их зависимость нельзя заменить числом
  дневных записей. Legacy NET и Monthly protection сохраняют свои frozen правила.
- **IBIT: серверный capture не равен своевременной доставке в лабораторию.**
  `19-net-ibit` был one-shot и PAUSED после фактической передачи. Запрос Claude
  `ZAPROS_CODEX_IBIT_EZHEDNEVNO_2026_10_20.md` принят как существующая DATA_ONLY
  зависимость: ежедневная доставка с actual availability/import timestamps и
  cross-source/adjustment parity. Ежедневная local delivery/предел60min пока
  NOT_PROVEN; один server latency963s не доказывает этот SLA. Massive остаётся PENDING.
- **Binance forward продолжение:** research сообщает213/335 perp series и паритет
  на10 рядах. Это ограниченный проход, не полное DATA_READY335. До использования
  конкретной гипотезой нужны её coverage/freshness и manifest, без изменения архива.

Это уточнение evidence/сроков, не новый roadmap, prereg, strategy change или LIVE GO.

## Gate гипотез и change control

Новая AI hypothesis содержит экономическую причину/кто платит, причинную формулу,
метрику, MDE, sample plan, независимое окно, costs/control, лимит попыток и falsifier.
Один автор не меняет evaluator после исхода; pins и read-only outcome access
фиксируются до теста. Комбинации атомов и выбор гипотез также расходуют бюджет;
отсутствие числовых параметров не устраняет overfitting.

Любое изменение LIVE: причина/CR → прежняя и новая версия → сравнение economic и
execution поведения → независимый review → точные owner terms → rollback criterion
и receipt. Bounded standing permission допускает только заранее согласованные
действия; это не право AI на произвольные live patches или расширение риска.

Research ориентиры12–15% для Alpaca и30–40% для активных sleeves сохранены как
целевые вопросы исследований, не promises, acceptance thresholds или разрешение
добавить плечо. KPI — completed reconciled cycles, independent economic verdicts,
forward candidates, unresolved incidents и confirmed net PnL; не тоннаж кода.

## Changelog управления —19Oct2026

- Обновлён исходный roadmap: единственный интегрирующий writer Codex; Claude research
  owner; PM priorities, owner financial authority. Board/KARTA роли разведены.
- Фазы1–5 сохранены, текущие статусы основаны на code/test/dated runtime receipts.
  Прежние «production/WF-22/phase complete» не переносятся на нынешнюю систему.
- Monthly получает MoneyP0 независимо от Factory/Brain. Published92dd3f2 принят;
  local3a349a3/82193fe/3e8f779 отмечены NOT_CONFIRMED_ORIGIN, не выданы за deployedPASS.
- Отдельно отмечены исчерпанное20/20 окно, manual AI proposals, stale catalog daemon,
  автоматический prereg без гарантии независимости и неизвестный portfolio edge.
- До23Oct закрыть доступные evidence gaps; остальные UNKNOWN, не бесконечный аудит.
  Следующие изменения добавляются сюда с причиной; исходная цель не заменяется.
- Follow-up19Oct07:14UTC: origin1407fbf подтверждён, publication blocker трёх
  research-коммитов CLOSED и acknowledgement Claude принят. Историческая запись
  NOT_CONFIRMED выше описывает предыдущую проверку. KARTA pointer ещё не подтверждён.
  Добавлены инженерные целевые даты/условное первое окно и NET same-window blocker;
  финансовые разрешения, strategy contracts и LIVE не изменены.
- Follow-up19Oct07:30UTC: owner разрешил неактивную передачу Monthly348690be;
  [code staging/readback DONE](reports/MONTHLY_STAGING_AND_BRAIN_CONTEXT_2026_10_19.md),
  прежний LOCAL_ONLY transfer blocker закрыт.165exact/51Brain-Elder targeted PASS;
  full server runtime не заявлен. Brain источник свежий19Oct07:13UTC, но existing
  receiver6136projected/28.2MB BLOCKED_CAPACITY;8oldreceipts неизменны. Continuity
  fix выбран текущим P1 без отвлечения от Monthly cost producer/runner P0.

- Follow-up19Oct cost-source cycle: actual new GET collector /7FILL/6FEE/$0.06,
  четыре account-day сверены; записывается pre-entry cash anchor; автоматический
  producer связан с existing finalizer, неизвестные/новые liabilities блокируют
  release. [Evidence и границы](reports/MONTHLY_COST_FINALITY_AND_BRAIN_INTEGRITY_2026_10_19.md).
  Это локальная ORDERS_OFF инженерная приёмка, не Monthly LIVE execution.
  Следующий P0 — один server applying runner, exact package rehearsal/handoff/rollback.
  Cleanup START HERE отложен; навигация восстановлена без массовых изменений.
- Published origin6826315 подтверждён19Oct12:15UTC,4587a34 — ancestor. U2 H2b:
  ежедневный1Day SIP/split источник пока DATA_BLOCKED, U58 Yahoo Monthly58 отдельный;
  первый16Oct снимок BACKFILLED_DIAGNOSTIC. Это P1 data queue, не условие запуска
  исходной Monthly и не подмена источника SIP/Yahoo. H2b economic assessment только
  по своему prereg; Codex не добавляет новые статистические gates.
- BIL/SGOV CR принят без финансового разрешения: дополнительный sleeve сейчас
  конфликтует с foreign-position admission Monthly. Account type/interest/SGOV
  execution costs не доказаны; отсутствующий INT не считается нулевым процентом.
  Polymarket QA документ опубликован (5 reported tests; subsequent commits report9),
  Codex tests не запускал. Favourite study NEGATIVE; новый NO shadow не LIVE/edge PASS.
  Actual Ollama cycle reported FAIL и stale-module fix7364443 опубликованы;
  непрерывная Factory/Brain полезность для net PnL по-прежнему не доказана.

---

## Историческая редакция до24Aug2026 — не текущие статусы и не полномочия

Ниже сохранён прежний текст без удаления истории. SHA256 исходных12003bytes: `fde91178a71ae84d7c2b6ccd80c2dbc6ee035c18bb2b792e770c0e65df8d1537`. Его «ЗАВЕРШЕНА», «Продакшн»,
«запущено», PF/доходность/планы и старые приоритеты являются историческими записями,
не подтверждением текущего LIVE. Старые процессы/стратегии по этому тексту не запускать.

# Roadmap: Self-Improving Algobot

**Цель:** Контролируемая самообучающаяся система, которая сама обнаруживает
возможности, проверяет их и адаптируется к рынку через воспроизводимые gates.
Автоматическая генерация не даёт права на деньги: AI/Ollama/DeepSeek работают
в режиме `proposal-only`, а promotion, риск и ордера требуют hash-bound
доказательств и явного owner-approved release.

**Дата создания:** 2026-04-10  
**Обновлено:** 2026-08-24
**Статус:** архитектура и исследовательский pipeline частично готовы; closed-loop
самооптимизация НЕ считается завершённой до live/research parity, shadow
control и paper lifecycle gates.

## Канонический жизненный цикл идеи

Для каждой ноги порядок неизменен:

`propose → preregister → parity → shadow + random control → paper lifecycle → tiny canary → scale`

Исследовательская вселенная должна быть шире денежной: evidence-shadow и
контроль собирают статистику на заранее зафиксированной широкой universe,
тогда как live money sleeve остаётся узким до отдельного parity и
exposure/correlation gate. AI только предлагает finding/experiment и не может
сам продвигать кандидата, менять конфиг, риск или включать торговлю.

## Фактическая граница текущей автономности

Оркестратор, router, allocator, watchdogs и исследовательская очередь существуют
как компоненты, но наличие компонента не означает, что он подключён к каждому
денежному caller. Для ATT1/SBR1 это проверяется caller receipt и fixed-universe
ON/OFF replay. Самоисправление означает безопасное обнаружение → reproduction →
patch → tests → deploy receipt; не бесконтрольное изменение live.

---

## Фаза 1 — Инфраструктура (ЗАВЕРШЕНА ✅)

- **4-режимный оркестратор**: bull_trend / bull_chop / bear_chop / bear_trend (BTC 4H EMA21/55 + ER)
- **Symbol Router**: динамический подбор монет per-strategy, retry + degrade
- **Portfolio Allocator v8**: sleeve multipliers per-regime, 24 рукавов зарегистрировано
- **Самовосстанавливающиеся watchdogs**: health_watchdog (2 мин), control_plane (30 мин)
- **Nightly autoresearch queue**: автоматические backtest-запуски ночью
- **DeepSeek оператор в Telegram**: `/ai`, `/ai_tune`, `/ai_results`
- **Alpaca monthly rotation**: v37 sweep pending, текущий PF=4.68, +130% compound (paper)
- **BTC Dominance Regime Filter**: `build_btc_dominance_state.py` → alt_bias overlay (4H cron)

---

## Фаза 2 — Портфель стратегий (ФИНАЛ 🔄)

Цель: 8-10 рабочих стратегий с WF-22 подтверждением, покрывающих все режимы.

### ✅ Продакшн (WF-22 прошли)

| Стратегия | Sleeve | Режим | PF | Сделок/год |
|---|---|---|---|---|
| alt_resistance_fade_v1 | flat | bear_chop (primary) | 1.4+ | ~150 |
| alt_sloped_channel_v1 | sloped | все | 1.3+ | ~120 |
| alt_support_bounce_v1 | bounce1 | bull_trend | 1.3+ | ~80 |
| alt_range_scalp_v1 | range_scalp | все | 1.2+ | ~200 |
| impulse_volume_breakout_v1 | impulse | bull | 1.48 | ~40 |
| alt_inplay_breakdown_v1 | breakdown | bear (disabled — re-WF pending) | 4.3 sweep | ~60 |

### 🟡 Ожидают WF-22 (параметры найдены, на сервере сейчас)

| Стратегия | Sleeve | Лучшие параметры | Статус |
|---|---|---|---|
| alt_inplay_breakdown_v1 | breakdown | LOOKBACK_H=36, SL_ATR=1.4, RR=2.0 → sweep PF=4.3 | **Запущен WF-22 на сервере** |
| elder_triple_screen_v3 | elder_ts_v3 | 96-combo macro-relax sweep | **Запущен sweep на сервере** |
| alt_trendline_touch_v1 | att1 | PIVOT_LEFT=2, R=2.0, TOUCH_ATR=0.25 → PF=1.295 | **Запущен WF-22 на сервере** |
| alt_horizontal_break_v1 | hzbo1 | sweep не запускался | Ждёт очереди |
| inplay_breakout | breakout | HTF-scale SL fix (96cf4fd), нужен retune sweep | Ждёт sweep |

### 🆕 Новые стратегии (написаны, нужен backtest)

| Стратегия | Sleeve | Идея | Статус |
|---|---|---|---|
| session_open_breakout_v1 | sob1 | London 08:00 / NY 13:30 — первая импульсная 15m свеча | ✅ Написана, зарегистрирована, **нужен WF-22** |
| funding_rate_reversion_v1 | funding_rev | Bybit 8H funding extremes → reversion | Зарегистрирована, нужен backtest |
| liquidation_cascade_entry_v1 | liq_cascade | Liquidation spike fade | Зарегистрирована, нужен backtest |
| sloped_resistance_choch_v1 | slope_choch | CHOCH at sloped resistance | Зарегистрирована, нужен backtest |
| micro_scalper_v1 | micro_scalp | 5m EMA pullback scalper | Зарегистрирована, нужен backtest |

### 🔴 Требуют фикса

| Стратегия | Проблема |
|---|---|
| alt_inplay_breakdown_v2 | 0 сделок в backtest — баг в коде (диагноз в Codex Task 3.4) |
| btc_eth_midterm_v3 | SL-баг исправлен, нужен param sweep |
| elder_triple_screen_v3 | 0 сделок при дефолтных параметрах — слишком строгие фильтры |

---

## Фаза 3 — Самооптимизация (СЛЕДУЮЩАЯ 🎯)

### 3.1 Auto-Apply Winners (ПРИОРИТЕТ #1)
```python
# scripts/auto_apply_research_winner.py
# Research winner может только сформировать проверяемый apply proposal.
# Применение требует независимого receipt, hash/config parity, owner approval
# и тихого окна; отсутствие любого условия = fail-closed, без изменения live.
```

### 3.2 Performance Degradation Detector (ПРИОРИТЕТ #2)
```python
# scripts/live_vs_backtest_monitor.py
# rolling_pf_live_30d < backtest_pf × 0.6 → пауза стратегии + добавить в reopt queue
# TG: "⚠️ ARF1 деградирует: live PF=0.9 vs backtest PF=1.4"
```

### 3.3 Regime-Triggered Reoptimization (ПРИОРИТЕТ #3)
```python
# В control_plane_watchdog.py — хук на смену applied_regime
# При смене режима → добавить в queue параметры под новый режим
```

### 3.4 Live Params Drift Tracker (ПРИОРИТЕТ #4)
```
runtime/params_history.jsonl — лог всех applied параметров с P&L атрибуцией
```

### 3.5 Stack Comparison Gate (ПРИОРИТЕТ #5)
```bash
python3 scripts/run_stack_comparison_queue.py --config configs/stack_comparison_queue_20260423.json
```

Задача: больше не принимать красивые strategy-only цифры без проверки всего стека. Каждый кандидат сравнивается в двух режимах:

- без control-plane: стратегия сама по себе;
- с control-plane: orchestrator + router + allocator + health gate.

Правило ремонта: если полный стек сильно режет сделки/доходность и не даёт сравнимого снижения просадки, чинить или ослаблять именно control-plane для этого рукава, а не списывать стратегию как "сломалась".

---

## Фаза 4 — Strategy Factory (БУДУЩЕЕ 🔮)

- **Strategy Genome Engine**: мутации параметров от рабочих стратегий
- **DeepSeek Research Proposals**: AI предлагает идеи на основе рыночной статистики
- **A/B Testing Framework**: параллельный запуск 2 версий, автовыбор победителя
- **Cross-Regime Learning**: выученные паттерны из реальных данных

---

## Фаза 5 — Масштабирование (БУДУЩЕЕ 🔮)

- Multi-account: aggressive / conservative risk profiles
- Cross-exchange: Bybit + Binance + OKX
- Crypto + Equities: единый оркестратор Bybit + Alpaca
- Volatility-adjusted sizing: адаптация к BVIV/ATR percentile
- Correlation-aware portfolio: лимит одновременных коррелированных позиций

---

## Текущий стек

```
LIVE BOT
├── smart_pump_reversal_bot.py        — главный loop
├── bot/deepseek_overlay.py           — TG оператор с AI
├── bot/operator_snapshot.py          — snapshot для AI
│
ORCHESTRATION
├── scripts/build_regime_state.py     — 4-режимный детектор
├── scripts/build_btc_dominance_state.py  — alt_bias overlay (NEW)
├── scripts/build_symbol_router.py    — динамический роутер
├── scripts/build_portfolio_allocator.py  — риск-распределение
│
SELF-HEALING
├── scripts/bot_health_watchdog.sh    — каждые 2 мин
├── scripts/control_plane_watchdog.py — каждые 30 мин
├── scripts/setup_server_crons.sh     — мастер-инсталлер
│
SELF-RESEARCH
├── backtest/run_portfolio.py         — портфельный backtest
├── scripts/run_nightly_research_queue.py — ночная очередь
├── bot/deepseek_autoresearch_agent.py    — AI анализ
│
SELF-OPTIMIZE (НЕТ — ФАЗА 3)
├── scripts/auto_apply_research_winner.py   — fail-closed proposal/apply gate
├── scripts/live_vs_backtest_monitor.py     — TODO
└── runtime/params_history.jsonl           — TODO
```

---

## Приоритеты прямо сейчас (август 2026)

1. Закрыть live-native caller parity ATT1/SBR1 и доказать фактическое
   подключение режима/аллокатора, не меняя деньги до PASS.
2. Расширить SBR1/ATT1 evidence-shadow и random control на заранее записанную
   universe, оставив money universe узкой.
3. Завершить Alpaca paper lifecycle и protection health auditor; SAFE_HOLD
   снимать только отдельным promotion receipt.
4. Провести XAU/Forex и Polymarket только как data/paper research, с exact
   costs, settlement и no-order authority.
5. Вести 30/90-дневные gates и receipts вместо календарных обещаний доходности.

---

## KPI прогресса

| Метрика | Сейчас (апр 2026) | Цель Фаза 2 | Цель Фаза 3 |
|---|---|---|---|
| Стратегий с WF-22 | 5 | 8-10 | 10+ |
| Сделок в день | 1-3 | 3-8 | 5-12 |
| Ручного вмешательства | много | редко | почти нет |
| Auto-reopt coverage | 0% | 0% | 80% |
| Конвейер стратегий | 5 в разработке | стабильный | автоматический |
