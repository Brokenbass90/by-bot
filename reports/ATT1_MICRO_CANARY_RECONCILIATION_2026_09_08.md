# ATT1 OLD / NEW reconciliation — public engineering summary

**RECONCILIATION COMPLETE; READY FOR OWNER ACTIVATION = FALSE.**

Direct broker/account truth and OLD trade risk/costs were reconciled in the
owner-local archive. Account identifiers, balances, actual executions/holdings,
PnL and derived live risk values are not published. Complete originals remain
on `local/private-evidence-20260908` and in the verified local Git bundle.

NEW is canonical for the next canary strategy/coordinator, not proven net edge.

| Behavior | OLD | NEW frozen public lifecycle |
|---|---|---|
| Signal | H1 short; pivot-left 2, min-R2 .55, touch .50 ATR | H1 short; pivot-left 3, min-R2 .80, touch .35 ATR |
| Stop | trendline + 1.1 ATR | trendline + 6.6 ATR |
| Targets | signal absolute levels preserved | rebase after stop rounding and final fill VWAP |
| BE / trailing | enabled | disabled |
| Time exit | 168h from legacy entry clock | 336h from first fill |
| Sizing | legacy equity/stop model and minimum-size fallback | virtual risk 1/notional 100, floor only |
| Coordinator | legacy caller/runner | journal -> LifecycleSession -> coordinator -> L2/L3 |

The public full NEW profile and configuration diff remain in
`research_lab/results/att1_micro_reconciliation_20260908/`. Actual OLD risk is
variable; an environment percentage does not establish a fixed cash amount.
The next money binding requires a separately verified owner-bound absolute
ceiling, no escalation, max-one reservation and a hard daily admission-loss cap.
These private inputs must never be inferred from the public virtual risk.

The ADA journal contains only public-market simulated execution. It records a
polling continuity gap 9315ms after entry observation. The 266-row snapshot
restores identically with flat simulated exposure and null clean net-R. This
was not a process restart. Preserve dirty evidence and the 2s threshold.

Activation is blocked by the gap, missing broker/actual-cost binding and an
untested exclusive OLD-to-NEW handoff. Prevent duplicates by OLD new-entry
pause, drain/finality, retained cooldown, fresh H1 watermark and one NEW entry
owner. NEW currently has no money authority. Zero-risk remains a separate
public-only comparator. No account/service/risk/order changes occur in export.

Plan: `docs/superpowers/plans/2026-09-08-att1-profile-migration.md`.
Private arithmetic verification remains reproducible from the original local
commit. This public summary is not an activation or a broker parity receipt.
