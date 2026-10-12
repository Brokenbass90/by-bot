# NET PAPER — actual October12 entry and protection

**ENTRY_PROTECTED_LIFECYCLE_PENDING** at 13:35:36 UTC / 16:35:36 Cyprus.
The original server opener dispatched once within its fixed opening window.
No Codex server/broker mutation, retry, reprice or restart occurred in this check.
Public receipt: `evidence/alpaca_net_paper_20261012/post_attempt_receipt.json`.
Raw authenticated capture is private; its SHA256 is
`da9d9c45e2cbe9fa57f10845e97e85f1a42c8580f1c662d77cebe186823c9403`.

| Actual source | Result |
|---|---|
| NET BUY | 0.325167779 shares, fully filled at $363.20, 13:30:07.506540 UTC |
| Actual principal | $118.1009373328 |
| Native SELL-stop | $329.66, DAY, status `new`, full 0.325167779 shares |
| Stop submitted | 13:30:09.965780 UTC |
| Stop-distance risk | $10.90612730766 before fees and possible gap/slippage |
| Durable ownership | one source attempt / one PAPER intent; phase `PROTECTED` |
| Recovery | two offline restores of actual captured intent return exact receipt; no dispatch |
| Guard | original PID1979385 active, NRestarts0, latest `PAPER_PROTECTED` |
| Opener | completed with exit0, NRestarts0; no restart needed |
| LIVE | flat, no orders, HALTED, cash496.12, published pending/accrued fees0 |

Fresh checks took2993ms, reservation104ms and entry/protection adapter6240ms.
Total first fresh-start to protected completion:9343ms, completed13:30:10.710UTC.
All81 installed app source hashes and packet/manifest identities match Sunday.
Broker entry, FILL activity, native stop, current position, reserved plan,
SQLite intent and native HWM/floor agree on exact IDs, quantity and fill-relative
risk distance33.54. Original reservation reference ask382.20/stop348.66 remains
in history; actual fill363.20 yields frozen-distance stop329.66. No repricing.
CAT liability reserve0.01 was present before sizing; published fee0 now is not
terminal finality for an unclosed position. IEX quote is not NBBO.

The five legacy PAPER holdings ABNB/ABT/AMZN/MA/SCHW remain outside candidate
authority; NET exclusion hash and all three production PIDs/NRestarts unchanged.
Offline recovery uses only the captured existing SQLite row/broker responses:
it proves deterministic restoration, not an actual server process restart.

Guard retained an initial LOCK_BUSY while the opener held the shared lock, then
`PAPER_FOREIGN_ACTIVE_ORDER` at13:30:11.205UTC; it recovered to full protection
at13:30:14.940UTC and remained protected in the captured13:35 source. The raw
failing GET response is unavailable, so the transient's cause is **NOT_PROVEN**.
No foreign NET order exists in the captured broker readback; do not infer an
actual foreign writer or silently remove the earlier log. Entry-to-stop placement
is sequential (about2.46s here), not proof of continuous pre-fill protection.

## Exact remaining lifecycle

If NET remains overnight, actual DAY rearm is **October13 at the next regular
opening**, not October12. The existing guard has scoped unwind no earlier than
October13 13:35UTC /16:35Cyprus and hard end14:00UTC /17:00Cyprus; dates are unchanged.
Read actual stop replacement, owned terminal exit and costs/finality sources.
There is no additional statistical PAPER waiting requirement or new entry.

Full `PAPER_EXECUTION_PASS` and `READY_FOR_LIVE_GO` remain **false** pending those
sources. Prepare the exact fresh LIVE ticker/quantity/risk/protection/ownership/
kill dossier only under the existing contract; LIVE HALT stays until separate
owner GO. Stop-distance risk is not a guarantee of maximum loss through gaps.

After this read-only P0, A7/V1.1 engineering may proceed separately: frozen
feasibility and tests only, original spent Brain run preserved. V1.1 outcome
consumption requires explicit written owner GO and its own sealed source pins.
