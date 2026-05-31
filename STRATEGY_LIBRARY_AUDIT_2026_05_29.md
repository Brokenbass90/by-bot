# Полный аудит библиотеки стратегий — 75 модулей
*Статический аудит. Для Codex и для понимания что есть.*

---

## Категории

### 🟢 PRODUCTION (wired в боте) — 14 стратегий

Эти включены через `(ENABLE_X, "module")` tuple в `smart_pump_reversal_bot.py`. Имеют env-флаги, risk_mult, allowlist.

| Family | Модуль | Sweep history | Статус |
|---|---|---:|---|
| ASC1 | alt_sloped_channel_v1 | 31 | Активная, shorts на ATOM/LINK/DOT |
| ARF1 | alt_resistance_fade_v1 | 30 | Активная, shorts на alt'ах |
| BREAKDOWN | alt_inplay_breakdown_v1 | 21 | Активная, shorts only |
| BREAKOUT | inplay_breakout | 21 | Wired через shim в archive/ |
| ATT1 | alt_trendline_touch_v1 | 11 | Shadow mode сейчас |
| RANGE | alt_range_scalp_v1 | 9 | Wired через shim в archive/ |
| ETS2 | elder_triple_screen_v2 | 9 | Wired, ждёт sweep results |
| IVB1 | impulse_volume_breakout_v1 | 9 | Wired |
| BOUNCE1 | alt_support_bounce_v1 | 5 | Wired |
| BRC1 | alt_bear_regime_continuation_v1 | 3 | Shadow, ждёт sweep |
| ASB1 | alt_slope_break_v1 | 1 | Wired, ждёт sweep |
| HZBO1 | alt_horizontal_break_v1 | 1 | Wired |
| ASM1 | alt_sloped_momentum_v1 | 1 | Wired |
| PUMP_FADE_V2 | pump_fade_v2 | 2 | Wired через shim в archive/ |

**Из 14 wired реально активно сейчас 4-5** (ASC1, ARF1, BREAKDOWN, ETS2, Midterm). Остальные либо в shadow либо отключены через ENABLE флаги.

---

### 🟡 CANDIDATES (имеют sweep history, не wired) — 27 стратегий

У них есть код, есть sweep-конфиги, но в боте не подключены. Можно подключить если sweep докажет PF > 1.591.

**Топ кандидаты по sweep активности:**
| Family | Модуль | Sweeps | Прогноз |
|---|---|---:|---|
| MTPB | btc_eth_midterm_pullback | 19 | Готов к wire, ждёт acceptance gate |
| BTC_CYCLE_PULLBACK | btc_cycle_pullback_v1 | 11 | Долгосрочные swing на BTC |
| BTC_REGIME_FLIP | btc_regime_flip_continuation_v1 | 11 | Trend continuation на сменах режима |
| BTC_REGIME_RETEST | btc_regime_retest_v1 | 11 | Retest support/resistance |
| FR | funding_rate_reversion_v1 | 4 | Funding overlay (наш Wave C-bis) |
| MICRO_SCALPER_BOUNCE | micro_scalper_bounce_v1 | 4 | 5m scalping |
| AWPF1 | alt_whale_print_follow_v1 | 2 | Following large trades |
| MTPB3 | btc_eth_midterm_v3 | 2 | Updated midterm |

**Все 27 кандидатов** уже частично проверены sweep-ами. Из них к году 2-3 ожидаемо **5-10 пройдут acceptance gate** (PF > 1.591, DD < 7%).

---

### 🔴 EXPERIMENTAL / DEAD (ни wired ни swept) — 34 модуля

Скелеты, концепты, или умершие проекты. **Большинство — не трогать сегодня**, но 5-7 имеют потенциал.

**Потенциально живые:**
| Модуль | LOC | Описание |
|---|---:|---|
| alt_stablecoin_depeg_arb_v1 | 161 | Stablecoin депеги — наш Wave C-bis |
| basis_arb_v1 | 294 | NEW, наша basis arb (написал сегодня) |
| alt_squeeze_breakout_v1 | 267 | Bollinger squeeze breakout |
| alt_volume_spike_momentum_v1 | 394 | Volume spike → momentum |
| alt_pullback_continuation_v1 | 252 | Pullback в тренде |
| alt_momentum_breakout_v1 | 271 | Momentum breakout |
| alt_trendline_touch_v2 | 902 | v2 ATT (улучшенная) |

**Технический шум (можно архивировать):**
- 6 файлов `*_live.py` — это thin wrappers, оставить
- alt_bear_breakdown_v1, alt_bear_consolidation_short_v1, alt_elder_revived_v1 — старые
- alpaca_dynamic_v3_event, alpaca_dynamic_v4_event — для Alpaca, не для крипты

---

## Что я СДЕЛАЛ за эту сессию по этой части

1. ✅ Карта 75 модулей в `runtime/strategy_registry.json` (автообновляемая)
2. ✅ Drift-детектор показывает 3 модуля с проблемами import path
3. ✅ Auto-apply поддерживает 8 семейств (ATT1, BRC1, ASB1, ARF1, ASC1, ETS2, IVB1, BREAKDOWN + новые добавил)
4. ✅ Validator проверяет схему всех sweep-конфигов

**Что Codex должен сделать после деплоя (в порядке приоритета):**

| Приоритет | Что | Эффект |
|---|---|---|
| 1 | Запустить 5 sweep'ов которые я починил (att1_rsi_relax, bear_brc1, asc1_longs, asb1, elder_ema) | Активирует 3-5 новых стратегий в портфель |
| 2 | Запустить package_funding_harvest_v1 | Активирует funding overlay (5% APR) |
| 3 | Запустить basis_arb_backtest.py | Активирует basis arb (5-8% APR) |
| 4 | Sweep'ы на топ-7 candidates (MTPB, BTC_CYCLE, BTC_REGIME_FLIP, BTC_REGIME_RETEST, FR, MICRO_SCALPER, AWPF1) | +3-5 стратегий к году 1 |
| 5 | Аудит 7 потенциально живых experimental | +1-2 стратегии к году 2 |

**К концу года 1**: ожидаемо **8-10 активных стратегий** вместо текущих 4-5. К году 2 — **12-15**. К году 3 — **15-18** с регулярной ротацией.

---

## Долгосрочная защита от деградации (5-10 лет)

Что **УЖЕ есть** для борьбы с деградацией:
1. `live_vs_backtest_monitor` — автопауза при падении PF
2. `regime_change_reopt` — авто-эксперименты при смене режима
3. `auto_apply_research_winner` — обновляет параметры при новых winner
4. `research_queue_worker` — постоянно гонит новые эксперименты

Что **НУЖНО добавить** в Wave C (через 3-6 мес после деплоя):
1. **Champion-Challenger framework** — каждая активная стратегия имеет дублёра в paper с мутированными параметрами. Если challenger 60 дней лучше — автопромоушн
2. **AI proposal pipeline** — Haiku/Sonnet раз в неделю предлагает идеи на основе live статистики
3. **Strategy genome mutations** — раз в месяц 1-2 рабочие стратегии получают ±10% мутацию параметров → автоматически в sweep
4. **Archive deprecation** — если стратегия 90 дней PF < 1.0 → автоматически в архив, ротируем
5. **Out-of-sample re-testing** — раз в квартал прогон всех стратегий на свежих 90d (которые не использовались в их sweep'е)

**Эти 5 пунктов = "система которая учится 5-10 лет"**. Без них через 2-3 года стратегии **могут начать деградировать** под новый рыночный режим. С ними — **бот сам себя обновляет**.

Сегодня я не пишу эти 5 — это работа на отдельную сессию через 2-4 недели когда увидим как ведёт себя в живую.

---

## Усиления стратегий — сделано 2026-05-29

### 1. `strategies/basis_arb_v1.py` — добавил селектор + partial profits

**Что добавлено:**
- `BasisArbSelectorConfig` — конфиг для выбора лучших позиций из пула
- `BasisArbV1Selector` — ранжирует кандидатов по `expected_pnl_pct`, выбирает top-N в рамках доступной маржи с резервом 30% на emergency exits
- `partial_profit_targets()` — генерирует план частичных закрытий: 33% при 50% конвергенции + 33% при 70% + 34% при финальной

**Что это даёт:**
- При 3 одновременных opportunities ($BTC, $ETH, $SOL с разными basis spread) — бот не открывает все три, а **выбирает лучшие 2** с максимальным expected PnL
- Margin guard защищает от full-margin entries — если capital почти весь занят, новые сделки не открываются
- Partial profits **снижают вариацию PnL** — половина прибыли фиксируется на середине пути, не ждём идеальной конвергенции
- Проверено unit-тестом: BTC (basis 0.4%) → ETH (0.3%) → SOL (0.35%) ранжированы в правильном порядке по expected_pnl_pct

### 2. `strategies/funding_hold_v1.py` — добавил quality scoring

**Что добавлено:**
- `min_funding_events: int = 60` — отбраковка свежих монет (нет надёжной истории)
- `sigma_penalty_weight: float = 0.3` — штраф за вариативность funding (стабильные > спайков)
- `min_mean_funding_rate: float = 5e-6` — отбраковка монет с тонким funding (не покрывает fees)
- `_quality_score()` — композитный score: `net_usd × events_score × (1 - sigma_penalty)`
- 3-phase select: hard filters → ranking by quality → greedy fill with concentration guard

**Что это даёт:**
- Старый код выбрал бы NEWCOIN с $8 net и 30 events (cherry-pick). Новый отбраковывает (too few events).
- Старый код пропускал TINYCOIN с микроскопическим funding. Новый отбраковывает (rate too small).
- BTC/ETH/XRP (стабильные majors) теперь **выше в ранжировании** чем альты с разовыми спайками.
- Проверено: на test set BTC/ETH/XRP отобраны, NEWCOIN и TINYCOIN отброшены с причинами.

### 3. Не делал сегодня (приоритеты для следующей сессии)

| Что | Где | Эффект |
|---|---|---|
| Multi-timeframe confirmation для ATT1 (4H pivot before 1H entry) | `strategies/alt_trendline_touch_v1.py` | +5-10% к WR, меньше ложных сигналов |
| ARF1 add BTC/ETH coverage (сейчас без них) | `.env` config | +20% больше сигналов |
| BRC1 trailing stop on partial profits | `strategies/alt_bear_regime_continuation_v1.py` | защита PnL в bear chop |
| ETS2 EMA slope mode wire (skeleton есть, нужно подключить флаг) | `.env` + small bot patch | разблокирует Elder сигналы |
| Out-of-sample backtest pipeline (вручную делать раз в квартал) | новый скрипт + cron | защита от overfit |

**Эти 5 — следующая сессия через 2-4 недели**, когда живые данные подскажут что приоритетнее.

---

## Что стоит усилить из CANDIDATES (топ-5 по потенциалу)

| Стратегия | Sweep history | Действие | Ожидание |
|---|---:|---|---|
| **MTPB** (btc_eth_midterm_pullback) | 19 sweeps | Wire через `ENABLE_MTPB_TRADING` + RSI_LONG_MAX до 60 | +1-2 сделки/нед на BTC/ETH |
| **BTC_REGIME_FLIP** (btc_regime_flip_continuation_v1) | 11 sweeps | Sweep на 365d, ищем PF>1.5 | trend continuation на сменах режима |
| **FR** (funding_rate_reversion_v1) | 4 sweeps | Wire после backtest_funding_capture pass | overlay 3-5% APR |
| **MICRO_SCALPER_BOUNCE** | 4 sweeps | Sweep на 5m данных, тестировать на bear chop | дневные сделки в плоском рынке |
| **AWPF1** (alt_whale_print_follow_v1) | 2 sweeps | Sweep с >$50k trades filter | следование за крупными игроками |

**Из 27 candidates 5 имеют топ-приоритет**. Codex после деплоя должен прогнать их sweep в первую очередь. С нашей очередью (`research_queue.jsonl` + worker) это автоматически — он просто ставит в queue, worker подхватит.
