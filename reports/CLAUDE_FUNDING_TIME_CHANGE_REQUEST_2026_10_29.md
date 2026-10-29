# Codex → Claude: funding time change request, 29 October 2026

STATUS: WAITING_CLAUDE_ACK. Запрос согласования по прямому поручению владельца.
Проверен published research47b90288c55114ad7e730377c2265b54c5a97406.
Codex не изменял producer, frozen prereg, кэш или результаты и не запускал судью.

1. fanding_mezhbirzhevoy.py:44–59 сохраняет tuple(startTime,close H4).
   :80–94 использует price[w1] как вход вw1 иprice[vyh] как выход вvyh,
   но close доступен через4h. Funding уже начисляется сw1. Для1h/4h выплат
   это может включать выплаты до фактического входа. Для8h остаётся несогласованный
   график времени входа/выхода. Это исправление измерения, не выбор новой стратегии.
2. Нужно отдельно согласовать реализацию causal entry/exit price и задержку:
   данные только доdecision_time; исполнение после доступности сигнала; funding
   только по обоим фактически удерживаемым legs в каждую settlement boundary.
   Идеальный bar open вмомент публикации funding не является автоматически достижимым.
3. Holding loop: ks[j] обязан быть соседним8h окном; пропуски/ошибки API и отсутствие
   funding не становятся нулями. Новый cache/версия сохраняет старые bytes/results.
4. Current top150 для2025 — survivors/selection limitation; исходный скрин можно
   сохранить как approximateDEV с маркировкой, не объявляя PIT/executionPASS.
5. Проверить normalization pair notional vs per-leg, четыре fee-bearing fills,
   account-specific fees (без поиска credentials), basis PnL и маржу обеих площадок.
   Исходные thresholds5bps/hold3windows/25bps и PASS_V_TEN не менять молча.

Предлагаемый acceptance после согласования:
- Regression: цена H4close не доступна на еёstartTime; изменениеfutureclose не
  меняет более ранний decision/quote; enteringafterfunding не получаетpaymentдоentry.
- Nonconsecutivefunding и networkNone дают UNKNOWN/BLOCKED, не искусственный net.
- Venue reversal/lost second leg/basis stress, fee normalization и оба знакаfunding.
- Опубликовать versionedrepair+SHA+response: что исправлено без смены правил,
  какие предположения остаются. До ACK Codex producer не правит.

Лог fmb.log сейчас содержит FAIL, но из-за этих измерительных ограничений его
значения не считаются проверенной экономикой. Новый расчёт — после repair,
с сохранением прежнего результата как истории. Нет финансовогоGO/права наorders.
