# Carry re-gate — спец для Codex (2026-06-30, Claude)

Цель: устранить разрыв между гейтом (проектирует net>0) и реальностью (125 циклов
net ОТРИЦАТЕЛЕН: WR35%, mean −0.02%, p25 −0.19%, proj −5.7%/мес). Привязка к коду:
`scripts/cross_exchange_funding_validate.py`, `scripts/arb_roi_calculator.py`,
`scripts/cross_exchange_arb_dry_run.py`, `bot/carry_neutral.py`.

## Диагноз (корень минуса)
Гейт уже считает: `net_hold_pct = spread_hold_pct − roundtrip_cost_pct`, требует >0.
НО `spread_hold_pct = spread_apr * (hold_hours/24)/365` — кредитует ПОЛНЫЙ APR на всё
удержание. Фандинг затухает/мин-реверт за время hold → реально собираем МЕНЬШЕ. Плюс:
- модельный slippage_bps недооценивает реальный филл (особенно тонкая короткая нога);
- dry-run ловит `insufficient_balance` на short-leg → план НЕ market-neutral / недохедж;
- hold по факту ~24ч при затухающем спреде.
Итог: проекция оптимистична, эмпирика отрицательна. Чиним проекцию + добавляем
эмпирический deploy-гейт.

## Фиксы (по приоритету)
### 1. Funding-capture haircut (главное)
Не кредитовать полный APR. Ввести коэффициент захвата `capture ∈ (0,1]`, оценённый
из ЗАКРЫТЫХ циклов: `capture = realized_funding_collected / projected_funding_at_entry`
(медиана по истории). Гейт: `net_hold_pct = capture*spread_hold_pct − roundtrip_cost_pct`.
Старт консервативно `capture=0.5`, затем калибровать по shadow-истории.

### 2. Эмпирический deploy-гейт (поверх per-opportunity)
Решение «выводить ли carry в live» принимать НЕ по spread_apr, а по `arb_roi_estimate`:
живой деплой только если rolling **median И p25 net-per-cycle > +buffer** на последних
N≥30 закрытых циклах. Сейчас median −0.097%, p25 −0.19% → деплой ЗАПРЕЩЁН (корректно).

### 3. Жёсткий full-funded both legs
В `cross_exchange_arb_dry_run.py`: если `available_short < need` ИЛИ `available_long < need`
— план НЕ создаётся (не undersize, не однонога). Сейчас MANTA-план шёл при short=11.7<20.

### 4. Delta-neutral enforcement (`bot/carry_neutral.py`)
Equal-notional обе ноги + проверка фактического нетто-дельта ≤ порога перед/во время.
Нет баланса под обе ноги в равном ноционале → нет сделки.

### 5. Decay-guard на входе
Требовать, чтобы фандинг-событие было свежим и не схлопывалось: persistence уже есть;
добавить «funding на последнем событии ≥ X% от среднего за окно» (анти-затухание).

## Приёмка (что вернуть)
1. Пересчитать `arb_roi_estimate` на ТЕХ ЖЕ 125 циклах с haircut+full-funded:
   вернуть mean/median/p25 net-per-cycle ДО/ПОСЛЕ.
2. Если после фиксов median ≤ 0 на N≥30 — carry в АРХИВ гипотез (не live, не корзина).
3. Если median > +buffer и p25 ≥ −небольшой — кандидат в крошечный canary (market-neutral,
   без концентрации; GWEI/SLX — ок, ESPORTS 57%-концентрация — нет).

## Принцип
Carry зарабатывает на РАЗНИЦЕ СТАВОК, а не на угадывании — но только если купон реально
перекрывает издержки ПОСЛЕ затухания. Пока эмпирика этого не показывает — в live не идём.
