# Bot Autonomy Loop — 2026-04-30

Goal: make the bot improve in a controlled rhythm instead of random AI chatter.

## Non-Negotiable Rules

- AI may diagnose, research, rank candidates, and write proposals.
- AI must not push a strategy to live risk without explicit human approval.
- Live promotion requires:
  - annual standalone pass
  - additivity versus the current live canary
  - WF/OOS check
  - live shadow or canary period
  - rollback path
- Production deploy requires:
  - committed Git state
  - server-side `py_compile` / import smoke before restart
  - `open_trades=0` or explicit emergency approval
  - post-restart heartbeat check

## Existing Server Loop

- Every 15 minutes: control-plane watchdog / repair.
- Hourly: regime state, geometry, operator snapshot.
- Every 2 hours: self-audit report.
- Every 4 hours: symbol router, BTC dominance, strategy monitor.
- Daily: Telegram digest and guarded auto-apply dry-run path.
- Weekly: DeepSeek audit/tune/research/universe/report.

## Upgrade Target

Add a deterministic two-day "proposal digest" loop:

1. Read operator snapshot, self-audit, live trade events, Alpaca paper state, and recent autoresearch results.
2. Produce one bounded report:
   - current live health
   - what is blocking entries
   - which research jobs passed or failed
   - top 3 next actions
   - explicit "do not deploy" list
3. If a strategy candidate passed all gates, queue a proposal, not a live change.
4. Send the proposal to Telegram/web for human approval.

## Near-Term Research Rhythm

- Keep live canary v2 unchanged until a candidate passes gates.
- Run at most two heavy autoresearch jobs at once on the small droplet.
- Priority order:
  - IVB1 annual repair rerun with missing-cache fetch enabled.
  - support_bounce annual rerun with fixed cache-mode handling.
  - range additivity versus canary v2.
  - liquidity hunter annual probe only after the first two finish or free a slot.
  - Alpaca intraday/swing income research in separate local/server slots.

## Deployment Lesson From 2026-04-30

The bot restart failed once because `smart_pump_reversal_bot.py` depended on `bot/order_link.py`, but that module was not included in the partial server file copy.

Prevention:

- Prefer full commit-based deploy or a generated deploy manifest.
- If doing partial deploy, include dependency smoke:
  - import the main bot module dependencies
  - run `py_compile` for touched modules
  - check service status after restart
- Never leave `systemd` in auto-restart failure state; diagnose immediately and restore heartbeat.
