# ATT1/SBR1 fixed-51 shadow status — 2026-08-27

Direct read-only VPS snapshot; no order or service mutation.

- both systemd timers are active/waiting and their last services exited `0`;
- `ATT1`: 3,111 journal rows, 3,005 raw decisions, 17 raw signals, **0 admitted**,
  0 final-N eligible, 0 money/order authority;
- `SBR1`: 3,569 rows, 3,427 evaluations, 1 raw signal (`CRVUSDT`), **0 admitted**,
  0 money/order authority;
- the current BTC causal state in the latest rows is `above_band`, so ATT1 short
  raw signals correctly remain regime-ineligible; SBR1's fixed-51 extra symbols
  are still preparity evidence and cannot silently enter final N.

There were 45 ATT1 replay-row mismatch errors on eight symbols from Aug 24 through
Aug 25 18:00 UTC; none appeared in later copied rows through Aug 27. SBR1 recorded
five public fetch errors and one initial missed-window batch. These are retained in
the journal rather than erased. The ATT1 mismatch needs a deterministic recurrence
alert and root-cause receipt before final-N evidence is declared clean, even though
the latest timer cycles are successful.

Conclusion: the broad shadows are alive and have observed signals, but there has
not yet been a qualifying shadow "trade" or closed prospective decision. This is
not evidence that the strategies are blocked globally; it is evidence that the
current decisions did not pass the frozen admission/evidence role.
