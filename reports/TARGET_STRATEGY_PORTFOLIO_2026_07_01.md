# Target Strategy Portfolio — 2026-07-01

Цель документа: зафиксировать конкретный целевой набор рукавов, чтобы не начинать заново в каждом чате и не путать smoke/локальные пики с готовностью к live.

## 1. Свежий факт по InPlay V4

`inplay_v4_mechanics_gate_full_ada_doge_sui_20260701` завершён.

- OOS-фолды: 4 rolling train/test.
- Train/test: 120d / 60d.
- Grid: 36 комбинаций на fold.
- OOS trades: 21.
- OOS net: +0.96R.
- Positive OOS folds: 2/4.
- `oos_selector`: FAIL, `unstable_frac_pos_0.50`.

Вердикт: новая механика `retest_quality -> level_entry -> pending limit fill -> oos_selector` работает технически, но InPlay V4 пока не денежный рукав. Его нельзя размораживать. Держать как research/diversifier после расширения universe и side-specific разреза.

## 2. Что реально live сейчас

| Контур | Статус | Комментарий |
|---|---:|---|
| Crypto ATT1 short-only | tiny live/canary | `risk_mult=0.10`, ждёт валидную наклонку. Это редкий рукав, не должен давать сделки каждый день. |
| Crypto horizontal/range/bounce | shadow/research | Горизонтальные уровни в фундаменте есть, но основные ноги ещё не полностью переведены на общий helper-chain. |
| Alpaca v38 | готовится к $500 canary | Самый доказанный контур по текущим данным, запуск после live account/key/funding и dry-run. |
| Carry / pair-arb | research only | Нужен re-gate и market-neutral исполнение. Не live. |
| FX/CFD | research only | Нужны собственные FX/CFD-ноги, не прямой порт крипто-стратегий. |

## 3. Целевой полный набор рукавов

### A. Directional crypto — уровневые

| Sleeve | Логика | Side split | Уровни | Статус | Следующий gate |
|---|---|---|---|---|---|
| ATT1 short | Отбой/касание наклонного сопротивления | short-only | Наклонные | live tiny | Набрать live/shadow сделки, контролировать breaker. |
| ATT1 long | Отбой/касание наклонной поддержки | long-only | Наклонные | надо отделить | Отдельный OOS/WF в bull/chop режимах. |
| ARF2 short | Fade от сопротивления в range/bear-chop | short-only | Горизонтали + HVN/VWAP, дальше добавить наклонки как confluence | partial wiring | Подключить `range_filter + retest_quality + level_entry + elder_filter + oos_selector`. |
| ASB2 long | Bounce от поддержки | long-only | Горизонтали + HVN, канал | partial wiring | То же, отдельно от ARF2. |
| ACB1 long/short | Bounce от границ канала | split stats, possibly one module | Наклонный канал + HVN | partial wiring | OOS по сторонам, не общим PF. |
| InPlay V4 short/long | Ретест свежего уровня / flip-уровня | separate sleeves | Горизонтали + flip, позже наклонные | mechanics wired, gate failed | Расширить universe, side split, true WF; не live. |
| Breakout/retest | Подтверждённый пробой + ретест | separate up/down | Горизонтали + наклонные | research | Использовать `breakout_confirm + level_entry`, не голый пробой. |

### B. Crypto — не чисто уровневые

| Sleeve | Логика | Side split | Уровни | Статус | Следующий gate |
|---|---|---|---|---|---|
| H4 liquidation cascade | Ликвидационный/vol/OI cascade reversal | long-after-flush / short-after-squeeze | Не обязателен | highest crypto research priority | Нужны реальные liquidation/OI/funding данные, H4 WF на mid-caps. |
| Pump exhaustion / SpikeFade | Fade после подтверждённого истощения | mostly short-only first | Уровень как confluence, не основной | research | True WF + fee stress + cross-symbol sanity. |
| IVB1 | Impulse volume breakout continuation | long/short separate | Breakout level secondary | watch | Maker/post-only fill-risk + DD cut + side-specific gate. |
| Funding/carry | Funding/basis edge | market-neutral | Не уровневый | research | Только delta-neutral executor, balance validation, concentration cap. |
| Pair arb | Cointegration/stat-arb | market-neutral | Не уровневый | research | Long-history WF, borrow/funding/fee stress. |

### C. Alpaca

| Sleeve | Логика | Side split | Уровни | Статус | Следующий gate |
|---|---|---|---|---|---|
| Alpaca v38 | Equities monthly/intraday candidate package | mostly long | Не основной фактор | canary-ready after funding | $500, dry-run, live only after order/fill/stop verification. |

### D. FX/CFD

Крипто-ноги напрямую не портировать. Нужны собственные ноги:

| Sleeve | Логика | Side split | Уровни | Статус |
|---|---|---|---|---|
| FX range/bounce | Отбой от range/channel | long/short split | Горизонтали + каналы + round levels | design/research |
| FX breakout/retest | London/NY continuation after level break | up/down split | Горизонтали + round levels + session levels | design/research |
| FX trend pullback | Pullback to EMA/VWAP/level in trend | long/short split | Уровень как confluence | design/research |
| XAU range/sweep | Sweep/false break around round/session levels | long/short split | Round levels + session highs/lows | design/research |

## 4. Ответ на вопрос про split long/short

Да, почти всё directional нужно разделять на чистые рукава:

- `ATT1_short` и `ATT1_long` — отдельно.
- `ARF2_short` и `ASB2_long` — отдельно.
- `InPlay_short` и `InPlay_long` — отдельно.
- `IVB1_short` и `IVB1_long` — отдельно.
- `breakout_up` и `breakout_down` — отдельно.

Флетовые/канальные стратегии могут жить в одном модуле, но статистика, breaker, gate и allocation должны быть side-specific. Общий PF bidirectional-стратегии больше не должен быть основанием для live.

## 5. Ответ на вопрос про уровни

Фундамент теперь умеет больше, чем старые стратегии:

- горизонтальные кластерные уровни;
- наклонные каналы/трендлайны;
- volume density / HVN;
- flip/broken levels;
- liquidity sweep;
- round/session levels для FX/CFD частично через фильтры.

Но не все активные стратегии уже используют всё это. Это текущий технический долг:

- InPlay V4 уже использует общий limit-at-level execution.
- ASB2/ACB1 используют часть `market_context`/HVN, но ещё не весь helper-chain.
- ARF2 пока имеет свою внутреннюю логику HVN/VWAP/resistance, её надо перевести на общий контракт.
- ATT1 остаётся наклоночным рукавом, горизонтальные уровни можно добавить как confluence, но не смешивать в одну статистику.

## 6. Что делать дальше без распыления

P0 — не писать новые десятки стратегий. Сначала довести 2 денежных контура:

1. Alpaca v38: $500 canary после dry-run и проверки stop/fill/ownership.
2. Crypto range/bounce package:
   - ARF2 short,
   - ASB2 long,
   - ACB1 side-specific,
   - общий helper-chain,
   - rolling OOS через `oos_selector`.

P1:

3. H4 liquidation cascade на реальных liquidation/OI/funding данных.
4. FX/CFD native range/breakout/trend-pullback, с news/session filter.

P2:

5. InPlay V4 оставить в research до устойчивого OOS.
6. SpikeFade/IVB1 — только после true WF, fee stress и cross-symbol sanity.

