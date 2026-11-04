# Monthly: проверка почты и следующий шаг —4 ноября2026

Обновление4Nov: владелец сообщил «Письмо написал» — OWNER_REPORTED_SENT.
Независимое подтверждение доставки/номер обращения пока UNKNOWN. Повторное письмо
Codex не отправляет. Ранее запрос не был отправлен; действие явно сообщено в чате. Codex не отправлял писем/форм и не создавал
нового финансового разрешения.

Проверены темы Alpaca с1Oct2026 и отдельный поиск LLY/rejected/restriction/
suspended/blocked/action-required, включая spam/trash. Соответствующих писем
об отказе LLY/блокировке/требуемом подтверждении счёта не найдено. Поиск не является
доказательством отсутствия любой скрытой брокерской причины.

Прочитаны сообщения:
- 1a19d477fcbaba91, maintenance7Nov: Paper+Live7–9AMET, endpoints/credentials/config
  unchanged, noactionrequired. Будущее обслуживание не является объяснением4223Nov.
- 1a1797a4780b71ea, maintenance31Oct:5–6PMET; те же указаниябезсменыключей.
- 1a16a6bc09bc6f32, securityupdate23Oct: no identified impact/noactionneeded.
- 1a0f7d993a29b100: AMDmarketBUY1Oct исполнен.
- 1a13fc4e78a1ddf5: NETlimitBUY15Oct исполнен.

Письмо об исполнении показывает filled quantity, но не доказывает, было ли
исходное поле запроса qty или notional. Нельзя из9знаков filled quantity выводить
допустимую точность notional. У Monthly другой source-bound код/запрос; конкретная
причина422UNKNOWN, захват ответа был потерян нашим transport.

Свежий approvedGET4Nov07:18:01UTC: LIVEidentity соответствует scope125/manager,
positions0/openorders0, oldrecoveryselectionpresent, history_completefalse.
Это не CASH/полная история/допуск новой покупки. Старое окно3Novзакрыто;
никакихPOST/apply/replay/claimreset/ротацииключей не выполнено.

Сохранённый текст обращения (владелец сообщил об отправке):
.private/monthly_http422_20261103/broker-support-request-20261104.txt
через https://alpaca.markets/support/request (официальнаяформа проверена4Nov)
или с зарегистрированной почты наsupport@alpaca.markets, указанный в письмеAlpaca.
Запрос содержит CID/время/реконструированныйpayload, не ключи и не пароль.
Текущее состояние WAITING_BROKER_REPLY_OWNER_REPORTED_SENT. Тело исходного422
по-прежнему утрачено, причина UNKNOWN; нового разрешённого пакета нет.
После ответа: подтверждённыйминимальныйремонт/независимаяпроверка→урегулирование
старогоuncertainintentпоотдельнойпроцедуре→новыйпакет→отдельныйownerGO.

Polymarket остаётся ограниченнымP1 на время внешнего блокаMonthly. Вчера19:08UTC
однократно получены публичныеRESTстаканы обоих исходов существующего рынка6501497
иGammaacceptingOrders=true/feeSchedule rate=.05/exponent1/takerOnlytrue.
/fee-rate base_fee1000 не подменяется автоматически коэффициентомfeeSchedule.
Текущийизмеритель вернулUNKNOWN(BOOK_CONTINUITY_UNKNOWN/FEE_SCHEDULE_UNKNOWN):
пока это отдельныеRESTснимки, не регулярныйWSadapter/реальныйсигнал/исполнение.
Следующийшаг — проверяемое преобразование rawGamma/fullbook в существующий
ORDERS_OFF; без новогоWSсборщика/измененияисследований/денежныхполномочий.

## Сравнение сериализации с успешными AMD/NET (read-only)

| Путь | Тип / time_in_force | Количество / сумма | JSON | Доказательство |
|---|---|---|---|---|
| AMD1Oct | market BUY / day | notional строка с2знаками f"{notional:.2f}" | json.dumps(...).encode UTF8 | Код развёрнутого74b7214b, scripts/equities_alpaca_paper_bridge.py:581–590; ALPACA_LIVE_LAUNCH_2026_10_01.json + письмо исполнения |
| NET15Oct | limit BUY / day | qty; limit_price2dp; принятый лимит328.22 | canonical compact sorted JSON | ALPACA_OCT15_FINAL_LIVE_PREFLIGHT.md и evidence/alpaca_oct15_actual_opening_20261015/live_fill_and_guard.json |
| LLY3Nov | market BUY / day | notional="101.413902261",9dp | canonical compact sorted JSON | Реконструированный запрос, HTTP422, исходные response body/request ID утрачены |

Подтверждено различие контрактов: старый AMD2dp против LLY9dp; NET был qty+limit,
а не такой же market-notional запрос. Старый source и последующие fill не являются
сырым wire capture; filled_qty с9знаками не доказывает допустимую точность notional.
Изменение JSON whitespace/key order само по себе не установлено причиной.
Точная причина422UNKNOWN; precision наугад не менялась. Код захвата HTTPError
уже209PASS локально, НЕ установлен в финансовый runtime; не заявлен ремонтом422.
По ответу брокера: конкретный фикс/проверка → отдельно разрешённое урегулирование
uncertain intent → новый датированный пакет/GO. Старое окно не переносится.
