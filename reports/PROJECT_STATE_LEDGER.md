# PROJECT STATE LEDGER — единая точка правды (обновляется каждую сессию)
Последнее обновление: 2026-06-30 (Claude). START HERE. План вперёд: reports/ROADMAP_V2_2026_06_30.md. Тестов: 71 зелёный.

## Принципы (не нарушать)
- АСИММЕТРИЧНЫЙ R:R: тейк 2-3R, стоп ~1R (прибыль через R, не винрейт).
- Свипы Корпатого ДА, но отбор по OOS-плато, не по in-sample (иначе overfit).
- Фокус сместился на ФОРЕКС-костяк + механику; directional переписываем OOS-first, не хороним.
- OOS-first: in-sample PASS ≠ успех. Судим по OOS.
- Не удаляем/не «замораживаем» идеи — спорное в архив, не в корзину.
- Деньги — в механические эджи (carry) + Alpaca; directional крипта должна
  ЗАСЛУЖИТЬ место через честный OOS.
- ИИ = аналитик/настройщик/менеджер В РЕЛЬСАХ, НЕ генератор кода (это нас подвело).
- Claude не трогает сервер/деньги — готовит код+артефакты; Codex деплоит/гоняет;
  деньги заводит владелец.

## НОВЫЙ ФУНДАМЕНТ (построен Claude, под тестами — 63 зелёных)
| Модуль | Что | Тесты |
|---|---|---|
| `bot/market_context.py` | детектор уровней: горизонт. кластеры, наклонные(R²,valid,min_slope), HVN, VWAP, classify_channel, nearest_broken_level, atr(exclude_last), build_context(max_age,exclude_last_atr) | 19 |
| `bot/volume_exit.py` | ранний выход по затуханию объёма + impulse-gate | 11 |
| `bot/strategy_breaker.py` | авто-роллбэк рукава (net-pnl/серия/expiry) | 11 |
| `bot/carry_neutral.py` | delta-neutral carry мозг (basis/liq/rebalance guards) | 9 |
| `bot/adaptive_context.py` | ИИ-настройщик параметров (rule-based + tuner-hook DeepSeek) | 5 |
| `scripts/market_survey.py` | обзор рынка: где какой эдж сейчас | — |
| `scripts/render_levels.py` | визуализация уровней | — |
| `scripts/market_survey.py` | обзор рынка: режим+структура по всем символам -> где какой эдж | — |

## СТРАТЕГИИ-НОГИ
| Файл | Статус | Заметка |
|---|---|---|
| `alt_trendline_touch_v1` (ATT1) | LIVE canary 0.10 short-only | редкий, пока 0 входов (нет наклонки) |
| `alt_resistance_fade_v2` (ARF2/пила) | research | OOS no-go; vol-filter ВКЛючён (fix); нужен упрощ.+WF (Codex) |
| `alt_support_bounce_v2` (ASB2) | research (тест) | ждёт 240d WF |
| `alt_channel_bounce_v1` (ACB1) | research (тест) | двусторонний канал; ждёт 240d WF |
| `inplay_retest_v3` | заменён на V4 | baseline PF 0.868 |
| `inplay_retest_v4` (НОВ) | research (5 тестов) | быстрый вход у уровня + асимметр. R:R (tp2.5/sl1) + свежесть + setup B (ретест пробоя); ждёт WF |
| `spike_fade_v3` | кандидат-диверсификатор | PF 1.99, редкий |
| `elder_*` | фильтр, не движок | проходил WF-22 до temporal-фикса |
| 71 прочих | архив/заморозка (по инвентарю) | не удалять |

## ДЕНЕЖНЫЕ КОНТУРЫ
- Alpaca v38: PF 6.47, ждёт live-аккаунт+$500+ключи (владелец) → dry-run → live.
- Cross-exchange carry: кандидаты GWEI/SLX; мозг готов; нужна обвязка ордерами (Codex).
- ATT1 short: live, риск 0.10, ждёт сетап.
- Pair stat-arb (`pair_stat_arb_v1`): cointegration, beta/z-score/half-life + СВОЙ WF тулинг (walkforward_pair_arb/validate_pair_arb) — закодирован, НЕ валидирован. Механический #2.
- Basis arb (`basis_arb_v1`, 382 стр) — закодирован, не валидирован.

## PENDING — CODEX (батч к коммиту/прогону)
- Закоммитить весь новый набор (фундамент-апгрейды, adaptive_context, render, ARF2 fix).
- ARF2: упростить параметры (убрать HVN/VWAP/recency веса) + ATR на rows[:-1] + честный WF.
- InPlay V4 (вход 1m/лимит у уровня, свежесть уровней).
- Carry: re-gate на высоком funding + delta-neutral обвязка.
- FX/XAU strict research (бесплатные данные) + Alpaca dry-run.

## PENDING — CLAUDE (локально)
- ASB2 + ACB1 adaptive ✓. СТОП пилить фичи на непроверенных ногах.
- Следующее: НЕ код, а WF-валидация (Codex). broken-level — опционально позже.
- Докрутить ASB2/ACB1 под broken-level + свежесть.
- По готовности: AdaptiveContextProvider → DeepSeek-tuner (когда будет API-бюджет).
- РЕФАЙН: sloped require_unbroken мерить на недавнем сегменте, не на всём окне (survey показал valid_sloped=0 — слишком строго).
- Survey-вывод: наклонные редки -> приоритет range/horizontal ноги, не ATT1.

## PENDING — ВЛАДЕЛЕЦ
- Завести Alpaca live $500 (реальный контур).
- Отдавать Codex батчи; носить ответы DeepSeek/GPT по аудиту.

## КЛЮЧЕВЫЕ ДОКИ (reports/)
- `COURSE_CORRECTION_2026_06_30.md` — разворот после OOS.
- `AUDIT_VERDICT_AND_FIXES_2026_06_30.md` — проверка claims DeepSeek + фиксы.
- `AUDIT_BUNDLE_2026_06_30.md` — карта кода для внешних ИИ.
- `WHAT_DIDNT_WORK_FOR_DEEPSEEK_2026_06_30.md` — для консультаций.
- `STRATEGY_INVENTORY_2026_06_29.csv` — все 91 с бакетами.
- `FUNDING_CARRY_READINESS_2026_06_29.md`, `PORTFOLIO_AND_AI_MANAGEMENT_PLAN_2026_06_29.md`.
