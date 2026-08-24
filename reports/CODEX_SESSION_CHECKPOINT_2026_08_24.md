# Codex session checkpoint — 2026-08-24

**Authority:** verified operational handoff. Research and shadow results below do not grant money authority.

## Continuation receipt — 2026-08-24 10:29 UTC

- Fresh direct Alpaca broker GET showed account equity `490.85`, cash `391.47`, and two positions with full-quantity protective stops still above entry:
  - `ABBV`: current mark `265.30`, unrealized P&L `+2.409294`, entry `247.55`, stop `257.37`, quantity `0.135734866`, `DAY`, status `new`.
  - `SCHW`: current mark `112.40`, unrealized P&L `+6.115853`, entry `101.552`, stop `108.20`, quantity `0.563776973`, `DAY`, status `new`.
- Current combined unrealized P&L was approximately `+$8.5251`. The two stop levels lock approximately `+$5.0809` before gaps, slippage and fees. The latter is a floor estimate, not a profit target and not a guaranteed fill.
- The live HWM ledger remained lifecycle-bound and monotonic: `ABBV hwm=266.71 / accepted_stop_floor=257.37`; `SCHW hwm=112.30 / accepted_stop_floor=108.20`. The protective manager arms after a `+3.5%` peak gain, proposes `max(current stop, broker-accepted floor, HWM minus 3.5%, entry plus 0.5%)`, caps the replacement below the current market, and only raises by at least 10 bps. It never intentionally lowers a broker-accepted floor.
- The deployed and recovery-branch source hashes now match exactly: bridge `1237fafb...`, protective manager `32390140...`. Scheduled coverage is the live bridge every 30 minutes and the exit-only protective manager every 15 minutes on weekdays.
- Larger account equity does **not** currently switch entries to whole-share sizing or native trailing automatically. The bridge sizes `qty = notional / entry`, which is normally fractional; fractional stop orders require `DAY`, and the native-trailing path skips fractional quantities. A future whole-share profile must explicitly floor quantity, preserve cash reserve and reject candidates that cannot buy at least one share. With three positions and 70% target allocation, `$5,000` supplies roughly `$1,167` per equal-weight slot, enough for at least one whole share for names priced below that amount, but this is only mechanical capacity.
- No current evidence supports a `4-5%` monthly Alpaca expectation. The strongest diagnostic challenger produced `+57.74%` over 25 months, `25.65%` annualized, about `1.84%` geometric monthly, PF `1.84`, 40 realized trades and `14.36%` daily max drawdown. It remains `exact_live_contract=false` and `capital_authorized=false`; the current-contract proxy was weaker (`11.14%` annualized, `23.71%` drawdown).
- Research is active: ten local screen sessions are alive. At `10:21 UTC`, the local station reported six of six supervised jobs healthy and `live_order_authority=false`. Orderbook/L2/trades collectors, ATT1 maker paper, two funding shadows, Alpaca adaptive shadow, XSEC and in-play prospective work continue; none grants capital authority.
- Disk remained `351 GiB` used with approximately `59 GiB` available. Large non-project consumers now isolated include `~/Library/Application Support/Claude` about `16 GiB` (`vm_bundles` about `12 GiB`, cache/code cache about `1.4 GiB`), `~/Library/Developer/Xcode` about `7.6 GiB` (old iOS 26.3 device support about `5.4 GiB`), `.codex` about `20 GiB`, and `.ollama` about `4.9 GiB`. No deletion was performed. The safest immediate non-project candidates are the old iOS 26.3 support (`5.4 GiB`, re-downloadable), Claude cache/code cache (`~1.4 GiB`, only after Claude exits), and Ollama update cache (`~180 MiB`).
- Proposed next bounded feature, not yet implemented: a read-only Alpaca health auditor that reconciles broker positions/orders, stop coverage and monotonic floors, deployed source hashes, schedule freshness, candidate age and money-authority flags; it writes a signed/hash-bound receipt and alerts Telegram, but cannot mutate orders or enable entries.

## Continuation receipt — 2026-08-24 09:00 UTC

- Direct Alpaca broker truth still showed two full-quantity protective stops above entry while the market was closed:
  - `ABBV`: `0.135734866` shares, entry `247.55`, stop `257.37`, status `new`, `DAY`, expires at the 2026-08-24 close.
  - `SCHW`: `0.563776973` shares, entry `101.552`, stop `108.20`, status `new`, `DAY`, expires at the 2026-08-24 close.
- Both orders were submitted after Friday's close and remained accepted as `new` through the weekend. The claim that there was no broker order for approximately 80% of the week is rejected. Alpaca queues non-extended-hours `DAY` orders submitted after close for the next trading day. Fractional stop orders do not support `GTC`. Gap/slippage risk remains because stops do not trigger outside regular market hours.
- The live protection implementation had not been preserved in the recovery branch. The deployed hashes matched the dirty source tree for `equities_alpaca_paper_bridge.py` and `alpaca_protective_exit_manager.py`. Their complete live dependency set was reviewed, copied into the isolated recovery branch, tested, and pushed as `7a39b99`.
- Fresh protection verification for that commit: `40 passed` for the two protection suites, `19 passed` for adjacent Alpaca truth/order-guard suites, standalone monotonic-floor invariant `17/17`, plus `py_compile`, `bash -n`, secret scan and `git diff --check` PASS. The old frozen Alpaca bakeoff preregistration still detects the intentional live-bridge hash drift; do not rewrite that historical hash merely to make the old preflight green.
- Alpaca new entries remain disabled. The current candidate list (`SNOW`, `MSFT`, `MA`) is derived from the 2026-07-31 cycle and would be a stale mid-cycle entry if armed now. The prospective 2026-08 month-end lifecycle manifest does not yet exist.
- SBR1 zero-risk timer remained active and successful at `2026-08-24 08:55 UTC`: nine hash-chained events (one regime bootstrap and eight evaluations), zero admitted decisions, zero fills/outcomes/orders/private calls. There has not yet been a shadow entry.
- ATT1 effective money geometry remains `sl_atr_mult=1.10`, `max_stop_pct=0.06`, risk multiplier `0.10`, short-only, and `MAX_POSITIONS=3`. The regime producer reports `bull_trend`, but the approved money config forces `REGIME_OVERLAY_ENABLE=0`, `PORTFOLIO_ALLOCATOR_ENABLE=0`, and static orchestrator multiplier `0.55`; the ATT1 caller has no regime-side gate.
- The proposed ATT1 `6.60/0.25` pair repairs raw-signal survival, but old research widened a completed stop while retaining old targets whereas live construction recomputes targets from the wider risk. It is not authorized for live until the live-caller parity and one-contract ON/OFF replay pass.
- The 12-slot historical table shows approximately `4.53x` monthly R versus three slots, but drawdown rose from `7.1R` to `8.7R` (about `22.5%`) and the monolith exposure/correlation gate is absent. Keep 12 slots shadow-only until that gate is wired and replayed.
- Local research had ten screen sessions alive; five of six supervisor jobs were healthy and project-audit was stale/degraded. Active collectors were above their 50 GiB disk guard. Local disk had about 60 GiB free. Reproducible cleanup candidates total roughly 944 MiB; no evidence or cache was deleted in this continuation. The largest newly isolated non-project consumer is `.codex/sessions` at about 17 GiB (`2026-07` about 9.2 GiB, `2026-08` about 4.3 GiB). The source tree is about 18 GiB and the temporary recovery clone about 3.4 GiB, including a separate 1.5 GiB Git object store. Do not delete session history or the recovery clone before an archive/merge receipt.
- Local `qwen3:8b` is proposal-only and occupies about 4.9 GiB. The VPS has one CPU, 961 MiB RAM and 7.9 GiB free disk, so that model must not be installed there. Paid DeepSeek background cron lines remain commented out; manual `/ai` remains the only paid path.

### Updated immediate gates

1. Freeze a technically corrected SBR1 random-control preregistration before the first admitted shadow decision; the draft written after the first nine evaluations must say `pre-first-admitted-decision`, not `before any shadow result`.
2. Implement the control with a deterministic per-decision seed, real UTC calendar months, causal regime evaluation at the sampled hour, the exact SBR1 cost/outcome contract, pending future draws, and a separate hash-chained journal. Do not reuse `research_lab/random_control.py` unchanged.
3. Finish the prospective live-native caller receipt and fixed-major8 ATT1 regime gate ON/OFF replay. Only a matching live-call contract may change ATT1 geometry, risk or slots.
4. At the completed 2026-08 Alpaca month-end, write the immutable lifecycle manifest and run signal -> fill -> protection -> management -> exit paper parity. Prepare, but do not arm, a one-slot bounded live canary profile.

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
- `07f5880` — isolated systemd release path outside the live repository.
- SBR1 shadow is deployed at `/opt/bybot-research/sbr1-zero-risk-shadow` and its five-minute timer is enabled. The first automatic cycle finished at `2026-08-24 08:10:23 UTC` with `Result=success`, `ZERO_RISK_SHADOW_OK`, `orders_created_or_changed=0`, `private_api_calls=false`, and journal tip `d59172995c12f7ee276628010b28abd6b86b9cb060dec3372e3233af5c52fca8`.
- This remains zero-risk research authority only; it is not a canary and cannot promote itself.

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
3. Keep the deployed SBR1 zero-risk public shadow healthy and collect clean prospective outcomes.
4. Reconcile economics and slot/concentration policy; only then consider SBR1 tiny canary or ATT1 risk changes.
5. Separately finish Alpaca paper-parity for signal -> fill -> stop -> management -> exit before enabling new stock entries.

**Resume phrase:**

> Continue from `reports/CODEX_SESSION_CHECKPOINT_2026_08_24.md`. Preserve the recovery branch. Work only on prospective live-native caller parity: persisted BTC H1 regime bootstrap, ATT1/SBR1 caller receipts, fixed-major8 ON/OFF replay, and `verify_live_config`. Do not change live orders, risk or money authority without the gates.
