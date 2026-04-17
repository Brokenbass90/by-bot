# Codex Task — Elder Base Retest (2026-04-17)

## Context

`elder_triple_screen_v2` with `ETS2_VOL_CONFIRM=1` **failed** (PF=0.895, DD=50%, net -37%).
The volume filter is making Elder WORSE in crypto bear markets — high volume in bear = panic selling,
not bullish confirmation. We need to test the BASE Elder (no vol filter) to know if the strategy
itself has edge, separate from the broken filter.

Also: Elder allocator mults were wrong (bear_trend=1.0 when it should be 0.0).
That's fixed in `configs/portfolio_allocator_policy.json` — deploy after this test.

---

## Task 1: Elder base retest (NO volume filter)

```bash
cd /root/by-bot
git pull origin $(git rev-parse --abbrev-ref HEAD)

python3 backtest/run_portfolio.py \
  --symbols BTCUSDT ETHUSDT SOLUSDT LINKUSDT \
  --strategies elder_triple_screen_v2 \
  --start 2024-01-01 --end 2024-12-31 \
  --env-file configs/strategy_profiles/elder_base.env \
  --tag elder_base_nofilt_20260417 \
  --fees 0.06 --slippage 0.05
```

Create `configs/strategy_profiles/elder_base.env`:
```
ENABLE_ELDER_TRADING=1
ETS2_VOL_CONFIRM=0
ELDER_RISK_MULT=1.0
ETS2_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT
```

**Promotion gate**: PF > 1.20 AND net > +15% AND max DD < 25%.
Report: PF, net%, max DD, trade count.

---

## Task 2: Elder bull-only test (regime-gated)

If Task 1 passes, test with ONLY bull_trend regime active:

```bash
python3 backtest/run_portfolio.py \
  --symbols BTCUSDT ETHUSDT SOLUSDT LINKUSDT \
  --strategies elder_triple_screen_v2 \
  --start 2023-01-01 --end 2023-12-31 \
  --env-file configs/strategy_profiles/elder_bull_only.env \
  --tag elder_bull_only_20260417
```

Create `configs/strategy_profiles/elder_bull_only.env`:
```
ENABLE_ELDER_TRADING=1
ETS2_VOL_CONFIRM=0
ELDER_RISK_MULT=1.0
ETS2_SYMBOL_ALLOWLIST=BTCUSDT,ETHUSDT,SOLUSDT,LINKUSDT
```

2023 was a bull year — if Elder has real edge it should shine here.

---

## Task 3: Deploy fixed allocator policy

The bear_trend mult for Elder was 1.0 (WRONG) — now fixed to 0.0.
After testing, push the fix:

```bash
cd /root/by-bot
git pull origin $(git rev-parse --abbrev-ref HEAD)
python3 scripts/build_portfolio_allocator.py
# Verify: elder_ts should show base_risk_mult=0.0 in bear_trend output
```

---

## Expected outcomes

| Scenario | Elder base (no filter) | Bear | Bull |
|---|---|---|---|
| Best case | PF 1.30+, → canary candidate | 0.0x allocation | 1.05x allocation |
| Neutral | PF 1.1–1.2, → watch with tighter symbols | 0.0x | 0.7x |
| Fail | PF < 1.1 → KILL elder entirely until market regime changes | — | — |

If base Elder also fails: set `ENABLE_ELDER_TRADING=0` in live env and remove from active sleeves.
Elder is designed for trending markets — if the base is broken it means current market conditions
(choppy bear) simply don't suit it. It may revive in a bull cycle.

---

Prepared by: Claude Sonnet 4.6 | 2026-04-17
