# Monthly V4: сквозной ORDERS_OFF кандидат завершён

18 октября 2026. Продолжение принятого account/transport/accounting этапа
`54afc18055506e9bf4bfb835171e8b43697bfb29`. Реальных заявок и новых финансовых
разрешений нет. SHOP остаётся отменённым; NET сохранён.

## DONE

Существующий полный источник **57 инструментов + SPY** проходит прежнюю QA и
замороженный Monthly selection в ту же owned книгу, которой пользуется native
binding. `MonthlyManager` связывает source, opening, maintenance и accounting;
исходный account lock и точные book/runtime/HALT сохраняют единственного writer.
Нового отбора, финансового журнала, broker adapter или Brain не создано.

На VPS установлен отдельный кандидат из **44 файлов**:
`/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-29d61ad33238dac0`.
Material SHA `29d61ad33238dac0c4df7153d18691dbed9800732c853e0cc9010b7c84945662`,
spec SHA `43d59100ba46775758a19011c93d2a070a48814c5b1e3ad03b59fb4e64c1e042`.
Численный contract `a32aaec31e8bb31d6fab8274661ecc4e79ed1557192a689cd8461fb8983e402e`
не изменён; новый technical identity учитывает исправленный код. В пакете оставлен
принятый Dynamic helper из `d205f8f`, SHA `7ab36fd9…09622`.

Четыре source/preview systemd unit зарегистрированы **disabled/inactive**,
проверка синтаксиса PASS. Их CLI не имеет финансового apply-переключателя.
Месячный календарь и дневной ratchet определяются существующим broker calendar
и книгой; timer только вызывает source/preview, не превращает каждый вызов в отбор.
Существующий GET-source timer сохранён. Денежный daemon не активирован.

Безопасное тестовое сообщение через существующий Telegram helper **доставлено**:
HTTP200, `ok`, message_id **15223**. Повторная отправка не выполнялась.
Отдельные source/manager incidents не скрывают друг друга, повторный сбой после
восстановления получает новую generation. Обычный успешный вызов молчит.

Rollback acceptance выполнен на изолированном ORDERS_OFF указателе после полного
simulated расчёта: первая операция ACCEPTED, повтор ALREADY_RECORDED. При owned
позиции, native reservation или неизвестной accounting finality откат блокируется:
существующий manager обязан продолжать защиту. Это **не проведённый LIVE rollback
NET** и не разрешение менять его custody.

## TESTED

- 316 целевых PASS; после последнего небольшого rollback исправления — отдельные
  целевые проверки и **135 PASS на окончательных точных файлах candidate**:
  34 source imports, **0 checkout fallback**. Числа перекрываются, не суммируются.
  Полный исторический repository suite не запускался.
- Сквозной прогон выполнен локально и на VPS: реальные source QA, frozen selector,
  serializer, native ledger и accounting, с полностью in-memory broker. Fixture
  содержит58 инструментов; selector сам выбрал **CVX**, один simulated вход,
  без подмены функции отбора и без искусственного дополнения корзины.
- Потерянный принятый ответ покупки → restart; потерянный принятый ответ native
  stop → restart; ровно одна покупка, полная защита, daily-close ratchet и DAY
  rearm, owned exit, broker flat, costs/cash finality, освобождение капитала и
  следующий допустимый месячный отбор. Время/цены/комиссии/weekday calendar этого
  прогона синтетические: это не prospective evidence и не доходность.
- Независимый reviewer действительно работал на `gpt-6-astra/high` (проверены
  runtime metadata). Critical0, Important5: fresh-equity weight, последний
  clock/HALT после GET, incident generations, полная custody, фильтр символа до
  replay. Все исправлены с регрессиями. Дополнительно устранены восстановление
  pending stop до rotation, ложная protection после cancelled stop и учёт native
  ledger при rollback. Повторного независимого review после исправлений и
  финансового signoff не заявляем.
- Фактический source/preview CLI на VPS PASS. **77 защищённых старых файлов**
  совпали до/после; исходный lock inode813893 сохранён. NET manager/timer и
  DAY-monitor19Oct13:30UTC активны; SHOP disabled/inactive. Изменений финансовых
  units0, реальных broker requests/writes0.

## REMAINING / BLOCKERS — только будущие факты и личная активация

Инженерные задачи этого ORDERS_OFF пакета закрыты. До **30 октября** нельзя знать
закрытые цены всей следующей месячной сессии, фактический SPY gate, выбранный
символ, его ATR/вес и точный размер. Допустим результат CASH. Подставлять сегодняшние
данные или заранее обещать покупку нельзя.

После actual source нужны отдельный точный **Monthly OWNER GO** и личная
активация/передача единственному денежному manager. Старые SHOP/KITY approvals не
подходят. Capital ceiling487.42, gross.70, weight.60, max4 — пределы, не сумма
первой заявки. Первый bounded scope — один выбранный символ/один новый вход за
сессию в пределах замороженного расчёта, без увеличения веса для освоения денег.

В открытие нужны актуальные account/cash/quote/tradability/fees/native custody и
оригинальный lock. Если NET ещё существует, сначала ранее разрешённый личный
выход2Nov, затем настоящий broker flat/orders/costs/cash finality и подтверждённый
single-manager handoff. Раньше продавать или усыновлять NET нельзя. Реальное
исполнение, фактическую защиту и расходы докажет только разрешённый брокерский
цикл; симуляция не заменяет этот факт. При пропуске окна — NO_SEND, без date carry.

Ближайшие календарные gates: **19Oct13:30UTC /16:30Кипр — NET DAY**,13:35UTC
независимая сверка; **30Oct20:00UTC** закрытие отбора, source после20мин;
**2Nov14:30–14:35UTC /16:30–16:35Кипр** условное Monthly opening. Broker calendar
перед окном перепроверяется. Monthly покупка19Oct не предусмотрена.

[Manifest](evidence/alpaca_monthly_e2e_20261018/source_manifest.json),
[tests](evidence/alpaca_monthly_e2e_20261018/verification.json),
[review](evidence/alpaca_monthly_e2e_20261018/review.json),
[фактическая VPS установка/уведомление/rehearsal](evidence/alpaca_monthly_e2e_20261018/deployment.json),
[точный инертный activation packet](evidence/alpaca_monthly_e2e_20261018/activation_packet.json).
Следующая доступная работа: KITY safety и Elder actual event intake; календарь
Monthly их не блокирует.
