# Live and research incident — 2026-08-09

## Executive verdict

This is not a clean ATT1 observation. The strategy opened 180 ADA, then a
legacy pump-fade DCA path added 90 ADA to the same exchange position while the
runner still tracked only 180. The exchange stop covered the whole position,
but the software TP ladder could have left an unmanaged residual.

Do not use this trade as clean ATT1 evidence and do not increase ATT1 risk from
the pre-fix cohort.

The reproducible order-lifecycle audit found the same contamination in two
older ADA ATT1 lifecycles as well: 116 + 104 units and 97 + 94 units. Together
with the current 180 + 90 lifecycle, 3 of 25 ATT1 lifecycles in the supplied
journals contain a confirmed extra non-reduce order. The order-link journal may
be retention-limited, so this is a lower bound rather than proof that the other
22 lifecycles were clean.

## Direct live truth

- Original ATT1 fill: ADAUSDT short 180 at 0.1980 on 2026-08-08 22:48:55 UTC.
- Legacy additional fill: short 90 at 0.1992 on 2026-08-09 00:03 UTC.
- Broker position observed on 2026-08-09: short 270, average 0.1984.
- Exchange stop observed: 0.2018. No exchange take-profit order.
- Planned TP1 was 0.196371789. The observed low was about 0.1966, so TP1 and
  the configured one-R trailing activation were not reached.

## Root cause and fix

The monolith's legacy DCA branch excluded only bounce/range strategies and
therefore accidentally applied pump-fade averaging to ATT1. Commit `39d87de`:

1. permits legacy DCA only for explicit pump/pump-fade strategies;
2. reconciles runner quantity to broker quantity on every open-position sync;
3. emits a dedicated reconciliation alert/event;
4. persists the macro regime and orchestrator multiplier with live events.

The fix is committed and tested but must not be deployed by restarting the
trading process while the broker position is open.

## Regime finding

ATT1 was short while the macro regime was `bull_chop`. This was possible
because ATT1 receives risk scaling but is not wired to the strategy regime
gate. A hard regime gate is not added in this incident fix because it would
change the strategy and requires an OOS comparison first.

## Research harness findings

### Pair stat-arbitrage V2

The original run was measurement-invalid: an AR1-entry-gate `continue` skipped
management of open positions, producing holds up to 201 days despite a 20-day
limit. Exit z-scores were also refit instead of using entry-frozen parameters,
and two-leg round-trip costs were undercharged.

The corrected run enforces a 20-day maximum, freezes the entry model and charges
four leg-sides. Result: 1,197 trades, PF 0.7401, 1/4 positive folds. The current
logic remains `FAIL_OR_REBUILD` after a valid measurement.

### FX smart-grid V2

Independent ledger validation passes, but the run has only five trades. PF
4.294 is not promotion evidence. The binding issue is excessive rarity, not a
proven arithmetic error.

### Measurement contract

`research_lab/result_receipt_validator.py` now checks timestamps, trade
arithmetic, maximum holding time, aggregate net and fold counts. Both research
harnesses write a validation receipt and must mark a failed receipt as
`MEASUREMENT_INVALID`.

## Local AI scope

Ollama remains proposal-only on the Mac and sees only an explicit safe source
allowlist. It does not see every repository line, secrets or broker functions.
The project audit supervisor runs every six hours and stores findings in the
project-audit registry; findings require deterministic reproduction before a
code change.

## Next gates

1. Confirm the broker is flat, then deploy the exact safety commit and verify
   deployed SHA, service heartbeat, broker flat truth and first clean sync.
2. Start a new ATT1 clean cohort after the DCA fix; preserve the incident as a
   contaminated record instead of deleting it. Use
   `scripts/audit_att1_order_contamination.py` to tag historical lifecycles.
3. Deploy BOUNCE1 reason telemetry at risk zero and identify the dominant
   blocker before changing any threshold.
4. Run an ATT1 regime OOS A/B (risk scaling only versus an explicit bull gate).
5. Do not increase live risk or promote FX/stat-arb from the results above.
