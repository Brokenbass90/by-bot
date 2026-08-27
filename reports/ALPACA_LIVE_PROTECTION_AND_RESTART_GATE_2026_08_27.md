# Alpaca live protection and entry-restart gate

Read-only snapshot: **2026-08-27 09:43 UTC**. No orders, positions, services,
configuration, or risk were changed by this audit.

## Broker truth

- account: LIVE / ACTIVE;
- equity: `$487.62`; cash: `$452.33`;
- position: `ABBV`, quantity `0.135734866`, entry `247.55`, observed price
  `259.99`, unrealized P&L about `+$1.69`;
- protection: one broker-side sell stop for the full quantity at `257.65`,
  status `new`, TIF `DAY`, created `2026-08-26 20:30:31 UTC`;
- new buys: blocked by effective `SAFE_HOLD` (`allow_new_entries=false`).

The floor at `257.65` is approximately `+$1.37` gross relative to ABBV entry if
filled exactly. It is a trigger, not a guaranteed execution price.

## The pseudo-trailing is dynamic

This is a software high-water-mark ratchet plus a broker fixed stop, not Alpaca
native trailing for the current fractional shares.

SCHW broker history shows the ratchet:

```text
108.20 -> 109.16 -> 109.52 -> 110.04 -> 110.52
```

The `110.52` trigger was rearmed after the session and the position later filled
at `108.00` on an adverse gap. The exit was still about `+$3.64` gross versus
entry, but gave up roughly `$1.42` relative to the trigger. ABBV's accepted floor
moved from `257.37` to `257.65`; its persisted high-water mark was `267.00`.

The ratchet target is the maximum of the current accepted stop, persisted floor,
HWM minus the configured trail, and minimum entry-profit floor. It is monotonic,
capped below the current market, and ignores sub-threshold raises. The bridge
must not rearm below the persisted accepted floor.

## Night and session semantics

Fractional positions use `DAY`, not `GTC`. The stop is a real broker-side order
during the supported session, but it cannot execute overnight. The bridge re-arms
a new DAY stop from the persisted monotonic floor after normal expiry. Repeated
nightly re-arms preserved the raised SCHW/ABBV floors, so the old reset-to-entry
defect is not recurring.

Residual risks remain:

- an overnight gap can fill below the trigger;
- a server, schedule, authentication, or broker failure can prevent rearm;
- fractional shares cannot obtain the same persistence as a whole-share GTC
  profile;
- one profitable protected exit proves the plumbing, not selector expectancy.

The deterministic auditor currently reports the fractional DAY limitation as a
warning while requiring full-quantity broker protection and a preserved floor.

## Exact gates before restarting entries

1. **Choose and freeze one selector.** The live v38 month-end list is stale from
   July, while the current adaptive shadow independently selected
   `BAC/SCHW/TGT/ABT`. Mixing them would make the prospective result uninterpretable.
2. **Fresh month-end manifest.** Pin candidates, source timestamps/hashes,
   universe, PIT limitations and decision configuration before the next cycle.
3. **Complete prospective paper lifecycle.** Record actual fill, full-quantity
   stop acceptance, 15-minute ratchet, nightly rearm, restart recovery, partial
   fill/quantity change, and final exit in one reconciled receipt.
4. **Gap and cost stress.** Replay trigger-to-fill gaps and at least the declared
   5/10 bps cost cases; a stop-price backtest alone is insufficient.
5. **Choose fractional DAY or whole-share GTC.** The default-off whole-share paper
   profile is useful, but native trailing remains off until the lifecycle passes.
   The current four-name adaptive basket mechanically needs about `$1,233.14` to
   buy one share of each, but this number changes with the selected basket and is
   not a profitability gate.
6. **Evidence scope.** Check XNYS calendar, corporate actions, delistings,
   concentration and remaining PIT limitations. A one-slot micro-canary may accept
   explicitly documented residual PIT risk; full promotion may not.
7. **Deployment parity.** The current deployed protection snapshot matches its
   deployed manifest and is healthy, but canonical HEAD has newer bridge/launcher
   bytes. Test the exact next release, verify complete dependencies on the VPS,
   reconcile broker/account truth, and require no CRITICAL health finding.
8. **Separate owner release.** Only then may one bounded new-entry slot leave
   `SAFE_HOLD`; capital or full rotation does not unlock automatically.

Focused audit tests: `64 passed`. This supports the protection implementation,
not the return forecast.
