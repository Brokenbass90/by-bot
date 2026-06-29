# Инвентарь стратегий — для DeepSeek cut-list + Codex freeze (2026-06-29)

Полная таблица: `reports/STRATEGY_INVENTORY_2026_06_29.csv` (strategy, in_backtest,
bucket, status, known_metric). Принцип владельца: **не удаляем — замораживаем/
архивируем** (обратимо, идеи сохраняем).

## Итог: 91 стратегия
| Бакет | Кол-во | Что значит |
|---|---|---|
| **KEEP** | 7 | живые кандидаты + новый фундамент — фокус здесь |
| **REHAB** | 7 | завалились, но идея ценная → по одной на новом фундаменте |
| **RESEARCH** | 6 | carry/basis/pair/liquidation/cross-exchange — структурные эджи |
| **FREEZE** | 44 | unproven; выключить из ротации, не трогать код |
| **ARCHIVE** | 27 | мёртвый BTC/ETH-directional + осиротевшие *_live стабы |

Вывод DeepSeek подтверждается цифрами: реально работаем с ~14 стратегиями, 71 —
балласт под заморозку/архив. Машина переразвита относительно числа живых ног.

## KEEP (7) — фокус
- `alt_trendline_touch_v1` (ATT1) — 457tr +37R PF1.32 DD~5; canary готова.
- `spike_fade_v3` — LINK short диверсификатор PF1.99 DD1.27.
- `alt_resistance_fade_v2` (ARF2) — research sweep идёт.
- `alt_support_bounce_v2` (ASB2) — новый фундамент, нужен WF.
- `alt_channel_bounce_v1` (ACB1) — новый, двусторонний канал, нужен WF.
- `inplay_retest_v3` — нога ручного метода владельца (+ volume_exit).
- `alpaca_adaptive_v1` — стабилизатор (акции).

## REHAB (7) — по одной, после вердикта ATT1 live
- `impulse_volume_breakout_v1` (IVB1) — есть эдж PF1.25, DD9 → чинить гейтингом.
- `alt_resistance_fade_v1` → перестроена в ARF2.
- `alt_support_bounce_v1` → перестроена в ASB2.
- `alt_inplay_breakdown_v1` → анти-манипуляционный rewrite.
- `alt_range_scalp_v1` (ARS1) → тест аддитивности с ATT1 идёт.
- `elder_triple_screen_v2` → не движок, в фильтр на ATT1/InPlay.
- `inplay_breakout` → REPAIR (cache invalidation).

## RESEARCH (6) — структурные эджи (путь DeepSeek)
funding/carry/basis/pair_arb/liquidation/cross_exchange — это рукава для
market-neutral дохода. Carry-готовность отдельно: `FUNDING_CARRY_READINESS_2026_06_29.md`
(сейчас NO-GO по величине, рычаг — отбор по аномальному фондированию + cross-exchange).

## ARCHIVE (27) — убрать из ротации (не удалять)
- BTC/ETH directional (`btc_*`, `eth_*`, `btc_eth_*`) — краудед-рынок, эдж
  арбитражится институтами; при наших комиссиях не конкурируем (вывод DeepSeek).
- Осиротевшие `*_live` стабы (нигде не подключены).

## FREEZE (44) — выключить из ротации
unproven ноги (pump_fade семейство, micro_scalper, smart_grid, trend_pullback,
range_mean_reversion и пр.) — код оставить, риск 0, не развивать пока нет живого эджа.

## Честная оговорка по метрикам
`known_metric` заполнен по хэндоффам там, где данные есть (~14 ног). Для FREEZE/
ARCHIVE надёжного per-strategy Sharpe/PnL локально нет — бакеты построены по
(подключена-ли-в-движок) + класс-по-имени + вердикты хэндоффов. Точный Sharpe по
каждой = серверный metrics-pull (Codex), если DeepSeek захочет цифры под каждую.

## Действия
- DeepSeek: по CSV дать финальный cut-list (что в ARCHIVE окончательно).
- Codex: перевести FREEZE/ARCHIVE в risk=0 / убрать из дефолтной ротации движка
  (физически файлы не удалять); оставить KEEP+REHAB+RESEARCH.
- Claude: вести KEEP/REHAB по одной через WF; carry — по readiness-доку.
