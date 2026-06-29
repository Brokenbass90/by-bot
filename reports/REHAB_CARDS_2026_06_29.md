# Failed-strategy rehab cards — 2026-06-29

Author: Claude (central). Principle (owner): we do NOT discard failed strategies.
A fail is almost always a bad implementation or a regime mismatch, not a dead
idea. Each card: what it tried → how it failed → triage bucket → the ONE fix to
test → how to test. New foundation (`market_context` real levels, `volume_exit`
early exit) directly attacks the documented failure causes. One change at a time,
each as a challenger through champion-challenger + WF.

Buckets: (1) good idea/bad mechanics → rewrite on shared layer; (2) edge exists/
DD-cost fails → repair gating; (3) wrong regime → regime-scoped challenger;
(4) no edge → archive with post-mortem (kept, not deleted).

---

## ARF1 — alt_resistance_fade_v1  (short resistance fade)
- Tried: short fades at resistance built from naive level logic.
- Failed: implementation likely uses weak levels ("max(highs)"-style), not real
  repeated clusters; edge didn't survive WF.
- Bucket 1 (good idea / bad mechanics). The fade idea is sound and matches owner.
- Fix to test: rebuild on `market_context.horizontal_levels` (min_touches≥3) +
  HVN/VWAP confluence + rejection confirm. (ARF2 is exactly this attempt — already
  running on server; some rows PF 1.7–1.9 but fail on red months/streak.)
- Test: ARF2 full sweep → monthly_analysis (bear-month filter) → WF. Priority: HIGH.

## ASB1 — alt_support_bounce_v1  (long support bounce)
- Tried: long bounce off support; repair sweep `asb1_bull_chop_repair_v1`.
- Failed: 432/432 FAIL; best r117 net -2.68, PF 0.924, WR 39.2%, DD 6.90.
- Bucket 1. Support-bounce is the mirror of ARF2; current level/context logic weak.
- Fix to test: rewrite as ASB2 on `market_context.support` + `sloped_support`,
  require rejection candle + volume confirm on the touch; bounce target = next
  level (near), tighter R (owner: "отскоки берутся проще, движения короче" →
  higher WR, smaller R geometry).
- Test: build ASB2 → cache-only smoke → WF on inplay alts. Priority: MEDIUM-HIGH.

## InPlay Breakdown — alt_inplay_breakdown_v1  (short break of support)
- Tried: short on support breakdown.
- Failed: fresh sweep failed badly; live shadow -2.41 over 15 trades (4W/11L).
- Bucket 1+3. Owner warns (setup C): impulse breakouts are now often manipulative
  (false flush then reclaim) → naked-impulse entries bleed.
- Fix to test: anti-manipulation rewrite — require retest/close-back-beyond the
  level (not naked impulse), partial early target ("колено", don't wait full
  measured move), tight stop; add `volume_exit` so dying breaks exit fast. Keep
  short-only, bear/chop-scoped.
- Test: rewrite gating → WF; compare vs current. Priority: MEDIUM.

## IVB1 — impulse_volume_breakout_v1  (impulse-volume breakout)
- Tried: breakout on impulse + volume.
- Failed gate (but has edge): 312 trades, net +16.45, PF 1.254, WR 55.4%, DD 8.99
  — DD too high, fill/maker risk.
- Bucket 2 (edge exists, DD/cost fails). DON'T rewrite — repair gating.
- Fix to test: side/symbol gating (drop the worst symbols/side), maker entries to
  recover fees, `volume_exit` to cut losers when the impulse dies, tighter stop /
  partial early target. Target: same net at DD≤~5 and PF≥1.3.
- Test: gated re-sweep → DD-doctor → WF. Priority: MEDIUM (real edge, worth it).

## Elder — elder_triple_screen_v2 / v3 / elder_crypto_v1
- Tried: Elder triple-screen as a standalone engine.
- Failed: mass FAIL, DD 40–83; hyperactivity ate fees.
- Bucket: NOT a standalone engine. Repurpose, don't keep tuning as a core sleeve.
- Fix to test: use Elder as a FILTER/booster on ATT1/InPlay — e.g. only take entries
  when Elder's higher-TF trend + `market_context` dist-to-structure agree; hard cap
  1 trade/symbol/day. Measure as an overlay on a working leg, not solo.
- Test: add as optional gate to ATT1 short, A/B the gate. Priority: LOW-MEDIUM.

## Range (legacy `strategy=range`)
- Tried: range/pila mean-reversion wrapper.
- Failed: 180d replay 280 trades, net -18.60, PF 0.61, DD 20.54, 5 red months.
- Bucket 3 (wrong impl/regime). Keep FROZEN; do not unpause.
- Fix to test: the structured replacement is ARS1 (alt_range_scalp_v1), already in
  the ATT1+ARS1 additivity test. Legacy range stays archived.
- Test: rely on ARS1 additivity verdict. Priority: LOW (covered by ARS1).

## ASR1 / ARR1 / BTCR1 / AVW1 / FRR1 (bear-canary configs present, unproven)
- Status: config stubs exist (`configs/*_canary.env`), no proven edge yet.
- Bucket: park as challengers; only pull into research when a clear hypothesis +
  data coverage exists (don't proliferate). Priority: LOW.

---

## Rehab pipeline (how each card runs)
1. Pick ONE card, make the single change behind its own flag/namespace.
2. Cache-only smoke (does it run, does it trade sanely).
3. monthly_analysis (bear-month = FAIL) + stack_comparison (wrapper not strangling).
4. multi-window WF gate: ≥3/4 windows +, PF>1 after 6/2 bps, ≤3 red months, streak ≤2.
5. Pass → shadow → tiny canary with breaker+expiry. Fail → write what we learned,
   archive the idea (kept), move to next card. Never tune endlessly.

## Suggested order
ARF1/ARF2 (in flight) → IVB1 DD-repair (real edge) → ASB2 rewrite → Breakdown
anti-manip rewrite → Elder-as-filter. AI (autoresearch agent) proposes/ranks; human
approves any live-risk step.
