# ATT1/SBR1 fixed-51 shadow routing — 2026-09-02

Both independent VPS fixed-51 shadow timers are now `enabled`, `active`, and
`waiting`. Their latest oneshot services exited successfully with status 0.
ATT1 had been running from an active timer that was not enabled across reboot;
the timer was enabled so evidence collection now survives a normal reboot.
SBR1 was already enabled and was not changed.

This change is strictly zero-risk: public-data shadow collection only. No
orders, private API, positions, live risk, promotion authority, or money
authority were added.

## Current evidence snapshot

- ATT1: 10,302 rows, 10,055 raw decisions, 44 raw signals, 6
  regime-eligible diagnostic signals, 0 admitted, 0 final-N eligible. The 45
  processing errors are historical; the latest 51-event cycle has no error
  event.
- SBR1: 11,330 rows, 10,900 evaluations, 19 raw signals, 0 admitted, 0
  final-N eligible. The latest 54-event cycle has no error event.

Zero admissions does not mean the timers are blocked: ATT1 fixed-51 is raw
diagnostic evidence, while SBR1 keeps its separate admission rules. The
journals are advancing and latest cycles are clean.

These timers remain an independent VPS evidence plane. They are not registered
as canonical local research-station jobs, so this receipt does not claim
canonical-station migration parity and does not add duplicate routes there.

Machine receipt:
`reports/receipts/ATT1_SBR1_FIXED51_SHADOW_ROUTING_2026_09_02.json`.
