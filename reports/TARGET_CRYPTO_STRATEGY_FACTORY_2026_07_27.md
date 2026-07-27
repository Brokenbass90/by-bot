# Целевая фабрика crypto-стратегий

Дата: 2026-07-27

Статус: архитектурная цель, не список разрешённых live-рукавов.

## Принцип

Проект не должен содержать 97 независимых вариантов одной идеи. Цель —
несколько физических sleeves с общими проверенными технологиями:

- единый причинный level snapshot;
- отдельно long и short;
- отдельно horizontal и sloped geometry;
- общий dynamic universe;
- единый execution contract;
- общий costs/funding/slippage contract;
- side/regime/PIT OOS;
- общий allocator при максимуме 3 открытых позиций.

Наличие общего движка не означает общий вердикт. Каждая сторона, геометрия и
режим зарабатывают право на риск отдельно.

## Целевые семейства

| ID | Семейство | Long | Short | Геометрия | Роль |
|---|---|---|---|---|---|
| LVL-REJECT | Отбой/отскок от уровня | support rejection | resistance rejection | horizontal + sloped, отдельно | тактический |
| BREAK-RETEST | Пробой и первый ретест | resistance break/retest | support break/retest | horizontal + sloped, отдельно | тактический |
| IMPULSE | Импульсный пробой | expansion long | expansion short | horizontal + sloped | трендовый |
| EXHAUST | Истощение разгона | dump exhaustion | pump exhaustion | без обязательного уровня, уровень как confluence | событийный |
| SWEEP | Закол/ложный вынос/возврат | low sweep reclaim | high sweep reject | horizontal + sloped | контртрендовый event |
| LIQ-DENSITY | Плотности и охота за ликвидностью | reaction/follow | reaction/follow | liquidity cluster | микроструктура |
| MIDTERM | Среднесрочный тренд и коррекция | pullback continuation | rally fade/continuation | H4/D1 levels | медленный core |
| XSEC | Кросс-секционная относительная сила | winners | losers | none | market-neutral/relative |
| UNLOCK | Разлок предложения | только редкие special cases | pre/event/post unlock | event | ортогональный short |
| FUND-OI | Funding/OI positioning | squeeze/reversal | squeeze/reversal | event + derivatives state | filter/event |
| TERM | Отклонение perp/dated-future basis | по знаку dislocation | по знаку dislocation | none | relative-value research |
| OPTIONS | Опционная экспирация/gamma | regime dependent | regime dependent | BTC/ETH only | low-priority event research |

## Что не является самостоятельной стратегией

- Elder — regime/confluence filter.
- Seasonality — preregistered filter/priority multiplier.
- AI — supervisor, allocator и диагност, но не источник «магического сигнала».
- Funding rate сам по себе — feature, пока отдельный after-cost edge не доказан.
- Open interest сам по себе — positioning feature.
- Уровень сам по себе — объект контекста, не вход.

## Среднесрок

### Core

- BTC и ETH.
- Максимум одна среднесрочная позиция.
- H4/D1 trend/pullback.
- Широкий causal stop, costs/funding, отдельные long/short verdicts.

### Challenger

- PIT top-liquid majors.
- SOL/BNB/XRP/LINK рассматриваются как кандидаты.
- Нельзя заранее фиксировать сегодняшний список как исторический universe.
- Параметры H1 ATT1 нельзя переносить на H4/D1 без новой валидации.

Для long-покупки коррекции нужна не «красивая линия», а:

1. подтверждённый старший тренд;
2. неизменяемый level snapshot с `known_at`;
3. касания/прочность и отсутствие пробоя;
4. horizontal/sloped confluence как отдельная ablation-гипотеза;
5. измеренный limit-fill либо next-open;
6. frozen invalidation;
7. volume/OI только как заранее определённый filter;
8. лестница выхода, проверенная отдельно от входа.

## Портфель при трёх слотах

- Слот A: максимум один MIDTERM.
- Слоты B/C: tactical/event/XSEC.
- Реализация может быть общим allocator, но эти reservation rules должны
  воспроизводиться в backtest.
- Глобально ограничиваются open risk, одинаковая сторона, symbol overlap,
  beta и корреляционный кластер.
- При конфликте побеждает заранее определённый quality/health priority,
  а не стратегия с лучшим результатом будущей сделки.

## Самоподдержание

Автоматически разрешено:

- собирать решения, отказы и outcomes;
- оценивать здоровье sleeves;
- снижать/обнулять риск при деградации;
- ранжировать прошедшие gate sleeves;
- предлагать challenger;
- останавливать входы при инфраструктурной или риск-ошибке.

Только через новый research receipt и owner/Codex approval:

- менять параметры сигнала;
- расширять universe;
- менять геометрию;
- повышать live risk;
- переводить shadow в canary;
- удалять/заменять champion.

## Приоритет исследований

1. Сохранить ATT1 short tiny-canary и собрать честный live ledger.
2. Исправить XSEC methodology, затем продолжить risk-zero shadow.
3. Проверить полный volume setup:
   dynamic volume universe → level/retest → measured entry → volume exit.
4. ATT1 seasonality как sealed filter study.
5. Token unlock PIT event study.
6. Funding settlement × OI × price/flow interaction.
7. MIDTERM BTC/ETH baseline и PIT-major challenger.
8. LevelSnapshotV2 и новые horizontal/sloped challengers.
9. Options/gamma и term-structure только после более дешёвых исследований.

## Что означает «полный пакет»

Полный пакет — не одновременный запуск всех строк. Это:

- 3–6 доказанных и слабо коррелированных sleeves;
- long и short readiness для разных режимов;
- один medium-term core;
- один relative/market-neutral sleeve;
- 1–2 event sleeves;
- общий allocator и risk rails;
- автоматическое наблюдение и понижение риска;
- ручное утверждение изменения сигнала и повышения капитала.
