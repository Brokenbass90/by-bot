# LIVE_CALLER_PARITY — execution plan

Дата заморозки плана: 2026-08-24. Authority: engineering/research only.
Этот план не меняет ордера, риск, геометрию, слоты или money authority.

## Цель

Доказать, что настоящий production caller ATT1/SBR1 принимает те же закрытые
свечи, causal regime, параметры, фильтры биржи, fill/rebase и portfolio gates,
что frozen research contract. Только после этого разрешён одноразовый
reserved-period replay; live-риск остаётся отдельным решением владельца.

## Текущая истина

- Component adapter parity: `PASS`.
- Production caller parity: `BLOCKED`.
- ATT1 money caller: short-only tiny canary, regime-side gate отсутствует.
- SBR1: public zero-risk shadow; money authority отсутствует.
- ATT1 live defaults расходятся с frozen contract по пяти пунктам:
  `1.1/0.06/BE=1/trail activation=1/2016` против
  `6.6/0.25/BE=0/trailing off/4032`. Это перечень для gate, не команда менять
  live.
- `VOLADJ` — 4h sizing multiplier по умолчанию, не измеренный 24h entry veto.
- `exposure_gate.py` существует, но production caller его не вызывает.

## Пакеты работы и критерии завершения

### P1. Persisted causal BTC H1 regime

- Один bootstrap EMA200 из непрерывной closed-H1 истории.
- Каждый новый H1 применяется ровно один раз; duplicate идентичной свечи
  идемпотентен, конфликт/gap/out-of-order — fail closed.
- State/receipt имеют hash chain, data/source/config provenance, atomic `0600`
  persistence и переживают рестарт.
- ATT1 допускается только в frozen `flat_down`, SBR1 — в `flat_up`; режим сам
  не даёт money authority.

`DONE`, когда corruption/restart/duplicate/gap tests проходят и ни один тест не
использует broker/private/order surface.

### P2. Настоящий production caller receipt

- Вынести одну pure decision boundary, которую вызывает сам
  `try_att1_entry_async()`, а replay вызывает без монолита.
- Receipt обязан содержать consumed rows hash, actual effective config,
  strategy source hash, causal regime proof, signal/drop reason, exchange
  filters, tick rounding, intended fill contract, slot/exposure decision и
  authority flags.
- Исключения стратегии и contract violations не проглатываются как
  `no_signal`; они становятся terminal fail-closed receipt.
- Default off; shadow mode не достигает submit/order code.

`DONE`, когда одни и те же frozen inputs дают byte-equal caller receipts в
production-shaped и replay paths, включая no-signal/drop/error cases.

### P3. Fixed-major8 regime ON/OFF replay

- До запуска заморозить один comparison: тот же сигнал/fill/outcome/cost
  contract, меняется только causal regime gate `ON/OFF`.
- Публиковать отдельно `N`, net R, PF, DD, positive months, symbol
  concentration, tail removal и base/stress.
- Порог/EMA/band после просмотра не настраивать.

`DONE`, когда coverage и hashes совпадают, scorer выдаёт единственный
предзарегистрированный verdict. PASS не меняет live автоматически.

### P4. Wide evidence shadows

- Money universe остаётся major-8.
- Evidence universe ATT1 и SBR1 — immutable fixed-51.
- Перед первой counted decision: frozen universe/filter manifest, public
  instrument coverage, caller receipt parity, causal regime, random control
  для SBR1, lifecycle/cost contract.
- Один закрытый контракт `HFTUSDT` не подменять другим символом; фиксировать
  как coverage limitation.

`DONE`, когда server receipts подтверждают exact `51`, zero private/broker/order
calls, zero money authority, timer health и first causal evaluation. `N` двух
рукавов нельзя складывать: каждый достигает своего порога отдельно.

Срок до final-N нельзя брать из `research_lab/chastota.py`: он называл
fixed-51 post-hoc лучшие 51 символов отдельно в каждом окне и использовал
устаревшую money-восьмёрку с XRP вместо SUI. До manifest-driven replay и
полного lifecycle ETA имеет статус `NOT_MEASURED`.

### P5. `verify_live_config` как gate, а не диагностический print

- Manifest-driven exact universe/data/source/config.
- Не глотать исключения, не брать первые 25 файлов по glob, не читать env с
  секретами.
- Проверять пять ATT1 расхождений, time-stop semantics, regime ON/OFF,
  exchange filters, caller receipt hash и liveness.
- JSON receipt + ненулевой exit при любом mismatch.

`DONE`, когда positive fixture = PASS, а каждый намеренный drift даёт
конкретный FAIL code.

### P6. Exposure/slots после caller parity

- Подключить `exposure_gate` к pure boundary default-off.
- Replay `3` против `12` слотов с теми же сигналами и risk budget.
- Требовать DD/tail/concentration gate; исторические `4.53x` и
  `7.1R -> 8.7R` не являются разрешением.

### P7. Ограниченный reserved-period replay

- Только после P1-P5 PASS и независимой проверки scorer/manifest.
- Exact window текущего guard: `[2025-10-01, 2026-07-01)` = 273 дня.
- Окно уже не идеально sealed: XSEC recount пересёк reserved rows и был
  quarantined. Поэтому результат — быстрый OOS diagnostic, не замена
  prospective shadow и не доказательство будущей доходности.
- Один запуск двух frozen legs, без перебора, outcome публикуется при любом
  знаке.

## Компрессия времени и Plan B

1. P1-P5 выполняются параллельно и дают инженерный ответ за дни, не месяцы.
2. Fixed-51 prospective сбор стартует сразу после своих safety gates и идёт в
   фоне.
3. Reserved replay даёт быстрый исторический falsification после parity.
4. Если одна нога FAIL — в тот же день она уходит в quarantine, а compute
   переключается на заранее замороженные 5m families; проигравшую конфигурацию
   не тюним на увиденном окне.
5. XAU/MT5 demo paper и Alpaca lifecycle идут отдельными zero-risk дорожками и
   не блокируют crypto parity.

## Definition of done для сильной сессии

- P1-P5 имеют machine-readable PASS receipts и pinned SHA.
- Ни одного проглоченного exception, missed causal decision или необъяснённого
  caller/replay mismatch.
- Deployed zero-risk shadows совпадают с Git и manifest hashes.
- Broker/live orders, ATT1 risk/geometry/slots и SBR1 money authority не
  изменены.
