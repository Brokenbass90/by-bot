# Codex queue — переприоритет (2026-06-30, день/вечер)

Контекст: ночной WF-батч из CODEX_QUEUE_2026_06_29_PM ЕЩЁ НЕ ВЕРНУЛСЯ (нет артефактов
30-06). Плюс открылась проблема: carry dry-run на 125 циклах НЕТТО ОТРИЦАТЕЛЕН.
Подробности: reports/WF_AND_LIVE_HONEST_READ_2026_06_30_PM.md.

## P0 — carry: НЕ live, диагностировать и ре-гейтнуть
Факт: `runtime/live_mirror/arb_roi_estimate.json` (settlement_execution_v2, 125 closed):
WR 35.2%, mean −0.021%/цикл, p25 −0.19%, проекция −5.7%/мес. Хедлайн APR не выживает.
- Ре-гейт входа по NET-ЗА-ЦИКЛ: (купон за hold) − (round-trip costs обеих ног) − buffer > 0,
  а НЕ по spread_apr.
- Жёсткий delta-neutral (`bot/carry_neutral.py`) + проверка фактического баланса обеих
  ног до плана (dry-run сейчас ловит insufficient_balance на short-leg → недохедж).
- Пересчитать `arb_roi_estimate` на тех же 125 циклах после ре-гейта. Вернуть: net-за-цикл
  ДО/ПОСЛЕ. Если остаётся ≤0 — carry в архив гипотез, не в live.

## P0 — выдать обещанный WF-батч (всё ещё нет результатов)
По CODEX_QUEUE_2026_06_29_PM обновлению: вернуть цифры в первую очередь по:
- pair-arb cointegration (`walkforward_pair_arb`/`validate_pair_arb`) на ETH/BTC, SOL/ETH,
  ARB/OP и пр. — OOS-плато, не пик.
- InPlay V4 (вход 1m/лимит у уровня, свежесть, tp2.5/sl1).
- ASB2/ACB1 (вкл. adaptive) 240d, next-open, честные издержки.
Формат: OOS по ≥3/4 окон + число сделок + красные месяцы. PF-выбросы (оверфит) — мимо.

## P0 — Alpaca $500 live (к открытию рынка)
Без изменений: dry-run `ALPACA_SEND_ORDERS=0` → пики/стопы/cap≤$500 → OWNER OK → SEND_ORDERS=1.
v38: PF 6.47, 9/11 зелёных, maxDD −3.86%. Это первый реальный плюс — приоритет.

## P1 — форекс honest pass
- lookahead-чек ВСЕХ ~20 стратегий (слайс candles[:i+1]); проверить `london_open_breakout`
  SMA[i] (жёлтый флаг из FOREX_AUDIT).
- добавить slippage в `forex/engine.py` (сейчас только разовый спред).
- честный WF range/bounce/mean-reversion с асимметр. R:R (tp∈{2,2.5,3}R, sl~1R), отбор по OOS.

## P1 — закоммитить набор Claude
adaptive_context, market_context апгрейды, render v2, ASB2/ACB1 adaptive, ARF2 fix,
strategy_breaker/volume_exit/carry_neutral + тесты, inplay_retest_v4, market_survey,
WF_AND_LIVE_HONEST_READ_2026_06_30_PM, этот queue.

## Вернуть в первую очередь
1) net-за-цикл carry ДО/ПОСЛЕ ре-гейта; 2) WF pair-arb; 3) Alpaca dry-run лог.

## ДОБАВЛЕНО 2026-06-30 (день, Claude, локально — без сервера)
- FOREX lookahead-чек ВСЕХ 18 стратегий: чисто, lookahead НЕ найден; london_breakout жёлтый флаг СНЯТ. См. reports/FOREX_LOOKAHEAD_FULL_AUDIT_2026_06_30.md. Остаётся Codex: slippage в forex/engine.py + WF.
- CARRY re-gate SPEC готов (привязан к коду): reports/CARRY_REGATE_SPEC_2026_06_30.md. Корень минуса = гейт кредитует полный APR на hold (фандинг затухает). Фикс: capture-haircut + эмпирич. deploy-гейт по arb_roi_estimate + full-funded both legs + delta-neutral. Внедрить — Codex.

## ДОБАВЛЕНО 2026-06-30 (range_filter wiring)
- НОВОЕ P1: подключить bot/range_filter.py ко всем bounce/fade ногам (крипто+форекс) по reports/RANGE_FILTER_WIRING_2026_06_30.md, убрать самодельные range-гейты, закоммитить модуль+тест, затем WF с асимметр R:R и require_all как параметром.

## ДОБАВЛЕНО 2026-06-30 (pump_exhaustion wiring)
- НОВОЕ P1: подключить bot/pump_exhaustion.py к pump_fade_simple/pump_fade_v2/pump_fade_v4r/pump_fade_smart_v1 и spike_fade — фейд только при short_ok/long_ok (подтверждённый разворот). Убрать старый вход-без-подтверждения. Закоммитить модуль+тест. Затем WF с асимметр R:R, отбор по OOS.

## ДОБАВЛЕНО 2026-06-30 (retest_quality wiring)
- НОВОЕ P1: подключить bot/retest_quality.py как общий грейдер ретеста к level-ногам (IRV4, support_bounce, channel_bounce, breakout-retest, forex retests). entry_ok/quality как гейт, long_ok/short_ok для сплита. Закоммитить модуль+тест. Затем WF.

## ДОБАВЛЕНО 2026-06-30 (elder_filter wiring)
- НОВОЕ P1: подключить bot/elder_filter.py как конфлюэнс-гейт ко всем рукавам (крипта+форекс). Рукав AND-ит свой сигнал с allow_long/allow_short. Закоммитить модуль+тест. В свипе require_with_tide как параметр (с тайдом vs не против тайда), отбор по OOS.

## ДОБАВЛЕНО 2026-06-30 (breakout + ночной деплой)
- НОВОЕ P1: подключить bot/breakout_confirm.py к пробойным ногам (confirmed long_ok/short_ok; ретест через retest_quality). Полный тёрнкей-план ночи: reports/DEPLOY_OVERNIGHT_2026_06_30.md (коммит 5 модулей -> wiring -> WF OOS асимметр R:R -> carry re-gate -> pair-arb WF -> Alpaca dry-run).
