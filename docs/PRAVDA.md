# ПРАВДА О ПРОЕКТЕ

Актуально на 20 августа 2026. Этот файл — текущий снимок, он перезаписывается целиком. История остаётся в Git. Ни одна строка research, paper, shadow или AI не даёт права менять live-риск.

## Live, подтверждено напрямую

- Bybit-монолит на сервере активен; при проверке прямой signed GET показал 0 открытых позиций.
- Серверный Git: `f7ed0116a5f5b8fed59dbf8a339a85989bcf2f3b`; локальная исследовательская ветка другая. Новые изменения этой сессии в live не развёрнуты.
- ATT1 остаётся tiny-canary/проверкой живого контура. Повышать риск по текущим историческим данным нельзя.
- Alpaca: снимок брокера от 19 августа — equity $489.75; ABBV и SCHW имели брокерские стопы. Это защищённый пилот, не доказанная доходная нога.

## Доказанные технические факты

1. Фактический тариф Bybit для проверенных linear-пар аккаунта: maker 2.0 bps, taker 5.5 bps. Maker-rebate нет. Spot BTC: 10/10 bps.
2. Замороженный Inplay-код воспроизводит исторические сырые частоты на четырёх 35-дневных срезах: 32, 40, 62 и 81 сигналов, то есть 0.91–2.31 сигнала/день. Это проверка идентичности и живости, не edge.
3. Гипотеза «Inplay молчал из-за отсутствующих `BREAKOUT_*`» отклонена. Коллектор намеренно запрещает эти override; текущий N=0 относится к свежему рынку при том же frozen-контракте.
4. ATT1 paper-limit теперь моделируется по публичным L2/tape без заявок: limit на best bid/ask, 60 секунд, затем market fallback. Первые N=3: maker 2/3, средняя экономия +2.478 bps. N слишком мал для live.
5. Wide-stop ATT1/SBR1 не имеет parity с live. На 906 сопоставимых сигналах исследовательский ×6 и предложенная live-конструкция дали разные стопы и TP. Это блокирует shadow с претензией на идентичность и тем более live.
6. В generic SLOPED найдено и исправлено смешение множителя риска ATT1 с `SLOPED_RISK_MULT`. Это технический ремонт, не новая нога.

## Денежные контуры

| Контур | Стадия | Что известно | Следующий gate |
|---|---|---|---|
| ATT1 | tiny live canary | живой execution-контур, историческая экономика конфликтует между контрактами | exact research↔live parity; paper limit N≥20; чистый forward |
| Inplay | prospective shadow | историческая частота воспроизводится, свежих сигналов пока 0 | продолжать frozen shadow; не менять параметры |
| ATT1/SBR1 wide stop | research blocked | raw signal density есть, geometry/exit parity нет | единый adapter-parity harness |
| Alpaca v38 | protected pilot | капитал сохранён, честная доходность ещё не доказана | exact live-contract replay, PIT/sector/corporate actions, GTC receipt |
| XSEC/funding | research/shadow | не live authority | spot/perp mapping, PIT universe, реальные комиссии, forward |
| XAUUSD | data ready | M5: 87,439 баров 2024-07-08…2025-09-30; доказанной ноги нет | prereg session/retest и causal replay |
| FX/CFD | harness/research | торговать пока нечего | XAU first, затем liquid FX portability |
| MT5 signal copy | local gated tool | код принимает ручную разметку только через owner approval; live выключен | новый токен только в local env, exact demo account allowlist, demo smoke |

## Текущие безопасные исследования

- Inplay prospective с обязательным startup-gate исторической частоты.
- ATT1 limit-execution paper, без private API и без заявок.
- Публичные L2/tape коллекторы BTC/ETH/ONDO и 24-alt density.
- Возобновляемая загрузка M5 2024-03…2025-09 для текущего 137-символьного H1-инвентаря. Это ещё не PIT-universe: делистинги и будущие листинги должны учитываться отдельно.

## Не доказано и не разрешено

- Нельзя обещать годовую доходность «по $1000 на каждую платформу»: нет 3–4 validated live-equivalent ног и нет совместной модели корреляций/просадки.
- Нельзя считать +2.478 bps paper-limit доказанными до достаточного N и сверки fill-модели.
- Нельзя считать ATT1 ×3.30 или ×6 улучшением live: сейчас это другая геометрия сделки.
- Нельзя включать micro-canary только потому, что backtest положительный. Минимум: exact contract, costs, independent audit, shadow/paper receipt и явный owner approval.
- Нельзя использовать AI как денежную власть. Он предлагает, диагностирует и объясняет; broker truth и risk authority остаются отдельными.

## Снято окончательно или до нового основания

- Maker-rebate Bybit на проверенном уровне аккаунта — отсутствует.
- «Подать `BREAKOUT_*`, и Inplay оживёт» — ложный диагноз для frozen prospective-контракта.
- Прямой перенос исторического wide-stop PnL в live — запрещён до adapter parity.
- Старые красивые бэктесты, не совпадающие с universe, sizing, entry, exits и costs live, не являются evidence.

## Ближайший порядок

1. Копить paper-limit и Inplay без риска.
2. Построить ATT1/SBR1 normalized adapter-parity, выбрать одну геометрию и только затем новый прогон.
3. Завершить Alpaca exact replay и отдельно подтвердить развёртывание GTC-защиты.
4. Запустить первый prereg XAU causal replay на уже готовых данных.
5. Довести wide M5 archive, затем прогнать Inplay portability без чтения sealed holdout.
6. Инвентаризировать грязный worktree по reference-map; ничего массово не удалять.
