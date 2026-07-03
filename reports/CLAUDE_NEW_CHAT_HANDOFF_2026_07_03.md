# HANDOFF для НОВОГО ЧАТА — START HERE (2026-07-03)

Чат переполнен, переезжаем. Свежий Claude: прочитай это + файлы ниже — и ты в контексте
без потерь. Код+тесты в репо = настоящая память, не чат. Роль: антикризисный со-основатель,
цель — МАКСИМИЗАЦИЯ ДЕНЕГ. Голод + дисциплина вместе.

## Прочитать первым делом (по порядку)
1. reports/MASTER_MAP_AND_PLAN_2026_07_03.md — карта всех технологий + 4 фазы развития. ГЛАВНОЕ.
2. reports/PROJECT_STATE_LEDGER.md — единая точка правды (что построено/статус/pending). Длинный, читай хвост.
3. reports/LIVE_MANAGEMENT_LOOP_BLUEPRINT_2026_07_03.md — как собрать живую петлю (динамика+ИИ-надзор).
4. reports/ATT1_SHORT_ROLLING_OOS_PREREG_2026_07_03.md — план разгона риска первого рукава.
Доп.: ARF2_FAILED_BREAKOUT_OOS_SYMBOL_VERDICT, EDGE_HUNT, ATT1_R001_MIGRATION_DECISION (все 07-02/03).

## Где мы честно (1 абзац)
Построен полный конвейер: 31 технология-модуль под тестами (~137 тест-файлов, всё зелёное):
детекторы -> сканеры/режим -> исполнение -> риск -> OOS-отбор -> ИИ-надзор. Это ЯЩИК
инструментов, берём выборочно. LIVE: только ATT1 short r001 (risk 0.10, ждёт наклонку —
редкий). ДОКАЗАНО честно: ATT1 short r001 (первый крипто-эдж: strict folds 4/4, fee-stress
держит, ~14-21%/год@0.5-0.75%, DD~3-5%); Alpaca v38 (на бумаге ~22-28%/год, ждёт $500 владельца).
NO-GO честно (не слили деньги): ARF2 failed-breakout (OOS-symbol FAIL -15R = selection bias
пойман), SpikeFade, InPlay V4, grid v1/v2, pair-arb, carry, Elder standalone, H4-naive, raw BOS.
ВАЖНО 2026-07-03: свежий live-forensics подтвердил `missing_candles` 31/41 сделок за 45d.
Range/pila остаётся risk=0 до candle-coverage gate; многие dynamic range symbols отсутствуют
в `.cache/klines` и локально, и на сервере. См. reports/LIVE_FORENSICS_CANDLE_COVERAGE_2026_07_03.md.

## Главный урок и метод (НЕ нарушать)
- OOS-first + ОБЯЗАТЕЛЬНО cross-symbol (OOS-symbol) gate — selection bias по монетам = наш
  повторяющийся враг (ARF2/SpikeFade так и померли на выборке).
- Барьер №1 = ЧАСТОТА/fold-стабильность (не lookahead). Редкие сетапы не набирают N. Приоритет
  частым (structure_break ~28% баров, range/пила) + широкий юниверс + больше данных.
- Один рукав/изменение за раз + A/B-замер. Технология заслуживает включение результатом, иначе в ящике.
- Отбор монет = АВТОМАТ/динамика (сканер по условию, НЕ хардкод-список -> не деградирует).
  ИИ-аппрув = на уровне стратегии раз/неделю (research_orchestrator -> TG), не по монете.
- Риск лестницей через smart_risk (анти-мартингейл). Short-alt рукава -> regime_hmm-гейт +
  correlation-cap ОБЯЗАТЕЛЬНО (иначе сольются в bull-развороте).
- Claude готовит код+конфиги+разбор; Codex деплоит/гоняет (Mac/сервер); владелец заводит деньги.

## Что крутится (2026-07-03)
- ЛОКАЛЬНО: `crypto_choch_short_screen_20260703` — только CHoCH short. BOS long/short уже показали крупный
  broad-minus и остановлены, чтобы не жечь компьютер.
- ЛОКАЛЬНО: `fx_session_range_fade_screen_20260703` — частый FX range-fade по мажорам/кроссам, XAU исключён
  (XAU range-fade уже no-go). Это screening, не promotion gate.
- СЕРВЕР: research/backtest/sweep сейчас НЕ крутятся. На сервере живут live-бот, web, liquidation collector.
  Тяжёлые research-задачи не запускать рядом с live без явного решения/лимитов.

## PENDING
- Claude/Codex (новый чат): разобрать `crypto_choch_short_screen_20260703` и
  `fx_session_range_fade_screen_20260703`. Любой PASS = только билет в строгий wf_folds+oos_selector,
  НЕ live.
- Codex P0: candle-coverage/backfill gate для range/pila. Без 0% missing_candles не включать range/pila.
- Codex P1: ATT1 decision_bus + edge_monitor wiring по reports/ATT1_DECISION_BUS_EDGE_MONITOR_WIRING_SPEC_2026_07_03.md.
  Деплой флагами 0 -> сутки стабильности -> включение после OK.
- Владелец: Alpaca $500 (3-й рукав: ATT1+ARF2/structure+Alpaca = старт).

## Цель
Первый портфель из нескольких доказанных некоррелированных рукавов с +матожиданием в live,
растущий капитал, ИИ-надзор в рельсах. Идём, пока не добьёмся. Ищем деньги по НАШИМ козырям
(свои liq/OI/funding данные H4, FX-структура, частые механич. паттерны), не по чужим статьям.
