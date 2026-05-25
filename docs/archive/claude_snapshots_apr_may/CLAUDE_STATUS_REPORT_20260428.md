# Сводный отчёт — 2026-04-28 (после захода Codex)

## Что было сделано к этому моменту

### Codex (сегодня)
1. Проверил сервер: heartbeat свежий, allocator/router OK, safe_mode=0, открытых сделок нет.
2. Прогнал dynamic control-plane replay по нескольким крипто-пакетам, нашёл первый рабочий live-кандидат.
3. Зафиксировал крупную регрессию: golden v5 пакет +89.65% → текущее воспроизведение +8.40%.
4. Подготовил три файла:
   - `docs/INCOME_LIVE_ROADMAP_20260428.md`
   - `docs/CRYPTO_INCOME_STATIC_V1_20260428.md`
   - `configs/crypto_income_live_canary_v1.env` (deploy candidate, не задеплоен)
5. На сервере не менял ничего.

### Claude (сегодня)
1. Картировал allocator/regime overlays/v7-рукава (`CLAUDE_RECON_REPORT_20260428.md` §2-3).
2. Подтвердил, что 4 из 5 v7-sleeves активно торгуют live в bear_chop без WF-22 (funding_rev/liq_cascade/slope_choch/micro_scalp).
3. Подтвердил `risk_pct=0.01` (1%) уже стоит в `.env` для main Bybit-аккаунта.
4. Заметил Bybit API ключи в открытом виде в `.env` — отдельный security-вопрос.
5. Создал tasklist на 10 задач, диффы и патчи готовлю локально без push.

---

## Текущие цифры (вся правда)

### Крипта — три уровня

| Уровень | Цифры | Состояние |
|---|---|---|
| **Live core сейчас (что бот реально торгует)** | global_risk=0.55, регулярная активность, цифры live attribution не приведены ни Codex, ни мной | работает, heartbeat OK |
| **Текущий "лучший воспроизводимый" пакет** (ATT1+ARF1+breakdown+midterm static) | 365d: +70.17% / PF 1.545 / DD 6.23% / 445 trades / 2 red months | static, но breakdown в **dynamic** негативный |
| **Лучший live-канарей-кандидат** (ATT1+ARF1+midterm, без breakdown, dynamic 11 окон) | +45.30% / PF 1.489 / WR 59.9% / DD 5.77% / 454 trades / 1 red month | готов к canary deploy после approval |
| **Старая "золотая v5"** | +89.65% / PF 2.121 / DD 2.88% / 427 trades | НЕ воспроизводится сейчас → даёт +8.40% |
| **Регрессия отдельных рукавов** | breakdown_v1: +34.24 → −7.00, inplay_breakout: +17.41 → −1.63 | КРИТИЧНО — потеря ~90% доходности |

### Alpaca — двухслойная картина

| Слой | Топ-кандидат | Цифры | Проблема |
|---|---|---|---|
| Monthly compounder | v38 hybrid top4 | OOS +27.95% ann / PF 7.85 / 15 trades за год / WR 86.7% / DD −2.28% | сильный, но **слишком редкий** — 1.25 сделки/месяц |
| Monthly active variant | alpaca_income_sweep top1 | ann 19.77% / PF 4.63 / 35 trades за 24 мес / WR 80% / 3 neg месяцев | компромисс: чуть активнее, чуть слабее PF |
| Swing strict | swing_strict top1 | ann 11.80% / PF 1.34 / 77 trades / WR 61% / DD −15.5% | заметно активнее, **PF на грани** |
| Swing classic | swing_sweep top1 | ann **−32.07%** / PF 0.60 | **сломан**, в текущем виде только теряет |
| Intraday dynamic v3 | shadow-режим | runtime/equities_intraday_dynamic_v3_shadow — пишет логи, не торгует | не оценено |

То есть твоё ощущение «сильные версии но крайне мало прибыльные» — это конкретно про monthly v38: PF=7.85 это блестяще, но 15 сделок/год = смехотворная частота для income. Альтернатива (swing classic) — сломана. Income variant сидит между ними и может стать настоящим income lane'ом.

### Live state на 2026-04-28 13:00 UTC

```
regime              = bear_chop
macro               = MACRO_BEAR (-0.15)
global_risk_mult    = 0.55
base_risk_per_trade = 1.0%
leverage            = 3
max_positions       = 3
v7-sleeves активны  = funding_rev (0.85), micro_scalp (0.80), slope_choch (0.75), liq_cascade (0.60)
                       — все без WF-22 валидации
```

---

## Чего ожидать (мой прогноз)

### Если запустить crypto canary v1 как есть (без моих v7-cut правок)
- Реалистичный диапазон по 90 дням live: PF 1.2-1.4, ann 25-50%, DD до 7-8%.
- Риски: red month от ARF1 в bull_chop, тихая утечка от 4 неубранных v7-рукавов.
- Я бы оценил доверие: 60% что попадём в "ожидаемое поведение".

### Если запустить crypto canary с дополнительным v7-cut (моё предложение)
- Тот же диапазон по PF/ann/DD, но без невидимой утечки от v7.
- Доверие выше: 70-75%, потому что закрыта известная неизвестная.
- Стоимость: теряем live-статистику по funding_rev/liq_cascade. Чтобы не потерять — оставить им risk_mult=0.3 вместо нуля (мой исходный гибрид).

### Что точно НЕ стоит делать
- Возвращать breakdown_v1 в live до восстановления regression (его dynamic attribution отрицательный).
- Возвращать range_scalp до повторного annual + additivity.
- Деплоить v38 на реальные деньги без broker-side trailing/stop защиты Alpaca (Codex отдельно отметил).
- Гнаться за +89% golden v5 без понимания, что именно сломалось — вернём вместе с регрессией.

### Что ожидаю на горизонте 2-3 недели
- Crypto canary даст первую честную live-статистику для ATT1 + ARF1 + midterm (этот пакет ещё не торговал live в чистом виде).
- Восстановим хотя бы половину "золотой v5" регрессии (return от +8% к +40-50%).
- Поднимем Alpaca income lane: добавим активный intraday/swing layer параллельно v38, чтобы суммарно было 5-10 сделок в неделю вместо 1-2.
- Закроем 3-4 пункта из задач #3-7 (диагностика, WF-22 TZ, weekly audit fix, проектирование Phase 3).

---

## Как развиваться дальше — три параллельных трека

### Трек A — Crypto canary deploy (срок: 2-4 дня)

Логика: первый сильный live-пакет, узкий и проверенный. Гонка идёт между быстрым стартом и "не наступить на грабли v7".

Шаги:
1. Обновить `.cache/klines` чтобы апрельский dynamic window не скипался (Codex next-step).
2. Дополнить `crypto_income_live_canary_v1.env` строками `ENABLE_BREAKDOWN2_TRADING=0`, `ENABLE_SLOPE_CHOCH_TRADING=0`, `ENABLE_LC_TRADING=0`, `ENABLE_FR_TRADING=0`, `ENABLE_MSCALP_TRADING=0` — закрыть v7-утечку.
3. Добавить guard ARF1 в bull_chop: либо `FLAT_RISK_MULT=0.25` в overlay для bull_chop (overlay-файла нет, надо создать), либо в allocator policy у `flat` поставить `bull_chop=0.55` вместо 1.00.
4. Прогнать парный backtest: текущий canary vs мой расширенный canary с v7-cut и ARF1-guard. Сравнить PF/DD/частоту. Если хуже — откатываемся к Codex'овскому варианту.
5. Approval, deploy с rollback-планом, мониторинг 48-72 часа на canary risk.
6. Если канарей живой и в плюс — поднимаем allocator multipliers ATT1/FLAT обратно к рабочим уровням (0.75 → 1.0).

### Трек B — Регрессия golden v5 (срок: 3-5 дней)

Логика: мы потеряли 80%+ доходности где-то между golden v5 и текущим состоянием. Это огромный апсайд, если найдём.

Шаги:
1. Найти точно когда golden v5 был "золотым": git log на конфиги breakdown_v1 и inplay_breakout, найти коммит с PF 2.12.
2. Diff конфигов golden v5 vs текущих (env, allocator policy, regime overlays, strategy code).
3. Diff trade-by-trade: где golden v5 поймал сделки, которые текущая версия упустила или взяла невыгодно. У нас есть `backtest_runs/` сравнить.
4. Подозрения по приоритету (на основе AUDIT и ROADMAP):
   - изменения в symbol router/regime overlays
   - изменения в default ATR/SL пайплайнах (history знает много починок)
   - macro/ER quality gate, который мог пережать сигналы
   - изменения в exits (TP/trailing) которые меняли equity curve
5. Когда regression локализована — точечный фикс или явное "не возвращаем, потому что текущая версия безопаснее в drawdown".

### Трек C — Alpaca income lane (срок: 1-2 недели)

Логика: monthly v38 не станет income engine'ом, как ни крутись — это compounder. Income должен прийти из второго слоя.

Шаги:
1. Изучить `alpaca_intraday_dynamic_v3_shadow.env` и runtime/equities_intraday_dynamic_v3_shadow — что собирает, как давно в shadow.
2. Прогнать backtest intraday_v3 на 365d, оценить PF/частоту/DD против swing_strict.
3. Если intraday_v3 PF≥1.3 при 200+ сделках — приоритет №1, выводим в paper canary.
4. Если intraday_v3 слабый — допиливаем `swing_strict_001` (PF 1.34, 77 trades): tighter stops? trailing v3? Цель — поднять PF до 1.5+ без падения частоты.
5. Параллельно — починить classic swing_sweep (там −32% годовых, явно сломан, надо понять что; возможно простой degraded SL/exits, иначе не объяснить такой провал).
6. Финальная архитектура Alpaca: v38 hybrid (compounder, 30% капитала, paper-сначала) + intraday_v3 или swing_strict (income, 70% капитала, paper-сначала). Live-real money — только после broker-side trailing protection (Codex отметил).

---

## Куда я предлагаю продолжать прямо сейчас

Расставляю по эффекту/риску:

| # | Действие | Кто | Эффект | Риск |
|---|---|---|---|---|
| 1 | Дополнить canary env моими v7-cut + ARF1 bull_chop guard, прогнать парный backtest | я | средний (закрытие утечки) | низкий |
| 2 | Изучить regression golden v5 vs текущая reproduction (Трек B шаг 1-3) | я | **высокий** (восстановление 50-80% доходности) | низкий — только чтение |
| 3 | Прогнать intraday_v3 backtest 365d по Alpaca (Трек C шаг 1-2) | TZ → Codex | высокий (открыть income lane) | нулевой |
| 4 | Diff swing_classic vs swing_strict — почему classic проседает на 32% | я | средний | низкий |
| 5 | Обновить .cache/klines (Codex next-step) | TZ → Codex | необходимо для шага 1 | нулевой |
| 6 | Подготовить broker-side Alpaca protection (stop/trailing) | TZ → Codex или я | блокер для real money | средний |

**Моё предложение по приоритету:** одновременно стартую (1) v7-cut + ARF1-guard и (2) regression golden v5. Параллельно даю Codex'у TZ на (3) intraday_v3 backtest и (5) обновление кэша. (4)+(6) — следом.

Это даёт за 2-3 дня:
- Готовый расширенный canary env с парным backtest → ждёт твой approval на deploy
- Локализованная regression (или подтверждение, что мы её не вернём)
- Alpaca intraday_v3 цифры → решаем, делать ли его income-слоем

---

## Открытые вопросы для тебя/GPT/Codex

1. **v7-cut**: применять моё расширение canary env (ENABLE_*=0 для пяти v7), или оставить на регрессию golden v5 (тогда v7 продолжит торговать живой статистикой)?
2. **ARF1 guard**: понизить `flat` mult в bull_chop в allocator policy (0.55) или создать overlay-файл `regime_overlay_bull_chop.env` с явным `FLAT_RISK_MULT=0.25` и явными отключениями?
3. **Alpaca income lane**: intraday_v3 первым (если жив), или сразу допиливать swing_strict до PF 1.5+?
4. **Регрессия golden v5**: возвращаем PF 2.12, если найдём root cause, или принимаем, что та версия была "удачной выборкой" и не возвращаем?
5. **Canary deploy**: ждём пока я закрою регрессию (1-2 недели), или деплоим ATT1+ARF1+midterm как есть и работаем с регрессией параллельно на бэктестах?

---

*Файлы по теме:*
- `CLAUDE_RECON_REPORT_20260428.md` (моя картировка)
- `docs/INCOME_LIVE_ROADMAP_20260428.md` (Codex)
- `docs/CRYPTO_INCOME_STATIC_V1_20260428.md` (Codex)
- `docs/ALPACA_V38_HYBRID_20260428.md` (Codex)
- `configs/crypto_income_live_canary_v1.env` (Codex deploy candidate)
- `runtime/alpaca_*_sweep_20260428.csv` (свежие свипы Codex)

Готов разбирать любой из 5 открытых вопросов.
