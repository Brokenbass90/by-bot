# Stack comparison — does the wrapper strangle ATT1 short? (2026-06-29)

Question (owner's long-standing hypothesis): does the control-plane (allocator /
slot caps) choke a good strategy's entries and kill its edge?

Method: fed the 365d ATT1 short journal
(`portfolio_..._att1_short_arf1_365d_..._20260611/trades.csv`, 195 ATT1 short
trades) into `backtest/stack_comparison.compare()`, using equity-normalized
per-trade return as the R proxy, sweeping the concurrent-position cap.

## Result
| posture | kept | dropped | PF | win% |
|---|---|---|---|---|
| BARE (no cap) | 195 | 0 | **1.32** | 58.5 |
| cap = 3+ | 195 | 0% | 1.32 | 58.5 |
| cap = 2 | 176 | 10% | 1.27 | 57.4 |
| cap = 1 | 126 | 35% | 1.24 | 56.3 |

## Read
- The bare ATT1-short numbers (PF 1.32 / WR 58.5%) match the server revalidation
  class (PF ~1.325 / WR 58.9%) — good cross-check that the candidate is real.
- **The wrapper does NOT strangle ATT1 at a concurrent cap of 3+** — zero trades
  dropped, PF fully preserved. Slot-starvation only bites at cap ≤ 2.
- So for ATT1, the answer to "does обвязка choke it" is **no, as long as the cap
  is ≥ 3**. The strangling hypothesis is real in general but not the blocker here.

## Action taken
- `configs/att1_short_canary_20260629.env`: `MAX_POSITIONS` 2 → **3** (smallest cap
  that costs nothing). 2 would have quietly trimmed ~10% of trades for no reason.

## Caveats
- This journal is a portfolio backtest output, so "bare" = ATT1's realized set;
  it measures incremental slot strangling, a close proxy for naked-vs-wrapper.
- Regime-gate dimension not tested (no per-trade regime column in this file).
  When you/Codex give a journal with a `regime` field, I'll run the regime-gate
  half too. The slot dimension — the main worry — is answered.
