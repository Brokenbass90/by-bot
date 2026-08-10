# План безопасной зачистки проекта

Срез: 2026-08-10 14:46 UTC, Git HEAD `c5eba1c`.

## Что измерено

Read-only manifest насчитал `1,138` измененных/неотслеживаемых paths:

| Класс | Количество | Действие |
|---|---:|---|
| tracked changes | 27 | разнести по владельцу и маленьким commits |
| document/metadata | 429 | оставить canonical index, остальное архивировать по ссылкам |
| reports/research output | 344 | сохранить verdict/receipt/manifest, bulk run вынести |
| archive/backup | 100 | quarantine вне checkout, затем owner review |
| manual code candidate | 61 | references + tests + owner; удаление запрещено до проверки |
| runtime/log | 29 | вынести из Git tree, сохранить требуемое evidence window |
| data/research output | 23 | content-addressed storage + hash manifest |
| secret/env-looking name | 14 | проверить permissions/content без печати; rotate при утечке |
| unknown | 111 | ручная классификация, default = preserve |

Крупнейшие untracked объекты — market/research data до примерно `10.7 MB` на
файл; они создают большую часть визуального и дискового шума, но могут быть
нужны для воспроизводимости.

## Очередь очистки

1. **Freeze owner map:** `CLAUDE`, `CODEX`, `GENERATED`, `RUNTIME`, `UNKNOWN`.
2. **Canonical set:** определить минимальные read-first roadmap/handoff/state,
   active entrypoints, configs, tests и immutable receipts.
3. **Bulk artifacts:** перенести data/log/full-run outputs во внешний
   content-addressed каталог; в repo оставить SHA256 manifest и компактный
   verdict. Никаких blind deletes.
4. **Backups/env:** permissioned quarantine вне checkout; искать возможные
   секреты без вывода значений. При подтвержденной экспозиции — rotation.
5. **Manual code (61):** для каждого path собрать imports/references, tests,
   last owner/change и runtime reachability. Canonical code — commit; полезный
   experiment — research namespace; остальное — patch/quarantine.
6. **Tracked batch:** отдельно принять/отклонить удаления старых reports и
   перенос четырех retired strategies, которые сейчас принадлежат работе Клода.
7. **Ignore/retention:** обновить `.gitignore` и retention rules только после
   того, как canonical manifests воспроизводят нужные runs.
8. **Final proof:** clean clone, tests, code index, startup smokes и deploy
   bundle строятся без файлов из quarantine.

## Fail-close правила

- `UNKNOWN` не удаляется;
- файл с runtime reference не удаляется без replacement/redirect test;
- research result без config/data/code hashes не считается canonical;
- secret-looking файл не коммитится и не печатается в отчеты;
- параллельные изменения другого агента не включаются в чужой commit;
- каждый destructive batch имеет manifest, backup/quarantine и rollback.

## Ближайший безопасный batch

Сначала вынести `runtime/logs`, bulk market data и явные backups по manifest.
Это уменьшит шум без изменения strategy/live behavior. Затем отдельно разобрать
61 code candidate и только после этого принимать массовую зачистку reports.
