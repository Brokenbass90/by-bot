# Deploy manifest — работа Claude за сессию 2026-06-15

*Всё аддитивно. Ядро `smart_pump_reversal_bot.py` НЕ трогалось. Для деплоя «разом».*
*Часть уже подобрана Codex'ом (коммиты 0aa37b9 / 32f4f06 / be935e3) — помечено [интегрировано].*

## Новые модули (код)
- `bot/strategy_catalog.py` [интегрировано] — каталог стратегий (конфиг + TP/SL-модель) для ИИ.
- `bot/code_access.py` — безопасное read-only чтение кода для ИИ (отказ на `.env`/escape/секреты).
- `bot/ai_tools.py` — единый AI-toolbox (все «органы чувств» + единственный gated write-канал).
- `strategies/alpaca_adaptive_v1.py` [интегрировано] — гейтнутая Alpaca (чемпион-стабилизатор: bear-2022 DD 2.23%).
- `backtest/ladder_exit.py` — каноничный runner-выход TP1→BE→TP2 (для честного fee-WF).
- `backtest/alpaca_adaptive_backtest.py` [интегрировано], `alpaca_scenarios.py`, `alpaca_param_robustness.py`,
  `portfolio_projection.py`, `crypto_efficiency_backtest.py` [интегрировано], `crypto_efficiency_wf.py` — аналитика.
- `scripts/export_server_snapshot.py` [интегрировано], `proof_of_life.py` (+`--tg`), `build_ai_codemap.py`.
- `web/static/operator_console.html` — P&L по периодам + менеджер API-подключений + просмотрщик стратегий + пульс.

## Тесты (все зелёные, ~242 passed локально)
`test_strategy_catalog`, `test_alpaca_adaptive_v1`, `test_ladder_exit`, `test_code_access`,
`test_ai_tools`, `test_crypto_efficiency_backtest`, `test_export_server_snapshot`.
Гигиена: `pytest.ini` [интегрировано], `conftest.py` [интегрировано], `requirements-dev.txt` [интегрировано].

## Доки/отчёты
`AUDIT_INTAKE_2026_06_14.md`, `CODEX_HANDOFF_2026_06_15.md` (§1-20), `reports/AI_CODEMAP.md`,
`reports/MONEY_MANAGEMENT_PLAN_2026_06_15.md`, `reports/CLAUDE_TO_CODEX_*`, этот манифест.

## Что Codex подключает при деплое (чтобы «разом»)
1. `pip install -r requirements-dev.txt` → `pytest` (ждём ~242 passed, 1 skipped).
2. **Осознанность ИИ:** подключить `bot/ai_tools.py` (read-инструменты) + `reports/AI_CODEMAP.md` в промпт бортового ИИ (TG+веб). Write — только через `deepseek_action_executor` (одобрение человеком).
3. **Наблюдаемость по cron:** `build_ai_codemap.py` (при изменениях кода), `export_server_snapshot.py` (регулярно), `proof_of_life.py --tg` (в Telegram).
4. **Веб:** реализовать API-контракт из шапки `operator_console.html` и встроить страницу.
5. **Доходность (на правде):** серверный fee/slippage WF по ASB1/ATT1 v2 через `backtest/ladder_exit.py`; Alpaca bake-off с 2022; **запустить Alpaca paper**; maker-входы для ASB1; per-sleeve risk caps.

## Go-критерии перед реальными деньгами (напоминание)
paper ≥4-8 нед И ≥20-30 сделок; OOS PF>1 с комиссиями; maxDD <~10%; live≈backtest; ноль сбоев защиты.
Капитал заводить малыми траншами по мере прохождения критериев каждым рукавом. $2500 — пока в резерве.

## Следующая сессия Claude начинается с
чтения `reports/SERVER_SNAPSHOT_latest.md` (свежий) → выбор live-кандидата на правде → продолжение по доходности и вебу.
