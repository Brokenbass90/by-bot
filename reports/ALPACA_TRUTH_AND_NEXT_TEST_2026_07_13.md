# Alpaca truth and next test — 2026-07-13

Статус: `SAFE_HOLD_EXISTING_POSITIONS`; прибыльность не доказана live; scale запрещён.

## Нужен ли ручной restart

Нет. Alpaca monthly manager — cron-invoked one-shot (`scripts/run_alpaca_live_v38_once.sh`), а не постоянно живущий `bybot.service`. Код/конфиги читаются при следующем invocation. Если менялся cron, нужно переустановить/проверить crontab; для немедленной проверки нужен ручной dry-run manager/report, а не restart core bot.

Первый автоматический weekday post-close Telegram report после установки запланирован на 2026-07-13 22:10 UTC, watchdog — 23:00 UTC (`scripts/setup_cron_alpaca_reports.sh`, `scripts/setup_server_crons.sh`). Утром отчёт ещё не был должен прийти. Последний manual delivery был PASS; scheduled delivery можно считать подтверждённым только после due window и server receipt.

## Что уже live, а что research

- SAFE-HOLD, truth-first Telegram reporting и broker stop coverage были адресно развёрнуты ранее; VPS checkout при этом намеренно остаётся старым/dirty, поэтому live truth задают targeted receipts, а не `git rev-parse` VPS.
- `v36` сейчас в основном имя runner/runtime namespace; live candidate имеет tag v38 и использует `runtime/equities_monthly_v36`.
- v38 parity/fresh-cache replays — research-only, без broker calls.
- v39 и adaptive-gated — research challengers; в live manager не включены.
- Idempotent intraday fill ledger остаётся Git/local до восстановления повреждённого broker-fill baseline.

## Почему первая неделя была отрицательной

Она не была чистой проверкой monthly v38. Номинальный v38 ошибочно ротировался ежедневно: семь round trips за три торговых дня, 2 wins / 5 losses, около `-$5.716`, gross PF примерно `0.44`. Исследовательская частота — примерно 15 OOS сделок в год. Поэтому неделя прежде всего показала ущерб churn/parity defect, а не опровергла monthly-гипотезу.

Это не означает, что monthly v38 уже доказана. Последняя прямая broker truth: equity `$486.93`, cash/BP `$328.45`, holdings `ABBV/ABNB/GE/SCHW`, broker stops `4/4`, примерно `-1.61%` к базе `$494.90`; после SAFE-HOLD новых buys/closes не было, только rearm защитных stops.

## Самые защитимые historical figures

Не forecast и не обещание дохода.

- Exact top4 replay 2024-05..2026-04: `N=33`, `PF=6.7439`, compounded `+50.7502%`, max monthly DD `-3.856%`; 8 positive и 2 negative active months, но только 10 active months из 24.
- Fresh shifted cache: `N=31`, `PF=7.2864`, `+58.0781%`, max monthly DD `-3.856%`; данные и выбор пересекаются с разработкой.
- April-signal -> May-entry forward: `N=2`, `+6.38%`, `PF=2.22`; выборка слишком мала для scale.
- v39 robustness verdict — REJECT: 12m labeled OOS был положительным, но bear-2022 `-23.47%`, `PF=0.415`, `DD=27.66%`.
- Adaptive gate уменьшил bear-2022 DD, но не стал прибыльным: `-6.54%`, `PF=0.280`, `N=12`, `DD=2.23%`. Это stabilizer, не доказанный income edge.

Основные caveats v38 replay: нет явных fees/slippage; DD построен по monthly curve, а не daily equity; intrabar BE/trail порядок грубый; fixed modern universe несёт survivorship/point-in-time риск; это не новый untouched OOS.

## Stops и trailing

- Research v38: stop `2 ATR`, target `3.2 ATR`, BE `0.8R`, trail `1.5 ATR`.
- Текущая live approximation: initial fixed stop `5%`, software trail arm/drop `+3.5%/+3.5%`, simple DAY broker stop обязателен.
- Fractional holdings используют simple broker stop + polling software trail; native trailing для fractional shares пропускается.
- Последняя coverage `4/4` подтверждает наличие защиты на всю quantity, но не точную research stop-price parity.
- DAY stops истекают, software trail зависит от регулярного запуска manager; exact BE+ATR live parity пока не доказана.

## Следующий замороженный тест

1. Оставить SAFE-HOLD и восстановить broker fills/order lifecycle за 6–9 июля.
2. До outcome зафиксировать только четыре arms: true-monthly v38 top4; accidental daily-rotation negative control; adaptive-default-gated; adaptive-ungated control. Нового parameter grid не делать.
3. Использовать один point-in-time universe/data contract, completed monthly-close decision и next-open fills с broker-calibrated costs/gaps.
4. Сделать один общий executable exit model: либо exact BE0.8R+ATR1.5 в live и replay, либо replay фактического fixed +3.5/+3.5 polling. Разные exits сравнивать нельзя.
5. Считать daily equity/DD, turnover, concentration, regimes, delistings/survivorship и untouched forward.
6. Re-enable rotation только на monthly boundary после signal/fill/exit parity receipts; adaptive остаётся challenger.

Никаких Alpaca live/config изменений в аудите 13 июля не было.
