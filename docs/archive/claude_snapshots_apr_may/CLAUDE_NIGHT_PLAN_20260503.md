# Ночной план Claude — 2026-05-03 (вечер→утро)

## ROOT CAUSE «0 сделок за 5 дней» — НАЙДЕНО

Live state на 2026-05-03 19:00 UTC:
- regime = **`bull_chop`** (сменился с bear_chop ~30 апреля)
- global_risk_mult = 0.7
- macro = MACRO_BEAR fallback не активирован

**Проблема №1 — нет regime overlay для `bull_chop`.** В `configs/` существуют только:
- `regime_overlay_bear_chop.env`
- `regime_overlay_bear_trend.env`
- `regime_overlay_bull_trend.env`

Файла `regime_overlay_bull_chop.env` **нет**. Это покрытие 75%, не 100%.

**Проблема №2 — мой ARF1 guard душит flat в bull_chop.** Я создал `configs/portfolio_allocator_policy_canary_v2.json` с `flat.bull_chop = 0.25` для защиты от единственного red month. В сочетании с canary env (`FLAT_RISK_MULT=0.50`) и global=0.7 эффективный риск ARF1 в bull_chop = `0.25 × 0.7 × 0.50 = 0.0875` — почти ноль.

**Проблема №3 — `REGIME_OVERLAY_ENABLE=0` в canary v2 env.** Hot-reload оверлея отключён, чтобы overlay не перезатёр canary. Но это значит, что **смена режима НЕ меняет ENABLE-флаги стратегий** — бот живёт со «снимком» bear_chop overlay'я навсегда (если бы он применялся).

**Проблема №4 — orchestrator rate-limited Bybit:**
```
2026-04-29 08:50:09 [ORCH] ERROR fetch_4h cached fallback failed for BTCUSDT:
                            Bybit error 10006: Too many visits (rate limit)
```
Стало работать через cached fallback. Не критично, но regime может обновляться с задержкой.

### Эффективный live mult в bull_chop (ATT1+ARF1+midterm)

| sleeve | policy.bull_chop | × global 0.7 | × env mult | = effective |
|---|---:|---:|---:|---:|
| ATT1 | 0.95 | 0.665 | × ATT1_RISK_MULT 0.75 | **0.499** ✓ |
| flat (ARF1) | **0.25** (мой guard) | 0.175 | × FLAT_RISK_MULT 0.50 | **0.0875** ❌ |
| midterm | 0.85 | 0.595 | × MIDTERM_RISK_MULT 0.50 | **0.298** ✓ |

ARF1 фактически выключен в bull_chop. ATT1 жив, но с тугими параметрами (`R²≥0.7`, `RSI<52`, `pivot age=20`) и в boring market делает мало signals. Midterm — BTC/ETH pullback, в bull_chop пуллбэков мало.

## Что я готовлю прямо сейчас (план до утра)

### 1. Patch v2.1 — bull_chop fix (до пользователя апрува)

**Создаю два файла:**

(A) `configs/regime_overlay_bull_chop.env` — полноценный overlay для пропущенного режима:
- ATT1 active (longs > shorts, longs primary в bull)
- ARF1 active с **более строгими entry-фильтрами вместо мульт-урезания** (RSI 65+ для shorts, only at fresh resistance)
- ASB1 active (support bounce — primary long в bull)
- midterm active (pullback longs)
- breakdown OFF (не для bull)
- IVB1 active (impulse breakout long — primary в bull, мы его не пускали)
- v7 sleeves OFF (как в canary)

(B) Обновлённый `portfolio_allocator_policy_canary_v2.1.json`:
- `flat.bull_chop = 0.65` (с 0.25 до 0.65 — torgyem но осторожно, защита через overlay-фильтры)
- `bounce1.bull_chop = 0.85` (ASB1 включён)
- `impulse.bull_chop = 0.6` (IVB1 включён в research mode)
- остальное как canary_v2

(C) `crypto_income_live_canary_v2.1.env`:
- `REGIME_OVERLAY_ENABLE=1` (включаем hot-reload — без него все мои фиксы бесполезны)
- ENABLE_BOUNCE_TRADING=1 (раньше было 0)
- ENABLE_IMPULSE_TRADING=1 в research mode
- остальное наследуется из v2

### 2. Ночные autoresearch — 5 параллельных прогонов

Готовлю spec'и для запуска через `scripts/run_overnight_research_queue.sh` на сервере:

- `bounce_v2_bull_chop_repair_v1.json` — ASB1 для bull_chop с tight params
- `pump_fade_v5_bear_window_v1.json` — pump_fade reskin на bear фазах
- `liquidity_sweep_reversal_v1_param_sweep_v2.json` — Codex'овский liquidity hunter, sweep params
- `elder_v3_macro_off_full_relax_v1.json` — Elder без macro gate (он 0 trades иначе)
- `att1_density_v3_more_pivots.json` — ATT1 c relaxed pivot age + r2 для bull_chop частоты

К утру у пользователя будут ranked_results по всем пяти.

### 3. Liquidity hunter — мини code review + улучшения

Codex реализовал чёрновую версию (research-only). Smoke 90d дал PF=0.7. Я вижу 2 потенциальные улучшения:
- Контекст pool «свежесть»: pool, который был тронут N раз — overcounted. Надо filter `pool_touches < 2`.
- Symmetry checks long/short: возможно фильтры асимметричные.

Делаю отдельный документ с анализом + предлагаю v2.

### 4. Alpaca $500 deploy plan

Конкретный пошаговый roadmap:
- Что блокирует real money сейчас (broker-side trailing)
- Какой минимум кода/защиты нужно добавить
- Как запустить v38 с $500 без full trailing (с tighter manual stops через cron)
- Как параллельно тестировать более активные swing/intraday

### 5. Веб аудит

Quick scan веб-routes на актуальность данных + UX list.

## Чего точно НЕ делаю до пользователя апрува

- Не пушу в git
- Не меняю ничего в live canary (ATT1+ARF1+midterm продолжают «спать»)
- Не вкладываю $500 в Alpaca без явного разрешения
- Не enable'ю новые v7 рукава
- Не трогаю base risk_pct=1.0%

## Сводка к утру

К моменту, когда пользователь проснётся, у него будет:
1. Этот документ — диагноз 0 trades + план фикса
2. Готовые `regime_overlay_bull_chop.env`, `policy_canary_v2.1.json`, `crypto_income_live_canary_v2.1.env` — готовые к review и push
3. 5 spec'ов autoresearch для ночного прогона
4. Code review liquidity hunter v1 + предложение v2
5. Alpaca $500 deploy roadmap
6. Веб audit + UX checklist

Время — 2-3 часа моей работы.
