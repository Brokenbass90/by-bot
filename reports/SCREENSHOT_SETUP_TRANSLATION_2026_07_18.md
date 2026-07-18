# Перевод скриншотов в причинные торговые контракты — 2026-07-18

Этот документ фиксирует не «красивые победившие картинки», а проверяемые гипотезы, которые можно реализовать без lookahead. Скриншоты сами по себе не доказывают edge: проигравшие примеры и полный point-in-time universe неизвестны.

## Что изображено и как это формализовать

### BANK / AKE: поджатие к горизонтальному сопротивлению

- fresh relative-volume/range event;
- несколько повышающихся минимумов под заранее известным горизонтальным resistance;
- сжатие диапазона и уменьшение расстояния до уровня;
- вход только после закрытого breakout, удержания уровня и/или первого причинного retest;
- исполнение на следующем M5 open, не внутри формирующейся свечи;
- long-only физически отделён от сценария failed-break short;
- L2 wall является только дополнительным evidence: нужно отличать исполнение от отмены/spoof.

Ближайшая существующая основа — `event_expansion_retest_long_v1`: H1 expansion -> later M15 hold -> first retest -> confirmed higher low -> strictly later bullish BOS -> exact next M5 open. Она причинна, но research-only и имеет восемь незакрытых blockers.

### LYN: многократное горизонтальное сопротивление после sweep/reclaim

- уровень должен существовать до решения и иметь несколько подтверждённых реакций;
- нижний sweep/reclaim оценивается только после закрытия свечи;
- breakout и retest должны быть двумя разными завершёнными событиями;
- отдельные контракты: breakout/retest long и failed-break/reclaim short;
- цели берутся из следующего заранее существовавшего level/liquidity zone, а не рисуются после результата.

### Наклонная поддержка: bounce или break/retest

Новый `bot/sloped_level_snapshot_v1.py` уже строит причинную линию отдельно для support и resistance: не менее трёх `pivot_right`-подтверждённых pivot, all-pivot OLS, минимум R2, отсутствие close-break до as-of, стабильные source/config/input/pivot/snapshot hashes. Он не генерирует сигнал и не имеет live authority.

Следующие потребители должны быть отдельными:

1. support-bounce long-only;
2. support-break/retest short-only;
3. resistance-rejection short-only;
4. resistance-break/retest long-only.

ATT1 нельзя незаметно перевести на эту геометрию. Нужен отдельный preregistered challenger и side-by-side shadow.

## Почему текущий scanner пропускает эти сделки

Фактический свежий geometry/router universe содержит 20 символов:

`AAVE, ADA, AERO, BTC, DOGE, DOT, ENA, ETH, FARTCOIN, HYPE, LINK, LTC, NEAR, ONDO, SOL, SUI, WLD, XAG, XRP, ZEC`.

`AKEUSDT`, `BANKUSDT`, `LYNUSDT` и `USUSDT` отсутствуют и отсекаются до геометрии. Дополнительно текущий geometry builder обычно строит только H1/H4 (`60/240`), поэтому 1m/5m/15m события со скриншотов не представлены. Web-карты — heuristic advisory rank, а не закрытый breakout/retest и не оценённая вероятность прибыли.

## Самый узкий следующий implementation task

Собрать отдельный research-only `event_universe_v1`, не расширяя live-router:

1. каждые пять минут читать полный Trading USDT-perpetual universe point-in-time;
2. fail-closed проверять tradability, spread, depth/turnover floor и listing age;
3. загружать только закрытые M5 prefix;
4. переиспользовать relative-volume/range event scoring;
5. ранжировать свежие movers и сохранять bounded top-24/40;
6. писать hash/time/source/reasons/missing receipt с restart-safe state;
7. подавать этот список отдельному M5/M15/H1 advisory scorer;
8. не иметь ключей, ордеров, risk mutation или live promotion authority.

После 30–60 дней prospective candidate logging можно измерять base rate, precision после costs и пригодность horizontal/sloped consumers. L2/стаканные плотности добавляются только для дней с полноценным replayable tape: wall lifetime, cancel-versus-execution, order-flow imbalance, microprice, absorption и depth recovery.

## Решение

- Скриншоты дают полезные causal hypotheses, но не разрешение на live.
- Главный текущий gap — universe discovery, а не отсутствие ещё одного индикатора.
- Приоритет: `event_universe_v1` -> horizontal event-long runner -> отдельные sloped long/short consumers -> prospective shadow.
- Старую пилу не включать: её историческое состояние `N21, WR 23.81%, PF 0.487`. Новый range-кандидат должен быть failed-break/sweep/reclaim с отдельными long/short контрактами, regime filter, time stop и stress costs.
