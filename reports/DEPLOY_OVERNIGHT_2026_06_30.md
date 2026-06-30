# DEPLOY + НОЧНОЙ ПРОГОН — тёрнкей для Codex (2026-06-30)

Claude собрал 5 технологичных слоёв-помощников под тестами (фундамент 106 зелёных).
Все со сплитом short-only/long-only, годны для крипты И форекса/CFD, учитывают уровни
наклонные И горизонтальные. Сервер/деньги — на Codex/владельце. Ниже — по порядку.

## 1. ЗАКОММИТИТЬ (новый код + тесты, всё зелёное)
bot/range_filter.py        + tests/test_range_filter.py        (7)
bot/pump_exhaustion.py     + tests/test_pump_exhaustion.py     (6)
bot/retest_quality.py      + tests/test_retest_quality.py      (9)
bot/elder_filter.py        + tests/test_elder_filter.py        (7)
bot/breakout_confirm.py    + tests/test_breakout_confirm.py    (6)
Прогон: `pytest tests/test_range_filter.py tests/test_pump_exhaustion.py \
  tests/test_retest_quality.py tests/test_elder_filter.py tests/test_breakout_confirm.py`
(внимание: общий `pytest tests/` падает на сборке из-за scripts/alpaca_v3_event_backtest.py,
который делает sys.exit(2) при импорте — ПРЕДСУЩЕСТВУЮЩИЙ баг, не наш; стоит починить отдельно).

## 2. ПОДКЛЮЧИТЬ помощников к ногам (единый источник, убрать самоделки)
- range_filter -> bounce/fade: ARF1/ARF2, ASB2, ACB1, range_mean_reversion, range_scalp,
  range_reclaim; форекс: range_bounce, grid_reversion, asia_range, adaptive_grid, bb_v1/v2/v2p.
  Нога SHORT-only торгует только при `short_ok`, LONG-only — при `long_ok`.
- pump_exhaustion -> pump_fade_simple/v2/v4r/smart, spike_fade. Фейд только при short_ok/long_ok
  (подтверждённый разворот; растущий пап НЕ фейдим).
- retest_quality -> inplay_retest_v4, support_bounce, channel_bounce, breakout-retest, forex retests.
  Гейт по entry_ok/quality; сторона по long_ok/short_ok.
- breakout_confirm -> пробойные ноги (горизонт+наклон). Вход только при confirmed long_ok/short_ok;
  ретест после пробоя — через retest_quality (broken-level flip).
- elder_filter -> ОБЕРНУТЬ все рукава: AND своего сигнала с allow_long/allow_short (конфлюэнс).

Детали wiring: reports/RANGE_FILTER_WIRING_2026_06_30.md (+ аналогично для остальных слоёв,
паттерн один: получить state -> торговать только по своей стороне -> иначе no_signal с reason).

## 3. ЧЕСТНЫЙ WF (ночь) — приоритет OOS, асимметр. R:R
Свипы с tp_rr ∈ {2,2.5,3}, sl~1R; параметры-переключатели: require_all (range),
require_with_tide (elder), enable setup-B (breakout). Отбор по OOS-ПЛАТО (≥3/4 окна),
НЕ по PF-пику. Дом приоритета — ФОРЕКС (ranges чище), затем крипто-альты.
Вернуть по каждой ноге: trades/окно, OOS net-of-fee PF, красные месяцы, fee-sensitivity.

## 4. МЕХАНИКА (деньги без угадывания) — параллельно
- CARRY: НЕ live. Внедрить ре-гейт по reports/CARRY_REGATE_SPEC_2026_06_30.md
  (capture-haircut + эмпирич. deploy-гейт + full-funded both legs). Вернуть net-за-цикл ДО/ПОСЛЕ.
- PAIR-ARB: WF на ДЛИННОЙ истории (walkforward_pair_arb) по корзине ликвидных пар, OOS.
  Локальный санити (мало данных) эджа не дал — нужен полный кэш сервера.

## 5. ALPACA — первый реальный плюс (владелец + Codex)
$500 dry-run (`ALPACA_SEND_ORDERS=0`) -> проверить пики/стопы/cap -> OWNER OK -> live.
v38: PF 6.47, 9/11 зелёных, maxDD -3.86%.

## 6. ВЕРНУТЬ УТРОМ (что разбирать Claude)
1) WF-цифры по форекс range + крипто bounce/fade/breakout (OOS);
2) net-за-цикл carry ДО/ПОСЛЕ ре-гейта; 3) pair-arb WF; 4) Alpaca dry-run лог.
Claude интерпретирует честно по OOS: что прошло плато -> крошечный canary; что нет ->
гипотеза-фикс -> обратно в свип.

## Принципы (неизменны)
OOS-first; асимметр. R:R; механика > угадывание; ИИ = аналитик в рельсах; не хороним —
архив; короткие/длинные рукава раздельно; уровни наклон+горизонт учтены в помощниках.
