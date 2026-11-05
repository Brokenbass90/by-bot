# Monthly cents proposal — bounded local draft, 5 November 2026

Status: DRAFT_NOT_READY_FOR_GO. This accepts cents as a proposed compatibility
choice for a future owner packet, not as a proven fix for the lost LLY422.
No date/window, new entry authority, broker POST or live installation is assigned.
The old3Nov reservation/GO remains spent/uncertain and cannot be reused.

## Concrete proposed amount and offline evidence

Original capped notional101.413902261 -> ROUND_DOWN to cents101.41.
Unused remainder0.003902261 stays cash; no rounding upward, budget increase or
redistribution. This is an illustration based on the original amount, not a
fresh sizing decision: future admission must recompute with fresh approved data.

The existing native AlpacaClient serializer was exercised with this quantized
amount, precision2 and an in-memory request sink only. It emitted notional
"101.41". No credential/client HTTP constructor or network endpoint was invoked.
The actual existing Monthly transport guard rejected that fixture with
MONTHLY_NOTIONAL_MARKET_WIRE_REQUIRED, because the frozen guard requires9dp.
This is an expected compatibility gate, not a new production failure.
[Reproducible offline result](evidence/monthly_cents_proposal_20261105/offline-proposal.json).

## Exact remaining implementation/acceptance boundary

Change the future source-bound Monthly candidate coherently: cents serialization,
exact permit payload, reserved wire amount and reconciliation of broker notional
against that same wire amount. Keep unrounded cap distinct from submitted amount;
never repair or reinterpret an existing uncertain intent. An isolated serializer
change can otherwise fail the guard or final reconciliation. Existing legacy paths,
old signed scopes, account lock, one owner, capital/gross/reserve/loss-stop and
fill-based STOP rules must not be widened. No application code was changed by
this draft; all selected LIVE bytes remain unchanged.

Mandatory rejection capture acceptance: exact response body and request identifier
in private evidence; safe derivative for ordinary observations/public reports.
Existing local capture is NOT full-body storage: it reads8193bytes, hashes8192,
records truncation and keeps only allowlisted/scrubbed JSON fields. It is also
NOT_DEPLOYED. It must not be represented as satisfying the proposed full-body
requirement. Future capture must bound reads and mark oversized/unavailable bodies
explicitly, retain exact captured bytes privately with hash/length/permissions,
avoid credential/header/public log export and preserve the original error without
retrying a consumed permit. No new journal/service is needed; use existing private
runtime evidence/observations. Tests must cover precision, cap, matching permit,
recovery reconciliation, accepted fill/STOP and rejection without resend.

After that local candidate/review and dated admission packet, owner GO is still
required before installation/POST. No automatic December wait or next-date carry
is imposed. The original LLY response body remains lost and reason UNKNOWN;
notional precision was not established as its cause. The claim "only difference"
is too strong: AMD and Monthly used different source-bound execution paths.
