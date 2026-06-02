# Exchange Keys Setup

Никогда не вставляй реальные ключи в чат, GitHub, документы или заметки. Этот файл описывает только имена переменных и правила безопасности.

## Зачем нужны ключи

Текущий cross-exchange funding scanner работает на публичных данных и ключи не использует. Binance/Bitget ключи нужны на следующем этапе:

- read-only проверка балансов и доступности инструментов;
- dry-run с реальными лимитами аккаунтов;
- tiny live canary только после отдельного подтверждения.

## Что создать сейчас

### Binance

- API key для futures/spot аккаунта.
- Withdrawal: disabled.
- Trading: disabled на первом этапе.
- Read-only / account info: enabled.
- IP whitelist: включить, если Binance позволяет, на IP сервера.

### Bitget

- API key для futures/USDT perpetual аккаунта.
- Withdrawal: disabled.
- Trading: disabled на первом этапе.
- Read-only / account info: enabled.
- Passphrase сохранить только в server `.env`.
- IP whitelist: включить, если Bitget позволяет, на IP сервера.

### OKX

Опционально позже. Если верификация не проходит, не блокируем работу: стартовый набор это Bybit + Binance + Bitget.

## Куда вписывать

Реальные значения вписываются только в server `.env`, не в этот файл:

```dotenv
BINANCE_API_KEY=
BINANCE_API_SECRET=

BITGET_API_KEY=
BITGET_API_SECRET=
BITGET_API_PASSPHRASE=

OKX_API_KEY=
OKX_API_SECRET=
OKX_API_PASSPHRASE=
```

Веб-страница API Keys сейчас показывает статус этих ключей, но не является полноценным сейфом для Binance/Bitget. До отдельной secure-формы вводим ключи вручную на сервере.

## Когда включать торговые права

Не сейчас. Порядок такой:

1. Public scanner + validator + shadow: уже работает без ключей.
2. Read-only keys: проверить балансы, инструменты, комиссии и режим аккаунтов.
3. Dry-run with account caps: бот рассчитывает, но не отправляет ордера.
4. Tiny live canary: маленькие суммы и жесткие caps.
5. Увеличение лимитов только после закрытых циклов и отчета.

