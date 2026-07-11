# NEXT CHAT START PROMPT — 2026-07-11

Ты продолжаешь recovery проекта multi-market trading station. Не начинай общий аудит заново и не считай наличие модуля доказательством его wiring или edge.

Сначала полностью прочитай:

1. `reports/PROJECT_RECOVERY_TRUTH_AND_ROADMAP_2026_07_11.md`
2. `reports/ARCHITECTURE_PARITY_AND_MONEY_PATH_2026_07_11.md`
3. `reports/PROJECT_CANONICAL_INDEX_2026_07_10.json`
4. `reports/MORNING_RECOVERY_CHECKPOINT_2026_07_11.md`
5. tail `reports/PROJECT_STATE_LEDGER.md`
6. `configs/ai_operator_canonical_state.json`

Затем проверь direct truth: local/origin HEAD, VPS HEAD/dirty/deployed-file state, fresh heartbeat/open positions, effective ATT1 contract/hash/expiry, Alpaca broker positions/stops/safe-hold, report delivery status, AI context freshness и состояние research screen.

## Verified handoff

- Implementation/security checkpoint `18050bf` (`codex/dynamic-symbol-filters`) совпадает с origin; documentation checkpoint идёт следом, поэтому current local/origin HEAD всё равно проверь командой. Опорные commits: `f459e9f`, `ba53710`, `a625a8b`, `4de548b`, `115d032`, `c307085`, `18050bf`.
- VPS Git checkout всё ещё `f7ed011` и dirty; Git не pull/advance. Targeted disk files новее VPS HEAD. Не делать blind pull.
- Bybit был flat непосредственно до и после обоих рестартов. После первого restart 11:13 UTC точно подтверждены: единственный money sleeve `ATT1 short-only`, risk `0.10`, RSI `45`, flat/range off, expiry `2026-07-20`, SHA-256 `fd8048f7b6fd483a6d246969ec5f72782c780a1dcbb9df373f2d6a966161eeb6`. Это config truth, не доказательство edge.
- P0 runtime watcher исправлен и адресно установлен. После второго restart bot active PID `2750296` since `11:18:48 UTC`; read-only audit в `16:10 UTC` подтвердил direct Bybit positions `0`, ATT1 short-only/risk `0.10`/RSI `45`/expiry `2026-07-20`/exact hash `fd8048f7…`. Единственный money sleeve — ATT1; IVB1/Bounce/Midterm enabled только с risk `0`.
- Backups: `/root/by-bot-backups/targeted_580d845_20260711T111235Z` и `/root/by-bot-backups/watcher_f459e9f_20260711T111848Z`.
- Web security hardened: новый 256-bit JWT хранится только в `/root/by-bot/.env.local` mode `600`; стартовый скрипт не логирует его префикс. Перезапущен только web, PID `2761068`; `/ping=200`, `/auth/me=401` и `/api/health=401` без cookie. Listener только `127.0.0.1:8765`, HTTPS proxy отсутствует, поэтому cookie secure остаётся `0`. Реальный password/TOTP login после ротации не replayed.
- Alpaca `$486.93`, `ABBV/ABNB/GE/SCHW`, simple broker DAY stops `4/4`, SAFE-HOLD. Native trailing для fractional позиций отсутствует; configured software fixed `+3.5%/3.5%` poll-dependent trail не совпадает с research `BE0.8R+ATR1.5`, поэтому exit parity FAIL.
- Alpaca reports: broker-truth dry-run PASS; weekday post-close `22:10 UTC`, monthly day1 `22:20`, weekday watchdog `23:00` установлены; manual real TG digest доставлен `11:22 UTC`. Saturday watchdog=`not_due`; первый scheduled post-close — Monday 2026-07-13, его ещё надо доказать.
- Honest Alpaca research range при target allocation `70%`: приблизительно `15.64–17.60%` CAGR по двум 24m curves; 12m OOS около `19.08%`, но `N=15`. Это не live expectancy и не разрешение снять SAFE-HOLD.
- Frequent crypto immutable output `20260711_112429` валиден, но итог `3/3 NO_PROMOTION`: ARS1 long ADX25 PF base/stress/90d `0.374/0.292/0.821`; ARS1 short `0.682/0.550/0.514`; ASB2 no-descending long `0.754/0.524/0.639`. Short control stress PF `1.005` — почти ноль, ниже gates. Отчёт: `reports/FREQUENT_CRYPTO_VERDICT_2026_07_11.md`. Runs `111740/111943` невалидны.
- Elder не перезапускать сеткой: V2 live/V3 research parity FAIL и existing evidence отрицательны/хрупки. Новый frequent путь должен быть event-first/persisted, а не threshold-tuning провалившегося ARS1.
- FX V3 реализован в `ba53710`: `failed_break_retest_short_v3`, `horizontal_range_rejection_v3` long/short отдельно, `range_edge_expansion_retest_v3` long/short отдельно. Preflight=`DATA_DIAGNOSTICS_ONLY`, performance forbidden, promotion symbols=`0`; отсутствуют hash-pinned historical news и OANDA cost calibration, strict data gate FAIL. PnL/demo/live orders не создавались.
- Все targeted ATT1/AI/Web/Alpaca-reporting файлы на VPS сверены по SHA с implementation checkpoint. `4de548b` deployed; `115d032` установлен с backup `/root/by-bot-backups/live_mirror_115d032_20260711T161011Z`. VPS Git HEAD при этом остаётся старым/dirty.
- Canonical AI/report bundle установлен с backup `/root/by-bot-backups/ai_canonical_3c26464_20260711T162537Z`; AI context пересобран и видит canonical `as_of=16:15 UTC`, frequent crypto `3/3 NO_PROMOTION` и FX V3 data block. Web code backup: `/root/by-bot-backups/web_auth_code_20260711T162806Z`.
- Full local regression: `981 passed`. AI critical truth: `control_recommendations_allowed=true`, blockers `[]`; AI остаётся observer/proposal-only.

## Первый порядок действий

1. Не тюнить и не включать ARS1/ASB2/Elder: сохранить `NO_PROMOTION` в AI/map и выбрать один новый event-first challenger.
2. Проверить scheduled Alpaca report/watchdog после первого due window и восстановить damaged intraday ledger из broker fills.
3. Построить exact Alpaca monthly-vs-daily-vs-adaptive replay с одинаковой live/research exit model; SAFE-HOLD сохранять до parity.
4. Для FX получить/hash-pin fresh M5, historical macro news и OANDA spread/commission/financing calibration. Только strict preflight PASS разрешает performance runner, не demo/live.
5. Реализовать vertical slice canonical Market/Level/Decision/Execution/Operator Truth и side-specific sleeve ID.
6. Подготовить reproducible VPS release manifest/clean checkout migration без blind pull и без удаления server-only state.
7. Проверить реальный owner password+TOTP login после JWT-ротации; при сохранении `Unauthorized` сбросить пароль локально/без передачи в чат.

Запрещено без новых ворот: повышать ATT1 risk/frequency, включать второй money sleeve, пополнять OANDA, включать ARS1/ASB2/Elder по частичному backtest, снимать Alpaca SAFE-HOLD, считать `/ping` доказательством auth login, удалять VPS archives или выдавать 70%-scaled backtest CAGR за ожидаемую live-доходность.

В конце сессии обязательно обнови canonical index/ledger и отдельно запиши: Git pushed, VPS disk deployed, services restarted, broker/live behavior changed, local-only research и непройденные gates.
