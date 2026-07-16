# Prompt для следующего чата — 2026-07-16

Продолжай проект из `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`.

Сначала полностью прочитай:

1. `reports/RECOVERY_CHECKPOINT_2026_07_16.md`;
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_16.json`;
3. `configs/project_capability_registry_v1.json`;
4. `configs/ai_operator_canonical_state.json`;
5. `reports/ALPACA_BAKEOFF_V2_AND_SAFE_HOLD_AUDIT_2026_07_16.md`;
6. `reports/PUBLIC_CASHCARRY_RESEARCH_STATION_V1_2026_07_16.md`;
7. `reports/BITGET_CASHCARRY_PUBLIC_ADAPTER_V1_2026_07_16.md`;
8. `reports/HORIZONTAL_BREAKOUT_LONG_72H_SEALED_V1_SCORER_2026_07_16.md`.

Не доверяй старым пересказам без direct receipt. Не путай local/Git/live. Сохрани чужие dirty-файлы `bot/fx_setups.py` и `tests/test_fx_setups.py`.

## Live truth на checkpoint

- Bybit services active, broker flat, equity около `$1020.08`, `bull_chop`.
- Единственный crypto money sleeve: ATT1 short-only x0.10, edge UNPROVEN, review 2026-07-20.
- Alpaca: SAFE_HOLD, ABBV/ABNB/GE/SCHW, stops 4/4, new order submit OFF. Не продавать принудительно.
- FX/CFD research-only. Второго crypto money sleeve нет.
- Bybit key заменить до 2026-08-05, expiry 2026-08-12. Секреты не выводить.
- AI proposal-only; setup card не является live permission.

## Первый рабочий маршрут

1. Read-only recheck live и Git before mutation.
2. Horizontal breakout long 72h больше не запускать и не ремонтировать: one-shot завершён `NO_PROMOTION` (N155, base/stress PF 0.392/0.281, stress DD 36.9%, 0/4 folds, 1/13 symbols). Не делать TAO-only rescue после outcome.
3. Если public network разрешён: запусти bounded cash-carry collector `bash scripts/launch_public_cashcarry_station_v1.sh`; подтверди receipt/status. Никаких ключей/капитала/ордеров.
4. Материализуй пять Alpaca bakeoff inputs. SAFE_HOLD не снимать, broker не трогать.
5. Для FX V3 сначала news manifest + account-specific cost manifest, потом performance. Не выдавать API key за исторические costs.
6. ATT1 review 20 июля: N, expectancy/PF after fees, geometry/rejection reasons. Не повышать risk по N5.
7. Следующую crypto hypothesis preregister отдельно до нового holdout: pump-short PIT additivity, event-expansion phase2 или horizontal range rejection long/short separate. Не подбирать продолжение на результатах breakout holdout.
8. Любой deploy — exact files, source SHA, backup, direct broker flat before/after, `.env` hash unchanged, receipt. Blind VPS pull/reset запрещён.

## Жёсткие запреты

- не обещать доход и не повторять `$5–15/month` для арбитража;
- не трактовать old Alpaca `+50–63%` или `2.2% DD` как live forecast;
- не расширять слабый 107-grid до тысяч без frozen inputs/trial ledger/multiple-testing control;
- не смешивать long-only и short-only;
- не открывать sealed rows частично и не менять scorer/gates после outcome;
- не давать ИИ unrestricted live authority;
- не утверждать «на live», если нет deploy receipt.

## Цель следующего чата

Дать измеримый progress по одному из трёх gates: cash-carry observation clock запущен; Alpaca authoritative input materialization существенно закрыт; либо FX news/cost artifacts заморожены. Crypto breakout gate уже закрыт честным `NO_PROMOTION`; не возвращаться к нему. Если ничего из этого не возможно, исправить конкретный blocker и оставить воспроизводимый receipt — не запускать случайный grid ради видимости работы.
