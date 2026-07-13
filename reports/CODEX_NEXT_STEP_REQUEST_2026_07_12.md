# Запрос Codex — следующий шаг (2026-07-12, от Cowork)

> **Audited/superseded 2026-07-13:** actual execution and verdict are recorded in
> `reports/RECOVERY_CHECKPOINT_2026_07_13.md` and
> `reports/PROJECT_CANONICAL_INDEX_2026_07_13.json`. Do not execute this request
> verbatim. In particular: pure-trail lost strict A/B; ARF2 unified-level replay
> already produced 15 trades at PF 0.588; FX M5 exists; strict pump successor is
> `NO_PROMOTION`; Alpaca/FX performance remain fail-closed.

Контекст: живой доход = только ATT1 tiny canary + Alpaca SAFE-HOLD. Все свежие кандидаты
NO_PROMOTION. Диагностика Cowork нашла КОРЕНЬ: research/live parity по УРОВНЯМ. Не строить новое —
закрыть parity и валидировать flat-семейство честно.

## 1. КРИПТА — закрыть level-parity, потом валидировать flat (ARF1/ARF2)  [приоритет]
Факт (Cowork, движок backtest/engine.py, 8 монет ~55д): ARF2 = 0 сделок; биндит `level_not_found`
(897) — движок не находит уровни, которые autoresearch находит. Значит ARF2 PF5.30/15tr из
autoresearch НЕ воспроизводим без сервиса уровней -> PASS недостоверен.
ЗАДАЧА:
- Вшить ЕДИНЫЙ Level Service (`bot/unified_levels.py`/`level_memory`) как обязательный источник
  уровней в research + backtest + live для ARF1/ARF2 (и остальных level-зависимых). Один и тот же
  level-набор (hash) на решение во всех режимах.
- После parity — строгий OOS ARF1/ARF2 (frequent, 66-88 tr в autoresearch): wf_folds + oos_selector
  + OOS-символы + per-period. Только PASS -> shadow risk=0.
- НЕ доверять autoresearch-PASS до level-parity. НЕ тюнить threshold.

## 2. ALPACA — перейти на regime-GATED adaptive + доказать parity  [деньги]
Факт (bakeoff 2022 bear): STATIC_TOP4 = PF 0.22, DD -35% (бычья стратегия, в медвежке течёт);
ADAPTIVE_V1_GATED = сохранил капитал (-6.5%, DD 2.2%) — сам уходит в кэш при плохом режиме.
Владелец хочет «мало просадок + зарабатывать в булле» = это и есть gated-adaptive.
ЗАДАЧА:
- Exact replay на ОДНОМ источнике с ЕДИНОЙ live/research exit-моделью: monthly top4 vs ошибочная
  daily rotation (neg control) vs ADAPTIVE_V1_GATED vs adaptive ungated. Восстановить ledger из broker fills.
- Привести live exit к research (BE 0.8R + ATR 1.5), убрать poll-trail +3.5%/3.5% mismatch.
- Снимать SAFE-HOLD ТОЛЬКО на месячной границе после доказанного parity. Кандидат для денег = gated-adaptive.
- Масштаб капитала/плечо — НЕ сейчас: сначала доказанный live-эдж на текущем размере.

## 3. FX/CFD — разблокировать ДАННЫМИ (нужны действия владельца, см. ниже)
FX V3 = DATA_DIAGNOSTICS_ONLY. Блокеры: нет реальных M5, нет hash-pinned historical news,
нет OANDA cost calibration. До этого performance/demo/live ЗАПРЕЩЕНЫ.
ЗАДАЧА Codex (после того как владелец даст данные): hash-pin M5+news+costs -> strict preflight ->
только PASS открывает performance runner.

## Запрещено без новых ворот
Повышать ATT1 risk/freq; включать 2-й money sleeve; снимать Alpaca SAFE-HOLD; плечо/докапитализация
без доказанного эджа; доверять autoresearch-PASS без level-parity; demo/live FX без strict preflight PASS.

## В конце сессии
Обновить ledger/canonical index: что pushed, что deployed на VPS, что restart, что live-changed,
local-only research, непройденные gates.

---

## ДОПОЛНЕНИЕ (2026-07-12): деплой + ТВОИ прогоны/загрузки
Codex, помимо деплоя — проделай СВОЮ работу (данные + прогоны), не только раскатку.

### Деплой (как обычно, targeted + backup + SHA)
- Подтвердить, что на VPS стоят runner-heartbeat + portfolio_health; флаги live не менять
  (RUNNER_EXCHANGE_TP_ENABLE=0, PORTFOLIO_HEALTH_AUTOCUT=0). ATT1 risk 0.10, не масштабировать.

### Прогоны (research, без денег)
1. **ATT1 + pure_trail — строгий OOS.** Cowork замер: +0.36R/сделку, +10.1R, win 67.9%, maxDD 3.3R,
   ~2 входа/монету/мес (кэш ~52д, 8 монет, малый N). Прогнать: exit=pure_trail (без фикс.TP, ATR-трейл
   1.5, be 1.0R) vs текущая лестница; wf_folds + oos_selector + OOS-символы + per-period + fee-stress 10/5.
   PASS -> сменить live-выход att1 на pure_trail. Метрики: expectancy_R, PF, MFE-capture, maxDD_R, красные мес.
2. **Level Service parity + ARF1/ARF2** (см. блок 1 выше). Чистый level-fade у Cowork = PF 0.54-0.55 ->
   быть готовым, что ARF-пульс окажется артефактом.
3. **Side-split** каждому основному рукаву: short-only / long-only отдельные ID и отдельные OOS.

### Загрузки данных (ты можешь, Cowork — нет)
4. **M5 FX (Dukascopy)** для EURUSD/GBPUSD/USDJPY/XAUUSD, 2-3 года -> hash-pin -> strict preflight.
   Издержки можно временно ОЦЕНОЧНЫЕ (типовой спред), OANDA-калибровка позже (владелец сделает demo).
5. **Сбор tape/тиков Bybit** для инплей-памп бэктеста (исходный edge бота тейповый, на свечах не тестится).
   Начать копить поток; это разблокирует проверку «ранних хороших памп-цифр».

### В конце — ledger/canonical index: pushed / VPS deployed / restarted / live-changed / local-only / gates.

## АУДИТ ГЕЙТА (Cowork, 2026-07-12) — к сведению
Анти-оверфит (wf_folds purge/embargo + oos_selector hero-rejection) и lookahead ядра engine.py
проверены = ГРАМОТНО/ЧИСТО. Действие: гнать строгий гейт на КАЖДОМ кандидате; не доверять
autoresearch/smoke PASS; новые раннеры — только на engine-store (completed-bars-only), не самодельный
курсор. Детали: reports/ANTIOVERFIT_AND_LOOKAHEAD_AUDIT_2026_07_12.md.

## БЛОК 6: PUMP_FADE_SIMPLE (raskopki подтвердили — исходный эдж зарезали фильтрами)
Baseline pump_fade PF 1.88 / DD 3.77% был ПРОСТОЙ 190-строчной стратегией (commit e341055e); live-версию
утопили фильтрами. Восстановлено: `strategies/pump_fade_simple.py`. Cowork-тест: 0 сделок на PEPE/DOGE
(нет +8%/час пампов -> нужен правильный юниверс свежих микрокапов).
ЗАДАЧА:
- Прогнать `pump_fade_simple` строгим гейтом (wf_folds+oos_selector) на baseline-периоде И на свежих
  волатильных микрокап-мемах. Spec готов: `configs/autoresearch/pump_fade_simple_meme.json` (486 combos).
- Построить динамический сканер «fresh volatile microcap» юниверса (не BTC/ETH/матёрые альты).
- PASS -> низкочастотный volatility-gated sleeve, shadow risk0. НЕ включать ENABLE_PUMP_FADE_TRADING без PASS.
Детали: reports/PUMP_FADE_ARCHAEOLOGY_2026_07_12.md. Цель-архитектура: reports/TARGET_INCOME_ARCHITECTURE_2026_07_12.md.

## БЛОК 7: breakdown + сканер микрокапов
- breakdown_retest_v3 (Cowork): PF 0.71 в не-bear окне, обе половины минус. Тестировать ТОЛЬКО на
  подтверждённом bear-периоде + regime_hmm-гейт. Не ближний кандидат.
- Реализовать сканер `build_pump_universe.py` (свежесть<120д + ATR%>=3% + ликвидность-бэнд +
  deny-list матёрых) -> runtime/pump_universe.json для pump_fade_simple. Спека:
  reports/BREAKDOWN_AUDIT_AND_MICROCAP_SCANNER_2026_07_12.md.
