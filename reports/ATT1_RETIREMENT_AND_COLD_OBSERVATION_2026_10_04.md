# ATT1 retirement and actual cold observations — October 4

Delivered **running OLD entry retirement and public-only observation**, NEW
orders OFF. This closes the running-process retirement blocker; it does not
settle historical liabilities, complete selected-account integration or prove net
edge. The reproducible source manifest is
`ATT1_RETIREMENT_AND_COLD_OBSERVATION_2026_10_04.json`.

## Runtime change and acceptance

The previous pause and single override key were insufficient under damage:
missing/unreadable override can inherit ENABLE_ATT1_TRADING=1, and damaged native
pause fails open. The existing operator control module now captures the opt-in
`ATT1_ENTRY_RETIRED` once at import, before the deployed core loads dotenv. Unset
or exact0 keeps existing behavior. Present invalid/1 denies only ATT1 entries and
refuses ATT1 resume within that process, even after later environment mutation.
Other sleeves and position management retain their existing semantics.

Installed only `bot/operator_strategy_controls.py`, an exact one-key
ENABLE_ATT1_TRADING=1→0 edit in the existing operator override, and
`/etc/systemd/system/bybot.service.d/99-att1-entry-retired.conf` containing
`Environment=ATT1_ENTRY_RETIRED=1`. Remaining override bytes/risk0.10 preserved.
The systemd EnvironmentFile does not supply that flag; actual new process initial
environment contains1. The existing direct Python ExecStart is preserved.

Fresh signed pre/post account-wide positions0/orders0, intact native pause,
heartbeat inventory0 including entry reservations, old PID exit and one new
service process were checked. PID1623970→**1648585**; running retirement sealed
only after two accepted signed postchecks at **02:38:58.175UTC**. Final signed
**03:06:36UTC** postcheck remains flat/orders0, initial pin1, complete heartbeat
money sleeves[]. Core unchanged at `c8ca2c325884a31521f160e9d690c301b8a58297443f32f3cde395e9c9a699d1`;
executor unchanged at `746a88c4abbf678a087bbc404970066a0d1a429ac2c779215dec507ce0a83c5a`.
Management source remains independent of ENABLE_ATT1_TRADING/operator pause.
Public PID1584802 and web PID1623208 were preserved; Alpaca was not restarted.

The initial postcheck incorrectly compared numeric heartbeat0.1 with string1/10.
Only the assertion was corrected; independently read actual risk/config remained
0.1/0.10. No second money-service restart or automatic rollback occurred.

## Actual quarantine, separate from actual handoff

H1 fence **October4 03:00UTC** follows the accepted retirement clock, not the
October2 pause. At the final observer snapshot: **1/96 common consecutive closed
M5**, fence availability established, quarantine IN_PROGRESS. Earliest96th close
is **11:00UTC /14:00Cyprus**, conditional on complete current bars. This is not a
tiny-live date. OLD watermarks/cooldown remain UNKNOWN.

`scripts/collect_att1_fresh_epoch.py` is installed separately at
`/opt/bybot-research/att1-fresh-epoch-observer-20261004/app`, under a systemd
DynamicUser with ProtectHome/ProtectSystem/NoNewPrivileges. The active timer polls
every180s. State/archive:
`/var/lib/att1-fresh-epoch-observer/observation.json` and `capture_<ms>.json`.
One flock/atomic writer, max256 captures and500MB free-space floor; no archive
deletion. ExecCondition stops further API collection once source-backed
QUARANTINE_OBSERVED is recorded. An old completed snapshot does not become fresh
through repeated timer ticks; later integration still needs fresh signed inputs.

Only fixed GET market/kline M5 and instruments-info for the existing eight
BROKER_ADMISSION_SYMBOLS are available. No keys, private API, broker client,
dispatch, DB/route mutation or promotion authority. Raw source captures and their
hashes are retained. M5/initial-eight endpoints needed a separate narrow adapter:
the existing public runner's H1/Fixed51 request contract was preserved exactly.
Closed bars use start+5minutes and require server/receive availability; open bars
never count. This matches the [Bybit kline definition](https://bybit-exchange.github.io/docs/v5/market/kline).
Gaps reset the contiguous count; incomplete/conflicting/future/stale inputs deny
current maturity. First observed maturity is pinned. This does not establish
Fixed51 engine bootstrap, continuous broker truth or actual handoff readiness.

## Measured remaining inputs

Signed **03:02:54UTC** pass captured all eight real fee rows: taker0.00055,
maker0.0002. SUI passed current one-way input validation. ADA/BTC/DOT/ETH/LTC/SOL
each returned duplicated idx0 over complete pagination and were rejected by the
existing validator. LINK returned1/2/0, retained as MODE_CONFLICT. No deduplication,
last-row selection, mode POST or universe filtering. Six repeated flat idx0
sources now have an exact bounded next engineering question; LINK remains a
separate conflict. HFT is outside this initial eight and previously reported
Closed; it remains in frozen public Fixed51, with no invented fee or trade.

Current funding limits/480minute intervals were captured per symbol. For an
explicit SHORT fixed-notional5USDT scenario, the frozen4032M5 hold is20160minutes;
ceil(20160/480)+1 gives43 settlements including phase reserve. Modelled funding:

| Symbol | Funding stress USDT |
|---|---:|
| ADA | 1.247 |
| BTC | 0.71595 |
| DOT | 0.7095 |
| ETH | 0.71595 |
| LINK | 1.419 |
| LTC | 1.419 |
| SOL | 1.075 |
| SUI | 2.15 |

These are conditional current-limit scenarios, not approved reserves, expected
costs or future ceilings. They omit price-envelope growth and fees/slippage, and
notional5 does not establish min-qty feasibility. Current interval/limit fields
are [Bybit instrument inputs](https://bybit-exchange.github.io/docs/v5/market/instrument).
At the unapproved draft's full R0.4/D0.8, even these5USDT scenarios exceed remaining
daily cash for every initial symbol. Do not increase caps or shorten hold to make
them pass. Smaller risk/quantity requires its own actual min-qty/cost validation.

Current in-process inventory is empty and signed broker exposure is absent, but
local ML sample **ADA id86** is still OPEN with no pnl/fees. No label was rewritten.
All-history intent/finality/cost completeness remains unproven. The six previously
reconciled cash islands remain dated evidence; retirement does not erase unknown
liabilities. Next audit is bounded to this named discrepancy/current cash and the
remaining accepted finality inventory, not an unlimited archive search.

## Production/research boundaries

Authenticated **02:55:13UTC** Alpaca: same AMD0.186377282 /CRWD0.469970151 /
META0.141939508; HWM/floor artifact exactly unchanged,58hashes match, one NEW send
manager cron, OLD processes absent, cap487.42/gross0.70. **0 open orders/stops**
after DAY expiry, no weekend broker protection claimed. Oct5 **13:30UTC /
16:30Cyprus** re-arm remains P0/NOT_DUE; queued next-session PAPER acceptance
NOT_PROVEN. No Alpaca change/order/restart.

Public same snapshot: **6sessions /34records /2filled simulations /4nonfills /
2RECOVERY_GAP /0clean /0held**, broker/ordercalls0, same epoch/profile/2s threshold.
New SUI gap says rejected future/stale book; its full24minute lifecycle interval
is not a measured request budget. Preserve all receipts; no clean/net-R claim or
new timing fix without retained source-age attribution. No research ref merge,
judge/holdout rerun or Factory start; Claude remains research owner. October3
KITY/TOLPA registry facts were not rechecked this cycle.

## Verification and next gate

Local targeted **97PASS**; isolated VPS Python3.12 **13 guard PASS** plus exact-core
entry denial before engine, **15 observer PASS**. One bounded6-astra/high critical
review and targeted fix check; actual turn_context model/effort verified by primary.
Scope limits are the unresolved financial inputs above.

Final full suite **3440PASS /58FAIL**.57 match October3 baseline; the additional
Alpaca PAPER node `[False-False]` reproduces with the unchanged HEAD control module
on today's clock. No unexpected added regression established; suite is not green.
The foreign allowlist journal's original SHA
`add587f1bd7059c2c706f1f7c604e36c2fb7b36b258b127e01fcd2101d3f19a1`
was restored after append-only watcher side effects and remains unstaged. Old
receipt oracle was not rerun; strategy/coordinator/public source pins unchanged.

Next: collect96 actual bars; reviewed duplicate-position-source handling and LINK
eligibility; source-bound viable funding/quantity policy; bounded ADA86/current
cash/finality reconciliation; selected-account protection/exit/cost recovery
integration ordersOFF. Then actual packet +2–3 clean prospective filled terminals
with terminal net-R + fresh OLD absolute-risk comparison/exclusive dossier +
separate owner money GO. Retirement and quarantine are never that GO.

## Runbook and rollback

Read-only: `systemctl show bybot -p MainPID`, `systemctl status
att1-fresh-epoch-observer.timer`, and the observer state/private retirement receipt
at `/root/by-bot/runtime/att1_fresh_epoch_20261004/retirement_receipt.json`.
Private signed pages, acceptance scripts and rollback backups are under that
runtime folder; source hashes are in the public JSON receipt. Reconcile broker
positions/open orders with the existing signed GET collector before integration.

Observer rollback: stop/disable only `att1-fresh-epoch-observer.timer`; preserve
StateDirectory/captures and existing public journal. OLD rollback keeps native
pause, ENABLE_ATT1_TRADING=0 and service retirement flag1. **Do not restore the
backup override's1, remove the pin or restart legacy entry authority automatically.**
If late exposure/order appears, invalidate flat acceptance and preserve its owning
manager. No NEW order path is installed. Do not run initial Alpaca activation.
