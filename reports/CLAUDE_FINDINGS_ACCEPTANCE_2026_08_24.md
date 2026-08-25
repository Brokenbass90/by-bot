# Приёмка находок Клода — 24 августа 2026

Статус этого файла: проверка утверждений по каноническому дереву
`bybit-bot-recovery-20260824`. Это не разрешение менять риск или live-конфиг.

## Подтверждено

1. Живой ATT1-класс по умолчанию расходится с frozen research-кандидатом:
   `sl_atr_mult=1.10` против `6.60`, `max_stop_pct=0.06` против `0.25`,
   `be_trigger_rr=1.0` против `0`, `trail_atr_mult=1.5` против `0`,
   `time_stop_bars_5m=2016` против `4032`.
   Эти значения нельзя менять по одному и нельзя переносить в деньги до
   live-caller parity.
2. `REGIME_OVERLAY_*`, `ENABLE_FLAT_TRADING` и связанная машинерия в монолите
   существуют, но approved-конфиг выключает overlay, а денежный ATT1 caller
   вызывает wrapper без regime-side gate.
3. `VOLADJ_*` существует и масштабирует размер риска. Это не тот же контракт,
   что измеренный запрет входа. Кодовый default `VOLADJ_TF=240` означает четыре
   часа; утверждение о фактическом 24h-gate пока не подтверждено.
4. `bot/exposure_gate.py` существует, но в денежном ATT1 caller/монолите не
   подключён. Поэтому 12 slots остаются исследовательским кандидатом.
5. Для 12 slots записан рост результата в `4.53x`, но drawdown вырос
   `7.1R -> 8.7R` (`+22.5%`). Формулировка «просадка та же» ошибочна.
6. Экономия limit-entry около `0.001R` на сделку; при 41 сделке в месяц это
   около `0.041R`, то есть примерно 2% относительно заявленного `2.14R/мес`,
   а не самостоятельный большой рычаг доходности.

## Принятые поправки

- `trail_activate_rr=1.0` сам по себе не означает активный trailing.
  Но свежий server heartbeat показывает живой `trail_atr_mult=1.5`, поэтому
  trailing в текущем ATT1 действительно включён; frozen-кандидат требует
  `trail_atr_mult=0`. Реальное расхождение — вся связка параметров и caller
  contract, а не один activation threshold.
- Соответствие research `HOLD=336h` живому `time_stop_bars_5m=4032` остаётся
  гипотезой до ON/OFF replay; это не доказанный эквивалент.
- «265 нетронутых суток и ответ за час» завышает определённость. Зарезервированное
  окно `[2025-10-01, 2026-07-01)` содержит 273 календарных дня; XSEC уже сделал
  современный recount и был quarantined. Однократный replay остаётся быстрым
  ограниченным OOS-диагностическим тестом, но не prospective proof.
- ATT1 и SBR1 нельзя складывать в общий `N=50`: это разные sleeves, каждая
  проходит собственные gates и контроль.
- `research_lab/chastota.py` не измеряет immutable fixed-51: он берёт
  post-hoc лучшие 51 символов отдельно в каждом окне, проглатывает исключения
  и использует устаревшую money-восьмёрку с XRP вместо SUI. Цифры
  `1.4–4.6 месяца` не являются fixed-51 ETA и в canonical не принимаются.
- `research_lab/pechat_reviziya.py` не доказывает чистоту печати: вопреки
  docstring он читает `ts` из NPZ, жёстко задаёт конец `2026-08-11` и ищет
  только строки месяцев в JSON-результатах. Его вывод `314 суток` и dirty
  правку `read_sealed.py` не переносить; guard остаётся
  `[2025-10-01, 2026-07-01)` до отдельного metadata receipt.
- `research_lab/orderblock2.py` ещё не promotion-grade v2.1: десяти control
  draws недостаточно для заявленного tail gate, кандидат не требует PASS
  concentration/control-B coverage, ATR seed использует будущие первые 14
  баров, а data identity связывает только имя и размер. Старые order-block
  выводы остаются недействительными, но этот файл их пока не заменяет.
- `research_lab/nastroyki.py` полезен как черновик диагностического паспорта,
  но не как `--strict` gate: он читает class defaults, не effective live
  config, не считает `НЕ НАЙДЕНО` ошибкой и проверяет не тот trailing switch.
  Переносить только после тестов и manifest-driven ремонта.

## Обязательный порядок до денежных изменений

1. Persisted causal BTC closed-H1 EMA200 bootstrap и receipt.
2. Actual production caller receipts для ATT1 и SBR1.
3. ON/OFF replay для regime gate и каждого спорного параметра на одном
   live-native контракте.
4. Manifest-driven `verify_live_config` без glob-first-25 и без swallowed
   exceptions.
5. `exposure_gate` replay до любого расширения slots.
6. Только затем один заранее объявленный reserved-window replay; после него —
   prospective shadow, clean lifecycle и отдельное решение о tiny canary.
