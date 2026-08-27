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
