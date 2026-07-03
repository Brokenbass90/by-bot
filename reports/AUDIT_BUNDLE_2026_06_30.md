# Audit bundle — для внешних нейросетей (DeepSeek/GPT) (2026-06-30)

Цель: дать сторонним ИИ всё, чтобы найти, ГДЕ directional-стратегии теряют эдж —
код стратегий + код, от которого они зависят + где были фиксы lookahead.

## 1. Стратегии под вопросом (directional)
| Файл | Что это | Статус |
|---|---|---|
| `strategies/alt_resistance_fade_v2.py` | ARF2 — «пила»/отбой от сопротивления (та, что я ошибочно назвал «спасённой») | in-sample 63 PASS → OOS no-go (overfit или нехватка cache) |
| `strategies/inplay_retest_v3.py` | InPlay — ручной флагман владельца (объём→уровень→ретест) | baseline PF 0.868 (минус) после фикса lookahead |
| `strategies/elder_triple_screen_v3.py` | Элдер triple-screen | проходил WF-22 до temporal-фикса, потом OOS отрицательный |
| `strategies/alt_range_scalp_v1.py` | ARS1 — range scalp | слабый, к ATT1 не добавляет |
| `strategies/alt_inplay_breakdown_v1.py` | Breakdown — пробой поддержки | sweep FAIL |

## 2. Код, от которого они ЗАВИСЯТ (общие зависимости)
| Файл | Роль |
|---|---|
| `bot/market_context.py` | детектор уровней: горизонт. кластеры, наклонные (R²), HVN, VWAP, classify_channel |
| `bot/volume_exit.py` | выход по затуханию объёма (с impulse-gate) |
| `strategies/signals.py` | TradeSignal + `validate()` — контракт сигнала (что считается валидным) |
| `backtest/engine.py` | Candle/KlineStore, ATR, stop/tp hit-логика |
| `backtest/portfolio_engine.py` | СИМУЛЯЦИЯ исполнения: вход на след. открытии, TP/SL/трейл/время, комиссии/слип |
| `backtest/run_portfolio.py` | селектор стратегий + параметры прогона (fees/slippage/next-open) |

## 3. ГДЕ были фиксы, обнулившие фейковую прибыль (ключ к «что сломалось»)
- InPlay anti-lookahead: `strategies/inplay_retest_v3.py:111` функция
  `_closed_rows_before(...)` — берёт ТОЛЬКО закрытые свечи до сигнала. Коммиты:
  `Fix inplay retest lookahead gate`, `fix inplay retest timeframe parity`.
- Elder: коммит `Fix Elder Screen 2 temporal misalignment` (до него — `Elder WF-22
  validated`). То есть «валидный» период был ДО устранения рассинхрона ТФ.
- ARS1: `fix ARS1 ADX regime filter`, `audit research parity`.
Гипотеза: старые «плюсы» во многом = lookahead/temporal артефакт. Проверка для
аудита: сравнить результат стратегии С и БЕЗ `_closed_rows_before` — если «плюс»
появляется только при подсматривании будущего, эдж был фейковым.

## 4. Что спросить у внешних ИИ
1. Найти в `portfolio_engine.py` и стратегиях ЛЮБОЙ остаточный lookahead/optimistic
   fill (вход по цене, известной только в конце бара; TP/SL приоритет; partial fills).
2. По InPlay: верно ли формализован ручной эдж владельца (объём→уровень→ретест→
   выход по затуханию объёма), или потеряна контекстная связка? Что добавить
   (orderbook imbalance, режимный гейт), чтобы эдж пережил честный OOS?
3. ARF2: это overfit (слишком много параметров) или нехватка покрытия cache на 60d?
   r055/r121 на 360d живы (PF~1.9) — настоящий ли это редкий эдж?
4. Cost-model: реалистичны ли 6/2 bps fees/slippage для этих монет/частоты?

## 5. Метод (с чем согласны и я, и DeepSeek)
Гипотеза → валидация на истории (БЕЗ перебора под кривую) → если PF>1.3 после
комиссий на OOS → минимальный код → paper → canary. ИИ = отдел СТАТ-АНАЛИЗА, не
генератор кода. Ничего не удаляем — спорное в архив, не в корзину.
