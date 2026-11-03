# Monthly OPENING repair — 3 November 2026

Status: **MONTHLY_SOURCE_PATCH_V7_INSTALLED_NO_BUY**, installed 06:05:57.398 UTC.

The existing 68943d4 OPENING scoped-refresh fix is selected on the actual VPS.
The original account lock inode 813893, account/book, financial limits, frozen
selection and execution dates are preserved. No order was sent. Source-only
owner authorization was rebound; this does not authorize another entry date.
The old source scope is entry-revoked only after the new unit was selected and
verified. Existing financial claims and history were preserved; no process killed.

## Actual GET qualification

The transport rejected non-GET methods, with writes disabled in the original
client. Actual bound-account flat/open-order GETs passed; account identity and
cash/gross/reserve checks passed. Initial cost evidence was deliberately aged
5.2 real seconds, then refreshed through the scoped OPENING path. The exact
production final-dispatch closure and fee TTL validator accepted source ages
1.272 and 2.721 seconds (coverage 2.189 / 3.638 seconds), below unchanged 5 seconds.
The actual final clock/window check correctly refused entry outside the window.
No broker POST, native financial reservation or financial journal constructor ran.
This is GET_PREPOST_FEES_PASS_WINDOW_BLOCKED, not a successful market-open order.

Three subsequent real native idle cycles returned OUTSIDE_MONTHLY_WINDOW with
no issues. Independent LIVE broker readback at 06:18:54.926364 UTC confirmed the
account matches both scope and manager, positions 0, open orders 0, recent orders 0.
That bounded recent-order observation is not a complete historical/finality claim.

## Selected identities

- Scope: `df537c12abb3889cbd526529f004e50b4071d7b853d1f2aca50737bfe56cb9b9`.
- Runner: `bf8857c3c58e3f6087c0168b3e62596107b33df2fb38127a4ccd15d50be9fd4b`.
- Packet: `4cf04904195eb0f4db6fb369524dced38d6f18e5f70481050db943b876ab2ab4`.
- App: `/opt/bybot-research/monthly-opening-refresh-20261102/candidate-4bb6b9e8cefc8a10-ta1a4f4e1/app`.
- Owner review: same candidate `/owner-review-opening-v7`.

## Remaining entry gate

Frozen Monthly rules permit only the first five minutes of the first session
after the month-end signal. The missed 2 November window cannot be retried under
unchanged rules. A 3 November 14:30–14:35 UTC initial-entry recovery would require
an explicit, separately approved date exception and its own validated scope and
source package. It is not yet prepared/armed, and must not be called a frozen
Monthly execution or be backdated. Current 400/280/40 caps and future custody remain.

## Evidence and review

Public sanitized evidence: `evidence/monthly_live_repair_20261103/`.
Private independent account readback and source packet remain excluded from Git.
One bounded independent Astra/high review identified premature old-scope
revocation, timer-stop cleanup, flatness freshness and AST-probe namespace issues;
all four were fixed before installation. Six focused guard tests passed after
reproducing the old failures. The already accepted exact 281 local/VPS source
checks were not repeated as a substitute for actual GET qualification.
Never rerun the consumed apply helper; use readback only.
