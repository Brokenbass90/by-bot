# Claude 4-day handoff — crypto controlled unfreeze and strategy repair

Date: 2026-06-28  
Repo: `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28`  
Server: `/root/by-bot` on `root@64.226.73.119`

## Non-negotiable guardrail

Do not blindly unpause live crypto risk.

The required path is:

1. execution-accurate replay;
2. DD/monthly/side/symbol forensics;
3. shadow or signal-only observation;
4. tiny canary with explicit expiry and auto-rollback;
5. only then raise risk.

Live bot is currently active and safe:

- `bybot.service` running;
- `trade_on=true`, `dry_run=false`;
- no open crypto positions;
- `runtime/strategy_pause.env` pauses:
  - `BREAKDOWN_RISK_MULT=0.0`;
  - `ATT1_RISK_MULT=0.0`;
  - `RANGE_RISK_MULT=0.0`;
- proof-of-life says only `flat x0.3` has live risk.

## What changed on 2026-06-28

### 1. Safety fix deployed

File: `smart_pump_reversal_bot.py`

ATT1 risk parsing had one unsafe refresh path:

```python
ATT1_RISK_MULT = max(0.05, ...)
```

This could theoretically convert an explicit pause `ATT1_RISK_MULT=0.0` into
`0.05` after allocator refresh.

Fixed to:

```python
ATT1_RISK_MULT = _risk_mult_or_pause("ATT1_RISK_MULT", str(ATT1_RISK_MULT))
```

Regression test:

- `tests/test_strategy_pause_contract.py`

Validation:

- local targeted tests: `17 passed`;
- server targeted tests: `5 passed`;
- `bybot.service` restarted after confirming no open positions.

### 2. ASB1 repair verdict

Old nightly run finished:

- `asb1_bull_chop_repair_v1`: `432/432 FAIL`;
- best: `r117`, net `-2.68`, PF `0.924`, WR `39.2%`, DD `6.90`.

Decision:

- do not promote ASB1;
- do not keep tuning the current implementation as a live candidate;
- preserve the support-bounce idea, but rewrite level/context logic later.

### 3. Elder forensics verdict

No Elder code changes.

Facts:

- `ets2_canonical_24h_bounded_v1`: `64/64 FAIL`;
- trading rows had severe DD, often `40–83`;
- old `elder_canonical_rewrite_v1` also mass-failed and was stopped.

Decision:

- current Elder is not a standalone engine;
- use future Elder work as a filter/booster for ATT1/InPlay or rewrite after
  the ATT1/range package work.

### 4. ATT1 + ARS1 package queued

New spec:

- `configs/autoresearch/package_att1_short_ars1_additivity_20260628.json`

Purpose:

- answer whether ARS1/pila improves or damages the strong ATT1 candidate.

Important design:

- strategy order:
  - `alt_trendline_touch_v1,alt_range_scalp_v1`;
  - ATT1 first, so ARS1 cannot override same-bar trendline setups;
- 360d;
- `--entry-on-next-open`;
- fees/slippage `6/2` bps;
- 192 bounded combos;
- `RANGE_RISK_MULT=0.00` rows are ATT1-only controls.

Queued in:

- `configs/research_priority_24h_20260626.json`
- immediately after `spike_fade_v3_link_short_bounded`.

Also added to:

- `configs/autoresearch/approved_specs.txt`

Server validation passed.

## Current research state on server

Around 2026-06-28 05:55 UTC:

- active process:
  - `spike_fade_v3_link_short_bounded_20260627`;
  - around row `r024/32`;
- next intended task:
  - `package_att1_short_ars1_additivity_20260628`.

Check with:

```bash
cd /root/by-bot
pgrep -fal 'run_strategy_autoresearch|run_portfolio|smart_pump'
tail -n 80 logs/research_priority_24h/spike_fade_v3_link_short_bounded_20260627_*.log
tail -n 80 logs/research_priority_24h/package_att1_short_ars1_additivity_20260628_*.log
```

## Current candidate map

### Strongest crypto candidate

ATT1 / trendline touch:

- file: `strategies/alt_trendline_touch_v1.py`;
- best recent server row:
  - `att1_density_top_revalidate_20260626_r005`;
  - 457 trades;
  - net `+37.35`;
  - PF `1.325`;
  - WR `58.9%`;
  - DD about `4.67–6.41` depending on summary/DD-doctor;
  - 2 red months, max red streak 1;
  - short side `+28.02`, long side `+9.33`.

Interpretation:

- first canary candidate should be ATT1 short-only;
- keep long side for future bull regime, but do not include it in first bear/chop
  canary unless package/DD work proves it helps.

### Diversifier candidate

SpikeFadeV3 LINK short-only:

- file: `strategies/spike_fade_v3.py`;
- previous best: 360d, 32 trades, net `+5.10`, PF `1.987`, WR `59.4%`,
  DD `1.27`;
- low frequency; good as a small diversifier, not engine.

### Watch candidate

IVB1:

- file: `strategies/impulse_volume_breakout_v1.py`;
- combined forensic sample: 312 trades, net `+16.45`, PF `1.254`, WR `55.4%`,
  DD `8.99`;
- needs DD reduction, maker/fill-risk, side/symbol gating.

### Range/pila

Legacy `strategy=range`:

- rejected implementation:
  - 180d replay: 280 trades, net `-18.60`, PF `0.61`, DD `20.54`,
    5 red months;
- do not unpause.

ARS1:

- file: `strategies/alt_range_scalp_v1.py`;
- still worth repair because older honest pocket existed:
  - 108 trades, net `+16.61`, PF `1.682`, DD `6.68`;
  - but 4 red months;
- current task is additivity with ATT1.

ARF1:

- file: `strategies/alt_resistance_fade_v1.py`;
- short resistance fade idea is valid, implementation likely needs better
  levels/context;
- repair spec already queued:
  - `configs/autoresearch/arf1_structured_short_repair_20260627.json`.

ASB1:

- file: `strategies/alt_support_bounce_v1.py`;
- current implementation failed repair;
- rewrite later, not live candidate.

Elder:

- files:
  - `strategies/elder_triple_screen_v2.py`;
  - `strategies/elder_triple_screen_v3.py`;
  - `strategies/elder_crypto_v1.py`;
- current standalone versions failed;
- future role likely filter/booster.

## What to do during the 4-day Claude window

### Day 1 — finish and interpret queued results

1. Pull final `spike_fade_v3_link_short_bounded` ranking.
2. Pull final `package_att1_short_ars1_additivity` ranking.
3. Compare package rows against ATT1-only controls:
   - PF;
   - net;
   - DD;
   - negative months;
   - max red streak;
   - worst month;
   - side/symbol contribution.

If ARS1 does not improve monthly stability, keep ARS1 research-only.

### Day 2 — ATT1 controlled canary package

If ATT1 remains best:

1. Build final ATT1 short-only canary env proposal.
2. Do not edit `runtime/strategy_pause.env` by hand.
3. Add an explicit controlled waiver/expiry mechanism or runbook:
   - strategy: ATT1 only;
   - side: short only;
   - risk multiplier: `0.05–0.10`;
   - max positions: conservative;
   - auto-rollback on stop streak/DD/PF gate.
4. Produce a human-readable “go/no-go” before touching live risk.

### Day 3 — level/context architecture

The user correctly asks why most strategies do not see both horizontal and
sloped levels like a human trader.

Proposed design:

- build a shared market context layer, not duplicated per strategy;
- for each symbol/timeframe it should expose:
  - horizontal pivot clusters;
  - sloped support/resistance lines;
  - level age/touches;
  - distance in ATR;
  - volume/funding/liquidation context if available;
  - side bias from regime/BTC state.

Strategies should consume this context rather than each re-finding primitive
`min(lows)`/`max(highs)`.

### Day 4 — rewrite plan, not random tuning

Prepare rewrite specs for:

1. ARF1 structured resistance fade;
2. ASB1 structured support bounce;
3. InPlay retest using shared horizontal/sloped levels;
4. Elder-as-filter.

Do not create 20 new strategies. Create small, testable legs with clear
hypotheses and gates.

## Alpaca status

Paper baseline:

- mode: `send_orders`;
- effective capital override: `$1000`;
- current paper positions: `UNH`, `V`;
- broker stops present/rearmed in latest logs;
- market closed; next open in logs:
  - `2026-06-29 09:30:00 -04:00`.

Real `$500` Alpaca canary:

- earliest practical time: Monday 2026-06-29 after fresh broker-protection check;
- only if:
  - live account role/confirm guard is correct;
  - all existing/new positions get broker stops;
  - no duplicate orders;
  - current picks are fresh;
  - expected capital cap is `$500`, no margin/power surprise.

## What not to do

- Do not promise 5–10%/month from current evidence.
- Do not unpause legacy `range`.
- Do not promote ASB1 or Elder current versions.
- Do not run heavy 12-symbol research concurrently with live on the 1GB VPS.
- Do not trust old 89–120% claims unless reproduced with current code,
  current cache, next-open, fees/slippage and closed-candle parity.
