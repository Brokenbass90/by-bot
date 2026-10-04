# ATT1 cold migration — running retirement, orders OFF

Latest continuation **October4 07:09–07:12UTC** — read
`ATT1_ACTUAL_INPUT_CONTINUATION_2026_10_04.md` and JSON first.
Terminal **BLOCKED_ACTUAL_PACKET; NEW orders OFF**. MainPID1648585 still
process-pinned retired; selected-account signed positions0/orders0 before+after,
effective money sleeves[], core/guard preserved. Real quarantine **50/96**;
earliest96 close11:00UTC/14:00Cyprus conditional on continuity, not a money GO.

ADA86 exact mixed closed island verified:180+90 entries,99+171 exits, all4 orders
fresh Filled, cash chain0/net+0.73928972. ML remainsOPEN; no label/DB rewrite or
clean attribution/all-history finality. Current UTC-day executions/cash0 through
07:08:08UTC with60s publication lag; wallet source captured privately.
Six duplicateidx0 sources explicitly retained/classified, strict validation
unchanged; LINK1/2/0 remainsCONFLICT, SUI only passing one-way subset. No silent
dedup/mode writes/universe changes. Inert14-day quantity/cost assessment rejects
infeasible sizes; observed interval/limit/stop-price assumptions remain conditional
and unbound to an actual admitted command. Full draftR0.4+5USDT scenario costs
exceed draftD0.8 for all8; no installed or approved risk cap changed.

Public NEW now **7sessions/39records/3filled simulations/4nonfills/2gaps/0clean**;
ETH simulated0.02 held without incident at capture. SamePID1584802/epoch/source
hashes/2s/journal, broker/ordercalls0. Actual NEW money lifecycle NOT_PROVEN.
Local135/VPS135 targetedPASS; bounded criticalreview78PASS after2P2 fixes,
actualmodel6-astra/high verified. Full3464PASS/57 oldFAIL, no new failures;
foreignSHA preserved/unstaged. No money-service install/restart/route migration.
Next: first96 receipt + authoritative mode handling + exact quantity/cost/fresh
OLD risk binding + finite inventory/prior-cost finality; then actual dossier.
2–3clean filled prospective terminals/net-R +fresh dossier+separate ownerGO remain.
Alpaca/AI/Claude/Factory untouched and not freshly rechecked this ATT1-only cycle.

Earlier snapshots below retain their original timestamps and are superseded here.

Latest delivery **October4 03:06UTC** — read
`ATT1_RETIREMENT_AND_COLD_OBSERVATION_2026_10_04.md` and its JSON receipt first.
OLD entry authority is now process-pinned retired: bybotPID1648585, initial
ATT1_ENTRY_RETIRED=1, effective heartbeat money sleeves[], native pause intact,
signed positions0/orders0. Only control module + one override key ENABLE_ATT1=0
+ bybot systemd flag changed; risk0.10/core/management preserved. Old PID exited.
Retirement clock02:38:58UTC, H1fence03:00UTC; separate non-root public observer is
running, **1/96 actual common closedM5**, earliest96 at11:00UTC conditional on data.
This is not actual handoff readiness or a money GO; historical state staysUNKNOWN.

Signed03:02UTC eight-symbol pass captured all taker0.00055/maker0.0002 fees.
SUI passes current one-way validator; six duplicatedidx0 sources reject, LINK1/2/0
remains MODE_CONFLICT. No dedup/mode write/universe change. Per-symbol14day funding
stress sourced, policy/price envelope/minqty viability unapproved. ADA MLid86 OPEN
still conflicts with flat broker; no label rewrite or all-history finality claim.
Next: bounded duplicate-source handling/LINK, ADA86/current cash/finality, viable
funding/quantity policy and selected-account protection/exit/finality ordersOFF
integration while the observer collects. Do not restart Tasks1–4 or OLD archives.

Public02:55UTC **6sessions/34records/2filled simulations/4nonfills/2gaps/0clean/0held**,
PID1584802/epoch/2s/one journal unchanged, broker/ordercalls0. Both fills gap-tainted;
no clean/net-R evidence. Gate2–3clean +actual packet+fresh OLD absolute-risk
comparison/exclusive dossier+separate ownerGO remains. Alpaca same3fractions,
HWM/floor exactly same,58hashes/one NEW manager, **0 active stops** afterDAY expiry;
Oct5 13:30UTC/16:30Cyprus re-armP0/NOT_DUE, queuedDAY PAPERNOT_PROVEN. No change.

Local97targetedPASS; VPS13guard+15observerPASS; actual6-astra/high review verified.
Final full3440PASS/58FAIL:57 old baseline +one unchanged-HEAD Alpaca PAPER failure
reproduced on today's clock. No unexpected added regression; suite is not green.
Foreign allowlist originalSHA restored/unstaged. AI stays on-demand/proposal-only,
$1/UTCmonth, no new paid calls/features/schedule; Telegram delivery still untested.
Claude registry/Factory not rechecked or changed this cycle; Oct3 snapshots remain
historical. Rollback never restores OLD entry authority automatically.

Earlier dated snapshots below are retained history, superseded by this delivery.

Latest actual input update **October3 11:24UTC**:
`AI_ANALYST_AND_ATT1_INPUTS_DELIVERY_2026_10_03.md` binds the signed collector
receipt. Full LINK pagination contains1/2 then0 -> BLOCKED_MODE_CONFLICT. HFT
instrumentClosed -> BLOCKED_CONTRACT_INELIGIBLE; fee remains unknown. Collector
is local/isolated-target only, no mode write, universe change or money install.
OLD native new-entry pause confirmed after guarded same-core AI reload at11:10UTC:
bybotPID1623970, signedpositions0/orders0. Heartbeat sleeve `att1` is OLD, not NEW;
open_trades0 is exposure evidence, not the cause of no entries. Native pause is
not durable retirement. Actual retirement/96-bar quarantine, reviewed mode /
contract handling, funding policy and selected-account lifecycle remain BLOCKED.
Public11:15UTC samePID1584802/epoch:4sessions/1filled SEI/3nonfills/1gap/0clean/
0held,0broker/ordercalls. Preserve original gap; no fresh epoch manufactured.

Owner accepted the existing fresh-epoch direction for orders-OFF implementation
on October3. Scope: the existing preparation/route boundary. Tasks1–4, strategy,
public epoch,2s freshness, risk caps and money authority remain unchanged.

Implemented interfaces:

- `validate_canary_fresh_handoff` / `bind_canary_fresh_handoff` in
  `bot/att1_canary_preparation.py` validate explicit `COLD_96_CLOSED_M5_V1`.
- `prepare_att1_fresh_cutover` in `bot/att1_coordinator_adapter.py` atomically stores
  the declaration and its evidence in the existing local route ledger.
- Existing entry preparation/command capture and cash-aware reservation consume
  the new binding. Legacy handoff validation still requires genuine watermarks.

Required declarations are source-bound, not self-authenticating. Fresh signed
collector/review provenance is still required for actual-account use. A policy
approval hash records migration acceptance; it is never owner money GO.

## Preparation sequence

1. Verify durable OLD entry retirement: effective existing entry guard disabled
   across reload/startup, native pause readable, entry restart denied and management
   preserved. Supply a complete current intent/finality/cost inventory and fresh
   authenticated flat/no-orders. No runtime retirement write was performed here.
2. Declare account, exact frozen profile and preparation implementation pins,
   approved-policy source, retirement clock and `legacy_state=UNKNOWN`.
   The H1 fence is the next H1 boundary at/after retirement, backed by actual
   availability. No fabricated `last_old_h1_ms` or OLD cooldown.
3. Supply actual closed M5 timestamps and source hashes after the fence, with a
   current complete capture. Require96 consecutive closes; gaps restart the
   pre-completion count, duplicates/future bars deny. Later observations preserve
   the first proven completion. The eligible signal cutover is its next/equal H1
   boundary. Missing/latest-stale data still denies current preparation.
4. Persist only into a disposable/local orders-OFF coordinator for acceptance.
   A live/occupied route or unresolved costs deny the transaction. NEW_READY is
   preparation only; no production DB migration or transport is installed.
5. Bind fresh existing budget/cash inputs and the exact declaration before captured
   command preparation. OLD re-enable, late drain, changed/missing epoch, wrong
   account/code/profile, stale evidence or budget failure denies. Existing uncertain
   prepared commands remain recovery-owned and return lookup-only after restart.

## Actual packet blockers — do not turn declarations green by hand

- Actual durable entry retirement/quarantine provenance is not yet collected.
- LINK repeatedly exposes hedge indices1/2; current command/binding require
  one-way positionIdx0. Global flat and the terminal placeholder row do not solve
  that conflict. No broker mode was switched or universe filtered.
- The source-bound funding policy for frozen14-day hold is unresolved. Captured
  full-limit stress at full draft R0.4/minimal notional5 exceeds D0.8 for OLD8.
  Smaller quantities can differ; no risk increase/hold change/latest-rate shortcut.
- HFT is broker-reported `Closed` at11:24UTC; symbol-scoped fee GET rejected.
  Missing fee is not zero cost. Reviewed ineligible-contract handling is required;
  no guessed fee, universe removal or frozen-profile change was performed.
- Existing selected-account GET/capture/recovery code is retained. Autonomous
  money dispatch/protection/exit/finality integration remains a separate delivery;
  this cold-path implementation does not claim it is finished.

Actual-account archive is **BLOCKED_ACTUAL_INPUTS**, not BUILD_READY. No actual
packet was manufactured from synthetic declarations. Latest public11:15UTC
snapshot is4sessions/1filled SEI/3nonfills/1gap/0clean/0held and0broker/order calls.

Rollback remains NEW ordersOFF; do not automatically resume OLD entries. If any
future exposure exists, preserve its owning protection/exit manager. Flat rollback
requires fresh authenticated absence of exposure/orders and captured finality.
Gate2–3 clean prospective filled terminals/net-R, fresh exclusive dossier and
separate owner money GO remain unchanged.
