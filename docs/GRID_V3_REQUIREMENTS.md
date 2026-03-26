# Grid V3 Requirements

## Goal

Redesign grid from a naive mean-reversion trap into a tightly controlled sidecar that
only operates in clearly bounded range conditions.

This is not a core strategy target.

## Why V1/V2 Failed

Observed failures:
- TP too close, costs eat the edge
- trades continue into trend transitions
- range detection too weak
- no inventory intelligence
- too many low-quality fades

## Hard Requirements

### 1. Inventory-Aware

Grid must know:
- current side exposure
- total inventory
- average price
- remaining risk budget

Rules:
- no unbounded averaging
- no martingale escalation
- hard max levels
- hard max inventory per symbol

### 2. Cost-Aware

Entry allowed only if expected move comfortably exceeds:
- spread
- fees
- slippage
- volatility noise floor

If expected mean reversion distance is too small:
- skip trade

### 3. Range-Regime Only

Required gates:
- narrow EMA gap
- low slope
- bounded ATR
- bounded local range width
- no recent range breakout

### 4. Breakout Kill-Switch

When range breaks:
- stop adding inventory
- flatten if risk threshold breached
- enter pause state

Pause duration:
- configurable
- longer after strong breakout

### 5. Better Exit Logic

Do not exit on tiny micro-TP.

Need:
- minimum gross move threshold
- partial exit only if economics remain positive after costs
- optional hold-to-mean / hold-to-opposite-half logic

### 6. Daily Risk Cap

Per symbol:
- max daily loss
- max signals per day
- max same-direction attempts

Global:
- sidecar capital bucket
- total grid exposure cap

## Candidate Design

### Mode A: Single-Excursion Reclaim

Not a true ladder.

Trade only:
- one deep excursion
- one reclaim signal
- one exit to mean/opposite quartile

Best for first safer version.

### Mode B: Limited Ladder

At most 2-3 levels:
- level 1 starter
- level 2 only if excursion deepens inside valid range
- level 3 only if still flat and risk budget allows

Never more.

### Mode C: Inventory Market-Making Sidecar

More advanced:
- passive bias
- fade only when range confirmed
- inventory rebalance around anchored mean

Probably later phase.

## Market Priority

First test candidates:
- FX: EURJPY, EURGBP, EURUSD
- Crypto: deprioritized unless clear range instrument subset found

Not first:
- GBPJPY
- gold
- high-beta crypto basket

## Backtest Requirements

Must pass:
- base positive
- stress positive
- no catastrophic DD
- acceptable monthly profile

If not positive after fees/slippage:
- reject

No more "looks fine before costs" candidates.

## Deliverables

Phase 1:
- detailed v3 config
- single-excursion reclaim prototype
- FX pair pilot on 3 pairs

Phase 2:
- limited ladder inventory model
- per-level accounting
- stronger pause / flatten logic
