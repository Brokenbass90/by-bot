# Recovery checkpoint — 2026-07-15

Главный подробный документ этой точки: `reports/PROJECT_VNEXT_AUDIT_AND_7DAY_PLAN_2026_07_15.md`. Этот checkpoint нужен следующему чату как короткий fail-safe.

## Live truth

- VPS `bybot.service` active; fresh heartbeat; `trade_on=true`, `dry_run=false`, `open_trades=0`, regime `bull_chop`.
- Единственный crypto money sleeve: `ATT1 short-only`, `risk_mult=0.10`, explicit review `2026-07-20`. Последние 5 current-canary closes: 2W/3L, около `+0.15 USDT`; edge не доказан.
- Bybit API key status `ok`, expiry `2026-08-12`, rotate by `2026-08-05`.
- Alpaca money authority: monthly v38 `SAFE_HOLD`, не gated-adaptive и не intraday. Broker receipt 16:00 UTC: equity `$486.77`, positions `ABBV/ABNB/GE/SCHW`, exact stop quantity coverage `4/4`, new entries disabled.
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
- Bybit cash-carry paper core: default disabled, public GET only, three settled-rate persistence, four adverse fills, both fee legs, funding/basis/delta guards and append-only receipt. `48` related tests PASS; synthetic mechanics cycle net `-$0.431/$100-leg`, deliberately no edge claim. Durable collector/quantization/recovery remain.
- Final full regression after research and independent AI-safety review: `1334 passed`.

## Publication/deploy truth

Implementation commits through `498307901e7899f052dc7772d98a8b85b7b43947` are pushed and local/origin match. They are not live until a targeted release receipt exists. Required next sequence: commit/push this canonical checkpoint -> targeted release manifest -> deploy only AI/web safety package -> controlled service restart only while broker flat -> wait for exhaustive heartbeat authority -> rebuild full AI context -> restart/smoke web -> record hashes and post-deploy truth. Research files never deploy to trading runtime.

VPS checkout remains stale/dirty `f7ed011`; blind pull/reset/cleanup remains prohibited.

## Active clocks

- Replayable tape collectors: ONDO depth50+trades and six-symbol trades, bounded, public-only, no keys/orders.
- Pattern Atlas discovery completed; receipt `reports/research/multicoin_pattern_atlas_v1_20260715/receipt.json`; sealed holdout remains unscored.
- No random autoresearch grid should be started.

## Next gates

1. Inspect Pattern Atlas receipt; interesting cells only become new prereg hypotheses, never instant strategies.
2. Finish public-data Bybit long-spot/short-perp paper engine; 10 cycles for mechanics, 30+ across 3 coins for edge.
3. Build Alpaca exact calendar/next-open/PIT/daily-MTM/cost/shared-exit replay; keep SAFE_HOLD.
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
