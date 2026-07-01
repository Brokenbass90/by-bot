# План уборки проекта (2026-07-01, Claude) — «архив, не корзина»

Факты: 93 стратегии (≈71 FREEZE/ARCHIVE по STRATEGY_INVENTORY_2026_06_29.csv),
85 .md в КОРНЕ, reports/ 155 файлов, 186 untracked, кэши/tmp. Активный код тонет.
Правило владельца: НЕ удаляем идеи — переносим в archive/. (Claude из песочницы не
может mv/rm — это делает Codex через `git mv`; ниже точные бакеты.)

## Принцип: разделить АКТИВНОЕ и АРХИВ, ничего не теряя
Активная поверхность должна быть ~15-20 стратегий, а не 93.

## 1. Build-артефакты / кэш -> убрать из дерева (уже в .gitignore)
`git rm -r --cached` + удалить рабочие копии: `__pycache__/`, `pytest-cache-files-*/`,
`tmp/`, `tmp_codex_sync/`, `pytest-cache-files-qjinodvv/`. (В .gitignore добавлено 2026-07-01.)

## 2. Корневые .md (85) -> docs/archive/
Все дат ированные хендоффы/аудиты/спеки (напр. *_20260517.md, CODEX_HANDOFF_2026_05_*,
ADVANCED_ARB_CONCEPTS, AI_*_CONCEPT ...) -> `git mv` в `docs/archive/`. В корне оставить
только: README.md, CLAUDE.md (если есть), PROJECT_MAP.md, CLAUDE_PROJECT_MAP.md (один из них).
Единая точка правды остаётся reports/PROJECT_STATE_LEDGER.md.

## 3. Стратегии (93) -> strategies/archive/ по инвентарю
FREEZE + ARCHIVE бакеты из STRATEGY_INVENTORY_2026_06_29.csv -> `git mv strategies/<f>.py
strategies/archive/`. ВАЖНО: перед переносом `grep -rn "from strategies.<name>\|strategies/<name>"`
по коду и strategy_catalog/registry — обновить импорты/каталог, иначе сломается загрузка.
Активными оставить (KEEP + живые кандидаты):
  alt_trendline_touch_v1 (ATT1 live), alt_resistance_fade_v2 (ARF2), alt_support_bounce_v2 (ASB2),
  alt_channel_bounce_v1 (ACB1), inplay_retest_v4, spike_fade_v3, pair_stat_arb_v1, basis_arb_v1,
  pair_arb_executor_v1, alpaca_* (активные v38), + то, что реально в ротации по heartbeat.
Всё прочее (~70) -> archive (НЕ удалять; risk=0 уже стоит).

## 4. reports/ (155) -> reports/archive/ по дате
Оставить в reports/ только текущие (2026-06-29..07-01) + START_HERE/LEDGER/ROADMAP.
Старьё (<= 2026-06-25) -> `git mv` в `reports/archive/`. Индекс: обновить handoff-ссылки.

## 5. Крупные бинарные/данные — проверить трекинг
`data_cache/`, `backtest_runs/`, `backtest_archive/` уже в .gitignore — убедиться, что не
затрекано случайно (`git ls-files | grep -E "data_cache|backtest_runs"`). Если да — `git rm --cached`.

## Порядок (безопасно, обратимо)
1) .gitignore (готово) -> `git rm --cached` кэши/tmp.
2) корневые .md -> docs/archive (низкий риск).
3) reports старьё -> reports/archive (низкий риск).
4) стратегии -> archive ТОЛЬКО после grep импортов + апдейт каталога (средний риск, тестами прикрыто).
5) `pytest` активного набора зелёный -> коммит «chore: archive legacy, declutter tree».

## Что НЕ трогать
bot/ (фундамент+хелперы), tests/ активные, forex/, runtime/live_mirror, configs (secrets),
data_cache (нужен для WF локально). Ничего не удаляем безвозвратно — только archive/.
