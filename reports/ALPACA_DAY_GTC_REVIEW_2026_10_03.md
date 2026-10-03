# Alpaca protection lifecycle — bounded review, October 3

Verdict: **GTC is unsupported for the three current fractional positions.**
No LIVE code, config, manager, quantity or order was changed. The dynamic
HWM/floor mechanism already exists; its broker order lifetime is the limitation.

Authenticated read-only capture **06:50:32 UTC /09:50:32 Cyprus** confirmed AMD
0.186377282, CRWD0.469970151, META0.141939508, market closed, zero open orders /
stops, unchanged deployed source manifest and no OLD manager processes. There
is one intended `--send-orders` cron, every5 minutes on weekdays. Next broker
regular open: **October5 13:30UTC /16:30Cyprus**. Current HWM/floors remain
AMD644.811/622.24, CRWD273.335/242.13, META736.33/668.76. No current overnight /
weekend stop coverage is claimed.

## Why DAY is selected

[Alpaca fractional order support](https://docs.alpaca.markets/us/docs/fractional-trading)
allows fractional market, limit, stop and stop-limit with DAY. Its supported
fractional types do not include trailing stop. This is a quantity/order-support
constraint, not a paid-data subscription limitation. Changing `DAY` to `GTC`
for these exact holdings would violate the documented order matrix.

The intended bridge already enforces the matrix:
`scripts/equities_alpaca_paper_bridge.py:1311` selects DAY for fractional quantity,
GTC for whole shares. Restart retains the accepted floor. Re-arm at1478 uses
remaining broker quantity, preserved floor and accepted-order readback.
`scripts/alpaca_protective_exit_manager.py:172` retains HWM and accepted floor
for the same entry lifecycle; its replacements only raise the stop. Existing
cancel/replace and recovery paths still need broker confirmation, not just local
state. This review does not prove continuously accepted initial protection.

## Operational consequence and recommendation

The top-level intended runner returns while the broker clock is closed
(`scripts/alpaca_adaptive_paper.py:907`). Therefore DAY expiry is expected and
Monday protection relies on the next open manager cycle. That dependency leaves
an additional re-arm window; calling the current setup permanently broker-protected
would be wrong. Monotonic local floors do not constitute an active broker stop.

[Alpaca order handling](https://docs.alpaca.markets/us/docs/orders-at-alpaca)
describes next-trading-day queueing for orders submitted after close. Stop and
trailing-stop protection cannot be treated as an off-hours execution guarantee;
extended-hours eligibility requires limit orders, and triggered stops can fill
away from the stop price.

Recommended next bounded candidate: **prepare the next-session DAY protection
before regular open**, retaining exact quantity/floor and one owner. First prove
fractional STOP queue acceptance in PAPER, status handling, duplicate prevention,
late fills, restart and floor-breach behavior; only then propose a reviewed LIVE
cutover. No such PAPER order or deployment occurred here. Broker acceptance for
this exact fractional queued-stop path is **NOT_PROVEN**; documentation alone
does not establish it. Do not bypass the runner's closed-clock guard by hand.

Whole-share GTC/native trailing would require a separately accepted execution /
sizing contract. We do not increase capital, round quantities up, replace the
frozen stop rules or add another manager to force compatibility.

Fresh relevant offline tests:49PASS (protective manager, intended runner, stop exit,
restart integration). These do not establish Monday broker re-arm acceptance.
Private source inventory: `.private/alpaca_day_gtc_oct3/inventory.json`.
Authenticated capture: `.private/fresh_handoff_20261003/live_snapshot.json`, SHA256
`22f4ac88a25bfb8e1b1e7b37cc35cef7c5190b35e3af7d007842d3a52ab1f5d6`.
