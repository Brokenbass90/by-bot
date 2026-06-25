# Regime affinity — midterm CSV validation, 2026-06-25

Источник: серверный `/root/by-bot-research-20260625-49a4ad0/runtime/midterm_trades_latest.csv`.

Метод:

- входные сделки — `midterm_trade_export.py`, ladder + 7h time-stop, net R после комиссии;
- режим BTC — daily SMA50 + наклон, классификация `BULL_TREND / BEAR_TREND / CHOP`;
- проверка — `strategy × regime × side`, macro-side filters, затем WF:
  выбор bucket'ов на train-окне, проверка на следующем test-окне.

## Главное

Идея режимной аффинности не мусор, но текущие данные **не дают права включать
regime-route в live**.

Причина: in-sample улучшение есть, но часть WF-режимов проваливается. Лучшие
OOS-варианты появляются только на коротком 12m→3m окне и дают мало сделок
(`15–19`). Это research-кандидат, не production gate.

## Server reg×side profile

`midterm_pullback` — 111 сделок, `+8.21R`:

| bucket | R/trades/avgR |
|---|---:|
| BULL long | `+0.86 / 40 / +0.021` |
| CHOP long | `+2.37 / 22 / +0.108` |
| BULL short | `+0.27 / 1 / +0.266` |
| BEAR short | `-0.64 / 24 / -0.027` |
| CHOP short | `+5.36 / 24 / +0.223` |

`midterm_v3` — 40 сделок, `-2.89R`:

| bucket | R/trades/avgR |
|---|---:|
| BULL long | `-1.86 / 20 / -0.093` |
| CHOP long | `+1.88 / 9 / +0.208` |
| BEAR short | `+1.08 / 6 / +0.180` |
| CHOP short | `-3.98 / 5 / -0.796` |

## Fixed filters

| filter | trades | total R | PF | green months | red streak | DD |
|---|---:|---:|---:|---:|---:|---:|
| All | 151 | `+5.32R` | 1.092 | 54.9% | 5 | `-11.64R` |
| Macro-side gate, chop allowed | 150 | `+5.06R` | 1.087 | 54.9% | 5 | `-11.64R` |
| Strict trend-only | 90 | `-0.56R` | 0.984 | 55.0% | 3 | `-10.87R` |
| In-sample bucket route | 61 | `+10.68R` | 1.534 | 64.3% | 5 | `-8.69R` |

Вывод: простое правило "не шортить bull / не лонговать bear" **не помогает**.
Strict trend-only даже уходит в минус. Улучшение даёт только bucket selection,
и его обязательно надо проверять OOS.

## Walk-forward

Основной строгий вариант `24m train → 6m test, minN=5, minAvg=0.0`:

- OOS routed: 36 сделок, `-5.28R`, PF `0.688`, DD `-7.56R`.
- Вердикт: **не проходит**.

Пороговые варианты `24m→6m` тоже не спасают:

- `minAvg=0.10`: 18 сделок, `-2.57R`, PF `0.678`.
- `minN=8, minAvg=0.05`: 18 сделок, `-2.57R`, PF `0.678`.

Короткий WF `12m train → 3m test` даёт promising, но тонкий результат:

| train/test/minN/minAvg | trades | total R | PF | green | red streak | top month | DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 12/3/4/0.10 | 19 | `+4.32R` | 1.793 | 64.3% | 3 | 36.6% | `-2.78R` |
| 12/3/5/0.10 | 16 | `+3.87R` | 1.776 | 61.5% | 3 | 40.8% | `-3.23R` |
| 12/3/4/0.15 | 18 | `+3.84R` | 1.705 | 61.5% | 3 | 41.1% | `-3.26R` |
| 12/3/5/0.15 | 15 | `+3.39R` | 1.680 | 58.3% | 3 | 46.6% | `-3.71R` |

Grid summary: 96 variants, 17 are positive with at least 15 trades.

## Decision

1. Не заводить `recommended regimes` в live/orchestrator сейчас.
2. Не архивировать всю идею: короткая WF-маршрутизация дала полезный сигнал, но
   выборка слишком мала.
3. Следующий честный тест:
   - расширить этот же profiler на все crypto sleeves из package runner;
   - использовать execution-like выходы, где они есть;
   - сделать portfolio-level WF с фиксированным selection rule;
   - только если OOS остаётся положительным по нескольким стратегиям и окнам —
     писать `regime_orchestrator` integration.
4. Для midterm конкретно: продолжать через monolith-accurate ATR trailing replay.
   Текущий ladder+7h export показывает, что midterm ещё не готов к risk.

Практический статус: гипотеза "логика отрицательных выводов сломана" частично
верна — простая aggregate-картина скрывает полезные buckets. Но production-вывод
остаётся строгий: OOS ещё не доказан.
