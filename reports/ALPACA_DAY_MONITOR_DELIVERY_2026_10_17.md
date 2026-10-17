# NET DAY monitoring — operational delivery, October17

CURRENT: **ALPACA_NET_DAY_MONITOR_ACTIVE_GET_ONLY**. This closes the recurring
source/schedule/Telegram wiring left pending at e715374. Monthly V3, entry HALT,
current NET protection policy and its existing manager are unchanged.

## Installed and independently read back

- Separate root `/opt/bybot-research/alpaca-net-day-monitor-20261017`.
- `alpaca-net-day-monitor.service`: oneshot GET observer; last execution
  Result=success/exit0. Inactive between timer ticks is expected.
- `alpaca-net-day-monitor.timer`: enabled, active/waiting. Next calendar
  execution **October19 13:30 UTC /16:30 Cyprus**, then every minute in RTH.
- Calendar expressions use `America/New_York`, not a fixed UTC offset. Broker
  calendar and clock decide actual regular-session eligibility, holidays and
  shortened sessions. A boot observation is fresh, never a backdated PASS.
- `alpaca-net-day-monitor-failure.service`: notification-only OnFailure hook.
- Actual initial/boot captures: `DAY_CLOSED_SESSION`, Saturday. These are not
  protection or future Monday re-arm confirmations.
- Telegram delivery check actually received HTTP200/oktrue, message **15210**.
  Its caption explicitly says TEST, not an alarm or protection confirmation.

[Installation](evidence/alpaca_day_monitor_20261017/installation.json),
[independent post-install readback](evidence/alpaca_day_monitor_20261017/readback.json).

## Isolation and behavior

The credential-bearing transport exposes only `get(path)` with exact Alpaca
origin/routes; it cannot accept an HTTP method, body, order/cancel/replace call,
manager command or money GO. Redirects are refused. The original account lock
is stat-checked for inode identity, never opened/acquired by this observer.

Systemd ProtectSystem=strict, ProtectHome=read-only, empty capability set and
ReadWritePaths only for the observer runtime protect trading state. The
observer uses its own single-instance lock. Before/after checks preserved **95
existing source/ownership/HALT pins**, including all **32 reviewed monthly V3
files**, current NET service/timer, original profile and HALT. Cron and original
account-lock inode stayed unchanged. No broker write, old-manager restart,
financial activation or policy/risk change occurred.

Each bounded capture retains raw GET evidence privately. The evaluator requires
account/ledger consistency, complete orders, current clock/calendar, exact owned
stop ID, quantity/floor and actual GET-order readback. Missing RTH protection
produces CRITICAL; unverified/conflicting source produces UNKNOWN/CRITICAL.
Closed hours are quiet and do not count as missing regular-session protection.
Re-arm/unwind remain solely the existing manager's job.

Immutable observation journal and incident state are durable **before** Telegram.
One persistent delivery claim prevents blind resend after a lost response;
repeat unchanged incidents are quiet. Confirmed recovery sends one notification.
New incidents after recovery may alert again. A separate failure hook does not
depend on a parseable observation state. Telegram delivery failures remain
explicitly UNKNOWN; successful observer execution is not itself proof of
protection or message delivery.

Reports expose first confirmed-protection delay, missing/unknown samples and
observation gaps. Continuous actual unprotected duration remains UNKNOWN without
complete intervening event evidence; no synthetic zero is published.

## Verification and limits

**168 targeted PASS**:16 new monitor/GET/CLI/notification/collector cases plus
DAY evaluator, repaired manager, monthly native and prior health tests. Tests
exercise duplicate/restart/uncertain delivery, RTH gap, weekend/short session,
material stop conflicts, failure hook and no writer/foreign-runtime mutation.
[Exact source/log pins](evidence/alpaca_day_monitor_20261017/verification.json).
The broad known-red suite was not rerun or represented as green.

Monday's actual re-arm is still a future observation. Current service/timer and
delivery proof do not claim that a reboot, future exchange failure or future
broker stop has already been observed. Source drift/UNKNOWN triggers an alert;
the observer never repairs/loosens a stop or creates another account writer.

Rollback of monitoring alone: disable/stop only this observer timer and service;
leave `alpaca-oct15-owned-manager` and monthly V3 untouched. Preserve all journal
and notification claims. Do not replay the installation or delivery check.

Next authorized engineering: KITY batch/private WS orders-OFF, then frozen
Elder Crash Hedge adapter orders-OFF. No expired KITY policy or old owner GO is
reused. Monthly financial activation remains a separate owner-controlled step.
