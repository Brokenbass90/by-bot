# KITY critical path — October 16

CURRENT: **`KITY_CRITICAL_PATH_READY`**, physically installed **ORDERS_OFF**.
New monetary policy is prepared but **not authorized or executed**.
This is execution engineering, not KITY strategy/C1–C3 evidence.

## What changed

The actual prior six-leg attempt exposed
`PLANNING_DEFECT: SEQUENTIAL_POST_GO_CRITICAL_PATH_EXCEEDS_ENTRY_DEADLINE`.
Its policy `e3b3f531…54325` remains spent. Its actual final net was
−0.06529398 USDT; all six positions were unwound and accounted. No reset/retry.

The new isolated profile keeps **sequential financial dispatch**, the original
single writer/lock, native Full stops in each entry request, exact ownership,
unknown-send barriers and recovery. It changes only GET scheduling/connections
and the delay between successful entry-cycle steps:

- TLS connection reuse for pinned-origin GETs only; original 2s timeout,
  raw bytes/timestamps, signing, endpoint allowlist and no internal retries.
- Parallel independent per-leg GETs and native/position readback groups.
  Every paginated source retains its own completeness and actual raw pages.
- One fresh all-contract fee response per risk cycle, rather than repeated
  equivalent per-symbol fee requests. Exactly one symbol row is required.
  Independent actual-account comparison matched all ten per-symbol rates.
- Overlap owned order readback with independent risk metadata in the same
  entering cycle. Positions and executable books still run after reconciliation;
  no cross-cycle or post-mutation position/book cache.
- Replace the unconditional 1s pause after entry progress with 10ms; no-progress
  polling remains bounded. Exit/recovery behavior is retained.
- GET pacing remains below official endpoint limits (fees4/s, account
  instruments8/s, aggregate40/s). Initial rate-limit benchmark failures are
  preserved privately; the paced benchmark had no API errors or retries.

Static source/config/ownership work is frozen before GO. Existing fresh account,
instrument, permissions and CTS checks remain; they were not removed for speed.
Batch financial POST was evaluated and rejected for this version: it would
change the existing stop-on-rejection/unknown-send semantics unnecessarily.

## Timings and their limits

| Evidence | Result |
|---|---|
| Actual previous run: GO → owner claim | 2.732s |
| Actual previous run: GO → capture/compile saved | 8.695s, filesystem timestamp |
| Actual previous run: GO → first entry intent | 12.003s |
| Actual previous run: GO → sixth intent / native readback | 56.357s / 61.480s |
| Actual previous run: entry POST acknowledgements | 0.259–0.587s |
| Actual previous run: GET count before unwind | 407 |
| New GET-only transport replay of those 407 requests / 94 original waves | 35.606s; 0 API errors |
| Installed fresh 10-leg account/instrument/depth checks | 10/10 PASS; 10.761s for checks/readback |
| Deterministic 180ms GET, 600ms POST, initial9s model | last entry40.600s; all stops read back43.755s |
| Deterministic 300ms GET, 600ms POST, initial9s model | last entry48.440s; all stops read back52.325s |

The conservative model leaves **11.560s** entry margin under the unchanged60s
window. This is a measured-structure simulation, **not actual ten-leg fills or
a guaranteed worst-case network bound**. API stalls still cause safe refusal or
owned unwind. Native stop creation is part of the guarded entry POST; a separate
protection POST was not present in the prior run. Full-size readback is retained.

One extra check initially used the earlier saved rehearsal plan and correctly
refused GRASS as no longer marketable (9/10 PASS). It was preserved. A single
corrected capture→compile→checks rehearsal ran immediately and passed10/10.
No policy, collar or gate was changed to obtain that result.

## Installed identity and verification

- App: `/opt/bybot-research/kity-micro-owner-20261015/app-post-go-fast-v1`.
- New namespace: `runtime/post-go-fast-20261016`; original history is unchanged.
- Config SHA256: `20b636046603c0b2b98a125f709f6f02290e73ddd5f08c634123de74bf48b168`.
- Unit SHA256: `8795ad7a584030425daf643f9fdec81586a0f6c373a1c7fab317ba1ecafe0b69`.
- 19 installed source pins, original lock inode818853; second lease refused.
- PID2290919, NRestarts0, HEALTHY/ORDERS_OFF at installation.
- Fresh complete flat/open0 before handoff, under the held original lock, after
  installation and after the GET-only rehearsal. Existing15 trading send barriers
  unchanged; **0 new trading POSTs**. Old bybot/web writers remain inhibited.
- Original kit, consumed policy/selection/claim/DB and 47 preserved evidence/wire
  files pinned. Rollback, if installation had failed, could restore only the
  previous KITY orders-OFF owner under fresh flatness, never old bybot/web.
- Existing ATT1/LIQ units unchanged; Alpaca/Claude/research not modified.
- **120 targeted tests PASS**: deadlines, native protection, unknown-send/no
  resend, restart/no reentry, partial recovery, foreign ownership, missing fees,
  full scoped exit and accounting; both deterministic latency profiles.
- Full suite: **5116 PASS / 60 FAIL / 1 warning**. Exact same60 baseline names,
  zero new/removed failures. Full suite **NOT_GREEN**; not described as all-pass.
- Root-only source review; no independent review or reviewer replacement claimed.

## One next personal owner decision

New price-free policy:
`98ae40e5c04754bb7aeea2095f66c7531bc8185051c622684f1364f55a78f3ee`.

Valid only until **October16 21:00UTC / October17 00:00 Cyprus**. No extension,
date transfer, automatic reprepare, retry or reuse of earlier GO.

Unchanged envelope: exact frozen10 symbols/sides; quantities derived by the
existing approved rounding frontier from **one post-GO fresh capture**; gross
≤215 USDT; prices±0.5%; rounding shortfall≤20.3%; immediate all-in exit trigger
15 USDT with accepted execution overshoot; 30-minute owned lifecycle from first
durable entry intent; native stops; no averaging/reentry/retry. Existing60s
post-GO entry deadline includes queue/capture/compilation/custody.

Last GET-only reference gross210.531520 USDT is dated evidence, not the future
price or quantity authorization. Fresh market/account gates may still yield
NO_SEND or partial-basket unwind. Static blocker list is empty.

The human may personally authorize this policy by running **once**:

```bash
bash /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-recovery-20260824/.private/kity_latency_20261016/owner-micro-once.sh
```

Agents must **never execute or schedule that launcher**, `--owner-go-policy` or
GO_POST_GO. Only `bash -n` was run here. Its one-shot local claim makes unknown
command status non-repeatable. After personal execution, inspect the queued
command/actual receipts read-only and let the existing runtime manage to
all-ten/protection and terminal accounting, or safe flat. Never resend unknown
commands, call the launcher twice or create a new policy automatically.

Evidence: `reports/evidence/kity_critical_path_20261016/` contains old per-stage
timings, transport benchmark, fee contract/parity, tests, installed source pins,
new policy and both saved-plan/fresh GET checks. Authenticated raw responses,
keys and private account evidence remain outside Git.

Official source contracts: [fee rates](https://bybit-exchange.github.io/docs/v5/account/fee-rate),
[rate limits](https://bybit-exchange.github.io/docs/v5/rate-limit),
[batch-order semantics](https://bybit-exchange.github.io/docs/v5/order/batch-place).
