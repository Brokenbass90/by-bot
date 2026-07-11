# Morning Recovery Checkpoint — 2026-07-11

## Executive verdict

Ночь и утро не пропали. Система не получила новый денежный рукав, зато впервые новая FX/CFD ветка была написана и проверена через причинный prereg-контур, который не разрешил превратить отрицательный тест в live-эксперимент.

- Новый код и frozen config запушены в `376ad21` до просмотра результатов.
- Live/demo/risk не менялись.
- Alpaca стала безопаснее, но не доказанно прибыльнее.
- Старый второй crypto InPlay short не прошёл независимую проверку.
- Все шесть сторон трёх новых FX/CFD семейств получили `NO_PROMOTION`.

## Live-money truth

### Bybit

- Последнее прямое подтверждение: позиции отсутствовали; денежный crypto sleeve только `ATT1 short r001`, `risk_mult=0.10`.
- Второго или третьего crypto money sleeve нет.
- ATT1 не масштабировать. Текущая чистая live-выборка мала и слаба; versioned canary expiry — `2026-07-20`, effective VPS env нужно проверить до этой даты и не продлевать автоматически.

### Alpaca

- Реальный safe-hold подтверждён: новые входы, stale rotation и mid-month rotation выключены; сопровождение существующих стопов сохранено.
- Последний снимок: equity `$486.93`, cash/BP `$328.45`, позиции `ABBV, ABNB, GE, SCHW`, broker stops `4/4`.
- Это около `-1.61%` от базы `$494.90`.
- После safe-hold не было новых покупок/закрытий; были только перевыставлены четыре защитных стопа.
- Fresh top4 forward `+6.38%`, PF `2.22`, но только `N=2`: это не разрешает вернуть ротацию или увеличить капитал.
- Intraday v1 ledger исторически повреждён повторным booking; v3 остаётся dry-run shadow. Idempotent ledger запушен, но не deployed до восстановления baseline из broker fills.

### Git/VPS

- Local и origin: `376ad21`.
- VPS checkout остаётся `f7ed011`, теперь на `15` коммитов позади.
- На VPS вручную присутствует выбранный safety-пакет, но полного Git deploy не было. Не делать blind pull/restart до flat-window reconciliation.

## Crypto: результат ночи

Clean independent InPlay short:

- stress `N=42`, `+1.4389R`, PF `1.075`, `3/4` positive folds;
- торговали только ETH/AVAX, положителен только ETH;
- концентрация прибыли `67.7%`;
- `1064` detections дали только `49` попыток входа, `1015` были повторными busy-symbol signals.

Verdict: `NO_PROMOTION`. Старый InPlay frozen. Он является break/retest continuation, а не настоящим «разгон → истощение пампа → unwind».

Следующие два crypto successor-контракта:

1. `pump_exhaustion_unwind_short_v1` — strictly short-only, event expansion/volume + liquidity high, reclaim вниз, bearish CHoCH и retest снизу, один persisted event — один plan.
2. `event_expansion_retest_long_v1` — strictly long-only, H1/H4 breakout/hold качественного horizontal/sloped/flip level, затем M5/M15 retest и higher-low/BOS.

Самое раннее окно risk-zero shadow — `25 июля – 8 августа`, только при строгом PASS. Tiny-money canary определяется не датой, а минимум `30` clean shadow closes. При старой частоте это заняло бы `5–9 месяцев`; ускорять sample ослаблением gates нельзя.

## FX/CFD V2: что построено

Research-only branch:

- `impulse_breakout_retest_v2` — уровень замораживается до импульса; breakout и retest физически разные бары; учитываются horizontal/range-edge/sloped levels, first intact retest и trend quality.
- `sweep_reclaim_bounce_v2` — bounded liquidity sweep или failed break с reclaim, level memory, regime/Elder/CHoCH confluence; long/short разделены.
- `regime_range_reversion_v2` — non-grid/non-martingale пила у frozen channel edge с midpoint target; ascending long, descending short, flat both, но статистика каждой стороны отдельная.

Testing frame:

- H1 closed-bar decision timestamp, только later-bar fill;
- synthetic bid/ask barriers для entry/SL/TP; base и stress spread полностью перезапускают fills/outcomes;
- SL-first для неоднозначного H1 intrabar order; adverse stop gaps;
- event/order signal ledger, stable instrument-specific event IDs, side-purity и duplicate gates;
- DST-aware sessions и повторная проверка фактического fill-window;
- fixed data window + input/source SHA, M5-before-H1 coverage, finite OHLCV;
- partial H1 удаляются; unknown market-hour gaps разрывают позиции и warmup; незавершённые orders/trades censored и gated;
- four chronological folds, untouched holdout, symbol breadth/concentration и leave-one-symbol-out;
- portfolio mark-to-market/correlation, native broker bid/ask, news calendar и calibrated costs остаются явными promotion blockers.

Verification: `135` связанных тестов passed; focused V2 suite `34` passed; compile/diff checks passed.

## FX/CFD V2: prereg result

Artifact: `reports/research/fx_v2_gate_20260711/summary.md`.

Strict promotion-grade data: `0/6` symbols. Snapshot был stale примерно `120h`; source caches содержат off-schedule bars, неизвестные gaps и partial H1. Для diagnostic-only после удаления partial bars и gap segmentation допустимы `EURUSD, GBPUSD, USDJPY, GBPJPY`; `EURJPY` и `XAUUSD` data-blocked.

| Sleeve | Base PF / netR | Stress PF / netR | Stress N | Verdict |
|---|---:|---:|---:|---|
| impulse breakout long | `0.793 / -4.06R` | `0.609 / -8.61R` | 26 | NO_PROMOTION |
| impulse breakout short | `0.414 / -8.17R` | `0.382 / -9.06R` | 16 | NO_PROMOTION |
| sweep/reclaim long | `0.832 / -11.69R` | `0.747 / -18.56R` | 101 | NO_PROMOTION |
| sweep/reclaim short | `0.859 / -9.66R` | `0.690 / -23.56R` | 101 | NO_PROMOTION |
| range/pila long | `0.566 / -10.96R` | `0.394 / -16.86R` | 28 | NO_PROMOTION |
| range/pila short | `0.747 / -8.42R` | `0.587 / -15.18R` | 41 | NO_PROMOTION |

Это не только cost problem: все base rows уже отрицательны. Ни одна сторона не имеет устойчивого edge.

Post-hoc anatomy используется только для проектирования нового prereg, не как promotion evidence:

- лучший подкомпонент — short failed-break, stress PF около `0.90`; всё ещё отрицательный;
- horizontal-only range short около PF `0.92`, sloped range entries существенно хуже;
- impulse range-edge long лучше horizontal, но лишь PF около `0.77`;
- sweep sleeves часто доходят примерно до `1R MFE`, затем возвращаются в stop. Это указывает на confirmation/exit-lifecycle проблему, но не разрешает подгонять BE/partial на этом же holdout.

## Следующий FX/CFD repair, без повторения grid

1. `failed_break_retest_short_v3`: short-only; не immediate reclaim entry, а отдельный retest снизу после failed break; horizontal/unified level должен быть свежим и stable; M15 execution; один event — один order lifecycle.
2. `horizontal_range_rejection_v3`: flat horizontal range only; sloped levels остаются контекстом/veto, но не entry source; никаких grid/martingale; отдельные long/short configs.
3. `range_edge_expansion_retest_v3`: breakout только frozen range/quality flip edge, causal relative strength и first retest; отдельные long/short prereg.

Перед любым promotion нужны fresh M5, broker holiday calendar, historical news, calibrated costs и native bid/ask parity. XAU/CFD не тестировать на капитал до data PASS.

## Ближайшие сроки

- `1 сессия`: обновить FX cache/calendar/cost evidence; восстановить Alpaca v1 ledger baseline; проверить ATT1 expiry/effective VPS env.
- `2–4 сессии`: реализовать и заморозить три V3 causal repairs; один ablation на причинную гипотезу, без threshold-mining.
- `1–2 недели`: возможен risk-zero shadow только у кандидата со strict PASS; иначе фиксируется REPAIR/NO_GO.
- Crypto tiny-money sleeve: оптимистично октябрь–декабрь 2026 только если новые event-first arms дают `10–15` чистых сделок/месяц и проходят 30-close shadow. При старой частоте — 2027.

Стабильный семейный доход по календарю обещать нельзя. Реальная цель ближайшего этапа — остановить ложные продвижения, доказать хотя бы два независимых edge и только затем обсуждать капитал/масштаб.
