# V3 version acceptance и Alpaca access GET,5Nov2026

## Alpaca: ключи работают для GET; ручной вход не выполнен

Pinned helper/bridge bytes проверены, clean process убрал inheritedALPACA/APCA
переопределения, guardedclient потребовал exacthttps://api.alpaca.markets доGET.
5Nov05:30:44.668UTC /07:30:44Cyprus: authenticatedGET прошёл, ACTIVE,
trading_blocked/account_blocked/trade_suspended_by_user=false,positions0/openorders0.
Это current snapshot, не полная история, неCASH и не доказательство разрешенияPOST.
Account identity vs текущийscope этим access-test отдельно не пересверялась.
Полный readback приватный; balances/id/env/keys не публикуются.

Подтверждённой причины менять ключи нет. Параметры новой заявки/причина исходного
HTTP422 остаютсяUNKNOWN: старый response body утрачен. РанееAMD/NET использовали
другие source-bound пути заявок.9dp отличались отAMD2dp, но US Trading docs
допускают9dp; BrokerAPIFAQ2dp не доказывает причину нашего отказа. Не меняли
notional/ключи/даты/GO и не выполняли новыйPOST ради диагностики.

Текущий поиск поддержки дал только прежний auto-ack, содержательного ответа нет;
частные почтовые metadata не экспортируются. После брокерского ответа или отдельно
разрешённой будущей попытки с исправленнымcapture — точныйфикс и новыйдатированный
пакет. Пропущенное окно3Nov не продлено. Автоматического ожидания декабря нет.
Ручная покупка не чинитAPIpath и может оказаться вне существующего ownedbook,
manager/protection. Она требует отдельного конкретного допуска и проверенногоSTOP/
custody; по вопросу владельца ручнойBUY или keyrotation не выполнялись.

[SanitizedGET](evidence/poly_v3_version_acceptance_20261105/alpaca-get-access-sanitized.json).
[Alpaca error categories](https://alpaca.markets/learn/how-to-fix-common-trading-api-errors-at-alpaca),
[US fractional precision](https://docs.alpaca.markets/us/docs/fractional-trading),
[Trading order](https://docs.alpaca.markets/us/reference/postorder).

## V3: новые source pins приняты; прежние данные сохранены

Проверены exactownerprovided producer86ed58279cc7e96f8abb50aa1e9fae6e03e058e5f17012be6fbb0f99a79cf9d0,
sharedwriterbd9175ee7ccd10791f71d214376d03322eef4d9ff94100894de57ada5fb908ff.
Source теперь хранится при фактической rawquote; processedquotes keyed by
market/time/side/source. Producer/prereg/judge Codex не менял и не запускал.

Новый manifestPID96751/start5Nov05:27:20UTC/startcount11; history latestentry
строго=manifest+perv_stroka12. Первые11 строк currentjournal совпали побайтно с
собственным ранее fsyncedprefix и11 savedsource-signal. Их intake/measurement/
blocked/outcome не редактировались. История запусков сохранена как sourceclaim,
а не независимый исторический timestamp. Новая строка12 относится к новой версии. Её source/rawSHA/quote timestamp
независимо совпали с одной строкой заявленногоpoly_monitor (компонентнаяпроверка,
не новое измерение и не prospectivecredit).

Consumer проверяет history/latestmanifest/startline и больше не может выдать
невиденную строку прошлого producer за своевременное новое наблюдение: rows<=
startupcount без собственного intake блокируются доqualify/GET. Уже измеренные
строки сохраняют оригинальные квитанции и продолжают только ожидание outcome.
Нет исправления старыхchain, повторного снятия стакана или утраченногошансаPnL.

102targetedtestsPASS,5REDдоизменения. Одинboundedindependentreview новогоdiff:
7точечныхtestsPASS, доказанныхP0/P1/P2нет; fullproject suite не запускался.
Новый immutable runtime3bf619bb0502d148f867ad191fba13258932d2aba398bffebdeeeda34b6a4c75
выбран5Nov05:40:17.663UTC; launcher268e9baf9501cbea118276a5fc56f051850d2d51e3805d131e56492e775991c7.
Заменён атомарно только собственный read-only launcher, oldbundle/backup сохранены.
Producer/hook/services/keys/financialowners/locks/risk не менялись.

Перваяпроверка новогоconsumer: V3manifestпринят, старая к этому времени строка12
(сигнал05:27UTC) получилаSTALE_SIGNAL, без bookGET/ретайминга/второйпопытки.
Это не новый SOURCE_PROVENANCE; свежий сигнал после установки ещё не измерен.
Порог120s остаётся на стороне consumer. score_age_ms_at_signal в новомproducer
считается отVPS score_received_ms; STALE_SCORE использует consumer_now−score_on_mac_ms.
Это разные часы; новое заявленное поле не подменяет независимую проверку.

## V2: ожидает штатного перехода у Claude

V2PID26905 остаётся со старым modulea2b3… в manifest, диск ужеbd9175…; это
PRODUCER_DRIFT. Владелец подтвердил, что передаст Claude штатный переход с
сохранениемlock/chain/ID. Старый manifest не переписываем и driftguard не ослабляем.
После совпадающего нового manifest/history consumer примет новое поколение тем же
hook; отдельный новыйservice не нужен. Общийконтур пока не заявлен HEALTHY.

Поддержка второго resolutionAPIформата остаётся OPEN (0705df4): её этим обновлением
не чинили и missingtime/payout не подставляли. Старые успешные полныеjoins сохранены.
[Source transition](evidence/poly_v3_version_acceptance_20261105/source-transition.json),
[installation](evidence/poly_v3_version_acceptance_20261105/installation.json),
[selectedcheck](evidence/poly_v3_version_acceptance_20261105/selected-check.json).
