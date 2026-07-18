# Recovery checkpoint — 2026-07-18

Каноническая точка продолжения после аудита live, Web/AI, ATT1, Alpaca, FX/CFD, cash-carry, исследовательских машин и новых screenshot-like setup hypotheses. Приоритет истины: broker/exchange -> свежий runtime receipt -> targeted deploy receipt/SHA -> immutable prereg research -> этот checkpoint -> интерпретация ИИ.

## Короткий вердикт

Проект не потерян, но полноценной доходной станции ещё нет. Мы перестали путать красивые бэктесты, локальный код и live: сейчас подтверждён один tiny-canary ATT1, защищённый SAFE_HOLD Alpaca, активный отказоустойчивый cash-carry research clock и несколько причинных research primitives. Второго денежного крипторукава, доказанного арбитража и FX/CFD live пока нет.

В этой сессии закрыты реальные инфраструктурные дефекты: Web truth fail-closed, утечка auth-конфига из Git HEAD, stale chart/fractional quantities, ложные exchange consoles, scanner freshness, onboard AI context и причинный контракт наклонных линий. Эти изменения pushed и адресно развернуты с receipts; core/risk не менялись.

## Git, local и live

- Branch: `codex/dynamic-symbol-filters`.
- Local HEAD и origin перед финальным checkpoint: `5db00d7`; совпадают.
- Commit `6f59938` — Web/auth/truth hardening, pushed и targeted-deployed.
- Commit `5db00d7` — causal sloped-level research primitive + canonical maps, pushed и targeted-deployed.
- VPS Git checkout остаётся `f7ed011` dirty/stale. Blind pull/reset/clean запрещены; runtime truth — точные deployed SHA и receipts.
- Foreign dirty `bot/fx_setups.py` и `tests/test_fx_setups.py` сохранены и не входят в наши commits.
- Полный regression после implementation: `1438 passed in 32.31s`.

## Прямая Bybit live-истина

Read-only snapshot около `2026-07-18 06:07 UTC`:

- `bybot.service` и `trading-journal-web.service` active;
- heartbeat свежий, `trade_on=true`, `dry_run=false`, `bull_chop`, broker positions `0`;
- allocator не в глобальном block: `safe_mode=false`; его `status=disabled` означает approved-env authority, а не остановку торговли;
- единственный денежный crypto sleeve — `ATT1 short-only x0.10`;
- canary: `N6`, WR `50%`, net `+0.4605 USDT`; последняя LTC-сделка закрылась trailing stop с net около `+0.3104 USDT`;
- edge не доказан. Один новый плюс не разрешает повышение риска;
- Bybit key заканчивается `2026-08-12`; безопасная ротация до `2026-08-05`.

Первый шаг масштаба возможен только после `20–30` чистых broker-reconciled closes и повторного review: максимум `0.10 -> 0.25`, никогда «на всю котлету». Из-за низкой частоты это может занять недели или месяцы.

## ATT1: сломана ли стратегия

Исполнение/backtest path не выглядит явно сломанным: closed bars, entry/exit mechanics и защитная логика существуют. Претензия внутреннего ИИ «входы нелогичны» относится к геометрическому edge:

- live допускает `min_pivots=2`;
- линия через две точки автоматически выглядит идеально, поэтому R2 почти ничего не доказывает;
- обязательные unbroken/respected/first-retest guards отсутствуют;
- в `bull_chop` касание такой линии часто является шумом.

Нельзя ослаблять фильтры ради частоты. Усиление делается отдельным preregistered challenger на новом `sloped_level_snapshot_v1`, минимум три подтверждённых pivot, отдельно support/resistance и отдельно long/short. Live ATT1 скрытно не переписывать.

## Новые скриншоты и способность бота видеть такие сделки

Текущий scanner не мог увидеть конкретные AKE/BANK/LYN/US setups:

- фактический universe — только 20 символов: AAVE, ADA, AERO, BTC, DOGE, DOT, ENA, ETH, FARTCOIN, HYPE, LINK, LTC, NEAR, ONDO, SOL, SUI, WLD, XAG, XRP, ZEC;
- AKE/BANK/LYN/US отсутствуют до стадии геометрии;
- geometry строится преимущественно на H1/H4, а скриншоты — 1m/5m/15m;
- setup score — heuristic rank, не вероятность и не executable signal.

Скриншоты переведены в causal contracts в `reports/SCREENSHOT_SETUP_TRANSLATION_2026_07_18.md`: compression/rising lows -> closed horizontal breakout -> hold/first retest; sweep/reclaim -> breakout/retest; sloped support break/retest. Первый узкий шаг — отдельный research-only `event_universe_v1`, который раз в пять минут сканирует полный Trading USDT-perp universe, сохраняет point-in-time receipts и top-24/40 fresh movers, не меняя live-router.

## Ближайшие криптокандидаты

1. `event_expansion_retest_long_v1` — наиболее зрелый screenshot-like long candidate: H1 expansion -> later M15 hold -> first retest -> confirmed higher low -> later BOS -> exact next M5 open. Он причинный, но имеет 8 blockers: runner/persist/receipt-before-ACK, funding completeness, external8 data/metadata/liquidity/funding и same-window ATT1 reference. Performance/live запрещены до их закрытия.
2. Новый `event_universe_v1` — не стратегия, а discovery layer для свежих movers. Он нужен, чтобы не пропускать AKE/BANK/LYN-подобные события.
3. Horizontal failed-break/sweep/reclaim short, затем физически отдельный long. Это новая «пила», а не re-enable старой range: old range `N21, WR 23.81%, PF 0.487` остаётся NO-GO.
4. Sloped consumers: support-bounce long и support-break/retest short; затем resistance variants. Новый primitive уже deployed research-only, без сигналов/ордеров/performance.
5. Weekly time-series momentum для BTC/ETH и позже FX — отдельные long-only/short-only среднесрочные рукава.

Horizontal breakout 72h из Pattern Atlas окончательно провален: N155, base/stress PF `0.392/0.281`, stress DD `36.90%`, folds `0/4`, positive symbols `1/13`. Retry, repair, TAO-only rescue запрещены.

Pump exhaustion short также не прошёл: stress PF `1.234`, но N39<40, holdout N6<10, ONDO даёт 93.4% результата; LOSO без ONDO около нуля/минуса. Новый pump/inplay research допустим только с point-in-time high-velocity universe, не через подгонку старого результата.

## Cash-carry / арбитраж

Public Bybit station реально активна до примерно `2026-07-23 04:37 UTC`. Snapshot `2026-07-18 06:18 UTC`:

- cycles `101`, attempts `606`, durable observations `570`;
- по `95` успешных observation на BTC/ETH/SOL/XRP/DOGE/SUI;
- execution/private API/broker calls/capital/orders отсутствуют;
- все действия `observe`, economics passes `0`;
- причина — conservative funding ниже entry minimum, а не программная поломка.

Account-specific fee receipt подтвердил Bybit main account:

- spot maker/taker `10/10 bps`;
- linear maker/taker `2/5.5 bps`;
- четыре taker fill = `31 bps`.

Текущий required carry около `54–61 bps` в зависимости от символа и книги, наблюдавшийся conservative funding значительно ниже. Поэтому старый прогноз `$5–15/месяц с $1000` отозван; ожидаемый доход сейчас неизвестен, текущая возможность равна `NO_ENTRY`.

Разблокировка: завершить 7-day clock -> положительная stressed economics distribution -> минимум 10 paper mechanics cycles -> минимум 30 cycles на 3+ ликвидных символах -> two-leg partial-fill/restart/recovery -> tiny canary. Дополнительные API keys сейчас не нужны. Bitget public research можно делать без ключа; private key только позже на отдельном subaccount, trade-only, IP allowlist, без withdrawal.

Cross-exchange shadow остаётся NO-GO: 174 cycles, mean `-0.031376%`, median `-0.10485%`, WR `33.3%`.

## Alpaca

Broker truth `2026-07-18 06:09 UTC`:

- режим фактически `SAFE_HOLD` / manager `dry_run`;
- new entries `false`, close stale positions `false`;
- equity около `$484.46`, cash/buying power `$358.11`;
- позиции: ABBV, ABNB, SCHW; GE уже вышла;
- static broker stops exact `3/3`, gaps/under/over-protection `0`;
- ABBV около `+2.8%`, ABNB около `-1.19%`, SCHW около нуля.

Принудительно продавать позиции не нужно. SAFE_HOLD не запустит successor автоматически — это намеренный fail-closed. После доказанного successor transition сохраняет пересекающиеся holdings и меняет только легитимно нецелевые позиции.

Native trailing фактически не работает для текущих fractional holdings: все три символа находятся в `native_trailing_fractional_skips`, поэтому сейчас стоят статические stop orders. Возможен synthetic cancel/replace stop ratchet, но только после parity/recovery tests.

Пяти-рукавный bakeoff существует, но performance blocked пятью authoritative inputs: XNYS calendar ledger, PIT universe, PIT adjusted market manifest, corporate actions/delistings, broker lifecycle + real cost calibration. Future seal `2026-08-03`–`2026-11-04`; честный final forward verdict не раньше 4 ноября. Старые `+50–63%`/PF6+ — diagnostic selected replay, не live forecast.

## FX/CFD и чужие dirty changes

`bot/fx_setups.py` и `tests/test_fx_setups.py` — полезный чужой legacy repair от 10 июля:

- ограничивает causal geometry окнами 120/240 баров;
- использует реальные найденные retest levels вместо текущей цены;
- передаёт touch/freshness metadata;
- fail-closed отказывается подменять sloped retest горизонтальным;
- focused suite `11 passed`.

Эти изменения нужны как диагностика, но их нельзя автоматически коммитить/деплоить: legacy `bot/fx_harness.py` всё ещё может использовать signal candle и вход на её close вместо exact next-open; breakout/retest временно не заморожены; Elder same-TF и side-level semantics требуют отдельной проверки. FX V2 результаты остаются research_no_go: лучший USDJPY trend-pullback N40 net `-0.284R`, PF `0.990`, только 2/4 positive folds; EURUSD/GBPUSD ещё хуже.

FX V3 — отдельная причинная ветка с failed-break/retest short, range rejection long/short и expansion/retest long/short. Для честных цифр нужны:

- frozen M5: точные файлы, hashes, symbols, timezone/window и только closed bars;
- historical point-in-time NFP/CPI/rates timestamps;
- выбранный broker/account cost contract: p50/p95 spread по symbol/session, commission, financing/swap, tick/lot, gap/slippage.

API key сам по себе не восстанавливает историю расходов. Первые честные V3 цифры реалистичны через 1–3 недели после появления news/cost artifacts; demo — только strict PASS и затем минимум 30 чистых demo closes.

## Web, onboard AI и Telegram

Web commit `6f59938` pushed и targeted-deployed восьмью точными файлами:

- secret auth config удалён из Git HEAD и игнорируется; example безопасен;
- AI code search больше не читает configs/secrets и admin-only;
- sync crash оставляет `incomplete`, а не вечный fake `syncing`;
- setup scanner fail-closed при stale geometry/router/allocator;
- score маркирован `heuristic_rank_not_probability`;
- fractional Alpaca qty отображаются правильно;
- flat/symbol change очищает старый график;
- ложные fallback accounts и fake successful tests в generic exchange console удалены.

Web login server не сломан: email/config валидны локально и на VPS, но пароль отвергается до TOTP. Владелец должен локально выполнить:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate
python3 web/setup_totp.py --email brokenbass1990@gmail.com --admin
```

Нужно выбрать новый пароль, заново отсканировать QR и подтвердить TOTP. Старый secret удалён из текущего Git, но остаётся в истории, поэтому rotation обязательна; историю Git без отдельного разрешения не переписывать.

Canonical/sloped map commit `5db00d7` targeted-deployed без restart/risk/orders. После финального map-only refresh из checkpoint commit `de06ad8` пересобранный server AI видит 28 capabilities, 80 setup cards, blockers `[]`, включая новый `event_universe_v1` gap. ИИ теперь лучше осведомлён, но остаётся observer/proposal-only. Он не должен сам переводить scanner card в live order. AI shadow trade mission надо проверить на 100–300 preregistered missions против mechanical/random/no-trade controls.

Telegram startup execution snapshot был корректным. Patch, разделяющий fresh runtime closes и stale historical health и убирающий duplicate first pulse, остаётся local-only; в live его не считать до отдельного exact-file deploy.

## Активные clocks

- Public cash-carry: active, bounded, до примерно 23 июля.
- Public event-universe v1: active local, bounded, до `2026-07-25T07:32:46Z`; implementation `9b5dfef` был pushed до первого наблюдения. На `07:36 UTC`: 2 immutable snapshots, 743 instruments, 100 scored, 13 advisory candidates, 0 errors, всего 296K. No keys/private calls/orders/risk/live-router.
- ONDO L2 collector и 6-symbol public trade tape: active local, но coverage нестабильна из-за сна Mac; promotion-grade требует stable host и >=98% valid days.
- Local Web truth mirror: active; sync может кратко показывать реальный `syncing` во время SFTP bundle.
- Активного blind performance/autoresearch grid нет. Это намеренно: 107 Claude variants дали 1 IS, 0 forward, 0 OOS survivors. Следующая машина должна искать causal proposals, учитывать multiple testing и открывать один sealed holdout только после freeze.

## Что требуется от владельца

1. Сбросить Web password/TOTP указанной командой; секрет не присылать в чат.
2. До 5 августа безопасно заменить Bybit key. При региональном риске подготовить Bitget subaccount; деньги и private key для public research пока не нужны.
3. Для FX выбрать broker/account и дать official cost schedule; demo credentials установить локально/на сервере позже, не в чат.
4. Не продавать Alpaca вручную, не добавлять арбитражный капитал, не повышать ATT1 после одной удачной сделки.
5. По возможности держать Mac awake или позднее разрешить отдельный bounded перенос collectors на stable VPS.

## Ближайший порядок работ и сроки

1. `event_universe_v1` research-only реализован, проверен и запущен; frozen clock закончится около 25 июля. Threshold tuning и promotion по этому discovery-run запрещены.
2. Event-expansion long phase-2 blockers и первый honest backtest: ориентир 1–3 недели, без обещания PASS.
3. Новый horizontal failed-break/reclaim «пила» и отдельные sloped consumers: 1–3 недели на contract/tests/gate после общей runner parity.
4. Cash-carry 7-day conclusion: около 23 июля; если economics passes остаются нулевыми, этот рынок/fee tier остаётся research NO_ENTRY, а не «чинится» риском.
5. ATT1 review 20 июля; scale только по выборке 20–30 closes, дата data-dependent.
6. FX V3 первые честные цифры: 1–3 недели после news/cost artifacts.
7. Alpaca historical bakeoff — после пяти inputs; untouched prospective verdict не раньше 4 ноября.

До трёх регулярно торгующих денежных рукавов нельзя честно обещать календарную дату. Инженерная готовность 2–3 shadow candidates достижима примерно за 3–8 недель; money promotion каждого зависит от OOS и 30 clean shadow closes и может занять месяцы.

## Запрещено без новых ворот

- повышать ATT1 по N6 или одной последней победе;
- делать live-router шире для microcaps до отдельного research universe и liquidity guard;
- включать старую range/elder/inplay только потому, что логика визуально нравится;
- считать скриншоты доказательством edge;
- давать onboard AI unrestricted live orders;
- продавать Alpaca для «перезапуска»;
- добавлять капитал в cash-carry до positive stressed paper distribution;
- повторно открывать/ремонтировать revealed breakout-72h holdout;
- blind pull/reset/clean VPS;
- называть local/Git код live без exact deploy receipt.

## Новые доказательные документы

- `reports/SCREENSHOT_SETUP_TRANSLATION_2026_07_18.md`
- `reports/EVENT_UNIVERSE_V1_PROSPECTIVE_FREEZE_2026_07_18.md`
- `reports/BYBIT_ACCOUNT_FEE_RECEIPT_2026_07_18.md`
- `reports/releases/WEB_TRUTH_TARGETED_DEPLOY_RECEIPT_6F59938_2026_07_18.json`
- `reports/releases/CANONICAL_SLOPED_TARGETED_DEPLOY_RECEIPT_5DB00D7_2026_07_18.json`
- `reports/releases/CANONICAL_EVENT_GAP_TARGETED_DEPLOY_RECEIPT_DE06AD8_2026_07_18.json`
- `reports/PROJECT_CANONICAL_INDEX_2026_07_18.json`
- `reports/NEXT_CHAT_START_PROMPT_2026_07_18.md`

## Дополнение 07:36 UTC — screenshot-universe gap закрыт на уровне discovery

- Commit `9b5dfef` pushed до первого public outcome. Focused event suite `25 passed`; full regression `1463 passed in 31.80s`; независимый freeze-аудит не нашёл оставшихся P0/P1 blockers.
- Реализован public GET-only full Trading linear USDT-perpetual selector с cursor pagination, listing/spread/turnover guards, 100-symbol bounded prefetch, 72+3 строго закрытыми contiguous M5, source/config/input hashes и strict increasing point-in-time cutoff.
- Persistence: deterministic-gzip immutable snapshots, exact normalized score replay через checkpoint+delta chain, whole-tree 512MiB cap, 20GiB free-space guard, single writer, 0600. Полные source response bodies не хранятся; их hashes tamper-bound, но source replay не заявляется.
- Первый снимок: universe 743, prefetch/score 100/100, advisory event cards 13, errors 0. Среди них NEAR/ZEC/SKHYNIX/AVAAI/GALA/VVV/GRAM/XRP/HYPE/CL/LAB/1000BONK/KAITO. Это события объёма/диапазона, не торговые сигналы и не probabilities; пример SKHYNIX отдельно показывает необходимость asset-taxonomy gate у downstream consumers.
- Detached screen `event_universe_v1_20260718` и `caffeinate` активны до `2026-07-25T07:32:46Z`. Snapshot 2 появился автоматически; размер run tree 296K. Порогов по первым результатам не менять.
- Gap теперь закрыт только для discovery. Следующие стратегии всё ещё отдельны: horizontal breakout/hold/retest long, sweep/reclaim long/short, sloped bounce long и sloped break/retest short. Каждой нужны отдельный prereg, costs, sealed time+symbol gate и prospective shadow.
