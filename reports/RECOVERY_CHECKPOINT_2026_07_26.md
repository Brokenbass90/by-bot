# Антикризисный checkpoint — 2026-07-26

Авторитетный срез: `2026-07-25T21:43Z` (локально уже 26 июля, Asia/Nicosia).

## Решение директора

Система не списывается и не выключается. У неё уже есть один маленький реальный
денежный рукав — ATT1 — и три осмысленных пути расширения:

1. межбиржевой funding/carry с maker-first исполнением;
2. рыночно-нейтральный XSEC, сначала только decision/execution shadow;
3. Alpaca как медленный отдельный рынок, но не как источник ежедневного дохода.

Нельзя обещать владельцу быстрый заработок: текущий капитал и статистика слишком
малы. Можно и нужно построить несколько независимых положительных ожиданий и не
дать издержкам/грязным данным выдать минус за плюс.

## 1. Прямая живая правда

### Bybit / ATT1

- Bybit equity по свежему mirror: около `1020.20 USDT`.
- `trade_on=true`, `dry_run=false`, режим `bear_chop`, открытых позиций `0`.
- Единственный live-money sleeve: `att1 x0.10`.
- ATT1: short-only, expiry `2026-08-05`, breaker `blocked=false`,
  `expired=false`, `risk_mult=1.0`.
- Когорта обновилась с N8 до `N10`: win rate `50%`, net `+0.2902 USDT`.
- После checkpoint 21 июля были две реальные закрытые сделки:
  - ETHUSDT, 22 июля: `-0.57715471 USDT`;
  - DOTUSDT, 24 июля: `+0.36813697 USDT`.
- Вывод: ATT1 не выключен и продолжает торговать. Ничего не продлевать и не
  повышать риск сейчас. Следующая переоценка — не по календарю, а по факту
  расширения когорты; владелец уже разрешил продолжение.

### Что означает повторяющийся Telegram startup-текст

- `strategy-flags=True` означает, что код стратегии включён.
- Это **не** означает доступ к деньгам.
- Строка `money-sleeves` является денежной правдой: сейчас только ATT1 имеет
  ненулевой множитель.
- `midterm`, `bounce1`, `ivb1` при `x0` — shadow/paused, они не открывают
  денежные позиции.
- Повтор строки приходит из нескольких легитимных сообщений: startup auth,
  runtime stats/digest. Это шум интерфейса, а не двойной запуск сделок.

### Alpaca

- Прямая broker truth: equity `$483.96`, cash/buying power `$391.27`,
  account ACTIVE.
- Реальные позиции: `ABBV` и `SCHW`.
- Обе позиции имеют broker-native stop orders точного количества: `2/2`.
- `ALPACA_ALLOW_NEW_ENTRIES=0`, `ALPACA_CLOSE_STALE_POSITIONS=0`: это
  сознательный `SAFE_HOLD`, а не случайное отключение после ошибки запуска.
- ABNB был закрыт по stop-loss 22 июля; повторный вход заблокирован до 12 августа.
- Прежнюю «удачную» версию нельзя честно назвать подтверждённой: exact-parity и
  forward evidence не дают права включать новые покупки. Но и принудительно
  ликвидировать защищённые ABBV/SCHW оснований нет.
- Практический вывод: Alpaca сейчас накопительный/диверсификационный контур, не
  решение задачи ежедневного дохода. Новую активную версию строить отдельно на
  широком PIT-универсуме, не размораживая старый менеджер.

## 2. Что дали исследования

### PIT-универсум Bybit

Материализован публичный источник:
`research_lab/data/bybit_instruments_linear.json`.

- `1677` контрактов всего;
- `757 Trading`;
- `917 Closed`;
- `3 PreLaunch`;
- payload SHA256:
  `a14984e5632f2cc0da23a084c2c8d3cafbfe540b6815f1c8e01d3a7ff711b9`.

Это впервые делает делистинги видимыми и позволяет измерить survivorship.
Ограничение: Bybit kline API вернул пустую историю для проверенных закрытых
контрактов. Значит membership-PIT готов, а price-PIT ещё нет. XSEC V3/V4 нельзя
объявлять money-ready, пока закрытые цены не взяты из независимого архива или
не доказана нечувствительность к исключённым делистингам.

### Вторая биржа и funding history

Материализованы 180 дней Bybit + MEXC:
`research_lab/data/cross_exchange_funding_history_180d.json`.

- 8 символов ATT1;
- 16 venue-symbol рядов;
- по `540` наблюдений на каждый ряд;
- coverage `179.6667` дня, median/max gap `8h`;
- всего `8640` записей;
- payload SHA256:
  `ec2a6393b3152f2cc0da23a084c2c8d3cafbfe540b6815f1c8e01d3a7ff711b9`.

Bitget был проверен, но публичная история оказалась около 90 дней; для
шестимесячного эксперимента выбран MEXC. Ключи для этих двух задач не нужны.

### Walk-forward funding differential

Воспроизводимый отчёт:
`reports/research/cross_exchange_funding_walk_forward_20260726.json`.

Правило: 60 дней train, фиксируем направление и top-3, затем 30 дней OOS;
четыре последовательных блока.

| OOS start | gross | после 8 bps maker RT | после 22 bps taker RT |
|---|---:|---:|---:|
| 2026-03-28 | +22.927 bps | +14.927 | +0.927 |
| 2026-04-27 | +9.658 bps | +1.658 | -12.342 |
| 2026-05-27 | +15.248 bps | +7.248 | -6.752 |
| 2026-06-26 | +3.669 bps | -4.331 | -18.331 |

Итого:

- gross: `4/4` положительных, cumulative `+51.503 bps`;
- maker 8 bps: `3/4`, cumulative `+19.503 bps`;
- taker 22 bps: `1/4`, cumulative `-36.497 bps`;
- stress 40 bps: `0/4`.

Это не live-бэктест: basis, legging, margin/liquidation, rate revision и
биржевой риск ещё не включены. Но старый вывод «арбитража нет» больше неверен.
Правильный вывод: у funding differential есть слабое устойчивое ядро, которое
умирает на taker-издержках и требует maker-first плюс длительного shadow.

### Текущий широкий scanner

Discovery threshold снижен с `15%` до `5.5% APR`; замороженный prereg V3 не
переписан. Два публичных snapshot примерно за 10 минут дали шесть прошедших
execution-economics маршрутов при `$100` на ногу:

- GWEI Bybit→Bitget: `+0.8648%` оценочного net за 24h;
- ESPORTS Bybit→Binance: `+0.5586%`;
- ERA Bitget→Bybit: `+0.5291%`;
- AKE Binance→Bybit: `+0.2239%`;
- MIRA Bitget→Bybit: `+0.1704%`;
- VANA Bybit→Binance: `+0.0721%`.

Это только `persistence_count=2` примерно за 10 минут, а не торговое разрешение.
Следующий falsifiable gate: 7 дней наблюдений, минимум 12 независимых snapshot
и хотя бы три settlement окна без смены знака, затем basis/legging stress.

### Старый cash-carry

- Остановился на `1784` наблюдениях по `minimum_free_bytes_breached`.
- Экономически проходных возможностей: `0`.
- Диск сейчас свободен, но prereg clock уже закончился; простой restart исказил
  бы эксперимент.
- Решение: не оживлять тот же прогон. Закрыть финальным отчётом как
  «spot-perp economics blocked», а межбиржевой perp-perp вести отдельным V4.

### Event universe

После перезагрузки V2r2 был восстановлен:

- screen `event_universe_v2r2_20260721`;
- sequence на этом checkpoint: `718`;
- latest snapshot:
  `snapshot_000718_1785015611227.json.gz`;
- hash chain state:
  `f87fe68274998b47b13fa00a56a259bb5560ed25caa58596d22cedb1829279e1`;
- `research_only=true`, `executable=false`.

Сбор продолжается до prereg deadline 28 июля.

### FX

Пункт «скачать Dukascopy» устарел. В `data_cache/forex` уже лежит около 728
дней M5 по EURUSD, GBPUSD, USDJPY, EURJPY, GBPJPY и XAUUSD. Предыдущие
side-specific FX V2 рукава отрицательны; повторная загрузка не создаст edge.
Следующий эксперимент — не grid и не старые M5 тесные стопы, а H1/H4
cost-feasible regime/level-memory family с чистым OOS.

### XSEC V3/V4

Исследовательский сигнал интересный, но отчёты 23 июля завышают готовность.
Реальное состояние:

- reference math и prereg есть;
- текущий результат survivor-only;
- maturity по `launchTime` теперь можно сделать честно;
- цены делистингов ещё отсутствуют;
- execution shadow adapter ещё не реализован;
- поэтому денег нет, и даже настоящий fill-rate ещё не измеряется.

Следующий шаг — risk=0 decision bus с PIT membership и виртуальным
maker-fill наблюдением. Только после 20 ребалансов и выполнения заранее
записанных execution gates обсуждать tiny canary.

## 3. Owner control — реализовано локально

Добавлен постоянный человеческий control plane
`bot/operator_strategy_controls.py` и проверки перед новыми входами всех
20 entry handlers.

Telegram-команды:

- `/strategy_controls`
- `/strategy_pause att1 причина`
- `/strategy_resume att1`

Семантика:

- pause запрещает только новые входы;
- открытые позиции продолжают сопровождаться до защитного выхода;
- файл переживает рестарт;
- повреждённый файл fail-open и не может молча остановить торговлю;
- изменить состояние может только авторизованный Telegram admin.

Проверки: `17 passed`; `py_compile` и `git diff --check` прошли.

Targeted live deploy завершён в `2026-07-25T21:50Z`:

- source commit: `e7e0478`;
- VPS Git HEAD оставлен `f7ed011` (HEAD не используется как ложное
  доказательство deploy);
- server drift сохранён, применены только owner-control hunks;
- backup:
  `smart_pump_reversal_bot.py.bak_e7e0478_20260725T2150Z`;
- pre-deploy positions: `0`;
- remote `py_compile` и control pause/resume roundtrip: PASS;
- `bybot.service` active, новый PID `1560017`;
- post-restart heartbeat: `trade_on=true`, `dry_run=false`, `open_trades=0`,
  money sleeve `att1`, breaker clear;
- live control state отсутствует, что штатно означает `all sleeves allowed`.

Receipt:
`reports/releases/OPERATOR_STRATEGY_CONTROLS_TARGETED_DEPLOY_RECEIPT_E7E0478_2026_07_26.json`.

## 4. Очередь денег

1. **ATT1** — live сейчас, оставить `x0.10`, накапливать N.
2. **Perp-perp funding** — ближайший второй независимый shadow. Не требует
   $10k для доказательства; tiny canary возможен только после persistence и
   maker/legging gates.
3. **XSEC V3** — следующий risk=0 контур после реализации честного shadow.
   Не ставить V4 первым: сначала измерить базовое исполнение V3.
4. **ATT1 A3/3R, Elder-simple, retest-short** — потенциальный пакет после
   LimitOrderManager; не включать все одновременно, потому что это одна и та же
   short-beta, а не три независимых заработка.
5. **Alpaca successor** — отдельный широкий PIT cross-sectional эксперимент.
   Старый SAFE_HOLD не размораживать ради частоты.
6. **FX H1/H4** — параллельная лаборатория без капитала.

## 5. Что не удалено и почему

Массовой зачистки не было. В worktree смешаны tracked user edits, новые
исследования Claude/Cowork, runtime данные и архивы. Удалять их по возрасту
опасно. Правильная зачистка:

1. построить manifest `path → references → owner → generated/source`;
2. отдельно commit-нуть канонические source/tests/reports;
3. runtime/cache вынести в ignore/archive policy;
4. удалять только нулевые references с восстановимым источником.

Так мы уберём мусор, не уничтожив единственный источник полезного эксперимента.

## Команды воспроизведения

```bash
.venv/bin/python scripts/materialize_public_market_inputs.py all --allow-public-network
.venv/bin/python scripts/analyze_cross_exchange_funding_history.py
.venv/bin/python -m pytest -q \
  tests/test_operator_strategy_controls.py \
  tests/test_materialize_public_market_inputs.py \
  tests/test_analyze_cross_exchange_funding_history.py \
  tests/test_cross_exchange_funding_model.py
```
