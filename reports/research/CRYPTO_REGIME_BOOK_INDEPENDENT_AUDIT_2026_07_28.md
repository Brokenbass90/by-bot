# Crypto regime book — независимый аудит 2026-07-28

Verdict: `SHADOW_GO / MONEY_NO_GO`

Live risk, ATT1 signal/universe и реальные ордера не менялись.

## Что воспроизведено

Условия: cache-only, 120 дней, BTC+ETH, next-open, fee 6 bps/side,
slippage 2 bps/side, risk 0.75%, leverage 1, максимум 3 позиции.

| Окно | Состав | Сделок | Net | PF | DD |
|---|---|---:|---:|---:|---:|
| падение до 2026-04-30 | ATT1 short + BOUNCE1 + BREAKDOWN | 65 | +11.08 | 1.861 | 2.07 |
| рост до 2024-12-30 | ATT1 short + BOUNCE1 | 37 | +8.70 | 2.054 | 1.36 |
| рост до 2024-01-29 | ATT1 short + BOUNCE1 | 31 | +1.71 | 1.285 | 1.71 |

Сумма `+21.49`, знак положительный в 3/3 окнах. После разведения env-префиксов
канонические `BOUNCE1_*` воспроизвели те же результаты без изменения строки.

## Почему это не money PASS

1. Геометрия BOUNCE1 настраивалась на этих же трёх окнах: это validation,
   но не untouched OOS.
2. Два BTC+ETH окна содержат 31 и 37 сделок.
3. При 1 000 случайных BTC-прогонах по 34 сделки random-entry дал:
   median PF `0.680`, p95 `1.241`, p99 `1.680`, maximum `2.033`.
   Максимум отдельного random run не является порогом сам по себе, но после
   множественного поиска selection adjustment обязателен.
4. На SOL по 64 сделки random-entry: median `0.655`, p95 `1.042`,
   p99 `1.235`. Альтовые выборки информативнее, но расширение universe
   ухудшило headline PF примерно до `1.09`; исключать DOT после просмотра
   результата запрещено.
5. Static cost model не измеряет live fill, пропуски и задержку.

## Исправленные несостыковки

- slope-break получает canonical prefix `ASLB1_*`;
- support-bounce получает canonical prefix `BOUNCE1_*`;
- `ASB1_*` остаётся только legacy fallback;
- BREAKDOWN имеет отдельный fail-closed capital gate;
- stale/missing/bull/neutral regime не разрешает BREAKDOWN;
- BOUNCE1 risk-zero теперь пишет полный decision/fill/partial-target/exit
  lifecycle, а не только счётчик попыток.

## Shadow contract

Конфиг: `configs/bounce1_risk_zero_shadow_20260728.env`.

Universe намеренно содержит восемь монет, включая DOT. Это предотвращает
повторный выбор только красивых символов. Ledger не вызывает брокера и
сохраняет:

- решение и геометрию;
- fill на следующей 5m границе с adverse slippage;
- частичные цели;
- stop/time-stop;
- net return и net R.

Следующий gate: минимум 30 закрытых shadow-сделок, но решение строится не по
одному N. Нужны positive net distribution, отсутствие single-symbol
concentration, приемлемый fill-rate и совпадение live decisions с
reproducible strategy contract.

## Что делать с процентами

`+21.49%` нельзя годовализировать как прогноз. До untouched и shadow haircut
рабочее ожидание для всей будущей crypto-книги не публикуется. Цель текущего
шага — доказать вторую независимую ногу и снизить зависимость от ATT1, а не
подобрать число без красных месяцев на уже увиденных данных.
