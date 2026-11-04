# PUMP4 DATA export для сравнения Brain,4Nov2026

Создан запрошенный `research_lab/data/ispolnimost_signalov.jsonl` в recovery checkout,
копия сSHA — [export](evidence/pump4_brain_executability_20261104/ispolnimost_signalov.jsonl),
[manifest](evidence/pump4_brain_executability_20261104/manifest.json).
8уже проверенных кандидатов:8BLOCKED,0EXECUTABLE,0FILLED. Это НЕ вся история LIVE.
5 имеют actual OBSERVATION_BOUND, SIREN actual ENTRY_SOURCE_STALE (причинаUNKNOWN),
2до exactoriginalpilot scope. BLOCKED — факт отказа/недопуска данного пилота,
не доказательство правильности source gate и не вердикт экономики стратегии.

Ключ: noga=PUMP4, sym, ts_ms=время открытия сигнальной свечи (SIREN02UTC, не03UTC).
known_since_ms — время текущей сверки/подготовки4Nov; старые статусы не объявлены
своевременно известными Brain в момент старого сигнала. Нет строки →UNKNOWN.
В причинном сравнении нужен known_since_ms<=время решения; retrospective validity
review нельзя выдавать за тогдашний вход/совет. Применять одинаковую выборку обеим
версиям, квалифицировать независимость и не называть модельные исходы реальными.

Владелец подтвердил UNKNOWN/time semantics и передаст Claude изменение reader.
Проверенный текущий brain_raspredelitel.py уже считает отсутствие UNKNOWN, но
known_since_ms ещё не учитывает. Поэтому DATA подготовлена в recovery/evidence,
активный reader/соседний research checkout не менялись и Brain не запускался.
Подключение к активному D/ispolnimost_signalov.jsonl — после исправления reader;
без него причинное сравнение NOT_CONFIRMED. Экспорт не новая финансовая authority.
