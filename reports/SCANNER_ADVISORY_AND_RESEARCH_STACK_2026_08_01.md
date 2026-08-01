# Scanner advisory + research stack — 2026-08-01

## Решение

Setup Scanner становится общей наблюдательной поверхностью для человека, AI и
стратегий, но не вторым генератором ордеров. Он публикует атомарный snapshot
`runtime/setup_scanner/state.json` со статусом `risk_zero_advisory`.

Карточка может:

- повысить приоритет проверки символа соответствующей стратегией;
- передать горизонтальный уровень, релевантную swing-линию, инвалидацию и причины;
- попасть в operator snapshot и контекст AI;
- оставаться видимой при `risk_mult=0` как shadow-кандидат.

Карточка не может:

- открыть ордер;
- включить выключенный рукав;
- изменить risk/universe/params;
- заменить native confirmation конкретной стратегии.

## Исправленная геометрия

- две swing-точки больше не считаются подтверждённой линией: их `R²=1.0`
  тривиален и неинформативен;
- валидная swing-линия требует минимум три подтверждённых pivot;
- resistance fade / breakout / bear continuation получают только resistance;
- support bounce / breakdown / trend pullback получают только support;
- volatility squeeze может получить обе стороны;
- regression channel остаётся контекстом и не называется ATT1-наклонкой.

Локальный rebuild после ремонта: 26 geometry snapshots, 52 line candidates,
17 валидных линий с 3+ pivot, 64 карточки, 0 карточек с противоположной ролью,
64 risk-zero advisory.

## Интерактивные графики

SVG-график карточки поддерживает колесо мыши, drag, кнопки `+ / − / Сброс`.
Живой position chart получил тот же viewport contract. Это наблюдательная
функция; торговое состояние не меняется.

## План подключения к стратегиям

V1 уже публикует подсказку и делает её доступной AI. V2 допускается только после
freshness/replay теста: priority router может раньше вызвать native scan указанной
стратегии, но стратегия обязана независимо подтвердить свой сигнал. Сравниваются
две shadow-когорты: обычный scheduler и advisory-prioritized scheduler. Gate:
ни одного дополнительного ложного входа, меньшая latency, одинаковый native
decision hash.

## VectorBT, Optuna, Ollama

- VectorBT — optional research prefilter для массового дешёвого отсева семейств.
  Финальный результат всегда повторяется event-driven движком с тем же ledger.
- Optuna — только train-only search/pruning. OOS не является objective; receipt
  хранит search space, seed, raw/effective trials и frozen winner.
- Ollama — на Mac, не VPS. Роли: критик prereg, классификатор blocker/log и поиск
  противоречий. Доступ к risk/env/orders/secrets запрещён.

Платные сервисы и действия владельца для этого этапа не нужны. Установка
VectorBT/Optuna/Ollama в production runtime не выполняется: сначала отдельный
research venv и воспроизводимый smoke.

## Статус FX-пакета

1 августа два новых фиксированных кандидата сразу получили terminal receipts:

- H4 Momentum: 452 сделки, stress `−29.20%`, 18/25 красных месяцев,
  1/4 положительных folds, 0/5 положительных пар;
- H4 Regime Mean Reversion: 102 сделки, stress `−10.58%`, 16/24 красных месяцев,
  1/4 положительных folds, 0/5 положительных пар.

Обе конкретные реализации закрыты без подгонки. Следующая FX-гипотеза обязана
менять источник edge: cross-pair relative value, session carry или внешний
macro-rate differential; очередной price-only indicator soup не запускается.

## Арбитраж

Контур не удаляется. Standalone cross-exchange funding остаётся low-priority до
N20; его collector, maker/legging lifecycle и basis telemetry переиспользуются.
Капитал запрещён до положительной executable distribution. Исследовательский
фокус — редкие крупные dislocation, basis mean reversion и directional funding
positioning с LOSO/concentration, а не обещание дохода из каждого funding event.
