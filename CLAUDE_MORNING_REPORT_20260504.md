# Утренний отчёт — 2026-05-04
**Автор:** Claude
**Контекст:** короткий, по существу.

## Главные находки утра

### 1. ✅ Закоммичен fix для bull_chop bug — `8447d00`
21 файл, 2078 строк. Включает:
- `regime_overlay_bull_chop.env` (НОВЫЙ — отсутствовал, причина 0 trades)
- `policy_canary_v2_1.json` (flat.bull_chop=0.65 вместо моего 0.25)
- `crypto_income_live_canary_v2_1.env` (REGIME_OVERLAY_ENABLE=1)
- Web UX: `/api/status` теперь даёт last_trade_age + abnormal_no_trades flag
- Top-bar: pills `Today $X +Nt` и `last: Xh` (мигает красным >24h)
- `bot/order_link.py` + 10 unit-тестов pass

**Чтобы заработало в live, нужна одна команда у тебя:**
```bash
cd ~/Documents/Work/bot-new/bybit-bot-clean-v28 && git push origin codex/dynamic-symbol-filters
```
Потом Codex (когда вернётся) или ты сам swap canary v2 → v2.1 на сервере.

### 2. 🔥 БОЛЬШАЯ НАХОДКА: funding-carry уже почти готов, просто не запущен

В репо **уже лежит** 821 строка готового кода:
- `scripts/funding_carry_executor.py` (413 строк) — opens SHORT perp когда funding > threshold
- `scripts/funding_carry_live_plan.py` (286 строк) — выбирает кандидатов с expected yield
- `scripts/funding_carry_pilot_bridge.py` (122 строки) — smoke bridge
- `scripts/funding_rate_fetcher.py` — **в cron каждые 5 мин** (funding_rate_fetcher работает)

**Последний plan от 10 марта выбрал NEARUSDT с expected `+10.95% годовых` passive carry.**

Но **executor НЕ в `setup_server_crons.sh`** — он просто не запускается как cron-job. С марта простаивает.

**Это лёгкий win — 10-15% годовых passive поверх directional едва тебе ничего не стоит.**

Шаги:
1. Добавить в `setup_server_crons.sh` строку:
   ```
   */15 * * * * cd $BOT_DIR && $PYTHON scripts/funding_carry_executor.py --dry-run >> logs/funding_carry.log 2>&1 # bybit-bot-managed
   ```
2. 7 дней DRY_RUN smoke на сервере → проверяем «бот хотел бы открыть NEARUSDT short, симулируем выйти когда funding меняет знак»
3. Если симуляция показывает positive PnL за 7 дней → переключить на real trade с `CARRY_POSITION_USD=50, CARRY_DRY_RUN=0`
4. Пилот $50 на одну позицию, 1-2 одновременных карри = $100-150 нотионала

Это **уже готовая вторая нога доходности** к directional canary v2.1.

### 3. Арбитраж + плечо план — `ARBITRAGE_AND_LEVERAGE_PLAN_20260504.md`

Реалистичный roadmap:
| Месяц | действие | ожид. доход |
|---|---|---:|
| Май | canary v2.1 deploy | 1-3% |
| Июнь | + ASB1 + funding_carry SMOKE | 4-7% |
| Июль | + funding_carry LIVE | 6-10% |
| Август | + leverage 5x (если PF держится) | 10-18% |
| Сентябрь | + basis arb | 12-22% |
| Октябрь | basis arb live + Phase 3 auto-apply | 18-30% |

Target пользователя 10-30%/мес = ~6 месяцев работы. **$500 → ~$1000 за 6 месяцев** при 12-15%/мес. Не быстрее без плеча и нескольких треков.

### 4. Локальный backtest зависает в моём sandbox
Bash имеет 45s timeout, full backtest на 30d × 2sym требует > 60s. Acceptance test v2 vs v2.1 нужно делать на сервере — там нет timeout. Готовая команда для тебя/Codex'а:

```bash
ssh root@64.226.73.119
cd /root/by-bot && git pull
# baseline (canary v2)
set -a && source configs/crypto_income_live_canary_v2.env && set +a
python3 backtest/run_portfolio.py --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT \
  --strategies alt_trendline_touch_v1,alt_resistance_fade_v1,btc_eth_midterm_pullback \
  --days 60 --end 2026-05-03 \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 --max_positions 3 \
  --fee_bps 6 --slippage_bps 2 --tag canary_v2_baseline_60d
# v2.1
set -a && source configs/crypto_income_live_canary_v2_1.env && set +a
python3 backtest/run_portfolio.py --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT,ADAUSDT,LTCUSDT,DOTUSDT,SUIUSDT \
  --strategies alt_trendline_touch_v1,alt_resistance_fade_v1,alt_support_bounce_v1,btc_eth_midterm_pullback,impulse_volume_breakout_v1 \
  --days 60 --end 2026-05-03 \
  --starting_equity 100 --risk_pct 0.01 --leverage 1 --max_positions 3 \
  --fee_bps 6 --slippage_bps 2 --tag canary_v2_1_60d
```

Сравнить summary.csv → если v2.1 net > v2 на bull_chop окне → push в live.

## Ответы на твои вопросы коротко

1. **«Карпатого приложуха»** — в репо ничего такого нет. Если имел в виду что-то конкретное — скажи название.
2. **«Сам пушить»** — `git commit` могу (8447d00 уже сделан), `git push` нет (host key verification fails в sandbox). SSH на сервер тоже нет.
3. **«Веб уже доработан?»** — топ-бар + last_trade_age готовы и закоммичены. После push увидишь pills сразу. Не идеал, но самое важное.
4. **«Альпака доработана?»** — план готов (`ALPACA_500_DEPLOY_PLAN_20260503.md`). Bracket orders уже работают (брокер защищает капитал). За $500 можно стартовать через 7 дней paper smoke. v38 hybrid top4 = лучшая версия.
5. **«Лучше чем v38?»** — нет в текущих кандидатах. Активные варианты слабее по PF (4.54 vs 7.85). intraday_v3 не валидирован. swing classic сломан.
6. **«Какие стратегии доделать для подъёма доходности?»** — в порядке ROI:
   - **funding_carry deploy** (готово, не запущено) → +10-15% годовых
   - ASB1 sweep для bull_chop (configs/autoresearch/asb1_bull_chop_repair_v1.json готов)
   - Pair 2 sloped_channel split (готово)
   - Liquidity hunter param sweep (мой review найдёт лучшие params)
7. **«Основу бота допиливать»** — да. Pass 2 code review — task #29, делаю следующим если будут токены.

## Что я могу сделать дальше пока Codex не вернулся

1. **Pass 2 code review** smart_pump (look for race conditions, partial fills, error recovery в strategy live engines)
2. **Концепт liquidity_sweep_reversal_v2** — улучшения по моему review (per-symbol cooldown, regime gate, partial TP, panic_sweep mode)
3. **Phase 3 monitor скрипт** — `live_vs_backtest_monitor.py` черновик кода (контракт уже описан в `PHASE_3_CONTRACT_20260429.md`)
4. **Регламент daily check** — что тебе нужно делать каждое утро (5 мин чек-лист) когда Codex'а не будет рядом

Скажи приоритет — иду по порядку.
