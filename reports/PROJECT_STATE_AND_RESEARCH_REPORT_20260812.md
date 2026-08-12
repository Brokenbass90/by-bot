# Состояние торговой станции — 12 августа 2026

Срез доказательств: 11:05 UTC. Это ответ «что реально работает, что сыро и куда
двигаться», а не рекламный список модулей.

## Короткий вывод

Шаг вперёд широкий, но пока в основном в достоверности и пропускной способности
исследований. Денежный crypto-контур по-прежнему один: маленький ATT1 canary.
Alpaca — защищённый пилот с двумя существующими позициями, но не доказанная
стратегия отбора. Новая практическая надежда появилась у Inplay: исправленный
causal replay допускает prospective zero-risk shadow, и этот collector уже
запущен. MPL и причинный XSEC текущей формулировки честно отклонены.

Live Bybit напрямую подтверждён с сервера: `0` открытых позиций. Локальный
read-only ключ истёк (`retCode=33004`), поэтому локальный checker временно не
является источником истины; server checker вернул `retCode=0` и broker flat.
Live-код, ордера, риск и сервисы в этой сессии не менялись.

## Карта системы и ворота капитала

```mermaid
flowchart LR
    A["Public/PIT data"] --> B["Passport + prereg"]
    B --> C["Causal replay"]
    C --> D["Independent audit"]
    D --> E["Prospective shadow"]
    E --> F["Tiny canary"]
    F --> G["Measured money sleeve"]
    H["AI / Claude / DeepSeek"] --> I["Findings and hypotheses"]
    I --> B
    H -. "no secrets, orders or risk" .-> E
```

AI помогает искать дефекты, фенотипы убытков и гипотезы, но не может перескочить
ворота, включить стратегию или менять риск. Любая находка становится знанием
только после `finding → reproduction → patch → tests → receipt`.

## Контуры денег и исследований

| Контур | Текущий статус | Что измерено | Главный следующий gate |
|---|---|---|---|
| ATT1, 8 majors | `CANARY`, tiny risk | старый narrow anchor `308` сделок, `+0.098R/сделку`; wide 62-symbol `-0.035R/сделку` | clean post-fix N20, exact lifecycle reconciliation, net `>=+2R`, PF `>=1.20` |
| Inplay ETH 24h | `SHADOW`, zero risk | causal next-open `N=455`, 3/4 folds positive, median `+0.1705R`; один fold `-0.4602R` | prospective N30–50 без tuning; затем symbol/time OOS |
| Funding positioning | `SHADOW`, zero risk | два свежих dynamic/frozen epoch; капитала нет | закрытые forward trials и net economics |
| XSEC crypto | `REJECT` для текущего causal V1 | base 15bps CAGR `3.81%`, Sharpe `0.41`, DD `25.72%`; stress 30bps total `-5.82%` | новая гипотеза, не спасение старой параметрами |
| MPL | `REJECT` обеих рук | V4 excess `+0.064R`, но bootstrap lower `-0.180`; V3 excess `+0.042R`, lower `-0.239` | закрыть формулировку; новый механизм = новая версия/новые данные |
| Alpaca equities | `SAFE_HOLD` | счёт около `$486`, ABBV/SCHW имели broker stops; старый v38 backtest не соответствует live-контракту | завершить PIT 1000, validator, exact live-contract replay |
| FX/CFD | `RESEARCH`, низкий приоритет | старые H4 варианты слишком редкие, preflight false | XAUUSD/OANDA contract, реальные spread/swap/news, затем честный annual replay |
| L2 / recent levels | `DATA_COLLECTION` | alt24: 24 символа, `28,544` observations; server BTC/ETH tape `1.31GB` | 2+ недели и различающий контроль `wall` vs обычный recent traded level |

Ни одну строку нельзя складывать в прогноз годовой прибыли. У контуров разные
стадии, разные окна и только ATT1 имеет ограниченную crypto money-authority.

## Что закончено в этой сессии

1. **MPL вскрыт один раз после freeze/push.** Обе заранее объявленные руки
   отклонены, независимый receipt audit прошёл без ошибок. Это освобождает WIP
   и не даёт месяцами улучшать отрицательную формулировку постфактум.
2. **XSEC пересчитан причинно.** Entry только next-open, funding cashflows
   фактические, stress-costs включены. Старые красивые `7.5–9.5%` отозваны.
3. **Inplay отремонтирован.** Физический ETH 5m пакет заканчивается до
   `2025-10-01`; signal-close не является входом, исполнение — next 5m open,
   incomplete windows fail-close. Независимый audit дал
   `CAUSAL_VIABLE_SHADOW_ONLY`.
4. **Inplay prospective collector запущен.** Screen
   `research_inplay_prospective_20260812`, цикл 15 минут, public-only,
   `authentication=false`, `order_capability=false`, капитал `0`. Он собирает
   signal timestamp, next-open, stop-first, 24h exit, MFE/MAE и net R.
5. **Research supervisor расширен до 6/6 healthy jobs:** Alpaca adaptive,
   XSEC process-observation, funding dynamic/frozen, project audit, Inplay.
6. **Данные для carry расширены.** Funding archive есть по 137 символам; spot
   daily pre-holdout: 74 поддерживаемых spot-инструмента, 67 с данными, 46,742
   бара. Покрытие частичное и PIT ещё не доказан.
7. **Реальные Bybit fee rates проверены read-only:** linear maker `2 bps`,
   taker `5.5 bps`; spot maker/taker `10/10 bps`. Модель `+2 bps` допустима для
   perp maker, но неверна для spot carry.
8. **Лаборатория стала строже.** Passport привязывает input/code/contract,
   static scanner больше не выдаёт пять ложных E1, AI registry видит `130`
   модулей (`45` wired, `85` not wired). `41` сфокусированный тест прошёл.

## Что обнаружено в 500+ грязных файлах

Массовая зачистка не выполнена и не должна выполняться вслепую. Новый read-only
аудит выделил `176` кодовых кандидатов:

| Корзина | Количество | Действие |
|---|---:|---|
| test-backed candidate | 15 | отдельный diff, тест, тематический commit |
| evidence-backed, needs reproduction | 118 | восстановить точную команду/data contract, затем повторить |
| referenced, needs review | 16 | проверить реального consumer и актуальность |
| unreferenced quarantine candidate | 27 | не удалять; вынести только после reference-map и receipt |

В этом пуле scanner не нашёл order authority или credential touch. Первая
полезная очередь: ATT1 filter diff, range mean-reversion, strategy adapter,
tech registry, trend pullback, Alpaca validator, sweep/reclaim, negative-trade
tools. ATT1 dirty filter не принят: это live-risk файл, пока нет reproduction.

Полный индекс: `reports/DIRTY_RESEARCH_WORKBENCH_AUDIT_20260812.md` и JSON в
`reports/evidence/DIRTY_RESEARCH_WORKBENCH_AUDIT_20260812.json`.

## Что хорошо, плохо и сыро

### Хорошо

- server-side Bybit truth сейчас flat; L2 server collector свежий, lag `2ms`;
- order book collectors имеют disk guards, ключей и ордерных методов нет;
- исследовательские процессы переживают паузы между сессиями;
- ложные backtest-контракты теперь fail-close, а не превращаются в «результат»;
- появилась вторая направленная crypto-гипотеза, которая уже копит forward.

### Плохо

- одной доказанной money-ноги недостаточно для станции;
- ATT1 wide-universe отрицателен: динамический подбор нельзя заменять простым
  расширением allowlist;
- текущие MPL/XSEC не проходят независимые денежные ворота;
- локальный Bybit checker key истёк; Alpaca/Massive секреты требуют rotation;
- серверный L2 tape близок к free-space guard: `6.4GB` свободно при минимуме
  `5GB`, tape `1.31GB` из cap `2GB`. Guard не переопределять.

### Сыро, но перспективно

- Inplay prospective ETH;
- funding/carry после exact spot↔perp mapping и survivorship/PIT;
- среднесрочный cross-sectional equities после завершения PIT;
- L2 target/false-break/maker fill после накопления недель ленты;
- отдельные BTC/ETH midterm families с дневным/4h горизонтом, но только через
  новый causal contract и реальные издержки.

## Секреты и безопасность

В `configs/alpaca_live_v38.env` и `configs/massive_stocks_local.env` лежат
не-placeholder ключи. Они mode `600` и игнорируются Git, но должны быть
перевыпущены в кабинетах провайдеров. Автоматически завершить rotation нельзя
без авторизованной dashboard-сессии. Безопасный порядок: создать новые ключи →
обновить локальные/server secrets → GET-only account/data smoke → отозвать
старые → записать только non-secret receipt. Значения ключей не копировать в
отчёты или Git.

## Почему пока нельзя честно ответить «$1,000 на каждый контур через год»

Новый годовой backtest делать можно и нужно, но только после фиксации для каждой
платформы пяти контрактов: point-in-time universe, causal execution, fees/
slippage/funding/swap, портфельные веса/слоты и единая accounting/DD модель.
Сейчас этих условий одновременно нет ни у Alpaca, ни у XSEC, ни у FX/CFD.
Сложение старых красивых чисел дало бы точный на вид, но ложный прогноз.

Разрешённый продукт следующего этапа — одна таблица `base/stress` за каждый
календарный год с CAGR, max DD, красными месяцами, turnover, capacity и
процентом дохода от top-5 symbols. Только после этого можно дать диапазон, а не
одну цифру, для `$1,000 × platform`.

## Актуальный план

### P0 — безопасность и источники истины

1. Ротировать Alpaca/Massive и восстановить отдельный read-only Bybit checker.
2. Не менять live по результатам research; сохранить ATT1 `0.10` до clean N20.
3. Ежедневно сверять broker ↔ runner ↔ owner ↔ accounting и server disk guard.

### P1 — ближайшая вторая crypto-нога

1. Копить Inplay ETH prospective N30–50 без tuning.
2. Параллельно воспроизвести level-reaction/retest на wide PIT universe;
   maker-entry только для возвратных, не импульсных сигналов.
3. Funding leg пересчитать на spot/perp intersection с exact funding, fee и
   borrow/capital contract.

### P2 — Alpaca и честные годовые числа

1. Дождаться `1000/1000` GET-only pool (на срезе `783/1000`, failures `0`).
2. Запустить независимый PIT validator и repaired live-contract replay.
3. Сравнить baseline, trailing/protective exits и regime sizing по одной
   степени свободы; AI — challenger/risk overlay, не автономный трейдер.

### P3 — разбор наследия и новые семейства

1. Забирать по 5–10 кандидатов из аудита в отдельные воспроизводимые batches.
2. Вести единый finding ledger: raw → reproduced → accepted/rejected → commit.
3. После crypto/Alpaca — XAUUSD/FX H4, затем CFD; арбитраж/DeFi возвращать
   только при измеримой положительной экономике после всех издержек.

## Точные receipts

- `reports/research/mpl_two_arm_holdout_20260812/result.json`
- `reports/research/mpl_two_arm_holdout_20260812/independent_audit.json`
- `reports/research/INPLAY_CAUSAL_RECEIPT_AUDIT_20260812.json`
- `research_lab/results/path_sim_v4_causal_preholdout_r2/run_passport.json`
- `runtime/inplay_prospective_shadow_v1/status.json`
- `reports/research/BYBIT_ACCOUNT_FEE_READONLY_20260812.json`
- `reports/research/BYBIT_SPOT_DAILY_PREHOLDOUT_VALIDATION_20260812.json`
- `reports/evidence/DIRTY_RESEARCH_WORKBENCH_AUDIT_20260812.json`
