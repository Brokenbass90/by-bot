# Exact initial-entry recovery — 3 November 2026

**READY_FOR_OWNER_GO**, not armed, no BUY. The v7 OPENING source repair is already
installed; this separate packet adds a single dated initial-entry exception.
Fresh actual GET at07:49:36.339UTC: LIVE account matches selected scope+manager,
positions0,complete openorders0,LLY active/tradable/fractionable, cash+40reserve
and equity/gross sizing pass. Broker next_open matches3Nov14:30UTC.
Premarket IEX quote is still2Nov21:00:01UTC, not fresh for entry; the real runtime
must receive/accept a new eligible quote in the opening window, otherwise noBUY.

## Exact decision for the owner

- Only LLY; one recovery selection/CID and at most one actual entry.
- Maximum101.41390226115651USD, wire rounds down; no automatic basket expansion.
- Window3Nov2026 **14:30–14:35UTC /16:30–16:35Asia/Nicosia** only.
- Same Oct30 sealed picks/ATR/weight; actual fill date3Nov, no backdating.
- Native full-quantity STOP uses actual fill minus raw2ATR20 under the existing
  protection/reconciliation/failed-stop safety path. No stop acceptance is claimed
  before a real broker response.
- Original400USD capital/280gross/40reserve and8USD cumulative net-loss latch stay.
  Existing standing rights through1Feb2027 and future normal monthly-session
  max4 entries remain; the added initial exception is restricted to one exact CID.
  Loss latch/STOP are controls, not guaranteed worst-case execution loss caps.
- This is an operator date exception/partial initial basket, not unchanged frozen
  Monthly historical performance. Original2Nov window cannot be replayed.
- If the window is missed or a check fails, no automatic move to4Nov or another
  symbol. Existing custody/ratchet continue after the entry window closes.

Scope1d6a09ade66fc0ec6b1cff403d8fb327c176d31305851082023ec3084118110a.
Runner848ca8626cd54a2ea0e7cf353597d53e0c82ddb1d859b0263554def856d54120.
Final packet23eb48b7703decbb0836e8b8bf2fad19fd5cd1a81163f4f2ab523f0654fcb865.
Exact separate approval: `GO ALPACA_MONTHLY_INITIAL_RECOVERY ` followed by that scope.
No new GO file or install claim exists. Previous GO does not cover this date.

## Actual engineering acceptance

Existing book has one sealed selection768a6421…a2c8 and one unsubmittedLLY ticket,
101.41390226115651USD. Positions/exits/dispatches/rotations empty; no native intent.
The new append-only selection preserves the original record and ticket, uses
actual3Nov for order/fill/daily-state, and is bound to the separately signed policy.
Original30Oct capture1793391603399509902 reconstructed the EXACT sealed source_id.
Frozen historySHAf028521bec52dfd0adce82dd96f1f84477574d456603b63195e32849e7e3bde6.
Current rolling2Nov history has different causalSHA; equality was NOT weakened.
The exception uses the pinned original snapshot; ordinary daily source stays current.

Full production CLI/dispatcher rehearsal used actual source prices and unchanged
selector with an isolated simulated account/clock/HTTP. One simulated buy, one
native stop, actual-date state and restart without duplicate; no source-loader or
selector replacement. This is engineering evidence, never a prospective trade.
Local exact302/302PASS. VPS first302 run:300PASS, one600s timeout and one1.222s
wall-clock test threshold under20%CPU (later50%). Only the two failed nodes were
repeated at100%onecore/Nice19/CPUWeight1, same bytes/network denied:bothPASS175.78s.
The originalFAIL/XML remain intact. Qualification explicitly verifies all302unique
nodes=300initial+2resolved; it does NOT relabel the first run302PASS or hide failures.
Both runs broker requests/writes0,no fallback.53source/20testfiles/40imports.
Eight installer guards and one retained-four-entry-grant/CID-isolation guard pass.

One bounded Astra/high core/history/installer review found one import-order issue,
fixed before actual clean-process static VPS verification at07:45:50.568UTC.
Actual verify passed; a missing-GO apply attempt was rejected before any action,
with no GO/claim created. Final compound-evidence verifier is root reviewed.

## Personal launcher and lost-response recovery

Private folder `.private/monthly_initial_recovery_20261103/owner-review-initial-recovery-v1`.
`owner-monthly-initial-recovery-v1.sh --readback` is default GET-only. Verified
readback07:22UTC saw existing v7 selected, flat0/orders0, recovery selection absent.
`--apply-once` is financial activation and MUST await this separate owner approval.
The helper stops only Monthly timer, waits idle without killing a process,
rechecks actual GETs under original account lock813893, appends the new selection,
selects/reloads exact source, then entry-revokes old scope. Existing history,
claims/halts/loss latch/capital/custody remain; it never itself calls BUY.
Timer may dispatch only when newly approved scope and live opening guards allow.
After uncertain response never repeat apply: use default readback/private receipt.
All source/packet/script hashes checked; readback uses existing approved pinned
Alpaca collector/bridge with original bound credential loader, no secret printing.

Public evidence: `evidence/monthly_initial_recovery_20261103/`.
Private scope/profile/account snapshots/history remain excluded from Git.
