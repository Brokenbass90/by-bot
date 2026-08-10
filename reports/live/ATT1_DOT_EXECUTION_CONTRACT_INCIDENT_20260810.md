# ATT1 DOT execution-contract incident

Status: confirmed; position still protected; corrective patch tested locally but
not deployed while broker exposure remains open.

## Broker-grounded facts

- strategy: `att1_trendline_touch`, DOTUSDT short;
- signal/request entry: `0.8136`; stop: `0.8205`; requested qty: `66`;
- broker fill: `0.8023` at 2026-08-10 15:55:15 UTC;
- planned TP1: `0.805391`; fill was already beyond TP1 for a short;
- planned stop risk: `$0.4554`; actual fill-to-stop risk: `$1.2012`;
- risk expansion: `2.6377x`; adverse entry drift: `138.89 bps`;
- runner immediately labelled TP1 and closed `36.3` at `0.8025`;
- broker closed-PnL receipt: `-$0.03929984`, including recorded open/close fees;
- read-only broker check at 2026-08-10 18:34 UTC: remainder `29.7`, broker stop
  `0.8205`, no broker TP, service active.

This is not a normal losing setup. The completed-candle signal was stale versus
the current execution price. A fill beyond an existing target invalidates the
trade contract and must be treated as a missed entry.

## Corrective contract

`assess_entry_risk` now rejects all entry paths, not only maker paths, when:

1. the actual/current price has crossed any planned target;
2. fill-to-stop risk expands above `1.20x`;
3. adverse drift exceeds `25 bps`;
4. stop geometry is crossed or invalid.

The check runs before ATT1 order submission using current websocket price and
again after the broker fill. A fail-close fill cannot fall through into runner
TP handling. Focused suite: 50 tests passed, including the exact DOT geometry.

## Release gate

No monolith restart while any broker position exists. After flat:

1. build committed atomic bundle including `smart_pump_reversal_bot.py` and
   `bot/maker_execution.py`;
2. verify manifest and imports with server Python outside live root;
3. bounded no-order startup smoke;
4. three direct broker-flat checks;
5. atomic apply with backup/rollback receipt;
6. verify service, heartbeat, authority, broker and file hashes.

The current DOT event is excluded from the future clean ATT1 promotion cohort.
