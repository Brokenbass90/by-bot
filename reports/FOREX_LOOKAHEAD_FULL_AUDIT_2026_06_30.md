# Форекс — полный lookahead-чек ВСЕХ стратегий (2026-06-30, Claude)

Метод: статический разбор всех 18 стратегий в `forex/strategies/` на 3 класса утечки
будущего: (A) прямой будущий индекс `candles[i+N]`/`[i:]`; (B) индикатор по ПОЛНОМУ
массиву с индексом `[i]`; (C) глобальная нормировка/фит по всему ряду.

## Итог: lookahead НЕ найден ни в одной. ✓
- **(A) Будущий индекс — 0 совпадений.** Никто не читает `candles[i+1]`/`candles[i:]`.
- **(C) Глобальная нормировка — 0.** Нет `mean(closes)`/`np.mean`/`.fit`/scaler по всему ряду.
- **(B) Полный массив — 2 файла, но ОБА причинные** (см. ниже).

## Таблица
| Стратегия | Паттерн доступа | Вердикт |
|---|---|---|
| range_bounce_session_v1 | `candles[:i+1]` | ✓ чисто |
| bb_mean_reversion_v1/v2/v2p/v3 | срезы `[:i+1]` / `[i-k:i+1]` | ✓ чисто |
| asia_range_reversion_session_v1 | `candles[:i+1]` | ✓ чисто |
| breakout_continuation_session_v1 | `candles[:i+1]` | ✓ чисто |
| failure_reclaim_session_v1 | `candles[:i+1]` | ✓ чисто |
| grid_reversion_session_v1 | `candles[:i+1]` | ✓ чисто |
| liquidity_sweep_bounce_session_v1 | `candles[:i+1]` | ✓ чисто |
| trend_retest_session_v1/v2 | `candles[:i+1]` | ✓ чисто |
| trend_pullback_rebound_v1 | `candles[:i+1]` | ✓ чисто |
| ema_trend_pullback_v2 | `candles[:i+1]` | ✓ чисто |
| adaptive_grid_range_v1 | `candles[:i]` | ✓ чисто |
| trendline_break_bounce_v1 | срез по окну | ✓ чисто |
| **london_open_breakout_v1** | full-array SMA, `_sma[i]` | ✓ причинно* |
| **london_open_breakout_v2** | full-array EMA, `_ef[i]/_es[i]` | ✓ причинно** |

\* `_ensure_sma`: trailing-SMA, `sma[idx]=mean(closes[idx-k+1..idx])` (running sum
   вычитает `closes[idx-k]`), делёж на `min(idx+1,k)` → `sma[i]` использует ТОЛЬКО
   прошлое+настоящее. Жёлтый флаг из FOREX_AUDIT 2026-06-30 — **СНЯТ.**
\** `_ema_series`: forward-рекурсия `out[t]=v*k+out[t-1]*(1-k)` → EMA причинна по
   построению; `_ef[i]/_es[i]` смотрят только в прошлое. Чисто.

## Что это значит
Подтверждено количественно: форекс-код написан АККУРАТНЕЕ крипты — lookahead-класса
багов, которые рисовали ложный «позитив» в крипте, тут НЕТ. Пивот в форекс стоит на
честном фундаменте. Цифрам форекс-WF можно будет доверять (на уровне отсутствия утечки).

## Остаточные TODO (НЕ lookahead, но для честных издержек)
1. `forex/engine.py`: добавить slippage (сейчас только разовый спред) — Codex.
2. Защита от lookahead держится на дисциплине стратегий (движок отдаёт весь массив).
   Все текущие дисциплинированы; при добавлении НОВЫХ — прогонять этот же чек.
