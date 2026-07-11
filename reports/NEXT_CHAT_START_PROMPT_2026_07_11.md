# NEXT CHAT START PROMPT — 2026-07-11

Ты продолжаешь recovery проекта multi-market trading station. Не начинай общий аудит заново.

Сначала полностью прочитай:

1. `reports/PROJECT_RECOVERY_TRUTH_AND_ROADMAP_2026_07_11.md`
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_10.json`
3. `reports/MORNING_RECOVERY_CHECKPOINT_2026_07_11.md`
4. tail `reports/PROJECT_STATE_LEDGER.md`
5. `configs/ai_operator_canonical_state.json`

Затем проверь direct truth: local/origin HEAD, VPS HEAD/dirty state, fresh heartbeat/open positions, effective ATT1 contract/hash/expiry, Alpaca broker positions/stops/safe-hold, report delivery status и AI context freshness.

На момент handoff:

- local/origin `e286534`, VPS `f7ed011` и на 22 commits позади;
- все изменения сессии pushed, ничего из них не deployed на VPS;
- Bybit last verified flat, money sleeve только ATT1 short `0.10`;
- server active override ещё использует RSI threshold `40`, Git r001 contract уже `45`;
- Alpaca `$486.93`, `ABBV/ABNB/GE/SCHW`, stops `4/4`, SAFE-HOLD;
- FX V2: все 6 сторон NO_PROMOTION, OANDA capital `0`;
- old InPlay frozen; новый `pump_exhaustion_unwind_short_v1` research-only, mechanics tests `58 passed`, performance gate ещё не построен;
- правдивые Alpaca TG reports, AI source freshness/canonical memory и proposal-only web controls находятся в Git, не на VPS.

Первый порядок действий:

1. targeted flat-window VPS deploy ATT1 fail-closed config + RSI45 + runtime contract hash; никаких blind pull;
2. deploy AI/report-only patches и проверить Telegram delivery/watchdog;
3. rebuild Alpaca ledger из broker fills и exact monthly/daily/adaptive replay;
4. frozen prereg runner для pump-exhaustion successor;
5. fresh FX data evidence и V3 prereg.

Запрещено без новых ворот: повышать risk/frequency, включать второй money sleeve, пополнять OANDA, оживлять retired InPlay wrapper, удалять VPS archives или выдавать backtest headline за live expectancy.

В конце сессии обязательно обнови canonical index и запиши pushed/deployed/live truth отдельно.
