# Recovery checkpoint — 2026-07-15

Главный подробный документ этой точки: `reports/PROJECT_VNEXT_AUDIT_AND_7DAY_PLAN_2026_07_15.md`. Этот checkpoint нужен следующему чату как короткий fail-safe.

## Live truth

- Direct check at `2026-07-15 17:26 UTC`: VPS `bybot.service` and `trading-journal-web.service` active; fresh heartbeat; `trade_on=true`, `dry_run=false`, `open_trades=0`, regime `bull_chop`; allocator hard-block/safe-mode both false. Direct Bybit API returned zero positions.
- Единственный crypto money sleeve: `ATT1 short-only`, `risk_mult=0.10`, explicit review `2026-07-20`. Последние 5 current-canary closes: 2W/3L, около `+0.15 USDT`; edge не доказан.
- Bybit API key status `ok`, expiry `2026-08-12`, rotate by `2026-08-05`.
- Alpaca money authority: monthly v38 `SAFE_HOLD`, не gated-adaptive и не intraday. Direct broker report at `17:26 UTC`: equity `$486.53`, day P&L about `+$2.16`, positions `ABBV/ABNB/GE/SCHW`, exact stop quantity coverage `4/4`, new entries and forced rotation disabled.
- FX/CFD: research only. Cross-exchange arb: `NO-GO`. No second crypto money sleeve.

## Corrections that must not regress

- Claude statement `Alpaca gated-adaptive max DD 2.2%` is withdrawn. Corrected sparse-endpoint DD is at least `8.205%`; true daily/intramonth DD unknown. 2022 result was `-6.54%`, PF `0.280`, N `12`, same-close diagnostic only.
- Claude estimate `$5–15/month per $1000` for arb is not project evidence. Cross-exchange 174-cycle shadow is negative. Same-exchange strict historical screen was only `1.1–1.8% annualized` and `NO-GO`.
- Fresh public scan produced an XRP lead (`0.01%/8h` gross funding snapshot), not an expected return. Paper four-fill/basis/funding cycles are mandatory.
- Claude Research Station completed 107 variants with zero final survivors. It is diagnostic, not promotion-grade and must not be expanded blindly.
- A stale local mirror does not prove VPS offline. AI/web now fail closed on stale or incomplete live truth.

## Work completed locally in this session

- AI context freshness/coherent-source precedence, exhaustive 21-flag runtime authority and static capability registry.
- Web AI stale-block exclusion and complete-bundle gate.
- Atomic non-overlapping live mirror sync; successful bundle `31 synced / 2 optional missing / 0 critical failures`.
- AI env mutation/deploy/rollback quarantine, Telegram auxiliary-pack age gates and `/ai_code` config/credential read denial.
- Alpaca diagnostic drawdown accounting fix and explicit non-promotion metadata.
- Machine-readable `configs/project_capability_registry_v1.json` with validation.
- Pattern Atlas v1 prereg and discovery: immutable dev13, six horizontal H1 hypotheses, physical long/short separation, `20,372` observations. Sealed-tail bytes were read only for SHA256 verification; holdout rows were not decoded, scored or used. One bounded lead only: breakout-long 72h mean `+54.5 bps`/median `-49.2 bps`, N `909`, 10/13 positive symbol means; fat-tail, not trade-ready.
- Bybit cash-carry v2: default disabled/public GET only; exact instrument rules, common base quantity, multi-level book walk, hash-chained journal, restart replay and fail-closed break-even gate. A real public adapter test caught and fixed Bybit spot `basePrecision` vs linear `qtyStep`. Fresh durable XRP/BTC/ETH observations all returned `NO_ENTRY`: expected carry `15.01/9.16/20.24 bps` versus required `55.79/54.03/54.10 bps`; no capital, position or daemon. Frozen v1 unchanged.
- Alpaca exact-parity mechanics are now executable research primitives: official calendar-month close -> next XNYS open, adverse costs/gaps, shared stop/BE/ATR trail, daily MTM and DD including initial capital. Performance remains blocked by six authoritative inputs plus a new genuinely future forward window; SAFE_HOLD unchanged.
- The single Pattern Atlas successor `horizontal_breakout_long_72h_v1` is frozen long-only with cost/funding/fold/concentration gates. Integrity preflight is `16 passed`, sealed holdout rows decoded `0`; scorer is intentionally not implemented yet.
- Full project regression after the successor, Alpaca parity, cash-carry v2, registry and preservation updates: `1362 passed` (the preceding AI-safety baseline was `1334`). A separate AI allocator-freshness regression brought the final suite to `1363 passed`.

## Publication/deploy truth

AI/web safety was targeted-deployed from Git source `aaf57f12223002dd4979c0cf7aafb26c2f183f87` under release `ai_truth_aaf57f1_20260715`. All nine deployed hashes match; backup is `/root/by-bot-backups/ai_truth_aaf57f1_20260715`. Core restarted after three direct flat confirmations; web restarted after the new 21-component heartbeat authority and full AI context agreed. Post-check: both services active, direct broker flat, only ATT1 risk `0.10`, AI truth blockers empty, `.env` hash unchanged. Canonical receipt: `reports/releases/AI_TRUTH_TARGETED_DEPLOY_RECEIPT_AAF57F1_2026_07_15.json`. Research files did not deploy.

At `17:44–17:51 UTC`, the PM canonical registry/state and one AI-context defect fix were targeted-deployed without restarting either service. The defect was exact: AI freshness allowed only `900s` for an allocator that is rebuilt hourly and governed elsewhere by a `10800s` fail-closed contract, so AI incorrectly blocked itself for most of every hour. Commit `b067ff6` aligns the threshold and adds a boundary test. Post-build context sees `26` components, `ATT1` as the sole money sleeve, `control_recommendations_allowed=true`, `blockers=[]`; direct Bybit positions remain `0`, PIDs and `.env` SHA are unchanged. Receipt: `reports/releases/AI_CANONICAL_AND_FRESHNESS_DEPLOY_RECEIPT_2026_07_15.json`.

The real public cash-carry adapter/screen is committed as `d9ec438`; exact result: `3 observed / 0 gate passes / 0 shadow positions`. Evidence: `reports/research/bybit_cashcarry_shadow_v2_public_screen_20260715/receipt.json`. Its NO_ENTRY conclusion was added to the onboard AI canonical state without deploying the research runner or restarting services; receipt: `reports/releases/AI_CASHCARRY_CANONICAL_REFRESH_RECEIPT_2026_07_15.json`.

VPS checkout remains stale/dirty `f7ed011`; blind pull/reset/cleanup remains prohibited.

## Active clocks

- Replayable tape collectors: ONDO depth50+trades and six-symbol trades, bounded, public-only, no keys/orders.
- Pattern Atlas discovery completed; receipt `reports/research/multicoin_pattern_atlas_v1_20260715/receipt.json`; sealed holdout remains unscored.
- No random autoresearch grid should be started.

## Next gates

1. Review/freeze a separate funding-complete parity scorer for the one breakout-long-72h successor, then allow exactly one sealed run; PASS would still mean prospective paper, not money.
2. Schedule public cash-carry `observe/refuse` receipts only. Ten closed cycles test mechanics; 30+ across 3 liquid coins test stressed edge. Current economics must not open a cycle.
3. Materialize official XNYS, PIT universe/data, corporate-action/delisting, broker-lifecycle and new future-forward inputs for Alpaca; keep SAFE_HOLD.
4. ATT1 canary review 20 July; geometry challenger separate and frozen before outcome.
5. FX V3 only after immutable data/news/account-cost inputs.

## Forbidden

- increase ATT1 or Alpaca risk; remove SAFE_HOLD; enable a second money sleeve;
- call local/Git work deployed without receipt;
- open manual trades from AI/setup cards;
- add arb capital before positive stressed paper distribution;
- treat gross funding annualization or selected backtest as income forecast;
- mix long-only and short-only identities;
- blind-clean or pull the dirty VPS checkout.

## Source priority

Direct broker/exchange -> fresh runtime receipt -> targeted deploy receipt/SHA -> immutable prereg research -> human-reviewed registry/checkpoint -> AI interpretation.
