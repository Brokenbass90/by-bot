# Codex Night Handoff — 2026-05-03 → утро

## Главное за вечер

### Найден КРИТИЧНЫЙ root cause «0 trades за 5 дней» в canary v2

Live regime сменился `bear_chop → bull_chop` ~30 апреля. И:
1. **`configs/regime_overlay_bull_chop.env` НЕ СУЩЕСТВОВАЛ.** В репо были overlays для bear_chop, bear_trend, bull_trend — но не bull_chop. Дыра в покрытии режимов на 25%.
2. Мой ARF1 guard в `portfolio_allocator_policy_canary_v2.json` понижал `flat.bull_chop = 0.25`. С учётом canary mults и global = 0.7, эффективный ARF1 риск = ~0.09 (почти ноль).
3. `REGIME_OVERLAY_ENABLE=0` в canary v2 env — даже если бы overlay существовал, hot-reload отключён.

**Готовы фиксы (НЕ применены, ждут review):**

- `configs/regime_overlay_bull_chop.env` — новый, полное покрытие bull_chop
- `configs/portfolio_allocator_policy_canary_v2_1.json` — `flat.bull_chop=0.65, bounce1.bull_chop=0.85, impulse.bull_chop=0.6, breakout.bull_chop=0.55`
- `configs/crypto_income_live_canary_v2_1.env` — `REGIME_OVERLAY_ENABLE=1`, ENABLE_BOUNCE/IMPULSE/BREAKOUT (управляется per overlay)

См. `CLAUDE_NIGHT_PLAN_20260503.md` для подробностей.

## Что прошу тебя сделать ночью

### 1. Acceptance test для v2.1 (приоритет — высший)

**Цель:** убедиться что v2.1 даёт на бэктесте сравнимое с v2 поведение в bear-режимах + улучшение в bull-режимах.

```bash
cd /root/by-bot
git pull

# Validation 1: bull_chop window. Найти 60d в истории где регим был преимущественно bull_chop.
# Прогнать canary v2 (текущий live) и canary v2.1 на этом окне.
python3 backtest/run_portfolio.py \
  --env configs/crypto_income_live_canary_v2.env \
  --policy-path configs/portfolio_allocator_policy_canary_v2.json \
  --days 60 --end <bull_chop_period> --tag canary_v2_baseline_bullchop

python3 backtest/run_portfolio.py \
  --env configs/crypto_income_live_canary_v2_1.env \
  --policy-path configs/portfolio_allocator_policy_canary_v2_1.json \
  --days 60 --end <bull_chop_period> --tag canary_v2_1_bullchop

# Validation 2: bear_chop window (текущий live проверенный). Не должно стать хуже.
python3 ... --tag canary_v2_baseline_bearchop
python3 ... --tag canary_v2_1_bearchop
```

**Acceptance:**
- canary v2.1 в bull_chop окне даёт ≥ +5 net (vs canary v2 = ~0)
- canary v2.1 в bear_chop окне дает net ≥ 90% от canary v2 (т.е. не сильно деградировал)
- DD не хуже на > 1.5pp

**Если passed:**
- commit & push v2.1 + три файла
- redeploy на сервере: `bash scripts/deploy_canary_v2_1.sh` (или вручную: stop → swap env → restart)
- 24 часа monitoring → отчёт в `docs/CANARY_V2_1_FIRST_DAY.md`

### 2. Запустить 5 ночных autoresearch (параллельно)

Файлы готовы в `configs/autoresearch/`:

| spec | combos | назначение |
|---|---:|---|
| `asb1_bull_chop_repair_v1.json` | 432 | ASB1 для bull_chop (Pair 4) |
| `att1_density_v3_more_pivots_v1.json` | 864 | ATT1 более частая версия для bull_chop |
| `liquidity_sweep_reversal_v2_param_sweep_v1.json` | 486 | Codex'овский liquidity hunter |
| `elder_v3_macro_off_full_relax_v1.json` | 81 | Elder без macro gate |
| `pump_fade_v5_bear_window_v1.json` | 243 | pump_fade на shorts |

Команда:

```bash
cd /root/by-bot
mkdir -p logs/overnight_20260503
for spec in configs/autoresearch/asb1_bull_chop_repair_v1.json \
            configs/autoresearch/att1_density_v3_more_pivots_v1.json \
            configs/autoresearch/liquidity_sweep_reversal_v2_param_sweep_v1.json \
            configs/autoresearch/elder_v3_macro_off_full_relax_v1.json \
            configs/autoresearch/pump_fade_v5_bear_window_v1.json; do
  name=$(basename "$spec" .json)
  nohup .venv/bin/python3 scripts/run_strategy_autoresearch.py \
    --spec "$spec" --jobs 2 \
    > "logs/overnight_20260503/${name}.log" 2>&1 &
done
wait
```

Утром у пользователя `backtest_runs/autoresearch_2026050?_*` со свежими ranked_results.

### 3. Code review patches (если время есть)

Проверь готовые документы:
- `LIQUIDITY_HUNTER_V1_REVIEW_20260503.md` — 6 замечаний по liquidity hunter, согласен ли с порядком фикса?
- `PATCH_TIER1_orderLinkId_RETRY_20260429.md` — Tier-1 patch уже применён локально + 10 unit-тестов pass. Запушить?

### 4. NOT TODO

- Не вкладывать в Alpaca real money (broker-side trailing блокер)
- Не enable v7 sleeves
- Не deploy v2.1 без acceptance teste из шага 1
- Не трогать canary v2 в live до решения по v2.1

## Что я сделаю утром после твоего отчёта

1. Прочитаю результаты v2.1 acceptance + 5 ночных прогонов
2. Если v2.1 passed → готовлю financial roadmap «как из 40% годовых сделать 100%+»
3. Если что-то отвалилось — оперативный rollback план
4. Готовлю Alpaca $500 deploy roadmap (broker-side trailing концепт)
5. Веб audit + UX checklist

## Контакт

Утренний отчёт пиши в `docs/CODEX_NIGHT_RESULTS_20260504.md` с цифрами по каждому из 5 ночных прогонов + verdict acceptance v2.1.
