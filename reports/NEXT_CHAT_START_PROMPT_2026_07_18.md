# Prompt для следующего чата — 2026-07-18

Продолжай проект из `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`.

Сначала полностью прочитай:

1. `reports/RECOVERY_CHECKPOINT_2026_07_18.md`;
2. `reports/PROJECT_CANONICAL_INDEX_2026_07_18.json`;
3. `configs/project_capability_registry_v1.json`;
4. `configs/ai_operator_canonical_state.json`;
5. `reports/SCREENSHOT_SETUP_TRANSLATION_2026_07_18.md`;
6. `reports/BYBIT_ACCOUNT_FEE_RECEIPT_2026_07_18.md`;
7. `reports/releases/WEB_TRUTH_TARGETED_DEPLOY_RECEIPT_6F59938_2026_07_18.json`;
8. `reports/releases/CANONICAL_SLOPED_TARGETED_DEPLOY_RECEIPT_5DB00D7_2026_07_18.json`.

Не доверяй старым пересказам без receipt. Local/Git/VPS checkout/deployed live — разные истины. Не используй `git add -A`. Сохрани чужие dirty-файлы `bot/fx_setups.py` и `tests/test_fx_setups.py`.

## Текущая истина

- Local/origin implementation head перед checkpoint: `5db00d7`; VPS checkout `f7ed011` dirty/stale, blind pull/reset/cleanup запрещён.
- Bybit core/web active, broker flat, `bull_chop`, global block отсутствует. Единственный money sleeve — ATT1 short-only x0.10.
- ATT1: N6, WR50%, net +0.4605 USDT, edge UNPROVEN. Не масштабировать до 20–30 clean broker-reconciled closes. Геометрия слабая: 2 pivots/R2 и нет mandatory unbroken/first-retest. Challenger строить отдельно.
- Bybit key expires 12 Aug; rotate securely by 5 Aug.
- Alpaca `SAFE_HOLD`: ABBV/ABNB/SCHW, equity около $484.46, cash $358.11, static stops exact 3/3. New entries off, successor сам не запустится. Не force-sell. Fractional holdings сейчас пропускают native trailing.
- Cash-carry public station active примерно до 23 Jul. На 06:18 UTC: 101 cycles, 606 attempts, 570 durable observations, 95 per symbol, economics passes 0, all observe, no keys/private calls/orders/capital. Fee tier подтверждён: spot 10/10bps, linear 2/5.5bps. Income unknown; capital forbidden.
- Horizontal breakout 72h окончательно NO_PROMOTION: N155, PF 0.392/0.281, DD36.9%, folds0/4, symbols1/13. Не retry/repair/TAO rescue.
- Event-expansion/retest long — ближайший causal crypto challenger, но 8 blockers и performance forbidden.
- New sloped primitive pushed+targeted-deployed research-only: >=3 confirmed pivots, support/resistance separately, no signals/orders/performance.
- Current scanner sees only 20 symbols and H1/H4; AKE/BANK/LYN/US screenshot setups находятся вне universe. Нужен отдельный research-only `event_universe_v1`, не расширение live-router.
- FX dirty repair полезен, focused 11 PASS, но legacy harness имеет next-open/parity gaps. FX V2 NO-GO; V3 требует pinned macro-news и broker/account/session cost contract.
- Web truth/auth hardening live; core/risk не менялись. Login требует owner password+TOTP reset через `web/setup_totp.py`; секрет не просить в чат.
- Onboard AI после map deploy видит 27 capabilities/80 setup cards/blockers empty, но observer/proposal-only.
- Telegram new health provenance/no-duplicate patch остаётся local-only.
- Full regression `1438 passed in 32.31s`.

## Начать работу в таком порядке

1. Read-only recheck Git/origin, VPS services/broker/heartbeat, Alpaca manager receipt, cash-carry station state и active collectors. Фиксировать timestamp.
2. Не менять риск и не запускать ордера. Проверить ATT1 review, но N<20 означает только продолжение canary.
3. Реализовать bounded research-only `event_universe_v1`: full Trading USDT-perp point-in-time scan каждые 5m, closed M5, tradability/spread/turnover/listing guards, relative-volume/range ranking, top-24/40, hashes/reasons/missing/restart receipt. No key/order/live wiring.
4. Подключить его только к отдельному M5/M15/H1 advisory scorer; построить prospective label ledger. Не подмешивать скриншот-победителей вручную.
5. Закрывать event-long phase-2 blockers в frozen order: runner/persist/receipt-before-ACK -> funding completeness -> external8 -> same-window reference -> one honest gate.
6. Затем отдельные preregistered consumers: horizontal failed-break/reclaim short, horizontal long; sloped support-bounce long, sloped support-break/retest short. Elder только как ablation/filter.
7. Завершить 7-day cash-carry clock и выдать evidence-only verdict. При 0 passes не менять threshold и не добавлять капитал.
8. Alpaca: materialize пять authoritative inputs, historical five-arm bakeoff, future seal Aug3-Nov4 не открывать досрочно. SAFE_HOLD сохранить.
9. FX: выбрать broker/account, pin PIT macro-news и real cost schedule, исправить next-open runner, только затем V3 figures.
10. Targeted-deploy Telegram observability patch отдельным exact-file release с backup/SHA/post-check, если diff всё ещё чисто изолирован.
11. Любой deploy: exact files only, backup, hashes, flat broker check при core restart, receipt. VPS Git не нормализовать вслепую.

## Владелец должен сделать

- Web auth reset:

```bash
cd /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28
source .venv/bin/activate
python3 web/setup_totp.py --email brokenbass1990@gmail.com --admin
```

- до 5 Aug заменить Bybit key через secure local/server path;
- выбрать FX broker/account и предоставить official costs, secret credentials в чат не отправлять;
- не продавать Alpaca и не добавлять арбитражный капитал.

## Запрещено

- обещать доход или дату трёх money sleeves;
- повышать ATT1 по N6/одной победе;
- считать setup score вероятностью;
- включать old range/elder/inplay без нового frozen contract;
- повторять revealed holdout;
- давать ИИ unrestricted live orders;
- называть local/Git код live без deploy receipt;
- трогать foreign FX dirty files;
- blind pull/reset/clean VPS.
