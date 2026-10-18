# KITY entry readback race — local repair only

The personally executed micro reached ten full entries, ten attached native
guards and reconciled flat finality. It exited early because the first account
execution snapshot exposed only VVV while the later position/native-order
snapshot already exposed all ten legs. That snapshot set the sticky entry block.
The subsequent complete execution reconciliation could not undo the block.

Keep every financial bound and the reducer's conflict handling unchanged. Before
an ACCOUNT_READBACK_V2 position reconciliation, if a known owned terminal entry
has cumulative executed quantity larger than its proven execution rows, perform
one fresh complete account order/execution readback, bypassing the earlier cycle
cache. Bind only exactly proven native guards, then take the ordinary fresh
position snapshot. Do not invent fills, defer conflicts indefinitely, retry
orders, add sleeps, reset blocks or adopt broker quantities. If the bounded
readback still cannot prove custody, the existing fail-closed path remains.

1. Preserve the actual trace privately; publish a reduced, pseudonymized replay
   fixture with source hashes and explicit derived-fixture status.
2. Add failing regressions for the actual terminal-before-executions sequence,
   still-missing executions, foreign quantity and foreign native orders.
3. Implement the bounded GET-only barrier in the existing account adapter;
   leave deployed financial files and spent policy unchanged.
4. Run focused regressions and all KITY tests, replay original actual events
   without rewriting evidence, reconcile independent broker cash and publish
   the exact verdict plus Alpaca personal-arm and timer readback.

No new monetary attempt, deployment, strategy promotion or financial authority.
The root agent reviews the change; independent financial review is unavailable.
