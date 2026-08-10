# ATT1 ADA execution-contract incident — 2026-08-10

Статус: `CONFIRMED_LIVE_INCIDENT`, сделка не входит в clean ATT1 cohort.

## Broker/runtime evidence

- signal/request: `ADAUSDT Sell`, entry `0.1953`, stop `0.1992`, qty `116`;
- order submitted: `2026-08-10 18:41:07 UTC`;
- actual fill: `0.1931` at `2026-08-10 18:41:08 UTC`;
- planned TP1: `0.19071964174685418`;
- broker position при последней прямой проверке: `Sell 116`, entry `0.1931`,
  stop `0.1992`, take-profit отсутствует;
- service оставался active, PID `2276002`.

Цена fill еще не пересекла TP1, но stop-distance выросла с `0.0039` до
`0.0061`: фактический риск исполнения равен примерно `1.5641x` планового.
Это выше нового fail-close лимита `1.20x`. Работавший live-код не записывал
post-fill поля проверки риска и пропустил позицию; staged fix должен ее
отклонять.

## Операционное решение

1. Не закрывать позицию вручную и не снимать broker stop без отдельного решения
   владельца; существующая защита и runner management должны продолжаться.
2. Немедленно запретить только новые входы ATT1 горячим операторским контролем:
   `/strategy_pause att1 execution_fix_release`.
3. Не включать ADA и DOT incidents и любые события до release receipt в N20.
4. После естественного flat трижды подтвердить broker flat, применить staged
   atomic bundle, проверить hashes/service/heartbeat/broker и только затем
   разрешать `/strategy_resume att1`.

Кандидат release: `475745108b5e7ff0668011694646181ba6d9bd00`, bundle
SHA256 `01eebc0541c77be78df496b3b261e76ab03e583fed4f2d91d3beaf944e7f4a01`,
server stage `/root/bybot-staging/475745108b5e`, manifest `8/8`, server-Python
import и bounded no-order main smoke: PASS. Это staged evidence, не live deploy.
