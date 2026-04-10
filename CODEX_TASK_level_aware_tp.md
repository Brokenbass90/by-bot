# Codex Task: Level-aware TP in alt_inplay_breakdown_v1.py

## Проблема

`strategies/alt_inplay_breakdown_v1.py` выставляет TP исключительно по ATR:
```python
tp2 = entry - self.cfg.rr * risk
```

Стратегия знает о пробитом уровне S1 (`self._armed["level"]`) но не знает о
следующем крупном уровне поддержки S2 ниже. Если S2 находится между entry и TP,
цена дойдёт до S2, отскочит — и либо заберёт прибыль до того как TP сработает,
либо вернёт позицию обратно до SL. Это реальная потеря edge.

## Правильная логика

Шорт открывается после пробоя S1 вниз. TP нужно выставлять ВЫШЕ следующего
крупного уровня поддержки S2, а не ниже него:

```
S1 (пробитый уровень)  ← вход в шорт здесь
↓
S2 (следующая поддержка) ← TP должен быть на уровне S2 + buffer, НЕ ниже
↓
ATR-based TP (старый)  ← может быть ниже S2 — это и есть баг
```

После выхода по TP около S2:
- Если S2 держит → support_bounce_v1 независимо видит отскок и открывает лонг
- Если S2 пробивается → breakdown_v1 видит новый пробой и снова вооружается

## Что нужно сделать

### 1. Добавить параметры в AltInplayBreakdownV1Config:

```python
# Level-aware TP parameters
next_level_lookback_mult: float = 2.0   # расширенный lookback = lookback_h * mult
next_level_buffer_atr: float = 0.30     # буфер выше S2 для TP (в ATR единицах)
next_level_tp_enable: bool = True       # включить/выключить level-aware TP
```

Env переменные:
```
BREAKDOWN_NEXT_LEVEL_LOOKBACK_MULT
BREAKDOWN_NEXT_LEVEL_BUFFER_ATR
BREAKDOWN_NEXT_LEVEL_TP_ENABLE
```

### 2. Добавить функцию `_find_next_support_below(lows, current_level, atr)`:

```python
def _find_next_support_below(lows: list, current_level: float, atr: float, min_gap_atr: float = 1.0) -> Optional[float]:
    """
    Найти следующий крупный уровень поддержки ниже current_level.

    Алгоритм:
    1. Из списка lows выбрать значения ниже (current_level - min_gap_atr * atr)
    2. Сгруппировать близкие значения (в пределах 0.5 ATR) в кластеры
    3. Взять кластер с наибольшим количеством касаний ближайший к current_level сверху
    4. Вернуть верхнюю границу этого кластера

    Если подходящих уровней нет — вернуть None.
    """
    threshold = current_level - min_gap_atr * atr
    candidates = [l for l in lows if l < threshold]
    if not candidates:
        return None

    # Кластеризация: группируем в пределах 0.5 ATR
    candidates.sort(reverse=True)  # высшие сначала
    clusters = []
    current_cluster = [candidates[0]]
    for val in candidates[1:]:
        if current_cluster[-1] - val <= 0.5 * atr:
            current_cluster.append(val)
        else:
            clusters.append(current_cluster)
            current_cluster = [val]
    clusters.append(current_cluster)

    # Берём ближайший к current_level кластер (первый после сортировки reverse)
    if not clusters:
        return None
    best = clusters[0]
    return max(best)  # верхняя граница кластера
```

### 3. Применить в `_arm_structure()`:

При арминге вычислить и сохранить next_support если он найден:

```python
# В конце _arm_structure(), перед self._armed = {...}:
next_support = None
if self.cfg.next_level_tp_enable:
    wider_lookback = int(self.cfg.lookback_h * self.cfg.next_level_lookback_mult)
    rows_wide = store.fetch_klines(store.symbol, self.cfg.structure_tf, wider_lookback + 10) or []
    if rows_wide:
        all_lows = [float(r[3]) for r in rows_wide]
        next_support = _find_next_support_below(all_lows, support, atr)

self._armed = {
    "level": support,
    "next_support": next_support,   # None если не найден
    "atr": atr,
    ...
}
```

### 4. Применить в `_signal_from_entry_bar()`:

```python
# После вычисления tp2:
tp2 = entry - self.cfg.rr * risk

# Level-aware TP: если есть следующий уровень поддержки и он ВЫШЕ tp2,
# переместить TP чуть выше этого уровня (чтобы не бороться с S2)
next_support = self._armed.get("next_support") if self._armed else None
if (
    self.cfg.next_level_tp_enable
    and next_support is not None
    and next_support > tp2  # S2 находится выше нашего ATR-TP
):
    # TP = S2 + небольшой буфер (чуть выше уровня, чтобы взять часть движения до него)
    level_tp = next_support + self.cfg.next_level_buffer_atr * atr
    if level_tp < entry and level_tp > tp2:
        # Только если level_tp даёт хоть какой-то profit и лучше чем ATR-TP
        tp2 = level_tp
        # tp1 тоже пересчитать чтобы он был между entry и tp2
        tp1 = entry - (entry - tp2) * 0.5

# Если next_support <= tp2 — уровень ниже нашего TP, можно идти дальше.
# В этом случае ATR-based TP остаётся.
```

### 5. Логировать decision в reason:

```python
reason = f"{reason}+level_tp" if next_support and tp2 != (entry - self.cfg.rr * risk) else reason
```

## Тестирование

После изменения запустить:

```bash
# Базовый smoke
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT \
  --strategies alt_inplay_breakdown_v1 \
  --days 90 \
  --tag level_tp_test \
  --starting_equity 100 --risk_pct 0.01

# Сравнить с baseline (без level-aware TP):
# BREAKDOWN_NEXT_LEVEL_TP_ENABLE=0 — должно дать прежний результат
# BREAKDOWN_NEXT_LEVEL_TP_ENABLE=1 — должно дать более высокий WR, меньше trades обратно отменённых
```

Ожидаемый эффект: WR вырастет (меньше сделок которые "почти дошли" до TP и вернулись),
trades count немного упадёт (TP ближе), но PF вырастет за счёт WR.

## Важно

- `next_level_tp_enable=True` — дефолт, но с безопасным фолбэком если уровень не найден
- Если next_support не найден → используется стандартный ATR-based TP без изменений
- Изменение должно быть backward-compatible: `BREAKDOWN_NEXT_LEVEL_TP_ENABLE=0` возвращает старое поведение

## Связанная архитектура (handoff)

После этого изменения естественный handoff уже работает через независимые стратегии:
- TP у S2 → support_bounce_v1 видит отскок и открывает лонг независимо
- Если S2 ломается → breakdown_v1 снова вооружается на новый пробой

Координировать их явно не нужно — ecosystem уже делает это через независимые сигналы.
