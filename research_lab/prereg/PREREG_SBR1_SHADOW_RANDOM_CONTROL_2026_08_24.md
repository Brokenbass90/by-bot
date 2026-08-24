# Предрегистрация SBR1 shadow random control — pre-first-admitted-decision

**Заморожено:** 2026-08-24, до первого допущенного решения SBR1.

На момент заморозки серверный журнал содержал bootstrap/regime/evaluation
события, но `admitted_decision=0`, `fill=0`, `outcome=0`. Поэтому это не
предрегистрация «до любых наблюдений»; точное утверждение —
**до первого допущенного решения и до первого результата**.

Authority: `research_only_no_orders_no_private_api_no_money_no_promotion`.
Контроль не отправляет ордера, не читает счёт и не может открыть печать,
изменить риск или продвинуть стратегию.

## 1. Два разных множества символов

**Вселенная денег:** текущий major-8 (`BTC, ETH, SOL, ADA, LINK, LTC, DOT,
SUI`). Она остаётся узкой и меняется только через денежный gate.

**Вселенная доказательства:** фиксированный список 51 символа ниже. Shadow и
control на ней имеют ноль риска. Итоги major-8 до запуска parity-certified
fixed-51 считаются инженерным smoke и не входят в финальный порог `N=50`.

```text
1000BONK,1000PEPE,1000RATS,AAVE,ACE,ADA,ALGO,APT,ARB,ATOM,AVAX,BCH,
BICO,BNB,BTC,C98,COTI,CRV,DOGE,ETC,ETH,FIL,GALA,HBAR,HFT,ICP,INJ,JTO,
LDO,MNT,ONDO,OP,ORDI,PAXG,PEOPLE,SEI,SHIB1000,SOL,STRK,SUI,TAO,TIA,
TRX,UNI,USDC,WIF,WLD,XLM,XMR,XRP,ZEC
```

Список нельзя расширять или сужать после первого допущенного fixed-51
решения. До старта он обязан получить тот же live-native adapter, causal
regime, exchange-filter и outcome contract, что major-8.

Фактический frozen-подсчёт на доступном 19-месячном H1-кэше: `1,188` raw и
`413` regime-eligible SBR1 сигналов, или `21.74` eligible/месяц. При идеальном
сборе `50` закрытых решений ожидаются примерно через `2.3 месяца + 7 дней`
после `T0`; операционный ориентир — **T0 + 2.5 месяца**. Это оценка, а не SLA:
slot blocking, листинги, пропуски данных и текущий рынок могут увеличить срок.

## 2. Единица наблюдения

Для каждого допущенного основного решения создаётся отдельная контрольная
группа. Совпадают:

- символ и сторона `long`;
- процентное расстояние fill→stop;
- цели в R и доли фиксации;
- time stop `168h`;
- tick/qty/min-notional contract;
- base: fee `6 bps/side` + adverse slippage `2 bps/side`;
- stress: fee `6 bps/side` + adverse slippage `5 bps/side` + фактический
  public funding, доступный на момент причинного расчёта;
- stop-first правило для неоднозначной свечи.

Различается только H1-момент решения. Fill — следующий закрытый M5 open после
контрольного H1 close, с тем же tick-native rebasing.

## 3. Детерминированные розыгрыши

Ключ группы:

```text
sha256(prereg_sha256 | main_decision_id | draw_index | collision_attempt)
```

Из ключа выбирается уникальный целый UTC-час внутри **настоящего календарного
месяца** основного решения. 30-дневные блоки запрещены. Час основного решения
исключается. Коллизия получает следующий `collision_attempt`; глобальный RNG
и общее состояние между решениями запрещены.

На каждый main decision нужно получить **20 regime-eligible контролей**. Для
этого детерминированный поток часов проверяется по порядку; causal regime gate
на sampled hour либо допускает час, либо пишет `gate_blocked` и берёт следующий.
Если календарный месяц закончился раньше 20 допусков, итог группы —
`insufficient_regime_eligible_hours`, а не молчаливый пропуск.

Будущий sampled hour хранится как `pending`. Его режим, fill и исход нельзя
вычислять до закрытия соответствующих свечей. Прошлый час всё равно считается
только из данных, которые были бы доступны на его timestamp; состояние EMA
строится причинно, без текущего regime и без sealed data.

## 4. Журналы и идемпотентность

Основная и контрольная ленты физически раздельны. Control journal:

- append-only, mode `0600`;
- отдельная SHA-256 hash chain;
- уникальный ключ `main_decision_id + draw_index`;
- хранит prereg hash, draw inputs, sampled hour, causal regime proof, exact
  geometry/cost hash, source/data hashes и lifecycle `pending → admitted or
  gate_blocked → fill → terminal`;
- конфликт payload под тем же ключом завершает процесс fail-closed;
- не потребляет и не меняет slot state основной ленты.

Один допущенный main decision обязан породить ровно 20 terminal admitted
controls либо явный insufficiency receipt. Ноль ордеров и ноль приватных
вызовов проверяются статическим import/call audit.

## 5. Единственный заранее объявленный тест

Вердикт разрешён только после `50` terminal main outcomes из fixed-51 и
полностью завершённых контрольных групп. SBR1 проходит random control, только
если одновременно:

1. `mean(main_net_R) > mean(paired_control_net_R)`;
2. разность средних больше стандартного отклонения 20 draw-level средних
   control-лент;
3. `N_main >= 50`, terminal coverage main/control = `100%`, missed causal
   decisions = `0` после T0;
4. разность остаётся положительной после удаления верхних 5% main outcomes
   по `net_R`;
5. ни один символ не даёт больше 35% суммарного положительного excess-R, и
   leave-one-symbol-out разность остаётся положительной.

Base и stress публикуются оба. Для прохождения знак excess должен быть
положительным в обоих; численный критерий 2 применяется к base. Это одна нога,
одна сторона, одна геометрия и один заранее зафиксированный тест. Использовать
эту ленту для перебора конфигураций запрещено.

Прохождение означает только «entry содержит информацию сверх случайного
момента при том же regime». Оно не является money authority. Отдельно нужны
caller parity, `verify_live_config PASS`, экономика, clean shadow и решение
владельца по tiny-canary.

## 6. Что может открыть гипотезу повторно

| Причина непрохождения | Что разрешит новый эксперимент |
|---|---|
| меньше 50 main outcomes | продление того же frozen-сбора с новой датой, без изменения параметров |
| excess положительный, но меньше control spread | больше N на той же вселенной и геометрии |
| excess только в одном заранее видимом режиме | новая отдельная prereg; текущую ленту переиспользовать нельзя |
| edge съеден издержками | новая prereg maker/limit-входа после broker-calibrated fill evidence |
| концентрация в 1–2 монетах | новая prereg с заранее замороженной диверсификацией/cluster gate |
| fixed-51 parity не закрывается | новый, отдельно обоснованный universe; текущий тест аннулируется до первого решения |

## 7. Блокирующие условия развёртывания

1. Fixed-51 actual caller/adapter parity и frozen exchange filters.
2. Детерминированные календарные draws и corruption/idempotency tests.
3. Causal regime proof, future pending lifecycle и exact 168h outcome/cost.
4. Prereg SHA-256 и source closure в deployment receipt.
5. Ноль money/private/order authority по коду и runtime receipt.

До выполнения всех пяти контроль может фиксировать только assignment/pending,
но не публиковать outcome и не участвовать в решении о стратегии.
