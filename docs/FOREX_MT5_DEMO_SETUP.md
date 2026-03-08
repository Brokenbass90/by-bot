# Forex MT5 Demo Setup

## Что нужно для нашего bridge

Bridge работает только с MT5-аккаунтом, где есть:

- `MT5_LOGIN` — номер торгового счёта
- `MT5_PASSWORD` — именно торговый пароль, не investor/read-only
- `MT5_SERVER` — имя сервера брокера в MT5
- `MT5_TERMINAL_PATH` — только если терминал не находится автоматически

Если брокер/платформа не даёт эти три значения и не использует MetaTrader 5, текущий bridge туда не подключится.

## Где это обычно взять

### Вариант 1. Уже есть demo MT5 счёт у брокера

Обычно в личном кабинете или в письме после открытия demo счёта есть:

- account/login
- password
- server

### Вариант 2. Открыть demo внутри MT5

1. Установить MetaTrader 5 от брокера или стандартный MT5.
2. Открыть `File -> Open an Account`.
3. Найти сервер брокера.
4. Выбрать `Open a demo account` или аналогичный шаг.
5. После создания счёта сохранить:
   - логин
   - пароль
   - сервер

## Локальный env для bridge

Создай локальный файл:

`~/.config/bybit-bot/forex_mt5_demo_local.env`

На базе:

`configs/forex_mt5_demo_local.env.example`

Минимальный пример:

```env
MT5_LOGIN=12345678
MT5_PASSWORD=replace_me
MT5_SERVER=BrokerName-Demo
FOREX_BRIDGE_SEND_ORDERS=0
FOREX_BRIDGE_MAX_OPEN_PER_PAIR=1
FOREX_BRIDGE_MT5_DEVIATION_POINTS=20
FOREX_BRIDGE_MT5_MAGIC=260308
```

## Dry-run

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
bash scripts/run_forex_mt5_demo_bridge.sh
```

Проверить:

- `runtime/forex_mt5_demo_bridge_latest.jsonl`
- `state/forex_mt5_demo_bridge_state.json`

Dry-run ничего не отправляет в MT5. Он только:

- читает active/canary combos из `docs/forex_demo_env_latest.env`
- ищет свежие сигналы
- пишет лог решения

## Включение demo-ордеров

Когда dry-run чистый:

```env
FOREX_BRIDGE_SEND_ORDERS=1
```

И снова:

```bash
bash scripts/run_forex_mt5_demo_bridge.sh
```

## Что сейчас будет торговаться

Текущий demo launch profile:

- `GBPJPY@trend_retest_session_v1:gbpjpy_stability_a` — active
- `GBPJPY@trend_retest_session_v1:gbpjpy_stability_b` — canary

Источник:

- `docs/forex_demo_env_latest.env`
