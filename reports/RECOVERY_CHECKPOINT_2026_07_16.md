# Recovery checkpoint — 2026-07-16

Этот документ — короткая каноническая точка продолжения после аудита live, Alpaca, арбитража, FX/CFD, Telegram и исследовательских контуров. Он не заменяет broker/runtime receipts. Приоритет истины: broker/exchange -> свежий runtime receipt -> targeted deploy receipt/SHA -> immutable prereg research -> этот checkpoint -> интерпретация ИИ.

## Решение владельца, которое нельзя потерять

- Цель — несколько независимых денежных рукавов, но ни один рукав не получает капитал по красивому selected-backtest.
- Long-only и short-only остаются отдельными физическими стратегиями и отдельными воротами.
- ИИ — наблюдатель, диагност и генератор предложений; он не ослабляет economics/risk gate и не получает самостоятельное право на live-ордер.
- Локальная реализация, Git и live — три разные истины. Нельзя называть изменение live без targeted deploy receipt и post-check.

## Прямая live-истина

Read-only проверка около `2026-07-16 04:06 UTC`:

- VPS `bybot.service` и `trading-journal-web.service` active; heartbeat свежий; `trade_on=true`, `dry_run=false`, режим `bull_chop`; прямой Bybit ответ — `0` позиций.
- Bybit equity около `$1020.08`, практически весь баланс в USDT. PnL: день `0`/N0, неделя около `-$0.72`/N3, месяц около `-$0.98`/N25, год около `-$4.53`/N51.
- Единственный crypto money sleeve — `ATT1 short-only x0.10`; текущий canary N5, 2W/3L, net около `+$0.15`, edge не доказан. Review — `2026-07-20`; повышать риск нельзя.
- После текущего restart ATT1 сделал 72 попытки и 0 входов: 60 отказов по trendline, 6 first-bar, 6 same-bar. Это не поломка ордеров, а редкий/жёсткий setup и пока слабая геометрическая гипотеза.
- `midterm`, `bounce1`, `ivb1` включены только как telemetry/shadow с risk `0`. Они не являются вторым денежным рукавом.
- `allocator status=disabled` в startup Telegram не означает глобальный block: authority сейчас у approved env contract. `safe_mode=false`, `hard_block=false`.
- Bybit ключ заканчивается `2026-08-12`; заменить желательно до `2026-08-05`. Если сохраняется региональный риск, Bitget готовится как отдельный adapter, а не как подмена Bybit payload.

## Telegram и onboard AI

- Показанный startup-блок Telegram соответствует реальному snapshot: единственный money sleeve ATT1 x0.10, остальные risk-zero, broker flat.
- Два одинаковых `strategy-flags` в старом startup были observability-дефектом: один блок отправлял auth-check, второй — первый periodic pulse. Локально таймер исправлен, чтобы первый pulse не дублировал startup.
- `configs/strategy_health.json` оказался историческим snapshot возрастом около 10.8 суток, хотя `runtime/portfolio_health.json` свежий. Локально Telegram `/sleeve` и `/brief` теперь показывают раздельно live alert-only closes и historical research health. Протухший research PAUSE/KILL больше не маскируется под свежую live-истину.
- Эти изменения Telegram/health пока **не live** без отдельного targeted deploy receipt.
- Onboard AI получает canonical state и свежий heartbeat, но остаётся proposal-only. Он не должен сам открывать setup из scanner-карты. Следующий полезный шаг для ИИ — ранжировать уже безопасные наблюдения и объяснять abstain, а не получать unrestricted trading authority.

## Alpaca: решение без принудительной распродажи

Последний локальный broker mirror `2026-07-16T04:02:03Z`:

- режим `SAFE_HOLD`;
- equity около `$486.34`, cash/buying power около `$328.45`;
- позиции `ABBV, ABNB, GE, SCHW`;
- broker-side stops `4/4`, protection gaps `0`;
- фактический order-submit/new entries выключен.

Принудительно продавать четыре позиции нельзя: это реализует текущий путь, добавит execution/tax/slippage и не исправит parity. SAFE_HOLD продолжает защищать позиции и допускает выход по защитному ордеру, но не делает новую ротацию. После одобрения successor переход должен сохранить совпадающие имена и продавать только нецелевые позиции в легитимную дату rotation.

Собран новый пяти-рукавный bakeoff:

1. v38 successor SPY200 gated;
2. v38 successor ungated control;
3. adaptive gated;
4. adaptive ungated control;
5. legacy reference, diagnostic-only.

Old `+50–63%` нельзя считать live forecast: legacy research использовал современный фиксированный universe, 100% вместо 70% exposure, другую top-k/earnings/sizing логику и sparse rebalance DD вместо daily MTM. Новый preflight pin checks `10/10`, future seal PASS, SAFE_HOLD semantics PASS, но performance заблокирован пятью authoritative inputs: XNYS ledger, PIT universe, PIT adjusted market manifest, corporate-action/delisting ledger, broker lifecycle + real cost calibration.

Untouched forward window заморожено заранее: `2026-08-03`–`2026-11-04`, минимум три полных monthly cycles, без interim outcome reads. Исторический bakeoff возможен после materialization входов; честный prospective verdict — не раньше окончания окна.

## Арбитраж: что разблокирует и какие цифры допустимо ждать

Cross-exchange shadow сейчас `NO-GO`: 174 закрытых цикла, mean `-0.031376%`, median `-0.10485%`, WR `33.3%`. Старое обещание `$5–15/месяц с $1000` не подтверждено проектными данными и отозвано.

Свежий same-exchange Bybit spot+perp screen также правильно отказал:

- XRP expected/required `15.01/55.79 bps`;
- BTC `9.16/54.03 bps`;
- ETH `20.24/54.10 bps`.

Все три — `NO_ENTRY`, позиции и капитал не создавались. Поэтому ожидаемая доходность сейчас — **неизвестна**, а не `$5–15`. Любая annualization текущего gross funding была бы ложным forecast.

Для разблокировки нужны последовательно:

1. семь суток публичных наблюдений без ключей;
2. account fee-tier receipt и реальная калибровка четырёх комиссий/книги/basis;
3. минимум 10 полных paper cycles для механики;
4. минимум 30 cycles на не менее чем 3 ликвидных символах для edge;
5. two-leg partial-fill/restart/recovery executor;
6. ручной review и только затем крошечный capital canary.

Собрана bounded public research station на `BTC/ETH/SOL/XRP/DOGE/SUI`: public GET only, hash journals, restart/replay, 30-minute + post-funding schedule, семисуточный/space/observation cap, frozen break-even refusal. Она не имеет execution flag. В этой сессии две bounded launch-проверки fail-closed: финальная попытка дала 6 DNS failures, 0 payloads/observations/shadow positions, state `PAUSED`; detached screen не остался. Launcher готов к запуску вне sandbox или на stable host.

Bitget: публичное исследование не требует API. Отдельный fail-closed public adapter уже собран и протестирован для spot instruments/book, USDT perpetual config/book, current/history funding и causal server time. У него собственные IDs `bitget_public_v2_cashcarry_v1 / bitget / bitget_public_v2`; он normalization-only и физически несовместим с frozen Bybit journal. Для полноценной Bitget station ещё нужны отдельные hash journal/replay, native common-quantity economics engine, account fee receipt и recovery/margin/transfer contract. Для будущего demo/live нужны отдельный subaccount, spot+futures trade rights, IP allowlist, key/secret/passphrase; withdrawal/transfer права запрещены.

## Второй криптокандидат и ATT1

ATT1 механически выглядит причинно: closed bars, next-open и защитная логика присутствуют. Фраза внутреннего ИИ «входы нелогичны» относится к edge/геометрии: двухточечная линия автоматически имеет R2=1, нет обязательного доказанного unbroken/respected/first-touch качества, а в `bull_chop` касания шумные. Это не доказательство сломанного backtest engine, но достаточная причина не масштабировать N5 canary.

Pattern Atlas обработал `20,372` discovery paths. Единственный bounded lead — physical long-only horizontal breakout с удержанием 72h: N909, mean `+54.5 bps`, median `-49.2 bps`, positive symbol means 10/13. Положительный mean при отрицательной median означает fat-tail lead, а не готовую стратегию.

Для него реализован one-shot scorer: exact next-H1-open, fixed 72h exit, long-only, base/stress costs, actual funding, four folds, breadth, LOSO, profit concentration, timestamp occupancy и portfolio MTM/DD. Public builder материализовал 13/13 funding histories, 32 raw API pages и 6,400 events до открытия price rows. После независимого review единственная sealed-попытка была израсходована и дала жёсткий `NO_PROMOTION`:

- N `155`, invalid/censored `0`;
- base PF `0.392`, aggregate net sum `-27,811.6 bps`;
- stress PF `0.281`, aggregate net sum `-37,853.6 bps`;
- stress timestamp portfolio max DD `36.90%`;
- winsorized mean `-249.4 bps`;
- positive folds `0/4`, positive symbols `1/13` (только TAO).

Спасать TAO после просмотра результата, менять фильтры или повторять holdout запрещено. Это не второй рукав; гипотеза архивируется. Отрицательный результат подтвердил, что discovery mean `+54.5 bps` был fat-tail ловушкой, которую уже предупреждала median `-49.2 bps`.

## FX/CFD: что означают frozen data, news и account cost contract

FX V2 честно провалил все шесть side-specific sleeves. Позитив в том, что V3 уже имеет причинные отдельные семейства: failed-break/retest short, horizontal range rejection long/short и range expansion/retest long/short, immutable M5 hashes примерно за 728 дней и closed-bar/next-open intent. Edge ещё не посчитан.

- **Frozen data** — заранее фиксированные файлы, хэши, symbols, timezone, coverage и closed bars. После результата нельзя сменить окно/символы или подложить другой cache.
- **Historical news** — point-in-time календарь timestamped NFP/CPI/rate events, известный на момент решения. Он нужен, чтобы заранее блокировать или отдельно оценивать event windows без lookahead.
- **Account-specific cost contract** — фактические p50/p95 spread по symbol/session, commission, financing/swap, tick/lot, gap/slippage именно выбранного broker/account. Один API key не восстанавливает исторические расходы.

Для первых backtest-цифр ключ не нужен, если материализованы news и cost artifacts. Для demo/live позже нужны broker demo key/account id. Реалистично: первые честные V3 цифры через 1–3 недели после появления двух внешних artifacts; demo — только после strict PASS, затем минимум 30 чистых demo closes. FXOpen/OANDA ключи в проверенном runtime не обнаружены; не считать старую строку/файл рабочей интеграцией.

## Исследования и долгие clocks

- Claude Research Station: 107 вариантов, 1 IS PASS, 0 forward, 0 OOS, 0 survivors. Это полезный отрицательный результат.
- Расширять этот grid до тысяч сейчас вредно: largest mutable cache, repeated OOS cohort, нет multiple-testing correction и смешаны legacy contracts. Он остаётся proposal generator.
- Правильная машина: broad causal discovery -> breadth/median/tail + multiple-testing control -> freeze одной гипотезы -> single sealed time+symbol holdout with full costs/funding/occupancy -> prospective shadow.
- Karpathy/autoresearch и ИИ могут генерировать hypotheses и код до freeze, но не читать sealed outcomes, менять gates после результата или auto-promote.
- Replayable tape collectors работают локально, но первый закрытый день имеет около `88.18%` coverage и крупные gaps. До переноса на стабильный always-on host/repair и ≥98% valid days clock нельзя считать promotion-grade.
- Старые VPS nightly crons протухли/сидят на cooldown и не являются полезным активным исследованием. Не считать время работающим только потому, что cron существует.

## Что реально требуется от владельца

1. До `2026-08-05` заменить Bybit key; не присылать секрет в чат. Если Bybit под риском — открыть/подготовить Bitget subaccount, но live key пока не нужен.
2. Для FX: выбрать broker/account, дать безопасно установленный demo key/account id позже; сейчас важнее предоставить/разрешить materialization historical news и выгрузку реальных spread/commission/financing условий.
3. Не добавлять арбитражный капитал и не продавать Alpaca вручную.
4. Держать Mac/collector host онлайн либо перенести public collectors на стабильный VPS после отдельного безопасного deploy.

## План ближайших ворот

1. Архивировать breakout-long-72h `NO_PROMOTION` без TAO-rescue, repair и повторного sealed run; выбрать следующую независимую causal гипотезу до открытия нового holdout.
2. Запустить семисуточную cash-carry station; текущий economics gate обязан продолжать отказывать плохим сделкам.
3. Материализовать пять Alpaca inputs; historical bakeoff, затем untouched Aug–Nov forward; SAFE_HOLD сохранить.
4. Review ATT1 20 июля и отдельно preregister geometry challenger; N20–30 clean closes до первого шага масштаба `0.10 -> 0.25`, никогда не «на всю котлету».
5. Заморозить FX news/cost manifests, затем один honest V3 run.
6. Перенести tape/public collectors на always-on host и довести validated daily coverage.

## Publication truth

- Live на момент проверки остаётся на последнем targeted deployed AI/core/web bundle 2026-07-15; services active, broker flat, ATT1 x0.10.
- Alpaca SAFE_HOLD и stops 4/4 live; новый bakeoff не меняет broker.
- Cash-carry station, завершённый sealed `NO_PROMOTION` scorer и Telegram health split — локальная research/observability работа, не live.
- Implementation commits этого checkpoint: `5343856`, `ca3da2f`, `11d00c3`, `f492c74`. Финальный full regression: `1411 passed in 29.17s`.
- VPS checkout всё ещё stale/dirty; blind pull/reset/cleanup запрещён. Деплой только exact files + hashes + backup + post-check.
- Foreign dirty edits `bot/fx_setups.py` и `tests/test_fx_setups.py` принадлежат другой работе и не должны попасть в этот commit.

## Связанные новые документы

- `reports/ALPACA_BAKEOFF_V2_AND_SAFE_HOLD_AUDIT_2026_07_16.md`
- `reports/PUBLIC_CASHCARRY_RESEARCH_STATION_V1_2026_07_16.md`
- `reports/BITGET_CASHCARRY_PUBLIC_ADAPTER_V1_2026_07_16.md`
- `reports/HORIZONTAL_BREAKOUT_LONG_72H_SEALED_V1_SCORER_2026_07_16.md`
- `reports/PROJECT_CANONICAL_INDEX_2026_07_16.json`
- `reports/NEXT_CHAT_START_PROMPT_2026_07_16.md`
