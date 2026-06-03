# Next Steps — 2026-06-02 PM

**Контекст:** Bot впервые торговал с 28 апреля. ETHUSDT short от `breakdown` → `bd1_dump_continuation`, entry 1926.19, SL 1931.97, runner exit 1917.25 за 4 минуты, **pnl +$0.20 net**. Выборка из 1, выводов нет. Цель этого документа — что делать дальше, не сломав то, что наконец заработало.

## Главное правило ближайших 14 дней
**Не трогать живые параметры стратегий и `.env`.** Все изменения — observability, safety-nets, replay'и в background. Цель — накопить 20-30 сделок, оценить PF/WR/DD, и только потом любые tuning-движения. История с "был хороший standalone winner → провален в package replay" (r259) — напоминание, что preliminary numbers лгут.

---

## Крипто-рукав

### Что делать сейчас (P0)
1. **Безопасность runner-TP** (Task #8). При `request_tp=null` (новая логика runner) если runner не выставит TP за N=5 минут после `entry_filled` — поставить fallback hard TP на бирже. Скрипт: `scripts/runner_tp_watchdog.py`, cron каждую минуту, читает `live_trade_events.jsonl`, ставит TP через `submit_trading_stop` если нужно.
2. **Regime mirror** (Task #9). heartbeat показывает `regime=unknown` при работающем orchestrator (`last_seen_regime.txt=bear_chop`). Найти мост, починить. Это не критично для торговли, но критично для AI/web/operator context.
3. **Latency probe** (Task #10). Send→fill 33с — это очень долго. Замерять: WebSocket send time, REST acknowledgement, fill confirmation. Тикет Codex'у с точками логирования `latency_phase_1/2/3_ms`.

### Что делать в течение 7-14 дней (P1)
4. **Накопить выборку 20-30 сделок** (Task #7). Без изменений. После — сводный отчёт PF/WR/max DD/avg duration vs `crypto_income_static_v1` baseline.
5. **Запустить мои replay'и** (`package_att1_trendline_recovery_v1.json`, `package_breakdown_recovery_v1.json`) на server-mirrored cache. Не на VPS памяти. Промоушн только при бьющем PF 1.591 / DD 5.16% baseline.
6. **ARF1 r002 параметры** в `approved_strategy_params.env` (по PROJECT_STATUS они уже исследованы, но в approved env не зашиты).
7. **MTPB wire-up audit.** Sample = 1 try за uptime. Либо стратегия не подключена правильно, либо ей не отдаются нужные символы.

### Не торопиться (P2)
- Champion-challenger для каждой активной стратегии.
- BRC1 переоценить после полного package replay.
- Новые символы в allowlist — только через rolling backtest → router → allocator → live.

---

## Alpaca

### Что у нас в работе
- Codex commit `996f779 Fix Alpaca paper protective order lifecycle` — проверить совпадает ли с моим pre-market patch'ем. Если разные подходы — слить.
- Мой patch добавляет `get_clock()` + `_market_is_open` guard в `_submit_buy_action`. Codex'овский lifecycle patch может быть про что-то другое (stale orders / cancel race).

### Что делать сейчас (P0)
1. **Сверка patch'ей.** Прочесть diff `996f779` и сравнить с патчем в `scripts/equities_alpaca_paper_bridge.py`, который я применил. Конфликта быть не должно (Codex закоммитил после моих правок), но проверить.
2. **Следующий market-hour refresh.** В 14:00-15:00 UTC прогнать paper bridge и убедиться что DDOG hold + QCOM/NOW pending buys реально филяются с protective stop.

### P1
3. **Завершить full filled cycle** на v38 паре. Один цикл с реальным fill closing.
4. **Paper credentials rotation** (PROJECT_STATUS блокер #10). До этого никакого реального депозита.
5. **HWM trail (commit 89c6f8d) валидация на реальном close.** Симуляция была, реальный close-fill ещё нет.

### P2
- v39 / v40 остаются research-only до отдельного решения.
- Дробление на multiple sleeves внутри Alpaca (intraday vs monthly) — обсудить когда базовый monthly даст 1-2 закрытых цикла подряд.

---

## Арбитраж

### Сделано
- `cross_exchange_funding_scan.py` (15m cron).
- `cross_exchange_funding_validate.py` (validator, 5 пар прошли).
- `cross_exchange_funding_shadow.py` (5 пар в shadow).
- `scripts/exchange_account_status.py` (мой helper + Codex env-loader). Сейчас все exchanges `ok=false reason=missing_keys`.
- Codex `ef04ebd Add cross-exchange arb dry-run context` — arb dry-run context в AI full-context.

### Что делать сейчас (P0)
1. **Read-only ключи на сервере.** Binance + Bitget. По `docs/EXCHANGE_KEYS_SETUP_20260602.md`. Никаких ключей в чате, документах, git. Withdrawal/Trading disabled, IP-whitelist на сервер.
2. **После ключей:** запустить `exchange_account_status.py` cron каждые 5 минут. Должны увидеть `ok=true equity_usdt=0` (read-only). Если 4xx — права ключа неверные.

### P1
3. **Dry-run executor** `scripts/cross_exchange_arb_dry_run.py`. По моему `docs/ARB_DRY_RUN_PLAN_2026_06_02.md`. Логирует плановые ноги, ордера не шлёт.
4. **14 дней stable shadow + dry-run.** Только потом думать про live.

### P2
- Live canary `$40/пара`, ≤2 пары, daily kill-switch $10.
- НЕ раньше чем после 14d shadow/dry-run + первого закрытого цикла Alpaca + PF≥1.4 в крипте за 30 дней.

---

## Core bot (база)

### Боль, которую видно из текущих данных
1. `regime` heartbeat-mirror stale (Task #9).
2. 33s entry latency (Task #10).
3. `request_tp: null` без runner safety-net (Task #8).
4. heartbeat показывает кучу `skip_*` counters, но не показывает **сколько entries дошло до broker**. `entry_submit_ok=1` есть, но нужны парные `entry_submit_fail`, `entry_canceled`, `entry_rejected`.

### Backlog для рефакторинга (P2, после стабилизации)
- **Splitless monolith.** `smart_pump_reversal_bot.py` 14k строк — это одна точка отказа. Не трогать пока торгует, но первый кандидат на phase 2.
- **State machine for entries.** Сейчас entry path размазан по async корутинам. Один FSM `PENDING → SUBMITTED → FILLED → PROTECTED → OPEN → CLOSING → CLOSED` сделает baddebugging радикально проще.
- **Per-strategy circuit breakers.** Уже есть allocator hard-block, но не per-strategy "5 убыточных сделок подряд → автоматическая пауза на 24ч". Это защищает от регрессий быстрее, чем weekly review.

---

## AI в боте — конкретные слои

DeepSeek сейчас живёт как Oracle (read+рекомендация, не исполнитель). Это правильно. Расширения по приоритету:

### Слой 1 (P0): Post-trade analyzer
Файл: `scripts/post_trade_ai_review.py`. Cron — после каждого `close` event.
- Берёт сделку из `live_trade_events.jsonl` + setup card на момент signal + OHLC ±1 час.
- Отправляет в Haiku (дёшево): «Вот сетап, вот результат. Что было видимо в момент сигнала? Что было неочевидно но повлияло?»
- Пишет в `runtime/ai_trade_journal.jsonl`. Не меняет параметры. Раз в неделю — сводный отчёт «10 повторяющихся паттернов проигрышей».

### Слой 2 (P1): Setup quality scorer
В `bot/deepseek_signal_gate.py` уже есть скелет evidence-gate. Расширить: перед каждым signal'ом (после внутренних фильтров, перед order submission) — быстрый Haiku score 1-10. Если score ≤ 3 — не блокировать сразу, а понизить `risk_mult` на 0.7. Так мы не теряем edge на ложно отбрасываемых сетапах, но снижаем экспозицию в шуме.

**Важно:** не делать это execute-stage. Только размер. Бот всегда может торговать без AI (off-switch).

### Слой 3 (P2): Drift detector
Cron daily. Сравнивает live counters за 7 дней vs предыдущие 30 дней. Если `breakdown_signal/try` упал >40% или `att1_ns_trendline` доля выросла >25% — AI пишет «вероятная регрессия, причины X/Y/Z». Не паузит, не меняет, просто кричит.

### Слой 4 (P3): Weekly proposal generator
Текущий `DEEPSEEK_WEEKLY_REVIEW_20260517.md` — спека. Сделать workflow:
- Каждое воскресенье AI читает `runtime/ai_trade_journal.jsonl` + текущие counters + sweep queue.
- Предлагает 1-3 концепции (новая стратегия / параметр сдвиг / новый символ).
- Пишет в `runtime/ai_proposals.jsonl`. Human approve через TG (когда команды появятся, см. IDEAS.md P0).
- Approved → автоматически в `research_queue.jsonl` для sweep.

### Что НЕ делать с AI
- Никаких execute-rights. Никогда.
- Никакого ADVISOR-stage (где AI говорит «открой ETH short») до 6 месяцев track record.
- Никаких "AI sentiment from twitter" — это шум, плохо отбэктестится.

---

## Приоритезация на эту неделю

| День | Кто | Что |
|---|---|---|
| Сегодня | Codex | runner_tp_watchdog + regime mirror fix |
| Сегодня | Ты | Решить про exchange keys (когда и как) |
| 3-7 июня | Bot | Просто торгует, накапливает выборку |
| 3-7 июня | Codex | Sweep replays `att1_trendline_recovery_v1` + `breakdown_recovery_v1` на server-mirror |
| 5-7 июня | Я / Codex | Post-trade AI analyzer (слой 1) |
| 8-14 июня | Я | Анализ первой выборки 20-30 сделок |
| 8-14 июня | Ты | Alpaca depo $500 решение после 1 closed cycle |

---

## Что отказываемся делать в этой неделе
- Champion-challenger framework (Wave C). Слишком рано — у нас нет champion'а.
- Forex/OANDA. Frozen до конца лета.
- Любые новые стратегии. У нас 76 файлов, из них 14 wired, и только сегодня одна впервые торгует.
- Новые символы в allowlist. Никаких "давайте добавим SOL/HYPE" — только через rolling backtest.
- HF scalping слой. После 6 мес стабильного swing.

---

*Подготовлено Claude Opus, 2026-06-02 PM. Источник правды: `runtime/live_mirror/bot_heartbeat.json` (ts 1780424187), `live_trade_events.jsonl` (последний event 2026-06-02 15:25:23 UTC).*

---

## Update — 2026-06-03 AM (Codex)

### Что реально изменилось

- Крипта ожила: после первой ETH сделки появились ещё один ETH close и открытая BTCUSDT SHORT позиция. На момент проверки Bybit API показывает `BTCUSDT Sell 0.001`, entry `68074.2`, broker-side `stopLoss=68754.9`, `takeProfit` пустой. Бот видит позицию через `runtime/live_positions.json`.
- Исправлен статусный разрыв `heartbeat.regime=unknown`: теперь heartbeat/UI/AI берут свежий режим из `runtime/regime/orchestrator_state.json`, если `ORCH_REGIME` не загружен в процесс. Это **не включает** `REGIME_OVERLAY_ENABLE` насильно и не меняет торговые параметры.
- `regime_mirror_diag.py` переведён на реальные server paths (`runtime/...`) и порог hourly orchestrator поднят до 65 минут, чтобы не было ложного `orchestrator_cron_dead_or_slow`.
- `runner_tp_watchdog.py` поставлен в cron **только dry-run** каждую минуту. Он ничего не меняет на бирже, только пишет, какие runner-only позиции без TP он бы страховал.
- `post_trade_ai_review.py` поставлен в cron каждые 30 минут с `--prefer-deepseek`. Первый запуск догонит старые close events, затем будет разбирать новые сделки.
- `drift_detector.py` поставлен daily; сейчас `green`, потому что выборка всего 2 свежих close.
- Web setup AI переведён на DeepSeek-first и явно требует русский язык. Anthropic используется только если поставить `WEB_SETUP_AI_PROVIDER=anthropic`.
- Telegram DeepSeek prompt обновлён: он должен использовать `snapshot.ai_full_context.setup_cards_top`, `snapshot.crypto_blocker`, `snapshot.ai_extras.trade_history.per_sleeve` и честно говорить, если свежий контекст не подъехал.
- Cross-exchange arb: Binance/Bitget read-only keys добавлены на сервер. `exchange_account_status.py` видит Binance, Bitget, Bybit; MEXC adapter готов, но без ключей. Dry-run пока `ready_count=0`, потому что Binance ~11.7 USDT, Bitget 0 USDT, а минимальный dry-run требует хотя бы ~$20 на каждую ногу.

### Что делать дальше

1. Наблюдать текущую BTC позицию до закрытия. SL стоит на бирже; TP пустой, потому что позиция восстановлена как `bootstrap`.
2. Не включать `runner_tp_watchdog --apply` раньше чем через сутки dry-run журнала.
3. Для arb private dry-run перевести по $30-50 USDT на Binance и Bitget. Это ещё не live trading; это только проверка готовности ног и балансов.
4. По crypto strategy expansion идти через `scripts/strategy_pipeline.py`: BRC1/ATT1/ARF1 только после package replay против baseline, без ручного добавления стратегий в live.
5. Alpaca v38: ждать market-hour paper fills/protection и первый закрытый цикл перед реальным `$500` deposit.
