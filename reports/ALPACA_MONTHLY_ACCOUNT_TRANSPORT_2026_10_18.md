# Monthly — закрытие account/transport и accounting стыков, 18 октября

**Результат: новый проверенный ORDERS_OFF компонент установлен отдельно на VPS.
Это не financial activation и не LIVE_READY.** Основной P0 остаётся Monthly.
Исходный отбор/веса/ATR/дневной храповик/месячный календарь не изменены.
SHOP отменён владельцем; действующий NET продолжает сопровождаться.

## Что закрыто кодом

1. Существующий `DynamicLiveClient` раньше принимал только qty/limit Dynamic.
   Добавлен явный Monthly wire contract: market/notional с прежними9 знаками
   вниз, owned native stops/rotation/safety exits. Endpoint/no-redirect/no-retry,
   default OFF и одноразовое точное разрешение payload сохранены. Default
   Dynamic по-прежнему отвергает Monthly; второго broker adapter нет.
2. Нативный Monthly раньше не проверял весь аккаунт перед новой покупкой.
   Теперь под исходным account lock сверяются account/clock/asset/quote,
   все позиции/открытые заявки, полные owned stops, актуальность DAY, доступные
   деньги с резервом, общий gross/число позиций и последнее время перед send.
   Чужая NET или заявка блокирует вход; миграции по тикеру нет.
3. После выхода раньше можно было принять новый риск при ещё неизвестных
   расходах. Подключён существующий `lifecycle.finalize_costs`: точные вход/выход,
   hash источников fees, actual broker cash и нулевые остаточные обязательства.
   До finality новый риск блокируется; изменение исходников сверки тоже блокирует.
   Денежная истина остаётся у брокера/существующего accounting, новый PnL движок
   не создан. Завершение accounting не создаёт новый GO или право на немедленный
   повторный отбор.
4. Старое Dynamic approval не активирует Monthly. Требуются отдельные source-pinned
   scope/GO, точные account/book/runtime/HALT и device/inode исходного lock.
   Первый ограниченный LIVE scope допускает один конкретный выбранный символ/
   одну новую заявку за сессию в заданном размере; это ограничение первого
   исполнения, а не изменение исследуемых весов или переименование Weekly.

## Проверки и физический пакет

- **270 целевых PASS** после последнего изменения; полный repository suite не
  запускался. Новый файл содержит27 проверок. До исправления9из10 исходных
  counterexamples падали; отдельный новый accounting regression также падал.
- **91 PASS на точных файлах candidate**:22 импортированных source files только
  из candidate,0 fallback в рабочий checkout. Это отдельная проверка, числа
  нельзя складывать с270 как независимые тесты.
- Сквозные тесты используют реальный serializer, restricted transport, native
  reservation/protection и оба LIVE acknowledgement gates. Заменён только HTTP.
  Покрыты потеря ответа stop, restart без повторной покупки, daily-close HWM,
  DAY rearm, полный stop-exit, accounting/cash closure и блокировка нового риска.
  Это не реальные брокерские исполнения/стоимость/доставка тревоги.
- VPS: `/opt/bybot-research/alpaca-monthly-baseline-20261016/source-binding-v4/app`;
  **33 файла**, spec SHA
  `351dbba7a773e7d9579469ad6965f277a6ca0b7f99e5b4aa42b8b6679fb5c278`.
  Verify-only CLI на VPS PASS; финансовых units/cron/profile не меняли,
  сервисы не запускали, broker requests/writes0.
- **77 защищённых static files** старого контура до/после совпали.
  Оригинальный lock inode813893 сохранён. SHOP timer disabled/inactive;
  NET manager timer enabled/active и DAY-monitor19Oct13:30UTC сохранены.
- Сохранены32 исходных V3 зависимости: изменены только3 runtime/native source
  files; добавлен существующий sizing audit для изолированных тестов. В candidate
  `alpaca_dynamic_v1.py` взят именно из принятого `d205f8f` (SHA7ab36fd9…),
  а не из более позднего EventReselection checkout. Новый code identity
  `ALPACA_MONTHLY_BASELINE_83a082b07ba75200e1343dc3e252454b3edca552a22c5bb6683c7c2e3e7873d4`;
  contract SHAa32aaec3…e402e и численные правила прежние.

[Манифест](evidence/alpaca_monthly_closeout_20261018/candidate.json),
[проверки](evidence/alpaca_monthly_closeout_20261018/verification.json),
[точный candidate](evidence/alpaca_monthly_closeout_20261018/exact_candidate_tests.json),
[фактическая установка](evidence/alpaca_monthly_closeout_20261018/deployed_disabled.json),
[сохранение действующих процессов](evidence/alpaca_monthly_closeout_20261018/preservation.json).
Локальные команды воспроизведения изолированной сборки/тестов сохранены в
`.private/alpaca_monthly_closeout_20261018/`; для восстановления пакета нужны
публичный V3 manifest, перечисленные source hashes и blob d205f8f для Dynamic.
В spec нет ключей, профиля с credentials или действующего owner GO.

## Что осталось до денег — без ожидания даты для инженерии

[Инертный activation dossier](evidence/alpaca_monthly_closeout_20261018/activation_packet.json)
явно хранит незакрытые условия, а не фиктивный PASS:

1. Связать existing full-universe source operation с owned финансовой книгой и
   единственным manager; закончить disabled scheduling/реальную доставку тревог/
   rollback acceptance. Source verify-only CLI сам по себе не торговый daemon.
   Это следующий инженерный P0, его не откладывать до30 октября.
2. Независимый review3 source deltas и точных activation controls. Здесь выполнен
   root review; новый independent financial signoff не получен. Исчерпанный
   reviewer bucket не перезапускался и не заменялся более дорогой моделью.
3.30Oct после закрытия: настоящее полное selection source, выбранный символ,
   ATR/вес/точный notional/модель stop-risk и источник комиссий/резервов. До этого
   реальные суммы первого ордера и потери не выдаются за известные. Потеря при
   гэпе/проскальзывании может превысить stop-модель.
4. Отдельный Monthly OWNER GO; прежний SHOP/KITY GO не переносится.
   NET не усыновляется: ранее разрешённый личный выход2Nov при необходимости,
   затем broker flat/orders/cash/finality и подтверждённый single-manager handoff.
   Если это не завершено в разрешённое окно — NO_SEND, без ранней продажи NET
   и переноса monthly entry на случайный следующий день.

**19Oct16:30Кипр:** фактический полный DAY-stop NET,16:35 GET сверка.
**30Oct20:00UTC:** закрытие сессии отбора (broker calendar перепроверяется).
**2Nov14:30–14:35UTC /16:30–16:35Кипр:** первое допустимое окно Monthly,
условное на всех перечисленных gates/GO. Покупки Monthly19Oct нет.

## Крипта / существующая очередь

ATT1 добавлен в каноническую доску как **REPAIR/BLOCKED_DATA**.
[Индекс прочитанных доказательств](evidence/alpaca_monthly_closeout_20261018/att1_intake.json):
последний использованный dated snapshot9Oct —26sessions/18gaps/1cleanADA/0held,
один simulated net-R≈−1.049; это не текущий runtime count и не положительный
экономический допуск. Старый registry PASS не переносится в LIVE. Сохранены CTS2s,
2–3clean terminals, actual-account/cost dossier и отдельный GO. Claude оценивает
актуальное преимущество; Codex использует существующие adapter/observation/replay
компоненты. Новые judge/outcomes, перезапуск завершённых проб и ретюнинг не выполнялись.

KITY: прежний реальный10entry/10guard/10exit цикл и net−0.22198250USDT сохранены;
policy SPENT, экономический INCONCLUSIVE. Fix8500c97/Health5820bac остаются
LOCAL/NOT_DEPLOYED; новый денежный повтор не назначен. Elder actual-event intake,
IBIT first forward/MassivePENDING и LIQ delivery продолжаются по существующим
контрактам. Эта поставка не заявляет новых событий/экономического PASS по ним.
