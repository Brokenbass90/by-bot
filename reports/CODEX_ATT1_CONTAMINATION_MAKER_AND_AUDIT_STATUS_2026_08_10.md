# Codex: ATT1 contamination, maker execution and audit status — 2026-08-10

## Outcome first

- Bybit direct broker truth after the incident: `retCode=0`, zero open positions.
- ADA was not an ordinary clean ATT1 lifecycle. ATT1 opened `180 ADA`; the
  legacy pump-fade DCA path added `90 ADA`; broker size became `270 ADA` while
  the runner originally owned only `180 ADA`.
- Exchange closes: TP1 `99 ADA` and final trailing stop `171 ADA`. Total broker
  closed PnL was `+0.73928972 USDT`; open/close fees were `0.05849218 USDT`.
  The trailing/breakeven path did work. Earlier AI text claiming that trailing
  did not work was stale/misclassified.
- The DCA authority leak is fixed and deployed. Unexpected broker quantity
  increases now permanently contaminate the lifecycle, runner quantity and
  average entry reconcile to broker truth, and contaminated closes are stored
  under `<strategy>__contaminated` rather than entering the clean ATT1 cohort.
- Historical ATT1 is retained and tagged; it is not deleted. The promotion
  cohort restarts after the deployed fix. The backtest result is not invalidated
  by this live-only DCA branch, but the old mixed live cohort cannot justify a
  risk increase.

## Git and server receipts

Branch: `codex/dynamic-symbol-filters`

| Commit | Scope |
|---|---|
| `39d87de` | Confine legacy DCA to pump/pump-fade and reconcile runner quantity |
| `4684b39` | Audit ATT1 history for hidden position additions |
| `f030d43` | Separate contaminated broker lifecycles from clean statistics |
| `2a122a4` | Repair the project-auditor seeded self-check |
| `4388e8d` | Harden maker entry lifecycle and nonfill/adverse-selection telemetry |

Targeted server deployment preserved server-only WIP. Backup:
`/root/by-bot/backups/codex_contam_20260810_0833/`.

Deployed server SHA-256:

- `smart_pump_reversal_bot.py`: `2fac3aa2b6dcb8a33cbe6c88706303c98987cc9e088e27df0754cca2e32dcb2f`
- `bot/runner_state.py`: `0e1e75fe5f4d12de9c7a3ed16779ef3ec4a8f08a0167cdeec0fc5bd3d50f6e4a`
- `scripts/backfill_contaminated_trade_close.py`: `8fc570fba8d3fe0b342f89a628dc78bda4f6d7e00fdf81ca15d192cf8b04140d`

Controlled restart happened only after 3/3 direct flat confirmations. At the
latest check the service was active, Bybit authentication returned OK, direct
positions were zero and `runtime/live_positions.json` contained zero rows.

## Clean accounting receipt

The missing ADA close was backfilled idempotently after a DB backup:

```text
strategy=att1_trendline_touch__contaminated
qty=270
entry=0.1984
exit=0.1949
pnl=+0.73928972
fees=0.05849218
reason=TRAILING_SL_BROKER_TRUTH|CONTAMINATED_QTY:expected=180,broker=270
```

A second backfill attempt returned `ALREADY_CLOSED`.

## Maker model: accepted idea, corrected implementation

Claude's economic diagnosis is directionally useful: execution costs are a
binding gate for thin-edge strategies. The original uncommitted implementation
was not yet promotion-grade:

1. a resting order could be silently overwritten by a newer signal each bar;
2. a bare OHLC touch counted as a guaranteed maker fill;
3. pending-at-end orders were mixed into the fill denominator;
4. nonfills had no adverse-selection telemetry;
5. the original signal price was lost after the entry-price mutation.

Commit `4388e8d` fixes these contracts. The engine now requires configurable
trade-through, keeps one order lifecycle until fill/expiry, reports
filled/expired/pending separately and records the direction of the expiry
markout for unfilled orders. Fifty focused tests pass.

Preregistration:
`configs/research/crypto_maker_execution_gate_20260810.json`.
It declares 12 trials per family and explicitly forbids money promotion from
the reused historical window.

### First bounded smoke (diagnostic only)

BTC/ETH, 30 days ending 2026-06-30, ATT1 exact signal code:

| Entry | Trades/fills | Net | PF |
|---|---:|---:|---:|
| Existing taker baseline | 8 | `-6.14 USDT` | `0.774` |
| Strict post-only, 2 bps offset, 2 bps trade-through, 6 bars | 6 fills from 11 placed | `-21.85 USDT` | `0.157` |

Three orders expired and two were still pending at end-of-period. All three
resolved nonfills had a favourable expiry markout. This window is far too small
for a strategy verdict, but it already falsifies the shortcut "lower fees must
improve the sleeve". Filled-maker selection can be worse than the baseline.

## Research supervisors at 2026-08-10 morning

The local station had five healthy research-only processes and no live order
authority: Alpaca adaptive shadow, XSEC shadow, dynamic funding positioning,
frozen funding positioning and project audit.

| Contour | Current evidence | Interpretation |
|---|---|---|
| ATT1 | live tiny `0.10`, post-fix clean cohort starts now | keep tiny; old mixed N cannot scale risk |
| BOUNCE1 | risk-zero BTC/ETH shadow; blocker counters now observable | prospective N/parity still required |
| Frozen funding | 9 closed, 9 fills, raw mean `606.09 bps` | too early and raw; N20-30 concentration/adverse-selection gate binds |
| Dynamic funding | 51 closed, 3 open, 1 nonfill, raw mean `484.43 bps` | research only; dynamic-universe concentration must be audited |
| XSEC V3 | 13 completed rebalance returns, 6 positive; median `-0.404%` | heavy positive outliers, not stable; no promotion |
| Alpaca adaptive | current risk-zero picks SNOW/BAC/PANW/CRWD | research selector, not live purchasing authority |
| Project audit | registry valid; internal seeded canary repaired | proposal-only; findings still require reproduction |

The large raw funding and XSEC sums are not annualized returns and are not safe
money estimates. XSEC's positive aggregate is dominated by a few large
rebalance outliers while the median outcome remains negative.

## Alpaca protection truth

The live monthly account remains a SAFE_HOLD portfolio, not a fully autonomous
adaptive strategy. The separate manager has protective-exits-only authority.
Before the August 8 fractional-order fix, Alpaca rejected stop replacement with
`qty must be an integer`; therefore the historical software trail did not lock
SCHW's gain. The fix was deployed on Saturday and the first real broker
acceptance test is the next US market session. It must not be reported as
working until the receipt contains a successful replacement/creation.

Latest pre-session broker snapshot used in this audit: equity about `485.28`,
ABBV about `-0.61%`, SCHW about `+5.88%`, two broker stops present. The next
protective manager window is scheduled every 15 minutes during `13-21 UTC` on
weekdays.

## What Ollama does and does not do

Ollama is a bounded, proposal-only critic over a non-secret registry and
selected source artifacts. It does not continuously understand every runtime
fact and cannot prove its own findings. The deterministic scanner has a seeded
known defect; its fixture had drifted after E1 was made stricter, causing a
false degraded status. The fixture is now aligned and 4/4 audit-health tests
pass.

The DCA incident required direct broker reconciliation: static source analysis
alone cannot observe that a broker position is 270 while the runner believes
180. The self-healing target therefore needs both layers:

1. deterministic code/data contracts and seeded defects;
2. broker/event-ledger reconciliation incidents written into the same audit
   registry for Ollama/human triage.

Ollama must never claim that it has read or verified the whole project merely
because it received a manifest.

## Next gates

1. During the next US market session, verify an actual fractional Alpaca stop
   ratchet receipt; otherwise mark the manager FAIL and repair it.
2. Continue the five existing risk-zero supervisors; do not start a sixth long
   job while the WIP cap is full.
3. At the first measurement slot, run the preregistered strict maker grid for
   ATT1, BREAKDOWN and ARF1. No best-cell-only reporting.
4. **DONE 2026-08-10:** quantity/authority/reconciliation incidents now feed
   the audit registry from a non-secret idempotent JSONL ledger. The confirmed
   ADA `180 -> 270` mismatch is present as critical finding `0aa5368872f8`;
   Ollama's fact index reads current registry counts instead of hardcoded ones.
5. Review ATT1 risk only after the new post-fix clean cohort reaches its
   declared N/PF/DD/zero-incident gate. No calendar promise substitutes for N.
