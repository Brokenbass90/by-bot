# Alpaca TINY_LIVE_CANARY_DOSSIER — 2026-09-23

**PAPER operational evidence 7/7 PASS. READY_FOR_OWNER_REVIEW = TRUE.**
**LIVE_ACTIVATION_READY = FALSE; no live capital or activation approval.**

Canonical evidence: `ALPACA_AUTONOMOUS_PAPER_2026_09_21.json`, including broker
IDs, exact fills, expiry/re-arm receipts and private artifact hashes.

## Frozen scope and observed execution

Strategy `ALPACA-BASELINE-26f7ff663dc98e87`; unchanged selector/profile:
v38 successor, SPY200, four slots, gross 0.70, weight cap 0.60,
actual-fill-relative 2 ATR20 stop, HWM ratchet 3.5/3.5/0.5,
21-calendar-day stop-exit reentry block. No new filters or research gates.

Verified source: `8dc738efa217d7f103da5ee88dec42697b8bcaff`, manifest SHA256
`bd521caa637c7e0d20ba715adca9605e78857a6a7b2ed7253662cdbf125c9395`.
151 focused checks passed on Mac and VPS Python 3.12.3; 46 hashes matched.
App: `/opt/bybot-research/alpaca-intended-paper/app`.
Runtime: `/root/by-bot/runtime/alpaca_intended_paper`.
Account: exact PAPER endpoint, identity suffix `86efaf`.

PAPER capital was $1000; actual entry qty × average fill totaled $699.94.
This is not an approved LIVE allocation or a profitability result.

| Existing row | Actual evidence | Verdict |
|---|---|---|
| Startup | Sep21 17:23 UTC automatic cron execution | PASS |
| Fractional fill | CRM/CRWD/CVX/MRK, exact broker qty/average | PASS |
| DAY protection | Four accepted full-quantity stops anchored to actual fills | PASS |
| Expiry | Sep21 original stops expired unfilled; positions remained | PASS |
| Next-session re-arm | Sep22 13:30 UTC four new IDs, same floors/quantities | PASS |
| Restart | Fresh cron process restored identical floors/HWM/entry identities | PASS |
| Kill/ownership | Sep23 13:44 UTC one command, four filled exits, intended flat; five foreign positions unchanged | PASS |

## Terminal disposition

The existing `--paper-kill-owned ... --apply-kill` command validated account,
latest entry IDs, original filled quantities/averages and current positions.
It cancelled only intended protective orders, closed only the four proven owned
positions, then confirmed flat. Broker returned four filled sell orders.
ABNB/ABT/MA/SCHW remained legacy-adaptive-owned; AMZN remained intraday-owned.
No orphan was adopted. Existing LIVE/ATT1 processes, risk and positions untouched.

Only the completed intended acceptance cron was removed, after confirmed-flat,
to prevent deliberate acceptance exits being mistaken for unexplained recovery
loss. All other cron lines were preserved. Account PAPER entry halt and complete
raw lifecycle evidence remain; do not delete/reseed them to resume trading.
The periodic Codex acceptance monitor can now stop.

## Limits and concrete next step

Seven PAPER operational rows are complete. They do not demonstrate profitability,
continuous monthly strategy selection, or an already deployable LIVE switch.
The verified runner explicitly rejects non-PAPER endpoints. Before asking for
money activation, bind the same frozen contract to the exact LIVE account in a
default-off deployment and present its concrete command/config for owner review.
No additional research gate or strategy change is needed for that binding.

Historical HWM for foreign legacy ABNB/ABT/MA remains unproven. These PAPER
holdings were neither adopted nor closed and are not evidence that the intended
manager recovered their floors. Fresh LIVE positions must be reconciled by exact
owner before activation; PAPER account truth cannot stand in for LIVE truth.

The current execution path halts on uncertain pre-persist order ownership rather
than auto-adopting it; a durable pre-submit client-order intent is not claimed.
Partial fills, accepted protection, cost finality and recovery failures remain
fail-closed under the existing contract; do not promote scenario costs to actual
LIVE net returns. Acceptance kill exits are infrastructure test exits, not
strategy exits or strategy-performance evidence.

Owner must eventually specify the tiny-LIVE amount and approve the exact
reviewed activation. No amount, existing LIVE position change, risk escalation,
or activation is authorized by this dossier.
