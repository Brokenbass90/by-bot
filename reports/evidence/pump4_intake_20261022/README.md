# PUMP4 closed-H1 intake evidence

This is a cursor/cooldown component, not an exchange executor or TINY acceptance.
Frozen b138735/request7b0a961 and the prior fixture manifest are reused; no judge,
outcome or net-profit computation. The seed is historical with zero prospective
credit; the fixture availability clock does not prove actual source timeliness.

- `parity.json`:65available fixture signals/plans +65unchanged restart duplicates;
  one ASTER source remains unavailable. These65 overlap the previous plan proof.
- Two additional **ZRO/BLESS** replay sequences: each parent plus26closed hours,
  repeated process construction and identical duplicate retry on every hour.
  All24cooldown hours suppress signals and every signal/state matches one
  uninterrupted frozen producer.54rows are state checks, not54independent trades.
- `tests.xml`:22new intake cases plus12unchanged plan regressions,34PASS.
  Covers persisted restart, changed duplicate/seed, gaps, open/future clocks,
  invalid OHLC/time/volume, wrong symbol/domain, PF overrides, partial tail and
  a lost fsync response after the complete durable row and an interleaved duplicate
  followed by a newer committed hour. No network permitted.
- Storage is the existing `LifecycleJournal` physical envelope in a **new separate
  per-symbol file**. PUMP4's domain checks reject ATT1 events. There is no
  ATT1 journal access, second financial ledger or production runner here.

Reproduce against the exact existing research input files without changing them:

```sh
.venv/bin/python -B reports/evidence/pump4_intake_20261022/verify.py \
  --research-root /Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28 \
  --output /private/tmp/pump4-intake-exclusive-result.json
```

Output and journal scratch must be exclusive/nonexistent and outside research.
The verifier disables sockets and validates input/source hashes before/after.
Replaying the committed journal after reply loss yields the same decision ID;
a future executor must reconcile those IDs. A `new=False` result alone must
not be used as proof that an exchange order already exists.

Limits: no137-symbol continuous census, authenticated market feed, next-open
fill proof, quantity/minimum-size validation, Bybit order/stop/partial exit,
funding/real fee source, TINY risk grant or financial authorization. Caller clocks
are explicitly unauthenticated. The journal is bounded; size/corruption fails
closed, with no truncation/seed reset. VPS deployment and performance acceptance
are not claimed. No previously accepted Monthly241-suite was rerun here.

One independent astra/high bounded review found one P2 concurrency error; a
named RED→GREEN regression fixes requested-bar identity after locked replay.
Reviewer21initial+1targeted checks overlap root34; no additive test claim.
Runtime model/effort verified from turn_context. See `review.json`.
