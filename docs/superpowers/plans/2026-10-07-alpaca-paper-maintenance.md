# Bounded Alpaca PAPER maintenance continuation

Owner-approved incident/PAPER lifecycle scope, existing frozen Dynamic V1 plan.
No selector/judge/risk/capital/LIVE changes. Reuse current native bridge helpers.

1. Require the existing PAPER intent and exact native owned ledger/account/entry
   before maintenance; no entry sender, adoption or repricing.
2. Recheck full native stop readback. For an expired/unfilled DAY stop, persist
   deterministic session re-arm dispatch before POST, use existing strict floor
   re-arm helper, then read back. Missing/uncertain re-arm lookup never resends.
3. On protection failure, use the existing proof-scoped PAPER owned kill only.
   Shared account lock and exact entry/quantity ownership remain mandatory;
   foreign/legacy holdings and orders have no write authority.
4. Proven actual stop or emergency MARKET terminal is journaled separately.
   Gross PnL is not net; account pending fees and ledger coverage remain explicit.
5. CLI default GET-only; maintenance apply/unwind explicitly PAPER-only. No
   daemon/cron until first actual owned PAPER intent and reviewed handoff exist.
6. Test DAY expiry/restart, 422 failure and partial/unknown ownership offline;
   real Oct8/9 PAPER evidence remains a future gate. No synthetic PASS.
