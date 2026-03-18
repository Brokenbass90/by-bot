# .env Changes — 2026-03-18 Audit

## ФАЗА 1: Разблокировать breakout (КРИТИЧНО)

### Изменение 1: Убрать quality score блокировку
```
# БЫЛО:
BREAKOUT_QUALITY_MIN_SCORE=0.52

# СТАЛО:
BREAKOUT_QUALITY_MIN_SCORE=0.0
```

**Почему:** В бэктесте quality=0.52 пропускает 100% сделок (идеальные условия).
В лайве реальные спреды/slippage дают score < 0.52 → бот блокирует ВСЕ входы.
Результат: 0 сделок на лайве за всё время с этим фильтром.

**Риск:** Минимальный. Quality score boost остаётся включён — хорошие входы
получают бонус к размеру позиции. Плохие входы проходят но с базовым размером.

---

## ФАЗА 2: Включить sloped channel для ATOM (после наблюдения breakout 1-2 недели)

### Изменение 2: Включить range trading
```
# БЫЛО:
ENABLE_RANGE_TRADING=0

# СТАЛО:
ENABLE_RANGE_TRADING=1
```

### Изменение 3: Настройки sloped channel
```
# Добавить в конец .env:
ASC1_ALLOW_LONGS=0
ASC1_ALLOW_SHORTS=1
ASC1_SYMBOL_ALLOWLIST=ATOMUSDT,LINKUSDT
ASC1_MAX_ABS_SLOPE_PCT=2.0
ASC1_SHORT_MIN_RSI=60
ASC1_SHORT_MIN_REJECT_DEPTH_ATR=0.75
ASC1_SHORT_MAX_NEAR_UPPER_BARS=2
ASC1_SHORT_NEAR_UPPER_ATR=0.15
ASC1_SL_ATR_MULT=0.90
ASC1_TP1_FRAC=0.55
```

**Почему:** ATOM показал 6/7 позитивных месяцев, WR 58.8%, PF 2.49, net +$4.89 за год.
LINK маргинально позитивен. Остальные монеты убыточные с этими настройками.

**ВАЖНО:** sr_range_strategy.py полностью закомментирован.
Нужно подключить alt_sloped_channel_v1 через другой путь —
либо раскомментировать sr_range_strategy и адаптировать,
либо создать новый entry point в smart_pump_reversal_bot.py.

---

## ФАЗА 3: Autoresearch для оптимизации (на сервере)

### Запуск поиска лучших конфигов sloped channel:
```bash
python3 scripts/run_strategy_autoresearch.py \
  --config configs/autoresearch/flat_slope_adaptive_families_v1.json
```

### Запуск поиска Triple Screen конфигов:
```bash
python3 scripts/run_strategy_autoresearch.py \
  --config configs/autoresearch/triple_screen_adaptive_v1.json
```

---

## Результаты бэктестов (подтверждение)

| Тест | Сделки | WR | Net | PF | Месяцы+/- |
|------|--------|-----|------|-----|-----------|
| Breakout quality=0.0 (5 монет, 180d) | 375 | 61.3% | +$18.96 | 1.37 | — |
| Sloped ATOM solo (360d) | 17 | 58.8% | +$4.89 | 2.49 | 6/7 ✅ |
| Sloped ATOM+LINK (360d) | 25 | 52% | +$5.21 | 1.98 | 5/8 |
| Combined breakout+sloped (180d) | 310 | 62.6% | +$19.60 | 1.47 | 9/12 ✅ |
| Triple Screen default (360d) | 23 | 34.8% | -$3.59 | 0.59 | — |

**Вывод:** Breakout — основной доход. Sloped ATOM — стабильная добавка.
Triple Screen требует per-coin настройку (autoresearch).
