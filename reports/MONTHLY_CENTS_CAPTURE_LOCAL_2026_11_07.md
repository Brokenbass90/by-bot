# Monthly cents and private rejection capture, local candidate

The owner authorized implementation, tests and review. The working candidate
floors the capped amount to cents and binds the same amount in the prepared
ticket, intent, permit and serialized market order. The historical example
101.413902261 becomes 101.41. Existing nine-decimal intent recovery preserves
the recorded amount and remains one-use. Sub-cent budgets fail before dispatch.

HTTP rejections preserve exact body bytes up to 2,000,000 bytes and the
request ID privately. The reader checks EOF and Content-Length and distinguishes
complete, truncated, incomplete and unavailable captures. The manager records
the file hash and reference in ordinary observations. Exact bytes and identifiers
stay in owner-only files. Transport capture happens before native handlers
consume the exception. A storage failure preserves the original HTTP error.

One independent Astra/high review reported two important findings. Ordinary
request IDs were still included in normal observations, and the handled
STOP422 path could discard the rejection before persistence. Both findings
were reproduced and corrected. A later dependency test found that binding the
capture sink broke the clientless rollback snapshot. The guard and that
regression are included in the final focused pass.

The final 7 Nov test runs passed 171 focused cases and the separate full frozen
rotation through the production CLI (229.60 seconds). The full rotation initially
timed out at the 120-second test limit. The isolated rerun used a 360-second
test timeout with the same code and financial gates. All HTTP used fixtures.

The source dependency manifest and final logs are under
evidence/monthly_cents_capture_20261107. Engineering status is
LOCAL_ENGINEERING_PASS_UNSELECTED. A fresh account and source preflight and a
separately dated owner decision are required before installation or entry.
The original LLY422 reason remains unknown.
