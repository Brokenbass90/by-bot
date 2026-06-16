# PROJECT MAP — Bybit/Alpaca trading bot (полная карта)

*Онбординг для человека и любого ИИ. Визуал: `reports/PROJECT_MAP.svg`. Машиночитаемая карта кода: `reports/AI_CODEMAP.json` (через `bot.ai_tools.get_codemap`). START HERE для новой сессии: `CLAUDE_HANDOFF_NEXT_SESSION_2026_06_15.md`.*

## Что это
Многорукавная торговая станция. Цель — устойчивый процесс с доказанным эджем, не «быстрое богатство». Человек в контуре на всех решениях о деньгах/коде. Деньги — только за доказанным OOS-эджем.

## Слои (поток сверху вниз)
1. **ДАННЫЕ:** Bybit WS feed (перпы, ликвидации) · Alpaca data (акции) · `data_cache` (история OHLC) · cross-exchange funding/basis (read-only).
2. **ПОДБОР МОНЕТ:** `scripts/build_symbol_router`/`dynamic_universe` → `scripts/strategy_scorer` (фитнес монеты 0-1 под стратегию) → `bot/cross_sectional` (ранг, не порог) → per-strategy allowlists (`bot/allowlist_watcher`).
3. **СТРАТЕГИИ (по логике):**
   - крипто-ядро: флэт-лонг `ASB1` (alt_support_bounce) ↔ флэт-шорт `ARF1` (alt_resistance_fade) · тренд `ATT1`/`IVB1`/breakout · bear-шорт `breakdown` · `midterm` BTC/ETH.
   - Alpaca: `strategies/alpaca_adaptive_v1` (SPY-гейт, стабилизатор) · intraday (shadow, research).
   - market-neutral: funding-carry (механический edge-кандидат; simple Bybit spot hedgeable basket пока NO-GO: ~1.8%/год после costs; picker `bot/funding_carry_picker` + gate `backtest/funding_carry_gate`) / pair-arb (shadow).
   - liquidation-sweep: research-движок `backtest/liquidation_sweep_research` (2-й некоррелированный edge — отскок после каскадов ликвидаций; фальсифицируется на истории Bybit).
   - forex/CFD — будущий рукав (заготовки).
4. **КОНТРОЛЬ (control-plane):** `bot/regime_orchestrator` (bull/bear × trend/chop) → portfolio_allocator (slot-caps, risk-mults) → risk rails (дневной −2% / общий −5%, в `portfolio_can_open`).
5. **ИСПОЛНЕНИЕ:** `bot/maker_entry` (post-only, экономит комиссии) → broker SL/TP (`set_tp_sl_retry` + failsafe-закрытие) → ladder exit (`bot/ladder_exit`: TP1 частичный → breakeven → runner до дальней цели + трейлинг + time-stop).
6. **ОФЛАЙН-ВАЛИДАЦИЯ (анти-overfit):** `scripts/strategy_coin_picks` → `backtest/crypto_multiwindow_wf` / `auto_pick_wf` (WF по окнам) → `bot/param_profiles` (тиры монет) → `backtest/stack_comparison` (обвязка vs голо) → `backtest/promotion_gate` (объективный GO/NO-GO) → малый canary.
7. **ИИ / НАБЛЮДАЕМОСТЬ:** `bot/ai_tools` (catalog·code_access·codemap·snapshot·pulse) · `bot/deepseek_*` autoresearch (propose → одобрение человеком → execute) · `web/static/operator_console.html` + `scripts/proof_of_life` + Telegram.

## Человеческие названия стратегий
В общении с человеком и в отчётах сначала используем трейдерское имя, код — в скобках:

- **Пробой уровня с ретестом** (`inplay_breakout`) — цена выбила уровень, вернулась проверить его и должна продолжить движение.
- **Импульсный пробой с откатом** (`IVB1`) — сильная свеча на объёме, затем неглубокий откат/ретест и вход по продолжению.
- **Пила от границ флэта** (`range_scalp`, `ARS1`) — покупка у нижней границы диапазона и шорт у верхней.
- **Отбой от поддержки** (`ASB1`, `support_bounce`) — лонг от сильной горизонтальной поддержки.
- **Шорт от сопротивления** (`ARF1`, `flat_resistance_fade`) — продажа от верхней границы флэта/сопротивления.
- **Отбой от наклонки** (`ATT1`) — вход от трендовой линии после касания.
- **Пробой наклонки** (`trendline_breakout`, `ASB1-breakout`) — вход, когда цена ломает наклонное сопротивление/поддержку.
- **Слом поддержки** (`breakdown`) — шорт после потери уровня и слабого ретеста снизу.
- **Шорт пампа** (`pump_fade`) — продажа перегретого вертикального движения после признаков выдоха.
- **Снос ликвидности / стоп-хант** (`liquidation_sweep`) — реакция после выноса стопов или каскада ликвидаций.
- **Тройной экран Элдера** (`elder`) — старший тренд, средний откат, младший триггер.
- **Кэрри на фондинге** (`funding_carry`) — сбор funding через хеджированную perp/spot позицию.

## Гейт промоушена в live (нерушимо)
кандидат → авто-подбор монет → multi-window WF (ladder+комиссии) → тир-профили → двойной тест → `promotion_gate` (≥3/4 окна + PF>1 после комиссий + expectancy≥0 + ≥30 сделок + обвязка не душит) → крошечный canary на $100.

## Текущее состояние (2026-06-15)
Бот жив/защищён; live-риск только `flat/ARF1=0.3`, `IVB1=0.25`; ядро в shadow; **0 доказанных карманов** (фильтр работает). Капитал: ~$100 крипта live / $0 Alpaca real ($500 paper) / $2500 резерв. Тесты 297 зелёных.

## Рукава (роли)
- Крипта (Bybit perps) — работяга/доход (ядро на горизонтальных уровнях + тренд).
- Alpaca — стабилизатор/инвест-канал для заработанного (не двигатель).
- market-neutral (funding/arb) — сглаживание просадки, 3-й некоррелированный источник.
- forex/CFD — будущая лошадка.

## Безопасность
`.env` не в git (mode 600); секреты никогда не выгружаются (allowlist+redaction в snapshot/code_access); read-only зрение ИИ по коду; действия с деньгами/кодом — только через одобрение человека (`deepseek_action_executor`).

<!-- AUTO_SNAPSHOT_START -->
## Авто-снимок
- generated_utc: `2026-06-16T08:31:50Z`
- git_head: `4abf8f9`
- tests: `61` test files
- strategies: `86` strategy modules
- backtest modules: `27`
- onboard AI project-map tool: `yes`
- liquidation collector: `yes`
- funding carry 180d hedgeable gate: `NO-GO, net=$7.22, annual=1.8%`
- latest progress note: `CODEX_MORNING_PROGRESS_2026_06_16.md`
<!-- AUTO_SNAPSHOT_END -->

## Ключевые документы
- `CLAUDE_HANDOFF_NEXT_SESSION_2026_06_15.md` — START HERE.
- `CODEX_HANDOFF_2026_06_15.md` (§1-20) — детальный журнал.
- `reports/FOUNDATION_UPGRADES_AND_LAUNCH_2026_06_15.md`, `HIGH_IMPACT_IDEAS_2026_06_15.md`, `CLAUDE_TO_CODEX_2026_06_15_entry_rework.md` — что делать дальше.
- `reports/SERVER_SNAPSHOT_latest.md` — реальное live-состояние.

## Координация ИИ
Claude = аддитивные инструменты `backtest/`, анализ, доки. Codex = монолит `smart_pump_reversal_bot.py` / `scripts` / веб / деплой / серверные прогоны. Связь — `reports/*_TO_*`.
