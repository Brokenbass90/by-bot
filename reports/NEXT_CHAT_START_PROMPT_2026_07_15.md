# Next chat start prompt — 2026-07-15

Continue `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28` from the July 15 checkpoint. Do not restart the audit from zero.

Read in this order:

1. `reports/RECOVERY_CHECKPOINT_2026_07_15.md`
2. `reports/PROJECT_VNEXT_AUDIT_AND_7DAY_PLAN_2026_07_15.md`
3. `configs/project_capability_registry_v1.json`
4. `configs/ai_operator_canonical_state.json`
5. `reports/PROJECT_CANONICAL_INDEX_2026_07_15.json`

First verify direct live truth, local/origin HEAD, dirty-file ownership, active tape/Pattern Atlas jobs, and targeted deploy receipts. Do not equate VPS checkout SHA with deployed file truth.

AI/web live source through `aaf57f12223002dd4979c0cf7aafb26c2f183f87` is targeted-deployed under `reports/releases/AI_TRUTH_TARGETED_DEPLOY_RECEIPT_AAF57F1_2026_07_15.json`: hashes pass, core/web restarted, broker flat, ATT1-only risk `0.10`, `.env` unchanged. The PM canonical state and allocator-freshness fix `b067ff6` were later targeted-deployed without restarts under `reports/releases/AI_CANONICAL_AND_FRESHNESS_DEPLOY_RECEIPT_2026_07_15.json`; onboard AI now sees 26 components and has `blockers=[]`. The real cash-carry NO_ENTRY conclusion was refreshed under `reports/releases/AI_CASHCARRY_CANONICAL_REFRESH_RECEIPT_2026_07_15.json`, also without restarts. Final regression is `1363 passed`. Research remains non-live. Foreign dirty files `bot/fx_setups.py` and `tests/test_fx_setups.py` remain owner/Claude work and must not be staged.

Current money authority is only ATT1 short r0.10 tiny canary and Alpaca SAFE_HOLD protection. Direct 17:26–17:50 UTC checks found both VPS services active, Bybit flat, and Alpaca `$486.53` with broker stops `4/4`. Do not scale either. Cross-exchange arb is NO-GO. Bybit cash-and-carry v2 is default-disabled public research; real XRP/BTC/ETH observations all failed break-even and opened zero shadow positions (`d9ec438`). FX/CFD has no money authority.

Do not repeat these false claims: gated-adaptive DD 2.2%; `$5–15/month` arb as proven; Research Station found a survivor; stale mirror means VPS offline; historical Alpaca PF is a forecast.

Completed after the original checkpoint: durable cash-carry v2 mechanics; one costed breakout-long-72h successor freeze with the holdout still undecoded; Alpaca exact calendar/next-open/cost/shared-exit/daily-MTM materialization. Immediate queue: a separate funding-complete scorer before the single crypto sealed run; public cash-carry observe/refuse receipts without capital; six authoritative Alpaca inputs plus a new future forward; ATT1 review on July 20; FX V3 input contract. Keep long and short physical identities separate and use horizontal LevelSnapshot parity; sloped contract is still missing.
