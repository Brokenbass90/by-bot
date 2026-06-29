# Portfolio expansion + failed-strategy rehab + AI management — 2026-06-29

Author: Claude (central). Recheck/deploy: Codex + owner.
Answers three owner questions: what to launch next, how to rehab (not discard)
failed strategies, and how the on-board AI manages the set smartly.

Ships with this plan: `bot/volume_exit.py` (NEW, tested 9/9) — the volume-fade
early exit that was missing from every automated leg (owner's "ключевая деталь").
Coin selection by volume inflow already exists (`bot/inplay_volume_universe.py`).

---

## A. What set of strategies to launch next (phased, each through the gate)

**Phase 1 — first money (ready now):**
- **ATT1 short-only canary** x0.10, cap 3 (slot test passed), breaker + expiry armed.
  Owner OK pending. This is also owner setup C (downward-sloped break) — proven by hand.
- **Alpaca $500 v38** — proves the real-money rails; ~22–23%/yr model, small $ but
  the first live equity loop. Needs `configs/alpaca_live_v38.env` + dry-run first.

**Phase 2 — make it active & earning (the owner's real edge):**
- **InPlay volume leg** = `inplay_retest_v3` (level retest) + `inplay_volume_universe`
  (coin selection) + **`volume_exit`** (early exit when impulse dies). This is the
  combination that matches how the owner actually earned by hand — and it trades
  inplay ALTS, structurally different from crowded BTC/ETH price patterns. Highest
  upside, must pass WF on the dynamic volume universe.
- **SpikeFadeV3 LINK short** — low-frequency diversifier (PF ~1.9, DD 1.27); add as a
  small smoother, not an engine.

**Phase 3 — rehabilitated cohort (see B):** ARF1/ARF2 structured resistance fade,
ASB1 rewrite on the levels layer, IVB1 (DD-repaired), Elder-as-filter — each only
after it re-passes the gate.

**Phase 4 — non-directional smoother:** funding-carry (the one market-neutral green
signal) once hedge/basis/liquidation guards are in. Lowers portfolio drawdown.

Launch discipline (unchanged): default-OFF/shadow → WF (≥3/4 windows +, PF>1 after
6/2 bps, ≤3 red months, streak ≤2, maker-friendly) → tiny canary with breaker+expiry
→ scale on live confirmation. Never a whole batch at once.

---

## B. Failed-strategy rehab framework (do NOT discard — analyze, polish, retry)

Principle: a failed strategy is almost always a failed **implementation** or a
**regime mismatch**, not a dead idea. We keep the idea, fix the cause, re-test.

Triage every failed sleeve into one of four buckets:
1. **Good idea, bad mechanics** → rewrite on the shared foundation. Most of the
   documented failures were exactly this: "levels from mush", fixed TP instead of
   volume exit, structure-ATR inflating risk. The new `market_context` (real levels)
   + `volume_exit` (early exit) directly attack those causes. (ASB1, ARF1, InPlay.)
2. **Edge exists but DD/cost fails** → repair gating, not the core: side/symbol
   gating, maker entries, volume_exit to cut losers early, tighter stops. (IVB1.)
3. **Wrong regime** → demote to a regime-scoped challenger (e.g. only bear/chop),
   don't run all-weather. (Range, ASB1 long.)
4. **Genuinely no edge** → archive the idea with a written post-mortem (kept, not
   deleted), so we don't re-try the same dead end.

Process — one "rehab card" per strategy:
- what it tried, how it failed (the actual metrics), the single hypothesis to fix,
  the one change to test. Run it as a **challenger** vs the current champion through
  the existing `CHAMPION_CHALLENGER_FRAMEWORK` + WF. Promote only on a clean gate.
- One change at a time, so we learn what actually moved the needle (no shotgun tuning).

---

## C. How the on-board AI manages this smartly (within hard rails)

The AI surface already exists: read-only code vision (`code_access`,
`strategy_catalog`), toolbox (`ai_tools`), human-approved action executor
(`deepseek_action_executor`), research agent (`deepseek_autoresearch_agent`),
signal/research gates. We use it as a **portfolio manager inside rails**, not an
unleashed trader.

What the AI does:
1. **Watches** — reads heartbeat + journal + the new `strategy_breaker` /
   `market_context` / `volume_exit` outputs and writes a daily portfolio-health
   digest (which sleeve is hot/cold, what the breakers are doing, what to review).
2. **Proposes, never auto-spends** — ranks which rehab card to prioritize, which
   challenger to queue, which sleeve to soft-cut or boost *within allocator caps*.
   Any action that changes live risk needs owner/Codex approval via the operator-
   override layer Codex just built.
3. **Runs the research loop** — generates rehab hypotheses and interprets sweeps
   (ARF2, ATT1+ARS1 additivity) continuously, feeding bucket B.
4. **Cannot override safety** — breaker hard-blocks, canary expiry, allocator caps
   and the live guards are floors the AI may not lift. That is what makes "let the
   AI manage it" safe: smart proposals, hard rails.

---

## Immediate next steps
- Owner decision (with Codex): enable ATT1 canary, and/or prepare `alpaca_live_v38.env`
  for the dry-run before US open.
- Claude (me), unblocked now: wire `volume_exit` into `inplay_retest_v3` behind a flag
  and backtest setup-A-with-volume-exit vs fixed-TP on the inplay volume universe.
- Claude, when logs arrive: ARF2 full-sweep interpretation + ATT1+ARS1 additivity on
  the corrected package.
