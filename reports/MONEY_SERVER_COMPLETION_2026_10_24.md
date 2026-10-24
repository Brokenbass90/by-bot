# 24 October — Monthly ready for personal arming; PUMP DATA running

Monthly's fee blocker is closed. The new v4 candidate is installed disabled and
independently verified. PUMP4's persistent DATA intake is installed and scheduled
hourly on the VPS. Neither strategy has been given a new executable financial GO
by the agent; no broker write occurred.

## Monthly — completed operational candidate

Owner-approved terms remain capital $400, gross $280, restricted reserve $40,
maximum four positions/single entry $168, aggregate loss admission $8. Frozen
selection, weights and monthly calendar stay unchanged. The loss latch inhibits
new entries; it is not liquidation or a guaranteed maximum loss.

The owner explicitly asked not to stall on delayed fees. An opt-in policy is now
bound to the exact scope and immutable book snapshot:
`ALPACA_MONTHLY_PENDING_ACCOUNT_RESERVE_V1`. Modelled unposted fees **plus** all
reported account pending liabilities must fit inside the existing $40 reserve.
They may overlap or be disjoint; no overlap is assumed. Reported liabilities
also reduce the conservative Monthly admission lower bound. They are not booked
as actual Monthly PnL, attributed to NET, refunded or debited from cash twice.
Old scopes without this opt-in keep rejecting an unclassified liability.
Unknown/foreign fills, incomplete fee provenance, stale source and book/scope
conflicts still reject. Crossing the existing loss boundary can block entries
earlier under this conservative buffer. Cost finality remains a separate fact.

A saved actual capture with pending $0.02 now passes provisional classification.
Fresh installation GET then independently observed **pending 0, cash $496.31,
no positions/open orders**, and $0.03 published legacy fees. Thus we did not have
to rely on an assumption that the earlier $0.02 was a broker lag. No final NET
net-profit claim is made from this handoff receipt.

**257 local and the same 257 VPS tests PASS**, 53 source files/40 imports,
zero fallback/skip/error; real network denied. Ten local operational-helper
checks also pass. One bounded independent astra/high static review found no
critical/important defect; reviewer model/effort verified from runtime metadata.
[Local](evidence/money_server_completion_20261024/monthly-local-acceptance.json),
[VPS](evidence/money_server_completion_20261024/monthly-vps-acceptance.json),
[saved actual replay](evidence/money_server_completion_20261024/monthly-saved-actual-replay.json),
[review](evidence/money_server_completion_20261024/review.json).

Installed candidate:
`/opt/bybot-research/alpaca-monthly-e2e-20261018/candidate-dcaafa089ff8f81f-t32a6a356`.
Material `dcaafa089ff8f81ffb55caaa426503ae27df68cf167e32484fe3f47d50ca9200`.
Scope `aadf1055090d40f01ee09469be7d37578e3d31ae9cce61f42d6845fe2e9cff2d`.
Spec `f3447a2856a68ad9609fa3db3141b70d8fddc9250c1ddf82430c3476385a8dbb`.
Original lock813893, legacy HALT and64 old static pins are unchanged. Old NET
and SHOP schedules remain inactive. Monthly timer is **disabled/inactive**;
no owner-go.json. Only its exact inactive service fragment was rebound.
[Installation](evidence/money_server_completion_20261024/monthly-installation.json),
[independent readback](evidence/money_server_completion_20261024/monthly-independent-readback.json).

Integration incident retained: the first install reached disabled-fragment
replacement but could not publish its receipt because the new runtime parent
had not been created. No GO/timer enable or broker write occurred. The empty
parent was prepared, staging now includes it, and the same pinned/idempotent
helper completed with fresh checks and independent readback. No signed code
was silently altered to recover this failure.

Human-only command is prepared in
`.private/money_completion_20261024_v4/owner-monthly-activate.sh`; instructions in
`OWNER_README.txt` in that directory. The agent did **not** execute it. It creates
the exact scope GO and enables the installed timer, with fresh read-only checks.
Budget approval is already recorded; no repeated budget permission is requested.
If the command result is ambiguous, reconcile before any retry. Older activation
commands are superseded by the v4 source/scope, not reset or reused.

Remaining future gates are actual completed **30Oct** selection and fresh
**2Nov14:30UTC /16:30Cyprus** source/account/cash/native-protection checks. Scope
ends1Feb2027 00UTC. Saturday arming does not authorize an off-calendar purchase;
CASH/NO_SEND remains valid. Rollback inhibits new entries while retaining sole
custody of existing/uncertain exposure. Never re-enable NET/SHOP or erase GO,
claims, journals, HALT or a loss latch to recover.

## PUMP4 — actual persistent server DATA, financial dispatch still open

`pump4_supervisor_v1.py` and `run_pump4_supervisor_v1.py` reuse existing exact137
public collector, immutable source archives, `Pump4Intake`, `causal_plan`, sizing,
account-owner/custody APIs and notification-once helper. They persist per-symbol
epoch/cursor, catch up missed hours in order and reject changed overlap, gaps,
missing epoch/hash/coverage drift. Bootstrap/replay never becomes prospective.
DATA uses its own lock; it never loads a credential profile or claims account.lock.
The selected bridge resumes admitted custody before consulting new candidate
inputs. New entry cannot supply a caller-built plan instead of causal replay.
The final crash-before-alert-claim regression was reproduced and fixed by
replaying the durable receipt through the existing notification helper. The
helper's ambiguous-delivery/no-blind-retry limitation remains explicit.

**213 local and the same213 VPS PASS**, 91 packaged files/38 imports,
41 memory receipts, zero errors/skips/fallback, network denied. One intermediate
package omitted a late-imported pinned notification module; exact acceptance
failed, the packaging closure was fixed, and a new immutable candidate passed.
The failed package remains unselected. [Local](evidence/money_server_completion_20261024/pump-local-acceptance.json),
[VPS](evidence/money_server_completion_20261024/pump-vps-acceptance.json).

Candidate `candidate-9c6901a65a66e035` under
`/opt/bybot-research/pump4-server-orders-off-20261023`, material
`9c6901a65a66e035f24e13ab3b96bc6734fb89d75f87ec45950ad63ac302e522`.
First actual cycle completed: **136/137 source intake PASS, HFTUSDT explicitly
UNAVAILABLE**, zero prospective credits/private requests/order writes. No
universe substitution. Full historical bootstrap is not an executable fresh
entry. It took minutes under CPU quota; it does not prove≤60s live admission.

Actual deployment is a persistent-state **hourly oneshot service+timer**,
`pump4-data-supervisor.timer` enabled/active, next13:00:02UTC at readback.
The long polling prototype was stopped only after its immutable first cycle,
then replaced with hourly scheduling, 900s timeout and3GiB free-space precheck.
No source files were changed for this scheduling adjustment. Source archives
are retained, no cleanup or collector epoch reset. Unit hardening denies access
to original credential configs and KITY runtime. No Telegram sender is yet
bound to the DATA CLI; callback behavior is only fixture-tested, not claimed
as delivered production alarms. [Actual DATA installation](evidence/money_server_completion_20261024/pump-data-installation.json).

Original KITY owner remains active, PID2825351, original config SHA
ff249e081eb9e07d7e482615c440786e550332ff17c2de5b35572af89c2047ef,
lock818853. PID differed from the older receipt2734312; read-only check established
its current invocation began24Oct06:08:54UTC, NRestarts0, same original config/lock.
Cause of that earlier invocation change was not inferred; this deployment did
not restart/stop/select it. `pump4-execution-owner.service` remains absent.
[Final unit readback](evidence/money_server_completion_20261024/final-unit-readback.json).

**Next execution gate:** trusted fresh per-signal/account provider and actual
original-owner physical handoff/inhibitors/rollback, financial alert binding,
then complete cost/funding/lot/risk TINY packet and exact owner GO. The CLI
`--dispatch` deliberately rejects before credentials/lease. No TINY_READY or
profit claim. Proposed50allocation/30gross/R1/day2/week3/DD6 remains proposal.
Monthly fees are not a dependency of this gate.

## Published Polymarket/KITY intake — no blind merge

Verified research ref `0c91b9ad2d867c7ae04a172245e9b2cdc3c9b639` and read the
published documents. [Intake receipt](evidence/money_server_completion_20261024/research-intake.json).
Polymarket NO history's binding date-cluster test remains **INCONCLUSIVE**;
fair-price measurements point to a forward shadow experiment, not economic
LIVE clearance. Live NO quotes/depth/fees and official resolution remain relevant.
No judge/outcome opening, research code/Claude-map edits or wallet activity.
KITY C1/C2/dossier readiness does not close weekly d+7 execution/funding/C3/money
approval. The DOSIE still contains the old8-leg/$800 template; the published
versioned path explicitly corrects it to CAP300/10legs. Do not execute the stale
fields. Economic result remains INCONCLUSIVE; the old micro GO stays spent.

Queue remains Monthly personal arm/runtime gates → PUMP financial integration
→ Polymarket execution/data intake → KITY weekly executor. Safe published-data
intake can proceed independently. No new framework or blind research merge.
