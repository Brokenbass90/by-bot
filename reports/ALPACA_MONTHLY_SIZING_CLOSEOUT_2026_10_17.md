# Alpaca sizing closeout and wire correction — October17

UPDATE: Claude507f782 independently confirmed d205f8f; ALPACA_STRATEGY_PARITY_PASS
received. Earlier pending-review statements below are historical. See
[accepted review and DAY next step](ALPACA_PARITY_ACCEPTED_DAY_NEXT_2026_10_17.md).

CURRENT: **ALPACA_MONTHLY_SIZING_PARITY_PASS**.
Claude's independent review7800b72 accepted b95550b's monthly/daily logic and
requested sizing proof. That proof is now complete. A newly reproduced native
wire-format defect was also corrected; Claude must confirm that small source
delta before a full `ALPACA_STRATEGY_PARITY_PASS` is recorded. Entry HALT remains.

## Exact sizing evidence

`scripts/audit_alpaca_monthly_sizing_v1.py` invokes the actual candidate
`MonthlyNativeBinding.prepare_entry` sizing code at the reference scale. It
does not run the baseline portfolio simulator, strategy/outcome judge or broker.

Starting with reference cash1000, it recalculates every entry quantity from
cash/equity/weight and the reference source's open+10bps fill. Cash is debited
after each sequential entry, credited using independently computed quantities
and archived terminal exit fills; retained positions contribute their current
open marks. All66 entries are computed, including the2 final open survivors.
The archived64 quantities are used only as expected outputs, never as inputs.

Selection gates are supplied as explicit offline fixtures because their parity
was reviewed separately. The uncapped reference-scale fixture has no account,
client, runtime, constructor or dispatch route. The production constructor still
rejects capital1000; its487.42 ceiling remains unchanged. All66 cases are also
checked with the real production ceiling.

| Check | Result |
|---|---|
| Closed reference entries compared |64/64|
| All entries independently sized |66|
| Monthly decisions / retained position marks |24 /2|
| Production ceiling checks |66|
| Maximum notional difference |1.1368683772161603e-13 USD|
| Maximum quantity difference |1.7763568394002505e-15 shares|
| Maximum9dp wire quantity difference |1.9767520953450912e-11 shares|
| Final reference equity difference |0|
| Required tolerance |1e-9|

[Full sizing receipt and64 comparisons](evidence/alpaca_monthly_sizing_20261017/sizing_audit.json).
The known exit dates/fills remain input evidence; this audit does not create new
exit/edge evidence or predict actual future broker prices.

## Material serializer defect found and repaired

The old test broker accepted an unformatted float. A new regression binds the
**real AlpacaClient serializer** to a fake transport and reproduces:

`compiled204.7164 → old payload204.72 → reserved_entry_order_mismatch`.

The old serializer both exceeded the compiled budget and caused a real-fill
readback to reject before initial protection. This was missed in the previous
fixture-only proof. The candidate remained disabled, so the finding caused no
actual monetary order or current-NET change.

Only the tagged monthly path now requests9-decimal notional, rounded **down**.
The exact encoded notional is journaled before send and compared numerically
with the raw broker readback. The same input now encodes204.716400000, without
increasing the budget. Legacy untagged callers keep their old2-decimal default;
current NET uses its separate immutable qty-based installation.

Alpaca explicitly supports up to9 decimal places for notional and quantity.
[Official fractional-order contract](https://docs.alpaca.markets/us/docs/fractional-trading).
No test order/HTTP probe was used.

**394 targeted PASS**, including the actual serializer regression, the reviewed
monthly/native/owned-manager tests and legacy intended runner/month-turn checks.
The full suite was not rerun after this narrow correction; its last measured
b95550b result remains5257PASS/60oldFAIL, not a current full-suite green claim.
[Verification and red/green details](evidence/alpaca_monthly_sizing_20261017/verification.json).

## Independent review and physical package

[Review intake](evidence/alpaca_monthly_sizing_20261017/independent_review_intake.json)
retains7800b72's exact file hash and conditional verdict: logicPASS, sizingUNKNOWN
at the time of that review. It is not rewritten into a later unconditional PASS.

The corrected candidate is installed separately, still disabled:
`/opt/bybot-research/alpaca-monthly-baseline-20261016/source-binding-v3/app`.
32 source files; spec
`14aea403bc8ccce376f438d766a4648bc1de03e333a9184e650eafcfd6776e3d`.
VPS verification PASS;59 current NET/source/unit/HALT pins unchanged. No broker
request/write, service activation, systemd/cron/profile change or money binding.
V1/V2 remain immutable history; V2 must not be activated as the final candidate.
[Installed receipt](evidence/alpaca_monthly_sizing_20261017/deployed_receipt_v3.json),
[exact source manifest/identity](evidence/alpaca_monthly_sizing_20261017/source_manifest_v3.json).

New strategy identity:
`ALPACA_MONTHLY_BASELINE_8f6d1fd2a5f72cf88133cdc390eb3230ed2ab8fc6686e6bf808145223277c799`.
Reference, numerical policy, gross/weight/capital limits and contract hash are
unchanged. Current NET is not migrated; stop277.69 and its manager are untouched.
This install is not a fresh broker-protection observation.

## Next bounded actions

1. Claude confirms the sizing receipt and serializer-only diff; no repeat of the
   already independently reproduced baseline or durable-book replay is needed.
2. Operational DAY-stop verification: confirmed broker readback in the first
   scheduled manager ticks of each regular session, explicit alert/escalation
   through the existing safety path if protection is absent. Report regular-
   session time without confirmed protection, with observation gaps UNKNOWN;
   do not count the whole closed night/weekend as a regular-session outage.
   No new observer/service/alert has been activated in this sizing task.
3. Only then the remaining existing fresh gates and separate owner financial
   activation decision. No new PAPER/statistical waiting or risk increase.
4. KITYbatch/privateWS orders-OFF, then ElderHEDGE orders-OFF. No expired policy,
   watcher READY or old GO becomes monetary authority through this receipt.
