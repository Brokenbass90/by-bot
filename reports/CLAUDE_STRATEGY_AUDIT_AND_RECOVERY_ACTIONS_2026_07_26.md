# Аудит стратегий Клода и план восстановления доходных контуров

Дата: 2026-07-26

## Решение

Переписывать станцию целиком не нужно. В ней есть ценный live-контур ATT1,
брокерская защита Alpaca, пригодные исследовательские заготовки XSEC и
cross-exchange funding, а также большая тестовая база. Нужна не ещё одна волна
стратегий, а строгий конвейер `research -> exact replay -> risk-zero shadow ->
tiny canary -> scale`, единая модель затрат и неизменяемые decision-ledgers.

Работы Клода частично релевантны:

- XSEC V4 — лучший новый кандидат, но заявленные 49.1% нельзя считать
  ожидаемой live-доходностью: результат зависит от post-hoc порога зрелости и
  survivor-only universe.
- ATT1 A3/3R — содержательный challenger. На фактических восьми символах ATT1
  short-only 3R сохраняет положительное математическое ожидание даже при
  11 bps, но нестабилен по фолдам и пока воспроизводит proxy Клода, а не точный
  production signal path.
- Elder/Retest — опубликованные положительные поздние результаты не
  воспроизводятся сохранённым скриптом. Сохранённый Elder после затрат
  отрицателен. Это ветка реконструкции, не кандидат на деньги.
- Carry-selection — может служить ранжированием, но опубликованные 11.5% не
  являются подтверждённой executable доходностью: в модели не хватает
  синхронного basis, двух ног, legging, стакана и полного round-trip cost.

## Что проверено

### ATT1

Новый аудит:
`reports/research/att1_a3_3r_actual_universe_audit_20260726.json`.

- Universe: ADA, BTC, DOT, ETH, LINK, LTC, SOL, SUI.
- Общий доступный интервал: 2025-04-25 — 2026-02-23.
- 819 неперекрывающихся raw candidates.
- A3, all sides, 3R, 4 bps: 380 сделок, +0.0497R на сделку.
- A3, short-only, 3R, 4 bps: 194 сделки, +0.1800R, PF 1.263.
- A3, short-only, 3R, 11 bps: +0.1182R, но один фолд -0.473R.
- Gate: один maker-pass, ноль taker-pass.

Вывод: текущий ATT1 остаётся champion на x0.10. A3/3R не заменяет его, а
переходит в exact live-replay и forward challenger-label. Масштабировать по
этому proxy нельзя.

### XSEC

Новый аудит:
`reports/research/xsec_v4_robustness_audit_20260726.json`.

- Baseline: 117 сделок, +49.1%, DD 6.8%, Sharpe 2.73.
- Cost 8/15/22/30 bps: +51.4/+49.1/+46.9/+44.4%.
- Maturity 180/270/390 дней: +29.7/+18.7/+49.1%.
- 20% случайный dropout universe: +25.4/+32.9/+48.3%.
- Все dropout-прогоны положительны, но величина результата нестабильна.
- Research gate проходит; capital gate заблокирован survivorship, post-hoc
  threshold, отсутствием независимого OOS, slippage и execution parity.

Запущен `xsec_v3_shadow_20260726`: публичные Bybit data, фиксированный universe,
три staggered-фазы, bid/ask и taker-cost, ноль ключей и ноль ордеров. Первый
decision: 62 usable symbols, 24 виртуальных ордера, turnover $333.33,
оценка входных затрат $0.252.

### Alpaca

Exact-parity preflight повторён:
`reports/research/alpaca_monthly_exact_parity_recheck_20260726.json`.

Он корректно остаётся fail-closed: нет подтверждённого PIT-universe,
delisted/corporate-action lifecycle, XNYS-календаря, source hashes,
execution parity и завершённого forward-window. Safe Hold ABBV/SCHW не
изменялся.

Параллельно запущен risk-zero adaptive shadow
`alpaca_adaptive_shadow_20260726`. Первый снимок: regime OK; PANW, CRWD, ABBV,
DDOG. Добавлен append-only ledger с decision id. Это сбор forward evidence, не
разрешение на покупку.

### Cross-exchange funding

Старый same-venue cash-carry с 1784 наблюдениями и нулём проходов снимается с
основного бюджета, но сохраняется как отрицательный контроль.

Запущен `cross_arb_shadow_20260726`:

- 1512 текущих funding rows на Bybit/Binance/Bitget;
- 30 discovery opportunities;
- 6 маршрутов прошли текущий depth/basis/fee validator;
- paper-позиции пока не открыты: требуется минимум три устойчивых наблюдения;
- размер $100 на ногу, round-trip taker fees, book slippage, basis и
  invalidation lifecycle включены;
- ключи и ордера отсутствуют.

Высокий snapshot APR не является годовым прогнозом: это короткоживущая
разница funding, которая должна пережить persistence и полный paper lifecycle.

### FX/CFD

Строгий 99.5% coverage gate выявил пробелы данных и корректно остановил первый
прогон. Диагностические прогоны с явно ослабленным coverage:

- H1: USDJPY breakout/retest, около 29–30 сделок, лучшие +2.5…+4.1R,
  только 2–3/4 положительных фолда.
- H4 base: GBPUSD range fade, 111–146 сделок, лучшие +8.5…+10.8R,
  PF 1.12–1.16, 3/4 фолда.
- H4 targeted stress при fee 2 bps + slippage 0.5 bps: все кандидаты
  отрицательны; лучший GBPUSD около -0.6R, PF 0.992.

Вывод: текущая FX-реализация не готова даже к demo-shadow. Следующий ремонт —
broker-specific spread/commission/swap, более широкие H4/D1 stop distances,
limit-entry и swap-aware holding. Отрицательный stress — полезный диагноз, а
не повод выбрасывать рынок.

## Новые защитные технологии

- Validator теперь различает research/shadow/canary/capital/live. Survivorship
  и post-hoc могут быть предупреждениями в research, но блокируют капитал.
- Для capital обязательны независимый OOS, slippage model и execution parity.
- ATT1 challenger только размечает exact production signals и не меняет
  поведение champion.
- XSEC и Alpaca пишут append-only decision ledger.
- Funding shadow ведёт полный виртуальный lifecycle двух ног.
- Следующий слой — execution digital twin, immutable data manifests,
  champion/challenger registry, change-point detector и allocator только по
  forward/live evidence, а не по лучшему backtest.

## Условия масштабирования

ATT1 x0.10 не увеличивается по календарю или после нескольких удачных сделок.

1. После минимум 30 закрытых live-сделок: net PnL после комиссий > 0,
   PF >= 1.20, drawdown <= 3R, ноль execution incidents — допускается
   x0.10 -> x0.15/0.20.
2. После минимум 60 сделок: PF >= 1.25, положительный rolling 30d,
   drawdown <= 4R и исправная защита — допускается x0.25.
3. Любой новый challenger начинает с shadow, затем отдельного tiny canary; он
   не наследует разрешение ATT1.

## Числа для планирования, не обещание доходности

- XSEC: после сильного haircut разумный исследовательский диапазон
  8–18% годовых на 1x; подтвердить его может только forward-shadow.
- Equity/Alpaca: рабочая гипотеза 6–12% годовых при equity-like drawdown;
  сейчас валидной оценки ещё нет.
- Funding carry: рабочая гипотеза 2–6% годовых без плеча после полного
  lifecycle; текущие snapshot APR нельзя экстраполировать.
- ATT1: текущие 10 live-сделок и +0.2902 USDT слишком малы для годового
  прогноза.
- FX/CFD: ожидаемая доходность сейчас считается неопределённой; targeted stress
  не прошёл.

При капитале около $1500 даже 20% годовых — около $25 в среднем за месяц до
налогов и отклонений. Значимый денежный поток требует одновременно доказанного
edge, времени на накопление статистики и большего капитала; увеличивать риск,
чтобы искусственно ускорить этот процесс, нельзя.

## Что нужно от владельца

Сейчас регистрации не блокируют risk-zero исследования.

1. Для Alpaca PIT желательно выбрать источник. Практичный кандидат —
   Massive/Polygon с point-in-time tickers, delistings, ticker events и
   corporate actions. API-key нужен только после выбора тарифа.
2. Для FX нужен либо OANDA practice account/token, либо точные MT5
   Specifications: spread, commission, swap long/short, contract size,
   minimum lot для EURUSD, GBPUSD, USDJPY, EURJPY, GBPJPY и XAUUSD.
3. Для live cross-exchange arb позже потребуются два верифицированных аккаунта,
   отдельные subaccounts, trade-only API keys без withdrawal и заранее
   разложенный капитал. Сейчас ключи не нужны.
4. Независимый аудит полезен перед первым новым canary: data/PIT audit,
   execution/security audit и quant reproduction. До появления воспроизводимого
   кандидата дорогой общий аудит преждевременен.

## Текущий статус проверки

- Полный локальный regression: 1524 passed.
- Risk-zero процессы: XSEC, Alpaca Adaptive, cross-exchange funding.
- Live money: только owner-approved ATT1 x0.10.
- Alpaca broker state: защищённый Safe Hold, без новых покупок.
