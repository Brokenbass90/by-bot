# Claude handoff → следующий чат (2026-06-15)

*START HERE для новой сессии. Кратко: где мы, что построено, что дальше. Тон: честно, без обещаний доходности, человек в контуре на деньгах/коде.*

## Прочитать первым делом в новой сессии
1. `reports/SERVER_SNAPSHOT_latest.md` — реальное live-состояние (heartbeat, P&L по рукавам, конфиг).
2. `reports/AUTO_PICK_WF_latest.json` (+ `..._param_profiles_latest.json`) — последний WF-вердикт.
3. `reports/CODEX_TO_CLAUDE_*` и `CODEX_PARAM_PROFILES_AND_LIVE_STATE_2026_06_15.md` — что сделал Codex.
4. Этот файл + `CODEX_HANDOFF_2026_06_15.md` (§1-20) + `reports/FOUNDATION_UPGRADES_AND_LAUNCH_2026_06_15.md`.

## Текущая честная картина (на 2026-06-15)
- Бот **жив и защищён**: feed OK (bybit_msgs >3.8M), regime bull_trend, open_trades=0, dry_run=false. Live-риск только `flat/ARF1=0.3` и `IVB1=0.25`; ядро (ATT1, ASB1/bounce1, BREAKDOWN, MIDTERM) в shadow (risk_mult=0); HZBO1/ELDER off.
- Капитал: крипта ~$100 live; Alpaca $0 real ($500 paper, держит AMD/GE/LLY/SNOW, стопы ок); **$2500 в резерве**.
- **Доказанного эджа пока НЕТ.** Серверный WF (авто-подбор монет + тир-профили + комиссии, top-8, 60/240, 4 окна) → **0 кандидатов прошли гейт** (лучшее 1/3, 1/4 окна = weak). Это фильтр от слива работает, не тупик.
- Фундамент (исполнение/безопасность): P0 исправлен, брокерские стопы, риск-рейлы, идемпотентность — здоров.

## Что построено за сессию (всё аддитивно, интегрировано Codex; ядро монолита не трогалось)
- Осознанность ИИ: `bot/strategy_catalog.py`, `bot/code_access.py` (read-only код, secret-safe), `bot/ai_tools.py` (единый toolbox), `scripts/build_ai_codemap.py`. Влияние — через существующий `bot/deepseek_action_executor` (одобрение человеком).
- Альпака: `strategies/alpaca_adaptive_v1.py` (SPY-гейт; bear-2022 DD 2.23% vs −15..−32% — чемпион-стабилизатор, но PF<1 = не доход), `backtest/alpaca_bakeoff_wf.py`, `alpaca_scenarios.py`, `alpaca_param_robustness.py`, `portfolio_projection.py`.
- Крипто-валидация (полная цепочка): `scripts/strategy_coin_picks.py` (авто-подбор монет) → `backtest/crypto_multiwindow_wf.py` (анти-overfit гейт) → `backtest/auto_pick_wf.py --use-param-profiles` (мульти-стратегия) → `bot/param_profiles.py` (param-сеты по тирам монет) → `backtest/stack_comparison.py` (двойной тест: обвязка vs голо) → гейт. + `ladder_exit.py`, `crypto_efficiency_*.py`.
- Наблюдаемость/веб: `scripts/export_server_snapshot.py` (secret-redacted), `scripts/proof_of_life.py` (+`--tg` в cron), `web/static/operator_console.html` (P&L по периодам + менеджер API-ключей + просмотрщик стратегий).
- Тесты: ~255 passed. Гигиена: `pytest.ini` (testpaths=tests — убрал обход 48k backtest-папок), `conftest.py`, `requirements-dev.txt`.

## Гейт перед live (нерушимый)
Кандидат → авто-подбор монет → multi-window WF (ladder+комиссии) → тир-профили → двойной тест (обвязка не душит) → **≥3/4 окна положительные + PF>1 после комиссий + maker-входы** → крошечный live risk на $100 = проба жизни. Не прошёл → не крутим риск.

## Что дальше (серверная работа Codex)
1. **Расширить data coverage** под авто-пики (1h/4h ASB1/ARF1, 5m/1h BREAKDOWN) → перегон auto_pick_wf.
2. **Лечить «тонкие окна»**: вход слишком строгий (RSI режет ~90% лонгов) → параметр-плато, не пик.
3. **Slot-caps** (per-sleeve) — проверять `stack_comparison` на реальном журнале (обвязка не должна душить).
4. **Валидировать backlog по одному:** ATT1 v2 (всепогодная) → funding-carry/basis-arb (market-neutral) → pair_stat_arb → RMR1/TPB1/smart_grid.

## Очередь новых стратегий в портфель (по приоритету)
ATT1 v2 → funding-carry/basis-arb (3-й некоррелированный рукав) → pair_stat_arb → RMR1/TPB1/smart_grid. Каждая: default-OFF/shadow → гейт → canary. Никогда пачкой. Идеи копит daily `scripts/market_scanner_ai.py`.

## Многорукавная станция (видение)
Крипто-ядро (работяга/доход) + Alpaca (стабилизатор/инвестканал для заработанного) + market-neutral/arb (сглаживание просадки) + форекс/CFD (будущая лошадка). Деньги — только за доказанным эджем; $2500 поэтапно по мере прохождения гейтов.

## Координация
Claude = аддитивные инструменты в `backtest/`, анализ, тюнинг-рекомендации, доки. Codex = монолит/`scripts`/веб/деплой/серверные прогоны. Связь — через `reports/*_TO_*` файлы. Секреты не выгружаются никогда (allowlist+redaction).

## Деньги/тон (для следующей сессии)
Не давать датированных обещаний доходности (это была прошлая ошибка). Цель — доказать положительное ожидание на честном OOS, не «запустить ради ощущения». Бот уже «запущен» (жив/защищён); настоящий запуск = первый карман через гейт.
