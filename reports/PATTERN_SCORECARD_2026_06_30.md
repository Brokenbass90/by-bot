# Pattern scorecard + покрытие рынков (2026-06-30)

Честно: помечено [IS]=in-sample (подгонка, не верить) / [OOS]=честная проверка.

## Directional паттерны (крипта) — общий пакет цифр
| Паттерн | Файл | Лучшее | Статус |
|---|---|---|---|
| Трендлиния (ATT1) | alt_trendline_touch_v1 | [IS] 457tr +37R PF1.32 DD~5; **LIVE: 0 сделок** (редкий) | LIVE canary, спит |
| Пила/range (ARF2) | alt_resistance_fade_v2 | [IS] r121 PF5.3 (overfit); [OOS-360d] r055 19tr +3.9R PF1.94; свежий OOS — **no-go** | research |
| Отскок горизонт (ASB2) | alt_support_bounce_v2 | [OOS] **no-go** | research |
| Отскок канал (ACB1) | alt_channel_bounce_v1 | [OOS] лучший +HVN PF **0.936**, −1.46R | research |
| ИнПлэй ретест | inplay_retest_v3 | [OOS] −4.31R PF **0.868**; +volume_exit хуже (PF 0.701) | repair → V4 |
| Пробой/breakdown | alt_inplay_breakdown_v1 | [OOS] sweep FAIL; live shadow −2.41/15 | rewrite (анти-манип) |
| Заколы/liq-sweep | liquidity_sweep_reversal_v1/v2 | не валидированы свежим OOS | research |
| Элдер | elder_triple_screen_v2/v3 | mass-FAIL DD 40–83; [IS] WF-22 проходил до temporal-фикса | фильтр, не движок |
| SpikeFade LINK short | spike_fade_v3 | [bounded] 32tr +5.1R PF1.99 DD1.27 | кандидат №2, нужен свежий OOS |

**Вывод по directional:** на честном OOS почти всё красное/около нуля. Единственные
не-красные — ATT1 (редкий, live 0 сделок) и SpikeFade (редкий). Это и есть причина
пивота в механику. Survey подтвердил: чистых наклонных почти нет → отскоки/range/
горизонтали перспективнее, но пока WF их не подтвердил.

## Сторонние штуки
- **Охота за ликвидностью / ликвидации:** `bybit_liquidations_collector` РАБОТАЕТ
  (собирает данные); стратегии `liquidation_cascade_entry_v1`, `liquidity_sweep_*`
  есть, НЕ валидированы. Это перспективный механический-ish трек (DeepSeek отметил).
  ⚠️ **Только крипта** — на форексе ликвидаций нет (OTC, нет централизованного фида).
- **Плотности:** объёмная плотность (HVN) построена и вшита в ASB2/ACB1 (крипта).
  Стаканные плотности (стены/абсорбция) — в бэклоге (нужен live WS + анти-спуф).
  ✅ **На OANDA это РЕАЛЬНО возможно**: у OANDA есть публичные Order Book /
  Position Book (где скапливаются ордера/позиции ритейла) — это известный edge,
  стоит копать на форексе.

## Форекс / CFD — нормальные стратегии или простейшие?
- В `forex/` ~20 СОБСТВЕННЫХ сессионных стратегий (london_open_breakout,
  bb_mean_reversion v1-3, asia_range_reversion, trend_retest_session, range_bounce_session,
  liquidity_sweep_bounce_session, ema_trend_pullback…). Это НЕ простейшее и НЕ порт
  крипты — реальные FX-стратегии. НО: спят (нет OANDA-ключа), свежего WF нет
  (FX strict gate сейчас крутится у Codex).
- **Пробел/возможность:** новый фундамент (`market_context`/classify_channel) пока
  НЕ применён к форексу. А твоя интуиция верна — **флет-отскоки на форекс-мажорах
  частые и эффективные** (мажоры реверсят в диапазонах гораздо чаще крипты). Стоит
  применить range/bounce-логику (с FX-параметрами) к форексу — там частота будет.
- Пробой на импульс — есть (london_open_breakout, breakout_continuation_session),
  работает концептуально и в крипте, и на форексе; нужен честный WF.

## Среднесрок — и там, и там?
- **Крипта:** есть (`btc_eth_midterm_v3`, `btc_eth_midterm_pullback_v2`, MIDTERM sleeve).
- **Акции (Alpaca v38):** это И ЕСТЬ среднесрок (месячный momentum, холд ~22 дня),
  PF 6.47 — наш самый доказанный среднесрочный эдж.
- **Форекс:** среднесрок (свинг на 4H/daily) развит слабо — trend_retest/ema_pullback
  ближе к интрадей. Пробел; можно добавить FX-свинг позже.

## Что это значит
Directional «пакет» сейчас не даёт денег честно → деньги в: Alpaca (среднесрок акции),
механика (carry/pair-arb/ликвидации крипта), и форекс-range/breakout (проверить на
бесплатных данных). Плотности на OANDA (order/position book) — отдельный
перспективный трек.
