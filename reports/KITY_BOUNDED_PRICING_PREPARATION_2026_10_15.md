# KITY bounded pricing — local preparation, October 15

**PRICING_INTENT_COMPILER_LOCAL_PASS / ORDERS OFF.** This is a local compiler
delivery, **not** `KITY_EXECUTION_MICRO_LIVE_READY`. The currently installed
physical owner still runs V1 with the consumed `ffeb…6570` experiment. No VPS
source, service, GO, plan, journal or broker order was changed by this work.

The owner asked to prepare bounded pricing before a second micro attempt.
The old literal GO and its `NO_SEND_NOT_LIFECYCLE_PASS` remain spent. Preparation
does not authorize a second experiment or turn an intent into money authority.

## Proposed contract

Keep the same ten symbols/sides and exact reference quantities. Freeze legal
per-symbol price bands before GO, the physical config pin, predecessor identity,
expiry and the existing V3 money limits. Proposed defaults for owner selection:
**±50 bps (±0.5%), ten minutes**. These numbers are **not yet owner approved**.
The implementation accepts narrower positive collars/shorter positive TTLs;
neither can exceed this proposal without a separately reviewed version.

Literal future approval would be
`GO KITY_EXECUTION_MICRO_INTENT_V2 <fresh intent_id>`, not the old exact-plan GO.
No current actionable GO hash is issued here. All example intents below are
expired recorded-source replays.

After the literal GO, atomically consume the intent **before** the new capture.
Select one exact plan using actual fresh account/instrument/fee/funding/depth
sources. Quantities do not grow; IOC prices are fixed at the authorized outer
legal band to allow bounded market movement before dispatch. Recompute native
guards under the same $15 rule. No subsequent repricing/retry is allowed.
A failed capture/materialization leaves an immutable no-send receipt. Restart
must never repeat that capture or authorize a new entry from its claim.

Existing constraints stay $215 gross, $15 immediate all-in exit trigger with
accepted execution overshoot, 30 minutes from the first durable entry intent,
20.3% reference floor-rounding shortfall, no averaging/scaling/re-entry and no
KITY/C1–C3/edge interpretation. The preserved rounding fractions describe the
frozen reference quantities; they are not a claim of exact equal notionals at
later prices. Favorable fills, gaps and exchange behavior do not become a
guaranteed final gross/fee/loss bound from this offline calculation.

## Verified local behavior

New transport-free module `research_lab/kity_micro_pricing_intent_v2.py` reuses
the existing captured-source parser, quantity/depth primitives, native guard
derivation and plan validator. It has no credential loader, HTTP sender,
supervisor activation or actual monetary journal. Its exclusive claim records
literal intent GO; it cannot translate the old GO into new authority.

**30 new focused tests**, **56 targeted tests total PASS**, including existing
single-writer/supervisor/preflight/concrete synthetic venue paths. New cases
cover an eight-minute human reply with fresh prices, both collar boundaries,
expiry, wrong config, foreign orders, invalid source CTS, changed ticks,
tampered bands, native guards, cap feasibility, immutable claim before a
failed capture and rejection of the old GO. Tests do not prove actual fills.
Full repository suite was not run; root-only review, existing independent-review
quota restriction remains.

Replay uses the already saved capture completed **13:41:03.803 UTC**,
SHA256 `9203850c7bde00f37147565b2ea839bc8d1dcb869ac84a2ddc96787b7d389192`.
The original parser reproduced `ffeb…6570` exactly before applying the new
compiler. No new broker capture or outcome test was performed for this replay.
Result: unchanged ten quantities, reference gross **206.482530**, IOC limit
notional sum **206.470400**, sum at all reference band upper prices
**207.508680**, current-price entry/exit fee reserve **0.216916172 USDT**,
ten native-stop payloads. These are dated calculations, not actual charges or
current executable prices.

| Symbol | Side | Quantity | Recorded lower band | Recorded upper band |
| --- | --- | --- | --- | --- |
| BTWUSDT | Buy | 10 | 2.01823 | 2.03851 |
| XAUUSDT | Buy | 0.005 | 4142.85 | 4184.47 |
| LTCUSDT | Buy | 0.3 | 57.98 | 58.56 |
| VVVUSDT | Buy | 0.94 | 22.6990 | 22.9270 |
| BNBUSDT | Buy | 0.03 | 714.38 | 721.54 |
| XAUTUSDT | Sell | 0.005 | 4128.55 | 4170.03 |
| XPLUSDT | Sell | 262 | 0.08159 | 0.08239 |
| XAGUSDT | Sell | 0.378 | 56.58 | 57.14 |
| GRASSUSDT | Sell | 34 | 0.61720 | 0.62340 |
| SPCXUSDT | Sell | 0.14 | 142.90 | 144.32 |

Sanitized delivery and code hashes:
`evidence/kity_pricing_intent_20261015/local_delivery.json`,
SHA256 `501a88fd0a020cd9581df94125e0353e5e298af201a00a661d1de0dbad2538e5`.
Raw account/capture evidence stays private and uncommitted.

## Complete remaining runtime binding scope

These are implementation steps, not new research/PAPER gates. They are not
claimed complete by the local compiler tests:

1. Add a bounded-intent command to the **existing one physical owner**. Its
   current V1 control correctly rejects that unknown command. Never generate
   a fictitious exact-plan human GO to bypass V1.
2. Prove predecessor terminal/no-send and fresh account flatness; select a
   separately identified experiment store while retaining the original
   account-lock inode and every byte of the spent plan/GO/journal.
3. Bind literal intent GO, capture hash and the derived plan to the writer.
   Check intent expiry before validation **and immediately before each entry
   POST**. Expiry blocks remaining entries and triggers existing scoped
   recovery; it must not disable protection/exits or reset the 30-minute clock.
4. Restart, health and rollback must all resolve the selected experiment.
   **Do not point a new experiment at the legacy rollback reader:** it only
   knows the original journal and could mistake an old terminal for current
   flatness. Current original runtime remains unchanged and valid for itself.
5. Version/hash the resulting package/config, install through the existing
   single-writer handoff safeguards and perform actual GET-only no-send
   rehearsal. Only then publish a fresh bounded dossier for a separate exact
   human GO. No second independent sender and no restoration of old bybot/web.

Owner parameter-selection question was sent while the local tests/replay ran.
No missing answer is interpreted as approval. Alpaca remains under its existing
owned manager; no live stop or trading-policy change was made. Elder/Factory
research, prospective counters and spent Brain verdicts remain unchanged.
