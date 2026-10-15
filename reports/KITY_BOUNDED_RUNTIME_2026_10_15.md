# KITY bounded single-writer runtime — October 15

**KITY_EXECUTION_MICRO_LIVE_READY / ORDERS OFF / MONEY GO PENDING.**
Direct owner parameter reply `call_fae5497f3ccc42b391a1df63a4809274` approves
±0.5%, ten minutes and binding to the existing writer. It is not monetary GO.
No additional research/PAPER/statistical gate.

## Actual installed state

Versioned app `/opt/bybot-research/kity-micro-owner-20261015/app-v2-bounded`.
Config `runtime/config-v2-bounded.json`, SHA256 `36f3d72e9ee55b8561e6b0429ec827dc5f5ad827969486604a04f587a452269f`.
Current `kity-execution-micro-owner.service` PID **2186777**,
active, NRestarts **0**, mode **ORDERS_OFF**. Same original account-lock inode
**818853**; second lease rejected. **16** deployed source hashes verify.
Original app-v1-2, config, GO, plan and SQLite remain untouched. Their four exact
pins are in the sanitized packet. The predecessor `ffeb…6570` stays terminal
NO_SEND; it is not reused. No automatic rollback to old bybot/web writers.

Upgrade performed only after authenticated flat/open/recent-history/execution
zero before stop, under the original lock after stop, and again after startup.
Exactly the current KITY unit was changed. Root cron, ATT1/LIQ PIDs/NRestarts,
old bybot/web inhibition and guard sources unchanged. No Alpaca unit, source,
position or stop mutation. Successful installation receipt SHA256
`9fdf60a8b815f0236ad2ea4c03fc64ab2f6d30f6978c3177b83cd73a1e8f6edc`. Trading POST barriers remain **0**.
No new monetary GO, selection or actual experiment journal exists.

## Real account rehearsal

One PREPARE and one GET-only rehearsal through the installed daemon:
commands `1792077597739127900` / `1792077612379710108`.
All **10/10** real per-leg preflights PASS with POST inhibited;
STATIC **[]**, FRESH_ONLY **[]**. Each attempted no-send call was rejected by
missing monetary authority before wire I/O. Throwaway test journal was removed;
the actual legacy/new experiment journals were not created or altered by it.

**239 targeted tests PASS**, including V1 compatibility, signed synthetic venue
10-entry/native-stop/readback/restart/30-minute unwind and actual cash finality
via V2. Full repository suite not run; independent-review quota restriction
retained, root-only review. Author self-review added a test/fix for rejecting
binding into the original or wrong experiment store before any journal write.
Only a three-line reducer dispatch hook changes the shared V1 journal module;
its default reducer stays unchanged. The old installed package is immutable.

## Exact bounded proposal

Intent `7aa4504da8268b16e61e316b5d64e81988e8a07b2c4686c21d7960d465c145cd`.
Expires **2026-10-15T18:30:11.877000+03:00** (**2026-10-15T15:30:11.877000+00:00**).
Reference gross **208.450500 USDT**, fresh rehearsal gross
**208.473730**. Sum at every band upper price
**209.494960 < 215 USDT**.
These are dated sources; future fills/fees/gaps are not guaranteed by them.

Saved reference account sources show REGULAR_MARGIN and trading permissions.
Estimated current-price entry/exit fees **0.21824180675 USDT**, fully funded
reference **208.66874180675**, approximate initial margin **30.171920** (not an
exchange-certified margin requirement). The reference 30-minute funding-limit
scenario is zero because of that dated settlement window; actual funding is
not assumed zero. The new GO capture recalculates these sources before entry.
Closing read-only custody check confirms PID2186777/NRestarts0,16pins,0POST,
same lock and retained predecessor; receipt is
`evidence/kity_pricing_intent_20261015/closing_readonly_verification.json`.

| Symbol | Side | Fixed quantity | Lower IOC band | Upper IOC band |
| --- | --- | --- | --- | --- |
| BTWUSDT | Buy | 10 | 1.89156 | 1.91056 |
| XAUUSDT | Buy | 0.005 | 4143.96 | 4185.60 |
| LTCUSDT | Buy | 0.3 | 59.81 | 60.41 |
| VVVUSDT | Buy | 0.88 | 24.5720 | 24.8180 |
| BNBUSDT | Buy | 0.03 | 727.66 | 734.96 |
| XAUTUSDT | Sell | 0.005 | 4130.51 | 4172.01 |
| XPLUSDT | Sell | 259 | 0.08403 | 0.08487 |
| XAGUSDT | Sell | 0.382 | 57.01 | 57.57 |
| GRASSUSDT | Sell | 32 | 0.67080 | 0.67740 |
| SPCXUSDT | Sell | 0.14 | 148.09 | 149.57 |

Quantities are sized once at the fresh reference dossier and remain fixed
within this intent. They are not a reuse of old stale `ffeb…6570` order prices
or quantities. Native SLs are recomputed once after actual GO using new actual
fee/funding/depth sources and the unchanged $15 allocation rule. No repricing
after the derived executable plan is frozen.

Existing money limits: **215 gross / 15 immediate all-in exit trigger /
30 minutes from first durable entry intent / 20.3% reference floor shortfall**.
Owner accepts possible final loss overshoot from gap/slippage/exchange failure.
Native protection, scoped unwind and actual accounting remain required.
No averaging, scaling or re-entry; separate EXECUTION_MICRO_LIVE ledger;
not KITY/C1–C3/edge evidence. No new research or monetary authority for Brain.

The exact pending literal GO is:

`GO KITY_EXECUTION_MICRO_INTENT_V2 7aa4504da8268b16e61e316b5d64e81988e8a07b2c4686c21d7960d465c145cd`

If it arrives after expiry, fail closed. Never reuse/extend this intent or
transfer that GO to another capture/day. A fresh proposal would need a new hash
and separate GO. No timer or repeat was added.

## Runtime/recovery and operator path

The existing one physical process is still the only holder of account.lock
and authenticated POST path. It reads/replays the old SQLite with `mode=ro`.
Before actual capture, exact intent GO publishes `selected-v2.json` and an
exclusive claim. One new store: `runtime/experiments-v2/<intent_id>`; no overwrite
of V1. Crash after claim never repeats capture/materialization. A selected
active plan with a missing journal BLOCKS; it cannot become a fresh experiment.

Only after literal GO, fresh capture, source/hash replay and existing gates does
the physical owner bind the derived plan. Stored GO retains the actual human
intent text; no fictitious plan GO is written. The legacy bridge's exact-plan
string is only its internal action token after this physical authorization.
Expiry is checked before/after fresh entry validation and immediately before
POST. It never disables owned exits/protection or resets the 30-minute deadline.

If expiry intervenes after durable intent but before POST, `LOCAL_NOT_SENT`
requires absence of the persisted wire barrier and an immutable proof. It does
not invent a broker order/rejection. If a send barrier exists, the result stays
UNKNOWN/reconcile-only; no resend. Restart can close proven no-wire intent but
never reinterpret possible wire I/O as a safe zero.

After an actual direct human GO, preserve its reply provenance, then queue
exactly one `GO_BOUNDED` command on the same installed module/config:

```json
{"kind":"GO_BOUNDED","intent_id":"7aa4504da8268b16e61e316b5d64e81988e8a07b2c4686c21d7960d465c145cd","exact_go":"GO KITY_EXECUTION_MICRO_INTENT_V2 7aa4504da8268b16e61e316b5d64e81988e8a07b2c4686c21d7960d465c145cd"}
```

Do not queue it merely because this runbook contains the text. Use the unit's
installed module `research_lab.kity_micro_bounded_owner_v2` with the config/hash
above. `PREPARE_BOUNDED`, `REHEARSE_BOUNDED`, and scoped `KILL` are the other
bounded commands. Old PREPARE/GO are rejected by V2. No independent sender.

**Rollback:** use only this version's explicit `--rollback` operator path,
never legacy `kity_micro_handoff_v1 --action rollback` for a selected V2 test.
The V2 path first fences entries, resolves the selected journal, requires
terminal/no-uncertain exposure plus actual fresh flat readbacks, stops the
current owner, reacquires the original lock and rechecks before restoring any
legacy authority. No such rollback was executed. Watchdog has no restart/order
or rollback authority.

Sanitized full packet: `evidence/kity_pricing_intent_20261015/physical_owner_packet_v2.json`.
Original local-only preparation and its expired replay remain dated history.
