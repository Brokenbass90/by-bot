# Утренний отчёт — 2026-05-03 → 2026-05-04
**Автор:** Claude
**Спрашиваешь — отвечаю по списку.**

---

## ВОПРОС 1: Почему 0 сделок за 5 дней?

**ROOT CAUSE НАЙДЕН.** Регим сменился `bear_chop → bull_chop` ~30 апреля. И:

1. **`configs/regime_overlay_bull_chop.env` НЕ СУЩЕСТВОВАЛ** в репо. Покрытие режимов было 75%, не 100%.
2. **Мой ARF1 guard** в `portfolio_allocator_policy_canary_v2.json` понижал `flat.bull_chop=0.25` — это эффективно отключило ARF1.
3. **`REGIME_OVERLAY_ENABLE=0`** в canary v2 env заблокировал hot-reload — даже если бы overlay был, бот бы его не читал.

**Я виноват.** Мой первоначальный guard был сделан как защита от единственного red month, не предвидел смены режима.

**Фикс готов** (НЕ применён, ждёт твоего апрува):
- `configs/regime_overlay_bull_chop.env` — новый, полное покрытие bull_chop
- `configs/portfolio_allocator_policy_canary_v2_1.json` — flat.bull_chop=0.65 (с 0.25), bounce1.bull_chop=0.85, impulse.bull_chop=0.6
- `configs/crypto_income_live_canary_v2_1.env` — REGIME_OVERLAY_ENABLE=1, ASB1+IVB1+breakout включены через overlay

Acceptance test для Codex прописан. После теста — push в git.

---

## ВОПРОС 2: Liquidity hunter Codex'а — какое мнение?

**Логика классическая ICT/SMC, основа корректна.** Sweep + reclaim + rejection wick — стандарт. Но есть **6 замечаний:**

1. `min_pool_touches=2` ловит шум (сам экстремум всегда в touches → реально =1 extra touch). Поднять до 3+.
2. **Cooldown похоже global per-instance, не per-symbol** — после одной сделки на BTC молчит 2 часа на ВСЕХ символах. Это режет частоту 10×.
3. Нет regime gate — fade в strong trend опасен.
4. Нет partial TP / breakeven / trailing — все exit одним shot.
5. `max_sweep_atr=0.9` отрезает паника-свипы (часто лучшие entry).
6. Нет pool persistence — pool, появившийся 2 бара назад, считается реальным.

**Полный обзор:** `LIQUIDITY_HUNTER_V1_REVIEW_20260503.md`. Я предложил v2 patch + autoresearch sweep на 486 комбинаций (готов в configs/autoresearch).

---

## ВОПРОС 3: Alpaca — реально ли запустить $500?

**ДА, можно деплоить $500 в течение 1-2 недель.**

**Главная находка:** bracket-orders на стороне брокера УЖЕ работают (`alpaca_paper_bridge.py:418-431` — `order_class=bracket` с TP+SL шлются прямо Alpaca). То есть «broker-side trailing блокер» из Codex'овых отчётов был неполной правдой — статичный bracket уже есть, нет только динамического trailing-stop. Это НЕ блокер.

**Ожидание дохода:**
- v38 hybrid top4 на $500 → ~$11/мес средний профит (это compounder, не income)
- v38 + intraday/swing layer на $500 → ~$30-50/мес (если intraday работает)
- На $5000 → $150-200/мес чистыми

**Полный roadmap в 4 stages:** `ALPACA_500_DEPLOY_PLAN_20260503.md`.

Stage 1 (real $500 deploy) можно начать сразу после 7 дней paper smoke, с conservative `MAX_POSITION_PCT=0.20` и `risk_pct=0.005`.

---

## ВОПРОС 4: Веб удобный?

**Бекенд здоровый, UX слабый.** 13 API endpoints, TOTP auth, mtime-aware данные. Но фронт:

- Нет «top-bar 1-glance summary» (today PnL, open positions, last trade, health)
- **Нет last_trade_age warning** — если бы был, ты бы поймал «0 trades 5 дней» на 2-й день автоматически
- Нет regime history timeline — ты не видел смены bear→bull, отсюда не подозревал causa
- Allocator state не объясняет «почему ARF1 фактически не торгует»
- TG-алерты без actionable advice

**Мой главный совет:** перед обещанием «оставить бот на месяцы» сделать pri-1+2 fixes (top-bar + last_trade warning). Без них «оставить без внимания» — самообман.

Полный аудит: `WEB_AUDIT_20260503.md`.

---

## Что я положил для Codex на ночь

5 autoresearch spec'ов в `configs/autoresearch/`:

| spec | combos | назначение |
|---|---:|---|
| `asb1_bull_chop_repair_v1.json` | 432 | ASB1 в bull_chop (Pair 4) |
| `att1_density_v3_more_pivots_v1.json` | 864 | ATT1 более частая для bull_chop |
| `liquidity_sweep_reversal_v2_param_sweep_v1.json` | 486 | liquidity hunter param sweep |
| `elder_v3_macro_off_full_relax_v1.json` | 81 | Elder без macro gate |
| `pump_fade_v5_bear_window_v1.json` | 243 | pump_fade на shorts |

**Итого 2106 backtest-runs.** Codex запустит параллельно ночью, утром у тебя ranked_results.

Полное TZ для Codex: `CODEX_NIGHT_HANDOFF_20260503.md`.

---

## Что меня тревожит долгосрочно

### Tier-1 patch (orderLinkId+retry) — НЕ задеплоен
Я применил его локально 5 дней назад и закрыл task #19, но Codex не запушил. **Без этого депозит нельзя растить.** Нужно проверить статус и запушить.

### Bot слепой к смене режимов
В системе нет авто-overlay generation для всех 4 режимов. Если когда-то появится 5-й (`bear_capitulation` etc.) — повторим эту же ошибку. Нужен гард в `setup_server_crons.sh`: «нет overlay для текущего регима — алерт».

### 5 дней без сделок и никто не заметил
Live monitoring сломан в смысле UX. У бота нет чёткого «health = trades_per_day_in_expected_range». Phase 3 контракт это решает, но он не реализован. **Это блокер для «бот без внимания на месяцы».**

---

## Реалистичный путь к 100% годовых

Сейчас (теоретически по бэктесту) canary v2 = 45% годовых. Чтобы выйти на 100%+:

| шаг | потенциал |
|---|---:|
| canary v2.1 fix (bull_chop overlay + ARF1 guard relax) | вернёт baseline |
| ASB1 bull-chop repair | +10-15% годовых (Pair 4) |
| ATT1 density v3 | +5-10% (если винер сохранится в WF-22) |
| IVB1 r073 promote (после WF-22) | +5-10% |
| sloped_channel split LONG/SHORT (Pair 2) | +8-15% |
| liquidity hunter v2 (если param sweep даст PF≥1.3) | +10-20% |
| ARF1↔ASB1 swap (Pair 4) | +3-8% |
| AI overlay gate shadow→live (после 2 недель доказательств) | +5-15% |

**Реалистично:** 60-80% годовых через 2 месяца работы.
**Оптимистично:** 100-120% годовых через 3 месяца.

Это не «несколько десятков процентов в месяц». **На разумных edge'ах в крипте 50-100% годовых — это уже агрессивный target.** Если хочешь больше — нужен или leverage (опасно), или арбитраж (нужны другие инструменты), или разные exchange'и.

---

## TL;DR на 30 секунд

1. **Главный bug «0 trades» — мой**: ARF1 guard убил торговлю в новом режиме. Фикс готов, ждёт апрува.
2. **Codex'овский liquidity hunter** — норм основа, есть 6 замечаний, ночью будет sweep на 486 комбинаций.
3. **Alpaca $500 деплой реален** через 1-2 недели — bracket orders уже на брокере, не блокер.
4. **Веб бекенд OK, UX слаб** — нужны top-bar и last_trade_age warning ради «оставить бот на месяцы».
5. **Tier-1 patch ещё не задеплоен Codex'ом** — это блокер для роста депозита.
6. **Реалистично 60-100% годовых через 2-3 месяца** — не несколько десятков в месяц.

Утром после твоего апрува по v2.1 fix → пушим → бот начинает торговать → ждём первых сделок 24-48 часов → дальше идём по 5-pair плану + Alpaca.
