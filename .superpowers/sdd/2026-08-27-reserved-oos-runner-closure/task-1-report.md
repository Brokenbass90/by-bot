# Task 1 report — reserved M5 identity materializer

Status: DONE

## Scope delivered

- Added `scripts/materialize_att1_sbr1_reserved_m5_v1.py`.
- Added focused synthetic tests in `tests/test_materialize_att1_sbr1_reserved_m5_v1.py`.
- Left preflight, runner, audit, live configuration, broker/order paths, and money authority unchanged.

## Contract evidence

- The materializer derives the universe from the frozen live-native candidate
  manifest and rejects any order/content drift from the required major-8.
- The sole fetch path is the public Bybit linear M5 endpoint and is reachable
  only after `--allow-reserved-public-network`; no environment, private API,
  broker, order, signal, trade, return, or performance path is imported.
- Each payload is atomically persisted only after exact-window validation:
  78,624 ordered, unique, contiguous M5 rows; exact first/last timestamps;
  finite positive OHLC; high/low consistency; and conflicting duplicate
  rejection during pagination.
- Valid existing payloads are independently revalidated and reused without a
  fetch acknowledgement or network call. Corrupt/drifted payloads fail closed
  unless acknowledgement permits a public refetch.
- The input manifest is written atomically only after every frozen payload is
  valid. Its input rows have exactly the preflight-required identity fields;
  it contains no prices or performance fields and explicitly records zero
  preflight decoding, no performance computation, and no money authority.

## TDD evidence

The focused test module was first run before the implementation existed and
failed at collection with `ModuleNotFoundError` for the new materializer. The
first green run exposed an incorrect end timestamp constant; it was corrected
to the exact 273-day boundary. The final focused run passed.

## Verification

Executed from the repository root using the available project Python runtime:

```text
/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.venv/bin/python -m py_compile scripts/materialize_att1_sbr1_reserved_m5_v1.py
/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/.venv/bin/python -m pytest -q tests/test_materialize_att1_sbr1_reserved_m5_v1.py tests/test_att1_sbr1_reserved_oos_preflight.py
...............                                                          [100%]
15 passed in 7.90s
git diff --check
```

No real reserved data was fetched or opened. No network command was run.

## Concerns

- The system Python does not have pytest installed; verification used the
  already-present sibling project virtual environment. This is an execution
  environment constraint, not an implementation dependency.

## Review fix round 1

- Reuse now requires the exact payload top-level key set and exact record key
  set, before checksum/row validation. Extra private, trade, or performance
  fields therefore fail closed even if an attacker recomputes `records_sha256`.
- Production CLI accepts only the explicit public-network acknowledgement and
  always uses the fixed output, manifest, and frozen-candidate paths. It
  rejects containment escapes and any existing symlink in a fixed path's
  ancestor chain; function-level path injection remains available for
  synthetic temporary-directory tests only.
- The manifest is deterministic (no volatile generation timestamp). When all
  payloads validate and its exact canonical bytes already match, reuse does
  not rewrite it. A drifted manifest without a new acknowledged materialization
  fails closed.
- Epoch bounds are derived from the explicit UTC strings and regression-tested
  against the hand-checked millisecond values.

Additional verification after this fix round:

```text
19 passed in 9.90s
```

## Review fix round 2

- `fetch_m5` now independently requires the explicit
  `--allow-reserved-public-network` acknowledgement before it can invoke its
  public GET dependency. `materialize` passes that acknowledgement only after
  its own guard; injected synthetic fetchers keep their existing clean
  function signature.
- A direct primitive-call regression test proves the refusal occurs with zero
  injected GET calls.

Additional verification after this fix round:

```text
20 passed in 10.16s
```
