# Approved Alpaca data parity implementation ledger

Owner approved all four corrections and immediate implementation. No new strategy,
financial authority, NET change or SHOP rearm. Work in existing recovery branch.

1. Reuse frozen Monthly capture/aggregator/selector; export exact Monthly58 daily
   view with260 exported sessions, source clocks/pins and adjustment policy.
   Actual capture has older partial sessions: preserve and flag them; require
   complete latest200 used by frozen Monthly, without filling or rebasing.
2. Prove JSON reader roundtrip, full-history vs260-window ranking/selection parity;
   reject SIP/universe/coverage/revision contamination. Use real16Oct capture.
3. DATA_ONLY all-symbol diagnosis and hypothetical Monthly/Weekly on identical
   inputs; no actual cash/ownership claims from market data. No calendar spoof.
4. Isolated VPS DATA_ONLY exporter after existing source; immutable seals/replay,
   daily local pull into Claude data folder and19Oct post-close intake prepared.
   Keep financial units/files/locks untouched; verify preservation.
5. Independent bounded review, targeted/exact tests, receipts, board and commits.
6. Next independent task: origin-confirmed ElderV1.2 f1 integration, no producer,
   outcomes/judge/history changes or new money. ATT1 economicFAIL out of money queue.
