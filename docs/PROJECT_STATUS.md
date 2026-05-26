# Project Status — LIVE

**Last updated:** 2026-05-26 morning (Alpaca reporting truth + completed research)
**Update rhythm:** еженедельно или при критическом изменении
**Источник правды:** этот файл + `docs/BACKLOG.md` + `docs/RESUME_AFTER_BREAK_20260519.md`

## Однострочник
Bybit perpetuals bot + Alpaca equities. Live equity ≈ $123 Bybit + $1000 Alpaca paper. **2026-05-26:** router/static-core inputs совпадают с benchmark (`100% input parity`), `bybot` active, allocator healthy, но crypto entries по-прежнему отсутствуют: измеренные blockers находятся внутри filters (`breakdown support`, `flat same_bar/range`, `ATT1 trendline`). Серверный `crypto_income_static_v1` является recovery benchmark (`+73.96%` за 365d, PF `1.591`, DD `5.16%`, 436 trades, 2 red months). Причина отличия от старого локального `+70.17% / PF 1.545` установлена: различался candle-cache; локальное изолированное зеркало на точном серверном cache воспроизвело `+73.96%` один в один. ATT1 density challenger ухудшил полный пакет и отклонён. Alpaca reporting исправлен; v39 остаётся research-only после слабого bear stress.

## Numbers (на 2026-05-19 после рестарта)

### Live state
- **Bybit equity:** ~$123 USDT
- **Last trade:** 2026-04-28 ALGOUSDT range −$0.92. После рестарта ждём первый entry.
- **Alpaca paper:** monthly-owned `GOOGL` с broker protection; intraday tracked позиций сейчас нет; `META/PANW` ожидают подтверждения закрытия; journal P&L `+$5.17` не считается realized до fills
- **Owner reserve:** $2000 в крипте, ждёт Фаза 1 trigger
- **Regime:** `bear_chop` на свежем server heartbeat 2026-05-25; прежний snapshot был `bear_trend`.
- **Allocator:** global_risk=0.8, hard_block=False
- **Service:** `bybot` active, рестарт прошёл чисто (open_trades=0 на момент рестарта)

### Что закрыто 2026-05-19

**P0 (все 5) — все Done:**
- P0-1 same-bar guard fix (11:13 UTC)
- P0-2 midterm grouped counters (11:43 UTC)
- P0-3 skip_portfolio split (11:43 UTC)
- P0-4 AI full-context + extras + ohlc cron
- P0-5 DeepSeek/web prompt подключение

**P0.5 — Done:**
- P0.5-1 Alpaca dynamic_v2 backtest → STATIC_BH wins, dynamic_v2 NOT promoted

**Ночные действия Codex'а (вторая половина 19 мая):**
- Surgical unlock ADA + ONDO в breakdown allowlist (после mini-backtest 180d: ADA PF 4.08, ONDO PF 2.14, ENA PF 0.801 — ENA отклонена)
- ADA активна в allowlist, ONDO staged (current geometry её фильтрует)
- DeepSeek evidence-gate правило: `setup card ≠ recommendation`
- Alpaca v3_shadow ↔ v38 monthly конфликт: v3_shadow отправлял SCHW paper orders, v38 отменял → 6 stuck orders, всё canceled, v3_shadow в DRY_RUN by default
- `runtime/allocator_decisions.jsonl` раздулся до 473 MB → архивирован, trace выключен по умолчанию
- Bybot рестартован безопасно

**Утро 2026-05-20:**
- Удалён архивный `runtime/archive/allocator_decisions_20260520_0515.jsonl` на сервере; `runtime/archive` теперь ~4 KB.
- Cleanup сломал портфельные backtests: `backtest/run_portfolio.py` жёстко импортировал удалённую `alt_liquidity_sweep_reversal_v1`. Исправлено optional import, задеплоено на сервер, `py_compile` OK.
- `scripts/alpaca_dynamic_full_backtest.py` больше не пишет жёстко в `/root/by-bot/runtime`; локально пишет в repo `runtime/`, на сервере работает как раньше.
- Локальный контрольный backtest `crypto_income_static_v1`: `+70.17%`, PF `1.545`, WR `58.7%`, MaxDD `6.23%`, 445 trades.
- Серверный точный rerun того же протокола 2026-05-26: `+73.96%`, PF `1.591`, WR `59.4%`, MaxDD `5.16%`, 436 trades, 2 красных месяца. Архив серверного cache для восьми benchmark-символов перенесён в изолированную локальную research-копию и воспроизвёл эти цифры один в один. Следующие package-sweeps обязаны побить именно этот fixed-dataset baseline.
- Attribution: ATT1 `+39.05`, breakdown `+16.42`, ARF1 `+7.61`, midterm `+7.08`.
- Live allocator сейчас отключает ATT1 и midterm в `bear_trend`, поэтому live не равен проверенному пакету.
- Быстрая статическая аппроксимация текущего live allocator (`breakdown + flat + sloped + asm1`, cached symbols only): `+17.45%`, PF `1.211`, MaxDD `13.25%`, 274 trades. Это хуже `crypto_income_static_v1` по return, PF и DD.
- P1-1a shadow/control-plane replay `crypto_income_static_v1`: `+42.31%` за 360d, PF `1.383`, WR `58.8%`, MaxDD `5.87%`, 536 trades, 1 красный месяц. Это подтверждает, что восстановление старого пакета через allocator/policy перспективнее текущего live-состава, но не равно слепому live-включению.
- В P1-1a replay основной вклад дал ATT1 (`+32.33`, 392 trades); flat stabilizer `+12.74`, breakdown `-2.76`. В `bear_trend` пакет торговал только `flat+breakdown` и был слабоплюсовой: PF `1.198`, `+0.66`.
- P1-1b: static-v1 policy/health/env артефакты досинхронизированы на сервер; allocator `--dry-run` с static-v1 policy работает, но `bear_trend` orchestrator всё равно оставляет только `flat+breakdown`. Это ожидаемо по replay, но объясняет почему ATT1/midterm не появятся без отдельного overlay-решения.
- Crypto blocker улучшен до symbol-aware отчёта: `runtime/crypto_blocker/latest.json`, 67 cards; классы: `blocked_runtime_disabled_or_zero_risk=36`, `blocked_by_symbol_allowlist=23`, `blocked_by_symbol=6`, `blocked_by_range=2`. Главный свежий разрыв: scanner видит flat на большем наборе монет, а allocator разрешает flat только `LINKUSDT,LTCUSDT`.

### Главные новые факты от Codex
1. **Bybit не торговал за ночь** — open_trades=0 при regime bear_trend.
2. **Причина не "нет рынка"** — после свежего рестарта доминирует `breakdown_ns_symbol`; allowed breakdown symbols не дают setup, а scanner чаще видит flat/ASB1 cards.
3. **365d simplified research результат:** только **IVB1_static слабоплюсовой** PF~1.18. Это не тот же пакет, что `crypto_income_static_v1`.
4. **Проверенный crypto package жив:** `crypto_income_static_v1` снова воспроизводит +70.17%/365d.
5. **Главный конфликт:** live allocator в bear_trend выключает ATT1/midterm, а router/allowlist слишком узко даёт `flat+breakdown`. P1-1a replay подтвердил, что контрольная плоскость может сохранить прибыльность, но P1-1b показал: текущий первый практический фикс — backtest-driven symbol/router expansion для `flat`/`breakdown`, а не включение ASB1.

### Validated backtests (только то, что прошло metric)
- **Alpaca v38 hybrid top4** (paper candidate): backtest 24м +50.77 %, PF 6.29, WR 82.9 %, MaxDD −2.28 %. Текущий paper-цикл ещё должен завершить fills reconciliation и итог цикла до решения о реальном депозите.
- **crypto_income_static_v1**: 365d static `+70.17%`, PF `1.545`, MaxDD `6.23%`, 445 trades; 360d control-plane replay `+42.31%`, PF `1.383`, MaxDD `5.87%`, 536 trades, 1 red month — **главный crypto recovery candidate**, но включать только через shadow/live parity.
- **IVB1_static** (crypto 365d): PF ≈ 1.18 — **слабоплюсовой, на границе**.
- **breakdown ADA 180d**: PF 4.08 — **сильный, но один символ, мало sample**.
- **breakdown ONDO 180d**: PF 2.14 — **сильный, ждёт geometry unlock**.

### Active research queue
- `att1_density_v3_more_pivots_v1` — finished 2026-05-26, `864/864`: standalone best `r259` `+38.48%`, PF `1.384`, DD `3.97%`; full-package replay **rejected** it: `+58.50%`, PF `1.386`, DD `15.18%`, 539 trades, 3 red months versus baseline `+70.17%`, PF `1.545`, DD `6.23%`, 445 trades, 2 red months.
- `package_breakdown_rsi_v1` → `package_arf1_flat_touch_v1` — running locally in detached `screen` session `crypto_package_sweeps_20260526` against mirrored server candle-cache. First breakdown row FAIL: `+69.34%`, PF `1.528`, DD `5.38%`, red months `>2`. These full-package jobs were moved off the 1 GB VPS after an initial server process left only ~63 MB available memory.
- `breakdown_recent_bear_window_v2_entry_quality` — fixed broken `4h` backtest timeframe (`240`) and rerun; 36/36 failed, best `-6.25%`, PF `0.679`, DD `7.30%`. Do not extend live breakdown from this window.
- `bear_regime_continuation_v1_initial_sweep` — pending/restart locally only: свежий server status показывает `active_process_count=0`; не считать BRC1 готовой без завершённого 360d результата.
- `att1_short_slope_v1` — finished `18/18`; best `+15.44%`, PF `1.097`, DD `9.96%`, failed gate; reject/no promotion.
- `flat_live_frequency_v3` — completed locally 2026-05-25: standalone best `+9.66%`, PF `2.232`, WR `59.4%`, DD `1.76%`, 32 trades, 3 negative months. Portfolio replacement test inside `crypto_income_static_v1` worsened benchmark to `+64.24%`, PF `1.491`, DD `7.31%` (vs `+70.17%`, PF `1.545`, DD `6.23%`); **reject for live promotion**.
- `asb1_bull_chop_repair_v1` — не продвигать в live без repair acceptance

## Что работает прямо сейчас
- ✅ Bybit auth + same-bar fix
- ✅ Allocator auto-tier
- ✅ Heartbeat + grouped counters (ATT1/ASM1/Flat/MIDTERM/breakdown/sloped split)
- ✅ AI context bridge (3 cron'а)
- ✅ DeepSeek-on-bot читает scanner cards + crypto blocker + extras + ohlc
- ✅ DeepSeek evidence-gate (новое правило: setup card ≠ recommendation)
- ✅ Web UI, admin endpoints, AI history
- ✅ Watchdog (один cron)
- ✅ Alpaca paper intraday + monthly v38 hybrid
- ✅ Alpaca v3_shadow DRY_RUN (больше не конфликтует с v38 monthly)
- ✅ Disk hygiene: allocator trace выключен default
- ✅ 2026-05-21 evening: scheduler теперь читает свежие allowlists для `ATT1`, `ASM1`, `sloped`; `sloped_ns_symbol` ушёл после патча, остался малый sample `same_bar/first_bar`.
- ✅ 2026-05-22 morning: `breakdown_bear_core` router geometry over-filter fixed for validated ADA/ONDO only; ADA/ONDO now survive geometry if already selected by market/backtest router.
- ✅ 2026-05-22 midday: `sloped_channel_live.py` now passes real closed 5m OHLC into pending confirmation instead of zero OHLC; this fixes live execution parity without loosening risk/filter thresholds.
- ✅ 2026-05-22 midday: `scripts/alpaca_v3_event_backtest.py` + `strategies/alpaca_dynamic_v3_event.py` added and first server run completed. `V39_EVENT`: `+34.47%`, PF `1.328`, WR `50.5%`, trades `222`, DD `24.07%`, red months `10/24`; verdict `REJECT`, not paper/live.
- ✅ 2026-05-25: AI full-context now carries dynamic `router_state` and compact `crypto_blocker_summary`; DeepSeek/web can see current symbol routing and blocked setup cards without write access to trading state.
- ✅ 2026-05-25: DeepSeek weekly audit now attributes P&L/PF/DD only to a strategy's own trades; universe ideas are explicitly backtest-only and cannot be described as market-validated without supplied evidence.
- ✅ 2026-05-25: Deployed read-only crypto entry-funnel counters (`try -> signal -> sizing/risk/order skip -> entry`) with controlled restart at `open_trades=0`. First live sample shows `signal=0` for all active sleeves, so current silence is inside strategy filters, before order submission.
- ✅ 2026-05-25 16:35 UTC: Deployed bounded read-only `signal_decisions.jsonl` trace for static-v1 sleeves (`midterm/att1/flat/breakdown`) and delivery through `crypto_blocker` into operator AI context. Restart was controlled at `open_trades=0`; this provides per-symbol decision evidence without changing orders, risk or enabled strategies. No rows appeared within the first 65 seconds, pending the next scheduled evaluations.
- ✅ 2026-05-25: `signal_decisions` produced first live evidence immediately after deploy: `breakdown` rejects included `ADA RSI 74.8`, `LINK RSI 78.3`, `ETH RSI 84.8`, `BTC RSI 72.1`, and `ONDO no_real_break`; target next replay at RSI/support rather than router changes.
- Alpaca intraday accounting audit: clean filled sample after the old cleanup incident is `DDOG +$3.43` and `UBER +$1.27` (`+$4.70` realized); `PANW/META` show approximately `+$5.17` but close orders are accepted/pending while the US market is closed on 2026-05-25, so they are not realized yet. Legacy `+$155.99` in the equity log is not acceptable as clean strategy performance.
- Deployed Alpaca paper-ledger repair at `2026-05-25 16:57 UTC`: manager close now remains `close_pending` until broker fill confirmation and does not book submission-time estimates as realized P&L. It must still be observed through a complete filled close before any live funding decision.
- ✅ 2026-05-26: deployed reporting ownership truth. Crypto periodic report is explicitly crypto-only; station digest, web and AI context distinguish monthly-owned `GOOGL`, pending intraday closes `META/PANW`, zero tracked intraday positions and unverified paper journal P&L.
- ✅ 2026-05-26: full-package replay rejected ATT1 `r259`; extra frequency increased drawdown and reduced return/PF. No crypto live settings changed.

## Что НЕ работает (top blockers)
0. **P0-NEW: decision parity after input parity.** Server check at 2026-05-25 16:20 UTC returned `input_symbol_parity_pct=100.0`, `verdict=PASS`, allocator `safe_mode=False`; therefore control-plane/allowlist are no longer the unexplained stop. Need match backtest entry timestamps to live filter outcomes on a stable post-fix window.
1. **Active internal blockers are measured.** Fresh counters: `breakdown_try=419`, `no_signal=419` (`rsi=320`, `support=80`); `flat_try=32`, `no_signal=32` (`touch=20`); `ATT1 try=57`, `signal=1`, `no_signal=56` (`trendline=24`), with the single signal stopped at rounding. This is targeted filter/replay work, not a server reset.
2. **Claude candidate rewrites are not live fixes yet.** The live bot already calls `BRC1.signal(...)`, so adding `BRC1.maybe_signal(...)` does not repair a missing live interface. Changing BRC1 indicators, ARF1 filters or `MTPB_USE_RUNNER_EXITS` changes strategy semantics and invalidates existing baseline comparisons until challenger replay is complete.
4. **Signal parity ещё не закрыт.** Latest weekly replay нашёл 9 backtest entries при нуле real entries, но все они вне `NO_ENTRY_HOURS_UTC=0,1,2`, а сам replay применял новый config ретроспективно к периоду до завершения router fixes. Следующий честный тест нужен на стабильном post-fix окне.
5. **Order-path blocker теперь измерим, но пока не проявился.** После deployment счётчиков новый sample: `breakdown signal=0/5`, `ATT1=0/7`, `flat=0/4`, `sloped=0/3`, `midterm=0/2`, `asm1=0/2`. До первого `signal>0` нельзя обвинять sizing/order/risk.
6. **direction-aware risk_mult** — long и short режутся одинаково в bear macro.
7. **Bybit broker-side TP/SL already exists.** Remaining safety task is a smoke assertion for the short interval between entry acceptance and confirmed exchange-side protection.
8. **Alpaca v39 written but not accepted** — fee-stressed 24m: `+70.37%`, PF `1.850`, DD `13.29%`, red months `6/24`; OOS 12m `+26.15%`, PF `1.895`, DD `9.51%`; bear-2022 `-23.47%`, PF `0.415`, DD `27.66%`. v38 hybrid пока единственный paper-кандидат для deposit gate.
9. **Market data freshness Alpaca** — fixed in paper bridge on 2026-05-25; v3 shadow remains `DRY_RUN`, verification after next US session is still required.
10. **Alpaca deposit gate** — credential literals were present in a tracked legacy handoff/history and paper intraday ledger books estimates before fills. Redact current HEAD, rotate paper keys, and fix filled-PnL accounting before funding an Alpaca live account.

## Принятые архитектурные решения (НЕ менять без owner)
- **Single live env:** `crypto_income_live_canary_v2_2_rescue.env`
- **Evidence-first acceptance gate:** PF≥1.25, DD≤8%, neg_months≤3, neg_streak≤2, trades≥30, fees учтены
- **DeepSeek = ORACLE stage только** (не ADVISOR, не EXECUTOR)
- **setup card ≠ recommendation** (новое правило, добавлено в DeepSeek prompt)
- **Не редактируем .env без явного запроса owner'а**
- **Не активируем new strategies без backtest gate**
- **Не запускаем real money Alpaca без 14d stable paper validated v39**

## Заморожено
- ❌ Forex/OANDA (до конца лета)
- ❌ 11 alt_*_v1 strategies (acceptance gate не пройден)
- ❌ AI ADVISOR/EXECUTOR stages
- ❌ Phase 2 monolith refactoring
- ❌ Champion-challenger framework
- ❌ Genetic algorithm
- ❌ ASB1 → live в bear_trend (r001 FAIL)
- ❌ Alpaca dynamic_v1, v2, v38 more-active (все проиграли benchmark)
- ❌ Включение ENA в breakdown allowlist (PF 0.801 < 1.0)
- ❌ Ручной подбор монет как способ заработать (только rolling backtest → router → allocator → live)
- ❌ DeepSeek с правом менять live state (только read + recommend)

## Финансовая фаза
**Сейчас:** Фаза 0. Никаких новых депозитов до:
- ≥ 10 trades за 7d
- PnL ≥ −5 %
- хотя бы 1 sleeve с PF > 1.0 на ≥ 5 trades

| Фаза | Trigger | Bybit | Alpaca | Total real |
|---|---|---|---|---|
| 0 | now | $123 | $0 | $123 |
| 1 | acceptance выше | $623 | $0 | $623 |
| 2 | 14d stable | $623 | $500 | $1123 |
| 3 | 30d, PF>1.1, DD<10% | $1323 | $800 | $2123 |
| 4 | 60d funding-carry validated | $1273 + $50 sub | $800 | $2123 |

## Артефакты Claude (сводно)

### Скрипты (5)
- `scripts/build_ai_full_context.py` — основной AI context
- `scripts/build_ai_extras.py` — trade history, errors, indicators, memory
- `scripts/build_ai_ohlc_and_logs.py` — OHLC top-3 + raw log tail
- `scripts/compare_live_pulse_vs_backtest.py` — диагностика
- `scripts/alpaca_dynamic_v2_backtest.py` — Alpaca research (verdict DONE)

### Документы (9)
- `docs/PROJECT_STATUS.md` — этот файл (live)
- `docs/BACKLOG.md` — приоритеты P0/P1/P2/P3
- `docs/RESUME_AFTER_BREAK_20260519.md` — handoff на 5 дней
- `docs/NEW_CHAT_START_PROMPT.md` — как заходить новому чату с минимумом токенов
- `docs/CLAUDE_AUDIT_20260519.md` — детальный аудит
- `docs/STRATEGY_SET_PER_REGIME_20260519.md` — strategy matrix
- `docs/MIDTERM_GROUPED_COUNTERS_SPEC_20260519.md` — выполнено
- `docs/MINIMAL_VIABLE_STACK_20260519.md` — NEW: что у нас доказанно прибыльное, как собрать MVP
- `docs/CLAUDE_START_HERE_20260518.md` + `docs/CODEX_CURRENT_STATE_20260518.md` — Codex'а (non-negotiable rules)

## Ссылки
- `docs/BACKLOG.md` — приоритеты
- `docs/MINIMAL_VIABLE_STACK_20260519.md` — ответ «можно ли уже сейчас собрать торгующую систему»
- `docs/NEW_CHAT_START_PROMPT.md` — как начать новый Claude-чат
- `runtime/live_mirror/bot_heartbeat.json` — counters
- `runtime/ai_context/{full_context,extras,ohlc_and_logs,memory_lines}.json` — что видит DeepSeek
- `runtime/project_doctor/latest.json` — auto health

## История изменений
- 2026-05-24: after 51h uptime still no crypto open trades. Fresh blocker report: 80 setup cards, 44 blocked by disabled/zero-risk sleeves (mostly ASB1/BRC1), 27 by symbol allowlist; active-hour strategy blockers are `breakdown_ns_rsi/support`, `flat_ns_touch/range`, `sloped_ns_r2/channel`. Static-v1 input parity was only 50%; Codex added router `force_include_symbols` support and pinned proven static-v1 core symbols for `breakdown`, `ATT1`, and `ARF1` without touching live env. Alpaca v39 best event-grid candidate saved to `configs/alpaca_v39_event_best_research.env`; still research-only.
- 2026-05-25: static-core router fix is active in live; fresh counters shift the crypto blocker from symbol/control-plane mismatch to internal filters (`breakdown_support`, `ATT1_trendline`, `flat_touch`). Fixed broken breakdown research TF and rejected its bear-window expansion; ATT1 360d sweep produced a positive challenger requiring DD repair. AI context deployed with router/blocker visibility. Alpaca v39 focused 4y stress remains research-only.
- 2026-05-25: fixed DeepSeek weekly report attribution bug: a portfolio result was previously repeated as if it were each sleeve's own result. Reports now calculate per-sleeve trade evidence and mark universe suggestions as research-only. No live strategy or account settings changed.
- 2026-05-25: weekly live-vs-backtest interpretation hardened: recent 9 replay entries were outside the live dead-zone, but the report used end-of-window config retrospectively over pre-fix days. Future reports expose dead-zone count and label this as counterfactual until the config has stayed stable through the measured window.
- 2026-05-25: added live entry-funnel counters and blocker-report support for signals stopped after generation. Deployment was diagnostics-only with `open_trades=0`; fresh sample confirms active sleeves currently fail before signal generation, so the next evidence task is filter-level replay (`ATT1 trendline`, `flat touch`, `breakdown support`).
- 2026-05-25: ran `flat_live_frequency_v3` and an additive portfolio replay. A standalone ARF1 variant passed, but substituting it into `crypto_income_static_v1` reduced return and increased drawdown; no flat live parameter promotion.
- 2026-05-25: found a hidden parity blocker: stale `configs/auto_apply_params.env` was loaded over live settings and tightened `ATT1` versus proven `crypto_income_static_v1` (`MIN_R2 0.9` vs `0.7`, `TOUCH_ATR 0.35` vs `0.5`, `MAX_PIVOT_AGE 12` vs `20`). Deployed reviewed `configs/approved_strategy_params.env`, disabled unattended auto-apply overrides by default, and restarted `bybot` only after confirming `open_trades=0`. Monitor fresh ATT1 signal/entry counters.
- 2026-05-25: hardened web credential rotation: no key fragments or secret backup paths are returned/audited, backups receive private permissions, and API expiry status is published safely for a new `API Keys` web page. Current Bybit monitor status: expiry date `2026-08-12`; no credential values exposed.
- 2026-05-25: corrected Alpaca v39 research semantics by separating event review interval from a real hard holding limit. Revalidation with `hard_max_age_days=60` preserved 24m candidate metrics (`+88.05%`, PF `1.987`, DD `12.90%`, red months `6/24`); 4y stress remains `REJECT` (`+140.20%`, PF `1.624`, DD `26.47%`, red months `16/52`), so v39 stays research-only.
- 2026-05-25: fixed Alpaca paper state isolation in `equities_alpaca_paper_bridge.py`: intraday positions with pending close orders (`META`, `PANW` in observed conflict) are protected from monthly stale cleanup until the order completes. The first scheduled monthly tick after deploy confirmed `protected=[META,PANW]`, `stale=[]`. Broker-side crypto TP/SL already exists with retry/ensure logic; funding carry remains dry-run-only because it is not hedged.
- 2026-05-25 evening: reran server diagnostics after the static-core router fix. Static-v1/live required symbol inputs now pass at `100%`; active crypto silence is inside filters (`breakdown_rsi/support`, `flat_touch`, `ATT1_trendline`) rather than allocator or router. Reviewed Claude follow-up drafts: BRC1 live already uses `signal(...)`; new ARF1/BRC1/MTPB/Elder changes remain uncommitted research challengers until replay.
- 2026-05-25 16:35 UTC: deployed bounded per-decision trace for static-v1 live sleeves and `crypto_blocker` AI exposure with `open_trades=0`; awaiting the next scheduled evaluations for its first sample rather than blindly relaxing filters.
- 2026-05-25 evening: first decision trace rows arrived and isolate breakdown rejections to high RSI/no real break. Alpaca audit separated clean intraday fills (`+$4.70`) from contaminated legacy ledger (`+$155.99`) and pending mark-to-market (`~+$5.17`); paper credentials exposed in legacy tracked material were redacted in current HEAD and rotation is now a deposit gate.
- 2026-05-25 16:57 UTC: deployed paper-only Alpaca freshness and filled-PnL safeguards. v3 dry-run now reads recent bars (`2026-05-22 19:55 UTC` while the market is closed), and new manager exits are recorded as realized only after broker fill confirmation; pre-patch `PANW/META` require reconciliation on the next US session.
- 2026-05-26 morning: corrected station reporting and AI/web ownership semantics for Alpaca paper. Digest now labels `$+5.17` as journal P&L awaiting fill reconciliation and separates monthly `GOOGL` from pending intraday closes `META/PANW`. Full-package replay rejected ATT1 `r259` (`+58.50%`, PF `1.386`, DD `15.18%`) against static-v1 baseline (`+70.17%`, PF `1.545`, DD `6.23%`); ATT1 slope is also rejected. Alpaca v39 remains research-only after bear stress failure.
- 2026-05-26: deployed Setup Scanner full candlestick modal and read-only `scripts/monitor.py`; monitor now marks stale `strategy_health.json` as historical rather than live gate evidence. Server rerun returned `+73.96%`, PF `1.591`, DD `5.16%`; an isolated local replay initially returned `+70.17%` because it used a different candle-cache, then reproduced the server result exactly after mirroring the server dataset. Long full-package sweeps run locally in `screen`/`caffeinate`, not on the memory-constrained live VPS.
- 2026-05-22 morning: Codex found overnight no-trade cause shifted from old scheduler mismatch to router geometry over-filter: `BREAKDOWN_SYMBOL_ALLOWLIST` was only `BTCUSDT,ETHUSDT` while scanner had ADA breakdown. Patched `scripts/build_symbol_router.py` + `configs/strategy_profile_registry.json` with `geometry_force_keep_symbols=["ADAUSDT","ONDOUSDT"]` for `breakdown_bear_core`. Rebuilt router/allocator on server: breakdown count 2→4, risk 0.7125→0.8550, `BREAKDOWN_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,ADAUSDT,ONDOUSDT`. Controlled restart with `open_trades=0`; stream recovered, bybit msgs growing, first fresh counters show no portfolio/global block.
- 2026-05-21 evening: Codex patched scheduler allowlist drift for `ATT1`, `ASM1`, `sloped`; added grouped `sloped_ns_*` diagnostics. Server restarted safely with `open_trades=0`; stream fresh, `bybit_msgs` growing. Fresh compare: allocator hard block false, `breakdown_ns_support`, `flat/sloped same_bar` with small post-restart sample, no `sloped_ns_symbol` domination.
- 2026-05-21 morning: P0-NEW поднят выше всех задач: `live-vs-static_v1 parity fix`. Проверка 7d до 2026-04-30 отброшена как неторговое окно; стартовала 30d parity-проверка до 2026-02-24.
- 2026-05-19 morning: первая редакция Claude. Снят старый baseline.
- 2026-05-19 day: Codex закрыл весь P0, P0.5-1, AI context, Alpaca 422 fix.
- 2026-05-19 evening: Claude добавил ohlc_and_logs.py + RESUME_AFTER_BREAK + NEW_CHAT_START_PROMPT + MINIMAL_VIABLE_STACK. Codex ночью: ADA/ONDO surgical unlock, allocator trace cleanup, v3_shadow DRY_RUN.
- 2026-05-20 morning: Codex удалил архивный allocator trace, восстановил запуск portfolio backtests после cleanup, подтвердил `crypto_income_static_v1` +70.17%/365d и зафиксировал live mismatch: ATT1/midterm выключены allocator'ом.
- 2026-05-20 midday: P1-1a control-plane replay прошёл: +42.31%/360d, PF 1.383, MaxDD 5.87%, 1 red month. P1-1b dry-run показал, что static-v1 policy на текущем bear_trend оставляет `flat+breakdown`; crypto blocker стал symbol-aware и выявил 23 scanner cards вне allocator symbols.
