# PROJECT MAP — Bybit/Alpaca trading bot (полная карта)

*Онбординг для человека и любого ИИ. Визуал: `reports/PROJECT_MAP.svg`. Машиночитаемая карта кода: `reports/AI_CODEMAP.json` (через `bot.ai_tools.get_codemap`).*

**START HERE (2026-06-30):** `CODEX_HANDOFF_2026_06_29.md` →
`reports/ROADMAP_WHERE_WE_ARE_2026_06_30.md` →
`reports/STATE_AND_MIGRATION_2026_06_28.md` →
`reports/OWNER_STRATEGY_SPEC_2026_06_25.md` (ручной эдж владельца).

**Текущая истина (2026-06-30):**
- Crypto live уже разморожен точечно: ATT1 short-only canary `risk=0.10`,
  остальные price-рукава `risk=0.0`. Нет сделок не из-за freeze, а потому что
  одна редкая наклонка ждёт валидный short setup.
- НЕ добавлять второй crypto sleeve без OOS: ARF2, ASB2, ACB1 и InPlay 240d
  не прошли live-гейт 30 июня.
- Ближайший crypto-диверсификатор: SpikeFadeV3 LINK short после свежего
  bounded OOS/replay.
- Ближайшие реальные деньги: Alpaca v38 `$500` canary после live-account dry-run;
  carry/funding — только market-neutral после execution/balance validation.
- FX/XAU research идёт отдельным бесплатным data-track; OANDA нужен только для
  исполнения позже, не для бэктеста.

## Что это
Многорукавная торговая станция. Цель — устойчивый процесс с доказанным эджем, не «быстрое богатство». Человек в контуре на всех решениях о деньгах/коде. Деньги — только за доказанным OOS-эджем.

## Слои (поток сверху вниз)
1. **ДАННЫЕ:** Bybit WS feed (перпы) · отдельный public liquidation collector (`scripts/collect_bybit_liquidations.py` → `runtime/liquidations/bybit_liquidations.jsonl`) · Alpaca data (акции) · `data_cache` (история OHLC) · cross-exchange funding/basis (read-only). Liquidation research обязан кластеризовать и join-ить события строго per-symbol.
2. **ПОДБОР МОНЕТ:** `scripts/build_symbol_router`/`dynamic_universe` → `scripts/strategy_scorer` (фитнес монеты 0-1 под стратегию) → `bot/cross_sectional` (ранг, не порог) → per-strategy allowlists (`bot/allowlist_watcher`).
3. **СТРАТЕГИИ (по логике):**
   - крипто-ядро: флэт-лонг `ASB1` (alt_support_bounce) ↔ флэт-шорт `ARF1` (alt_resistance_fade) · тренд `ATT1`/`IVB1`/breakout · bear-шорт `breakdown` · `midterm` BTC/ETH.
   - Alpaca: `strategies/alpaca_adaptive_v1` (SPY-гейт, стабилизатор) · intraday (shadow, research).
   - market-neutral: funding-carry (механический edge-кандидат; simple Bybit spot hedgeable basket пока NO-GO: ~1.8%/год после costs; picker `bot/funding_carry_picker` + gate `backtest/funding_carry_gate`) / pair-arb (shadow).
   - liquidation-sweep: research-движок `backtest/liquidation_sweep_research` (2-й некоррелированный edge — отскок после каскадов ликвидаций; фальсифицируется на истории Bybit).
   - forex/CFD — будущий рукав (заготовки).
4. **КОНТРОЛЬ (control-plane):** `bot/regime_orchestrator` (bull/bear × trend/chop) → portfolio_allocator (slot-caps, risk-mults) → risk rails (дневной −2% / общий −5%, в `portfolio_can_open`).
5. **ИСПОЛНЕНИЕ:** `bot/maker_entry` (post-only, экономит комиссии) → broker SL/TP (`set_tp_sl_retry` + failsafe-закрытие) → ladder exit (`bot/ladder_exit`: TP1 частичный → breakeven → runner до дальней цели + трейлинг + time-stop).
6. **ОФЛАЙН-ВАЛИДАЦИЯ (анти-overfit):** `scripts/strategy_coin_picks` → `backtest/crypto_multiwindow_wf` / `auto_pick_wf` (WF по окнам) → `bot/param_profiles` (тиры монет) → `backtest/stack_comparison` (обвязка vs голо) → `backtest/promotion_gate` + `scripts/evaluate_crypto_promotion.py` (next-open + cost floors + monthly stability + WF + portfolio compare) → shadow → малый canary.
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
кандидат → авто-подбор монет → 360d next-open с fee≥6 bps/side и slippage≥2 bps/side → monthly stability (≥10 месяцев, ≤3 красных, streak≤2) → multi-window WF → strategy-only/full-stack compare → `evaluate_crypto_promotion.py` → shadow → крошечный canary на $100.

## Текущее состояние (2026-06-30)

Серверный `bybot.service` активен: `trade_on=true`, `dry_run=false`,
`open_trades=0`, режим `bear_chop`, `ws_guard_active=0`.
Операторский override загружен:
`configs/att1_short_canary_20260629.env`.
Живой риск сейчас только у **ATT1 short-only**: `risk_mult.att1=0.10`.
`flat/range/breakdown/ivb1/midterm/bounce1=0.0`.

ATT1 не заблокирован: breaker `enabled=true`, `blocked=false`,
`expired=false`. Нет сделок, потому что стратегия не нашла валидную наклонку;
это ожидаемо для редкого canary.

Доказательная истина:
- ATT1 short-only остаётся единственным crypto live canary.
- ARF2 OOS 30 июня не дал частого/устойчивого live-кандидата.
- ASB2/ACB1 240d отрицательны; ACB1+HVN — research baseline, не live.
- InPlay + volume_exit текущей версии ухудшил результат; `volume_exit` off.
- SpikeFadeV3 LINK short — лучший следующий crypto candidate, но нужен свежий
  OOS/replay.
- Alpaca v38 — первый реальный non-crypto canary candidate на `$500`, после
  live-account dry-run без ордеров.

## Рукава (роли)
- Крипта (Bybit perps) — работяга/доход (ядро на горизонтальных уровнях + тренд).
- Alpaca — стабилизатор/инвест-канал для заработанного (не двигатель).
- market-neutral (funding/arb) — сглаживание просадки, 3-й некоррелированный источник.
- forex/CFD — будущая лошадка.

## Безопасность
`.env` не в git (mode 600); секреты никогда не выгружаются (allowlist+redaction в snapshot/code_access); read-only зрение ИИ по коду; действия с деньгами/кодом — только через одобрение человека (`deepseek_action_executor`).

<!-- AUTO_SNAPSHOT_START -->
## Авто-снимок
- generated_utc: `2026-06-19T14:55:00Z`
- git_head: `4aba49f`
- tests: `87` test files
- strategies: `88` strategy modules
- backtest modules: `29`
- onboard AI project-map tool: `yes`
- liquidation collector: `yes`
- funding carry 180d hedgeable gate: `NO-GO, net=$7.22, annual=1.8%`
- latest progress note: `CODEX_HANDOFF_2026_06_19.md`
<!-- AUTO_SNAPSHOT_END -->

## Ключевые документы
- `CODEX_HANDOFF_2026_06_20.md` — каноническая точка продолжения, проверка последних коммитов и текущая серверная истина.
- `CODEX_HANDOFF_2026_06_19.md` — предшествующий подробный handoff.
- `reports/LIVE_TRADING_AUDIT_2026_06_18.md`, `reports/RANGE_FORENSICS_AND_ADAPTIVE_PAPER_2026_06_18.md` — live/runtime и execution evidence.
- `reports/audit_bundle_20260619/AUDITOR_README.md` — пакет для независимого ревью.
- `CLAUDE_HANDOFF_NEXT_SESSION_2026_06_15.md` — START HERE.
- `CODEX_HANDOFF_2026_06_15.md` (§1-20) — детальный журнал.
- `reports/FOUNDATION_UPGRADES_AND_LAUNCH_2026_06_15.md`, `HIGH_IMPACT_IDEAS_2026_06_15.md`, `CLAUDE_TO_CODEX_2026_06_15_entry_rework.md` — что делать дальше.
- `reports/SERVER_SNAPSHOT_latest.md` — реальное live-состояние.

## Research-инструменты (Claude, 2026-06-22..25)
Аддитивные раннеры в `backtest/` (offline на `data_cache`; memory-safe, потоковый
вывод, JSON-чекпойнты). Карта находок и команд: `reports/CLAUDE_AUDIT_2026_06_22.md`
(§1-24), сценарий запуска на сервере: `reports/SERVER_TEST_RUNBOOK.md`.
- `package_efficiency_run.py` — пакет крипто-стратегий, taker/maker издержки,
  `--strategies`, `--max-symbols` (на live-VPS 2..3, иначе OOM).
- `midterm_efficiency_run.py` — среднесрочка (4h/дневки).
- `candidate_shortlist.py` — читает чекпойнты → GO/WATCH/CUT для gate.
- `portfolio_combiner.py` — книга целиком (диверсификация, просадка).
- `red_month_doctor.py` — кто «лечит» красные месяцы книги (цели аллокатору).
- `hedge_pairing_run.py` — range vs breakdown по месяцам.
- `alpaca_leverage_probe.py` — regime-gated плечо Alpaca.
- `funding_carry_maximizer.py` / `liquidation_sweep_run.py` / `ai_vet_ab_run.py` —
  market-neutral carry / снос ликвидности / A/B ценности ИИ-вета.
**Ключевые находки:** комиссии убивают высокочастотные стратегии (среднесрочка
выживает); maker-входы оживляют IVB1; диверсификация режет просадку вдвое.
Все цифры — на кэше без финального WF/monthly/gate (доказательство = сервер).
Веб: `web/static/live_chart_prototype.html` — живой перематываемый график (прототип).

## Координация ИИ
Claude = аддитивные инструменты `backtest/`, анализ, доки. Codex = монолит `smart_pump_reversal_bot.py` / `scripts` / веб / деплой / серверные прогоны. Связь — `reports/*_TO_*`.
