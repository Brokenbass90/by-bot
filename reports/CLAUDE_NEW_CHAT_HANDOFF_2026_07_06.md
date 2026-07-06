# HANDOFF для НОВОГО ЧАТА CLAUDE — START HERE (2026-07-06)

Ты — антикризисный со-основатель, разработчик и трейдер этого проекта. Код+ledger в репо =
твоя память. Прочитай это, подтверди понимание и сразу работай.

## Прочитать по порядку
1. Этот файл. 2. reports/PROJECT_STATE_LEDGER.md (ХВОСТ — свежее). 3. reports/CODEX_HANDOFF_2026_07_05.md
(архитектурная картина). Доп. по задаче: MASTER_MAP_AND_PLAN, VISION_TO_EXECUTION_MAP,
SELF_IMPROVEMENT_AND_REGRESSION_DEFENSE, CAPITAL_ALLOCATION_PLAN, ROADMAP_TIMELINE (все в reports/).

## ГДЕ МЫ (правда на 2026-07-06)
- ВЕХА: ПЕРВАЯ live-сделка. ATT1 short r001 открыл ADAUSDT Sell (entry 0.189137, SL на бирже,
  runner-лестница), uPnL был +0.41. Телеметрия включена (decision_bus+edge_monitor, START_TS изолирует старое).
- Деньги: Bybit ~$1019, торгует ТОЛЬКО ATT1 r001 x0.10 (8 монет, bull_trend — short-only рукав
  редкий, это структурно). Alpaca $500 ждёт зачисления, SEND_ORDERS=0 до funded dry-run.
  IVB1 long r003 = shadow/risk 0.0 (time-folds PASS, symbol-OOS FAIL).
- Лучший кандидат #2: inplay_breakout_retest HTF (152-177 сделок! PF 1.33-1.48 на base-скрине) —
  СТРОГИЙ gate бежит (screen inplay_br_strict_20260706). PASS -> shadow. Это лучшая частота за всё время.
- Известный незадеплоенный фикс: runner qty-sync (bot/runner_state.py) — деплой ТОЛЬКО на flat
  или по отдельному плану с OK владельца.
- FX/CFD: капитал ЗАБЛОКИРОВАН данными (coverage 360d всего 13-47%) — сначала backfill, без исключений.
- Честные NO-GO (не трогать в старой форме): ARF2, ARS1/пила, raw BOS/CHoCH, XAU round_sweep,
  ATT1-long, ATT1-universe (11 монет, PF 1.08<1.15), midterm v2/v3 на свежем окне, HZBO long,
  IVB1 dynamic selector, FX фейды, каскады строгим триггером (0 входов за 18д — копить поток).

## КОНТРАКТ ПРОМОУШЕНА (нерушим, теперь формализован)
data/cache gate -> backtest -> stress costs -> time-OOS -> symbol-OOS/каузальный селектор ->
shadow risk=0.0 -> чистая телеметрия -> tiny canary (breaker+expiry) -> лестница риска через
smart_risk. Пороги пре-регистрируются ДО прогона. Selection bias = главный враг (ловили 5+ раз).

## РАЗДЕЛЕНИЕ ТРУДА
Claude: код+тесты+спеки+честные разборы+ledger. Codex: деплой/прогоны/сервер (VPS 1GB = только
live+коллекторы; research на Mac). Владелец: деньги, аппрувы live-изменений, докидывания по
правилам CAPITAL_ALLOCATION_PLAN. Live-деньги двигаются ТОЛЬКО с явного OK владельца — всё
остальное (код, research, ремонты, новые модули-инструменты) делай сам, не спрашивая.

## ДАННЫЕ-КОЗЫРИ (монополия, зреют)
liq-поток (сервер, недели), orderbook-плотности (с 04.07), funding/OI, decision_bus live-атрибуция
(с 04.07), ml_samples. ML-дорожка: мета-лейблинг после сотен размеченных сделок. Каждый live-день
кормит датасет.

## PENDING (проверь первым делом)
1. Вердикт inplay_br_strict_20260706 (разобрать ЧЕСТНО: stress/folds/leave-one-out).
2. Судьба ADA-позиции ATT1 (первая сделка = первая точка live-vs-backtest parity, разбор через bus).
3. Деплой qty-sync фикса при flat. 4. Alpaca funded dry-run -> включение. 5. FX backfill.
6. P1-инженерка: selector_status.json + web/TG поверхность (спек за Claude).
