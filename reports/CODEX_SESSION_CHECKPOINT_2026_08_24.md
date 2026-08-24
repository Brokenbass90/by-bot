# Codex session checkpoint — 2026-08-24

**Authority:** verified operational handoff. Research and shadow results below do not grant money authority.

## Executive truth

- Alpaca LIVE protection is present. At `2026-08-24 07:43:44 UTC` broker GET returned two full-quantity stop orders above entry:
  - `ABBV`: entry `247.55`, stop `257.37`, qty `0.135734866`.
  - `SCHW`: entry `101.552`, stop `108.20`, qty `0.563776973`.
- The old reset floors `235.17/96.47` have not returned since the monotonic-floor fix. Fractional protective orders remain `DAY`; do not change them to `GTC` without a broker-contract proof.
- Alpaca new entries remain disabled. The protection repair is live; prospective paper parity for a new stock-selection lifecycle is not complete.
- `bybot.service` and `trading-journal-web.service` were active on the VPS. Bybit direct read-only check returned zero open positions at approximately `2026-08-24 07:40 UTC`.
- Latest ATT1 live closes inspected:
  - `BTCUSDT` short: about `-0.59849 USDT` including the reported fee field.
  - `DOTUSDT` short: about `+0.48758 USDT` after fees; TP1 and monotonic runner protection worked.
- Do not raise ATT1 risk. Actual presealed economics is not a promotion pass.

## Root cause: regime output exists, but ATT1 does not consume it

The producer is alive: `configs/regime_orchestrator_latest.env` was fresh and reported `ORCH_REGIME=bull_trend`, confidence `0.608`, risk multiplier `0.85`.

The money consumer is not wired correctly:

1. `smart_pump_reversal_bot.py` loads `configs/approved_strategy_params.env` with `override=True`.
2. That file sets `REGIME_OVERLAY_ENABLE=0`, `PORTFOLIO_ALLOCATOR_ENABLE=0`, and the static `ORCH_GLOBAL_RISK_MULT=0.55`.
3. `try_att1_entry_async()` calls `ATT1_ENGINE.signal()` without a regime-side decision.
4. Live ATT1 events therefore retained `regime=unknown`, confidence `0`, risk multiplier `0.55`, even while the producer reported `bull_trend`.

This is an integration defect, not proof that the classifier failed. Do not patch it with an ad-hoc `bull_trend => no shorts` rule: that would create another research/live geometry mismatch. The already-preregistered live-native contract uses causal closed-BTC-H1 EMA200 evidence and needs a prospective bootstrap plus a real caller receipt.

## ATT1 symbol evidence

Corrected major-8 ledger and actual live-native parity use different windows/contracts and must not be mixed.

- Corrected major-8 ledger: BTC, ETH, SOL and LTC were negative; ADA, LINK, DOT and SUI were positive.
- Actual live-native stress parity produced a different symbol ranking.
- Therefore BTC-specific parameter tuning or exclusion is not authorized from the recent six live losses alone.
- Next falsifiable experiment: fixed major-8 gate `ON/OFF` under one hash-bound contract; then preregistered fixed-51 ATT1 run. Wide-137 requires coverage/listing-bias QA first.

## Parity and SBR1

Recovery branch: `codex/recovery-20260824`.

- `5e1ee59` — live-native ATT1/SBR1 parity contract, receipts, wrappers and tests.
  - focused verification: `101 passed`.
  - actual runner verdict remains `COMPONENT_PARITY_PASS / LIVE_CALLER_PARITY_BLOCKED`.
- `8c86aa4` — default-off SBR1 zero-risk public shadow.
  - verification: `12 passed`.
  - no-argument preflight: `RESEARCH_ONLY_DISABLED`, no network, no writes, no private API, no orders, no money/promotion authority.
- SBR1 shadow is **not deployed or enabled**. Deploy only after independent source-closure review and an explicit zero-risk acknowledgement.

## DeepSeek cost incident

The prior claim that all paid background calls were disabled was false. The VPS still had active cron lines for:

- `post_trade_ai_review.py --prefer-deepseek` every 30 minutes;
- `deepseek_weekly_cron.py` weekly;
- `weekly_trade_forensics_ai_report.py --ai` weekly.

At `2026-08-24`, all three were disabled reversibly in crontab. Backup:

- `runtime/cron_backups/crontab_before_manual_only_ai_20260824T0748Z.txt`
- SHA-256 `c8029109780671ded9a305136f7f1fc0eae0fbd18a297cd0101b5b417b3ceff0`

Installed crontab SHA-256: `bbfc2c95f643bb3c9921f77e3f2e67837fc95c98651eab72aa56536f6825ce78`.

Auto-apply now explicitly runs with `--dry-run`. The running bot also had `DEEPSEEK_OPERATOR_USE_API=0`, `DEEPSEEK_OPERATOR_TRADE_REVIEW_ENABLE=0`, and `POST_TRADE_AI_ENABLE=0`; manual `/ai` remains available.

- `fa9f95e` — atomic spend ledger, bounded prompts/retries, weekly cap tests and fail-closed auto-apply receipt.
- verification: `50 passed`.

## Git preservation and security

- Source workspace branch: `codex/dynamic-symbol-filters`, base HEAD `76fc63c`, locally `ahead 6 / behind 2`, approximately 481 dirty records at audit time.
- `.git/index.lock` is **not orphaned**. Claude VM process PID `32714` holds the lock, index and temporary Git objects. Do not delete it while Claude is running.
- Six existing local commits were preserved remotely as `codex/recovery-20260824-base`.
- Reviewed new work was copied through an isolated clone and pushed as `codex/recovery-20260824`; no force push and no history overwrite occurred.
- Candidate-file secret scans found no literal credentials. This does not close old-history incidents.
- Telegram, MT5 and exposed Bybit credentials still require owner rotation. Keep runtime env files mode `600`; never print `*_JSON` values or credential prefixes/suffixes.
- Do not use `--force-with-lease` until rotation and an explicit owner decision.

## API key entrypoints

- Alpaca LIVE keys: double-click `START_ALPACA_LIVE_KEY_SETUP.command`, then `START_ALPACA_LIVE_DEPLOY_ENV.command`.
- Binance/Bitget tooling currently provisions **read-only cross-exchange research keys**, not a second live trading executor: `scripts/set_exchange_keys_server.sh`.
- Do not grant withdrawal permission. Use exchange IP allowlists where supported.
- A second live exchange requires an exchange adapter, normalized symbol/tick/fill contract, isolated account authority, replay parity, zero-risk shadow and tiny canary. Adding keys alone does not authorize two-exchange trading.

## Next critical path

1. Build one prospective live-native decision caller with a persisted, hash-bound BTC H1 EMA200 bootstrap and durable decision receipts.
2. Run fixed major-8 ATT1 gate `ON/OFF`; neutral/missing/stale evidence must fail closed in money mode.
3. When parity is green, deploy SBR1 as zero-risk public shadow only and collect clean prospective outcomes.
4. Reconcile economics and slot/concentration policy; only then consider SBR1 tiny canary or ATT1 risk changes.
5. Separately finish Alpaca paper-parity for signal -> fill -> stop -> management -> exit before enabling new stock entries.

**Resume phrase:**

> Continue from `reports/CODEX_SESSION_CHECKPOINT_2026_08_24.md`. Preserve the recovery branch. Work only on prospective live-native caller parity: persisted BTC H1 regime bootstrap, ATT1/SBR1 caller receipts, fixed-major8 ON/OFF replay, and `verify_live_config`. Do not change live orders, risk or money authority without the gates.
