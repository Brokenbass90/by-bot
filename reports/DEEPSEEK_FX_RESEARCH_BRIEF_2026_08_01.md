# Brief для DeepSeek: новые FX/CFD источники edge

Нужно выступить как независимый quant reviewer. Не оптимизировать параметры и
не обещать доходность. У нас уже terminal FAIL у D1 carry+trend, H4
break/retest, H4 time-series momentum и H4 regime mean-reversion на EURUSD,
GBPUSD, USDJPY, EURJPY, GBPJPY с OANDA spread, side-specific swap и stress
commission.

Предложи максимум 8 **причинно различных** H4/D1 гипотез, преимущественно не
price-only. Для каждой дай:

1. экономический механизм, почему edge должен существовать сейчас;
2. точные данные и `known_at` timestamp;
3. отдельную логику long/short;
4. causal signal, entry next bar, stop/exit/max hold;
5. spread, commission, swap/session/gap model;
6. train/OOS/LOSO/regime splits и negative control;
7. главный способ сфальсифицировать гипотезу за 1–3 дня расчёта;
8. ожидаемую частоту, а не ожидаемую прибыль;
9. риск корреляции с уже имеющимися crypto/Alpaca sleeves;
10. критерий `PASS_RESEARCH / REPAIR / BLOCKED_DATA / NO_GO`.

Приоритетные направления для критики:

- cross-pair relative strength с currency-neutral weights;
- London/NY session transition после overnight compression;
- rate-differential/carry surprise, а не статический carry;
- commodity/FX linkage для AUD/CAD/JPY;
- XAU отдельно с собственным contract/pip/swap;
- macro event drift с календарём, известным до публикации.

Запрещено предлагать: сетку, мартингейл, усреднение без hard risk, индикаторный
перебор сотен комбинаций, использование OOS как objective, игнорирование swap,
выбор только победивших пар после просмотра результата.
