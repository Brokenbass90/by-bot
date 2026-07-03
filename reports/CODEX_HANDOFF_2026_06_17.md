# Хэндофф для Codex — что прогнать/вшить (2026-06-17)

Всё ниже сделано Claude аддитивно и протестировано локально (**334 passed, 2 skipped**). Задача Codex — серверные прогоны и вшивание в монолит/крон. Запушить отчёты и эти файлы.

## Новые/изменённые файлы
- `strategies/inplay_retest_v3.py` — + `max_entry_dist_atr` (анти-блоуап против −100).
- `strategies/alpaca_adaptive_v1.py` — + градуированный регим (`soft_regime`), ATR-трейлинг (`trailing_exit`/`update_peak`), пресет `lively_config()`. **Дефолт = прежнее поведение.**
- `backtest/hedge_pairing.py` — инструмент хеджа красных месяцев (range + breakdown/Elder).
- `scripts/proof_of_life.py` — русский PULSE + `build_daily_digest_ru` (флаг `--daily`).
- `web/activity_feed.py`, `web/routes/ai_routes.py` (`GET /api/ai/activity`), `web/static/index.html` (панель «Лента бота») — веб-часть единой ленты.
- `bot/maker_entry.py` — готов (без изменений), ждёт вшивания.
- Тесты: `test_inplay_retest_v3`, `test_alpaca_adaptive_v1`, `test_hedge_pairing`, `test_activity_feed`, `test_proof_of_life_digest`.

## 1. adaptive_v1 «бодрее» — A/B на сервере
Сравнить на bakeoff (вкл. медведь-2022) три конфигурации:
- baseline `AdaptiveConfig()` (как сейчас),
- `lively_config()` (soft_regime + трейлинг + max_positions=5),
- и по отдельности soft_regime-only и trailing-only (чтобы видеть вклад каждого).
Критерий: частота/доходность чуть выше, **просадка не вырастает существенно** (держим преимущество 2.2% DD). Трейлинг (`trailing_exit`) вшить в Alpaca-исполнитель как пер-бар оверлей между ребалансами.

## 2. Alpaca реал $500 (по запросу владельца — на следующей неделе)
Условия (см. `SYNC_ALPACA_AND_IDEAS_2026_06_17.md` §2):
1. Ордер-крон → **adaptive_v1** (можно `lively_config`), НЕ v38.
2. Исключить дорогие имена (LLY) — чтобы $500 разложились на 3–4 бумаги.
3. Софт-трейл + брокерский стоп.
4. **Сначала 1 неделя пейпера с adaptive_v1, реально выставляющим ордера** (не shadow) → проверка исполнения на $500 → потом реал.
5. Ожидание: стабилизатор (сохранение капитала), не доход.

## 3. Идея #2 — хедж красных месяцев
Прогнать `backtest/hedge_pairing.hedge_report(primary, hedge)` на реальных трейд-стримах:
- primary = range (лучший зелёный), hedge = breakdown (для медвежьих сломов) и отдельно Elder (для трендов).
- Цель: `improved=True` (FAIL→PASS), `covered_red_bear_months` покрывают красные месяцы range (2025-10, 2026-03), `hedge_drag_months` маленький.
- Если хедж закрывает красные месяцы → можно поднимать `RANGE_RISK_MULT` (путь к двузначным %).

## 4. Идея #1 — maker-входы
Вшить `bot/maker_entry.post_only_price` в тело ордера (`timeInForce=PostOnly`) для входов «у уровня» (ASB1/ARF1/range/v3), и `should_fallback_to_taker` — пересечь спред, если цена ушла/не налилось. Хелпер готов и протестирован.

## 5. Идея #3 — ежедневный RU-дайджест
`python scripts/proof_of_life.py --daily --send` в крон (раз в день). Шлёт человеческий русский дайджест: пульс + P&L по рукавам + риск-постура.

## 6. Единый чат веб↔ТГ — шаг 2 (монолит)
Зеркалить свободный текст ТГ в `runtime/web_ai_history.json`: `_tg_reply()` входящие как `{"role":"user","channel":"tg"}`, `_tg_send_raw()` ответы как `{"role":"assistant","channel":"tg"}`. Веб-лента (`/api/ai/activity`) это уже подхватит. Затем единый «мозг» обоих каналов через `bot/ai_tools`.

## 7. Остальное (из прошлых хэндоффов, ещё висит)
- inplay_retest_v3: разбор trade-stream (причина −100) → узкий sweep → monthly/stack.
- Русификация `pulse()`/`reports_loop()`/`_tg_reply()` (словари в `proof_of_life.py`).
- Фикс экспортёра снапшота: 3 раздела env (.env / overlays / live-process) — снапшот сейчас устаревает и врёт про live-конфиг.
- Запушить `REVIEW_CODEX_AND_UNIFICATION_2026_06_17.md`, `STRATEGY_ROSTER_REVIEW_2026_06_17.md`, `SYNC_ALPACA_AND_IDEAS_2026_06_17.md`, этот файл.
