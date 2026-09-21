# Continuation handoff — 2026-09-19

September 21 supersedes preparation notes below: autonomous PAPER is deployed;
**4/7 real receipts PASS**. Read checkpoint TOP and
`reports/ALPACA_AUTONOMOUS_PAPER_2026_09_21.json`. Do not redeploy/reseed or repeat
entry acceptance. Only remaining broker events: DAY expiry, next-session re-arm,
then proof-scoped PAPER kill. LIVE/ATT1 untouched; no canary authority granted.

Earlier notes:

September 20 update: read checkpoint TOP and
`ALPACA_PAPER_PREPARATION_2026_09_20.json` first. Frozen offline prepare and
PAPER kill dry-run validated; active execution wiring still unfinished.
Exact next location: bridge `_submit_buy_action` → existing floor/HWM persistence.
No claim that only market opening remains; no emergency order executed.

UPDATE: Start from checkpoint TOP and `ALPACA_PAPER_PROGRESS_2026_09_19.json`.
Owner now prioritizes Alpaca dossier before ATT1. PAPER endpoint fixed/tested,
not production-deployed. All five legacy position owners resolved; AMZN belongs
to intraday. Intended broker evidence remains 0/7; legacy HWM recovery and frozen
PAPER wiring are next. The following section records the earlier analysis snapshot.

This is an analysis/handoff cycle, not permission to activate money. Owner's
September 19 scope supersedes the older Alpaca pause. Start from the TOP of
`reports/CODEX_SESSION_CHECKPOINT_2026_09_06.md`, then this file and
`reports/CURRENT_PROJECT_ROADMAP.md`. No new chat has been created.

## Confirmed now

- Canonical production checkout: `bybit-bot-recovery-20260824`, branch
  `codex/recovery-20260824`. Research packet/registry are in sibling
  `../bybit-bot-clean-v28`, not this checkout. Do not search from scratch.
- ATT1 read-only VPS snapshot 2026-09-19T08:29:23.174000+00:00: OLD heartbeat
  3.17s, fairness source hash still
  `c8ca2c325884a31521f160e9d690c301b8a58297443f32f3cde395e9c9a699d1`.
  OLD service start is September 18 06:38 UTC, so do NOT claim uninterrupted
  OLD uptime since deployment. Cause of that later restart was not checked.
- Public service PID 451398 still starts September 13 07:52 UTC, NRestarts=0,
  heartbeat 0.77s; 21 sessions,
  **0 clean filled terminal lifecycles**. Current scan snapshot is 49 symbols;
  do not advertise current 51/51 without the completed scan receipt.
- September 14 bounded stack capture contains START and DONE only, no stacks.
  It is completed, not armed. No proof of a new blocking call from that capture.
- NEW production dispatch/protection/fill/cost finality remains unfinished,
  default-off; exact current OLD absolute risk must be refreshed before dossier.
- Public gap localization already done: synchronous orderbook I/O in the
  serial observation loop can exceed the existing 2s continuity budget.
  This is a localized reproducible mechanism, not proof of every real gap.
  Only recorded this blocker per owner; no public fix/deployment this cycle.

## Alpaca packet assessment

**Sufficient as research handoff to START operational work: YES.**
No strategy research, parameter changes, new gates or monthly observation wait.
`READY_FOR_BUILD` comes from existing registry; packet itself still says
`CANDIDATE`. Record this documentation mismatch; it grants no money authority.

Correct evidence link: `research_lab/data/alpaca_repetitsiya.json` contains
9/9 passing OFFLINE checks. Packet instead points to
`alpaca_namerennyy_ten.jsonl`, which contains one research selection record.
Do not count either as PAPER broker or VPS operational PASS. No rerun needed
merely to discover the already existing receipt.

**Operational evidence confirmed from supplied artifacts: 0/7.** This counts
exactly the seven rows under `ЧТО ДОЛЖЕН ДОКАЗАТЬ ПРОГОН НА VPS` in the gate
file. It does not assert that no additional evidence exists on VPS.
1. Manager startup with UTC receipt: not supplied.
2. Fractional broker fill price and qty: not supplied.
3. Accepted DAY stop ID/TIF and actual-fill anchor: not supplied.
4. DAY expiry snapshot across session boundary: not supplied.
5. Next-session reconciliation/re-arm and new order ID: not supplied.
6. Restart with identical floor/HWM: not supplied.
7. PAPER kill command and ownership/orphan disposition: not supplied.

Next executable action: authenticated PAPER account/positions/orders read-only
truth plus existing `owned_position_lifecycles.json`,
`protective_exit_hwm.json`, `latest_manager_receipt.json` from the actual VPS
service paths. Identify manager/config/ownership before PAPER mutations; do
not assume ownership of AMZN or flatten unrelated positions. Then execute the
packet's existing seven-step PAPER protocol with its frozen strategy contract.

Freeze existing source/config for the build, without retuning. Source code
and config exist (hashes below); the packet does not itself pin their complete
production revision. Hashes here identify READ artifacts, not a claim of
validated deployment parity. The packet/gates/registry are untracked in the
source checkout at inspection; coordinate their preservation with Claude.

Live capital amount is deliberately an owner decision, still absent. The
$1000/$700 offline rehearsal numbers do NOT select a live canary size.
This does not block read-only preparation or PAPER verification. Only after
operational PASS produce `TINY_LIVE_CANARY_DOSSIER`; separate owner approval
covers live amount and emergency overlay activation. No current approval.

## Ownership and queue

Codex: ATT1 production/canary + Alpaca packet → existing VPS/PAPER → readiness.
Claude: existing registry/factory, Gold, bounded fallback to the next cheap
family on a recorded external-data blocker. Do not build another architecture.
The existing single candidate registry is
`../bybit-bot-clean-v28/research_lab/data/reestr.json` (23 entries at read).
A future `STRATEGY_MASTER.md` should be a view/index of it, not another manually
maintained authority. Claude's inventory must not pause Codex operational work.

SBR1 is next after ATT1: restore its existing deployed shadow/parity evidence,
not a new research cycle. `reports/evidence/SBR1_ZERO_RISK_SHADOW_DEPLOY_RECEIPT_20260824.json`
already records an August 24 public-only deployment. Its present runtime and
preliminary +22.35R/PF2.14 have NOT been revalidated this cycle.
Then recover XSEC PIT/Bull Continuation; ATT1-long follows existing leads.
Gold is Claude's independent queue. ETS2S/other shadows retain profiles and
collect evidence. Ordinary cross-exchange ARB remains closed; the existing
parked premium-event entry refers to **deposit-disabled** EGLD, while owner's
label says withdrawal-disabled. Preserve the wording distinction; no new ARB
research or assumption that either is risk-free. Cleanup comes after P0.

## Artifact fingerprints (research source checkout)

- `research_lab/pakety/PROMOTION_PACKET_ALPACA_INTENDED.md`: `4274cce3ea64a32435b5e029a3ce92a0a3102e08114e5b7e8c023bb654c69c2b`
- `research_lab/ALPACA_VOROTA_2026_09_14.md`: `8e440ed19d661ba64a4825a25054b7a224d7b2b6b1b562280d8d954e732253e8`
- `research_lab/data/alpaca_repetitsiya.json`: `d610ee68fcbdcff968d9897bcb90cdec0bd8fb32d900e373029949cdd57d3f44`
- `research_lab/data/alpaca_namerennyy_ten.jsonl`: `60c281952695928ac17373bd1b2abe00a3d7c048959fdf1e93aa7b633a8d8e85`
- `configs/preregistered/alpaca_honest_diagnostic_v1_20260810.json`: `7b1022ce47933e1de579ca4ebb950cf84675958ba62c3aee9d8337534ad6b245`
- `backtest/alpaca_honest_portfolio.py`: `21c83fe9bff1659990a869a40bd2f62b8f8c3a359f88d4b398291b4096f978b8`

## Paste into next chat

Continue from `reports/CODEX_SESSION_CHECKPOINT_2026_09_06.md` (top) and
`reports/CONTINUATION_HANDOFF_2026_09_19.md`. P0: ATT1 default-off production
binding/clean lifecycle and Alpaca intended frozen packet to VPS/PAPER.
Do not re-research strategies or add gates. First retrieve fresh Alpaca PAPER
truth and existing ownership/protection receipts; close only packet's seven
operational evidence rows. Keep OLD money/risk and existing shadows unchanged.
No live activation without a separate owner decision. Use Mac offline compute;
use bounded cheap agents for mechanical work, verify their actual model.
End with: ATT1 distance | packet sufficient | evidence X/7 | blocker | next step.
