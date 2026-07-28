# Massive Stocks Basic — что делать владельцу

## Текущий статус

На этом Mac всё уже настроено:

- ключ хранится только в `configs/massive_stocks_local.env`;
- права файла `0600`;
- файл исключён из Git;
- 28 июля повторно проверены три бесплатных endpoint;
- результат: `all_checks_passed=true`, HTTP 200 по reference tickers,
  adjusted daily aggregates и corporate-action splits.

Передавать ключ в чат или Codex не нужно. Платный тариф сейчас не нужен.

## Если ключ когда-нибудь придётся создать заново

1. Открыть Massive Dashboard.
2. В левом меню выбрать **Keys** → **Manage keys**.
3. Скопировать API key `Default` либо создать отдельный ключ `bybot-alpaca-research`.
4. В Finder открыть корень проекта и дважды нажать
   `START_MASSIVE_BASIC_SETUP.command`.
5. Вставить ключ в невидимое поле Terminal и нажать Enter.
6. Дождаться строки `all_checks_passed: true`.

Launcher сам:

- запишет `MASSIVE_API_KEY=...` в локальный env;
- выставит права `0600`;
- выполнит только три запроса, не превышая бесплатный rate limit;
- сохранит обезличенный receipt в
  `runtime/massive_stocks_basic_audit.json`.

## Ручная повторная проверка

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
.venv/bin/python scripts/verify_massive_stocks_basic.py \
  --env-file configs/massive_stocks_local.env \
  --output-json runtime/massive_stocks_basic_audit.json
```

Ключ не присылать. Если он когда-либо попадёт в скриншот, лог или Git —
отозвать его в Massive Dashboard и создать новый.

## Для чего бесплатного Basic достаточно

- проверить point-in-time поля, inactive/delisted tickers и corporate actions;
- построить двухлетний PIT-прототип Alpaca;
- воспроизвести exact-parity входы и выходы на доступном периоде.

Для окончательного многолетнего robustness-verdict двух лет недостаточно.
Покупать Starter/Developer имеет смысл только если бесплатный PIT-прототип
сначала пройдёт untouched и cost-stress gates.
