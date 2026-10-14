# Alpaca Oct15 final LIVE static preflight

**STATIC_PREFLIGHT_PASS — 2026-10-14. PREPARED / NOT ARMED; LIVE HALTED.**

The installed source, first-intent wiring, explicit failure branches, retained actual payloads and no-send path have been checked. No known unresolved static material defect remains in the scoped first-entry path. This is an engineering verdict, not owner GO, tomorrow's broker truth, a completed LIVE fill, or a profitability claim. Code is frozen after this result until the Oct15 fresh preflight; no additional PAPER/statistical/research gate is introduced.

## Exact source and intent

| Item | Pin / scope |
|---|---|
| Original 37-file trading package | `0a3fce3b3d1af18060c2e5e4fdf787828e12eaf803df15b847df78a613187f20`, unchanged |
| Actual final PAPER receipt | `70f5a03d24cad443957fab62b02cba95b758c88024d46343d803cfdbe30c1888` |
| First intent | `198903481c94357e3ae76d11688aa23f9a8740f2515062a64c7c267f0600f2fd` |
| Static binding | `47cc8ce61750bd32d981f3ba7ed93e2096fdaf607bb8c8bd50d123dfea294c62` |
| Corrected separate control | `/opt/bybot-research/alpaca-dynamic-live-20261013/control/oct15-first-entry-v1-1` |
| Control spec | `3d92ae10124a208f3e4eebfac15d28a0745ac53a72f4e1e7f86103c2b946f074` |
| Target | NET, Oct15, 13:30–13:35 UTC / 16:30–16:35 Asia/Nicosia |
| Envelope | qty ≤ 0.469970151; notional ≤ $124.699999985736; modeled stop risk ≤ $10.906127324106; limit ≤ $349.82 |
| Preserved policy | capital $487.42, gross 0.70, max positions 4; frozen ranking and reference risk distance 33.54241333009 |
| Reserve / attempts | actual sourced CAT reserve reduces spendable cash; current bound $0.01; one attempt, no reprice/repeat/carry |

All four envelope bounds apply simultaneously. Maximum qty is not a requested qty. Modeled stop risk is the fill-relative stop distance, not a guarantee against market gaps/slippage.

The original app and fee kit were not patched in place. The executable launch target loads the pinned clock-corrected runtime overlay from the separate control; it reuses the unchanged planner, compiler, first-intent validator, native bridge and ratchet. The publisher is the unchanged pinned definition from the sealed 81-file app, not that app's PAPER opener/guard. The old unregistered 120-second draft templates and the failed bootstrap draft are retained history and are **not** tomorrow's launch target.

Exact executable/static hashes and sanitized observations: [source contract](evidence/alpaca_oct15_final_preflight_20261014/source_contract.json), [installed readback](evidence/alpaca_oct15_final_preflight_20261014/installed_static_receipt.json).

## Static defects found and resolved

| Defect | Reproduction / narrow correction | Proof |
|---|---|---|
| Invocation time used as observation time | A normal later fill was called future; slow GETs caused false broker-clock conflicts. Use elapsed monotonic time at the actual receive/use phase, including initial stop handoff, maintenance, exit and final pre-dispatch clock. Same 5s broker-clock and existing quote/window gates. | `test_actual_fill_after_call_start_is_checked_at_receive_time`, `test_maintenance_clock_uses_current_observation_after_gets`, `test_preflight_http_elapsed_is_not_broker_clock_drift` |
| Missing first-intent→source-plan→intake wiring | No approved first plan existed in the independent LIVE book; draft service referenced nonexistent session intake/GO files. Preview unchanged planner in a SQLite RAM backup; only external exact GO plus nonhalted account permits the real reservation/export; invoke original runtime once through OpeningDispatcher. | RAM replay on real installed book; `test_post_go_whole_control_path_reserves_once_and_protects_once` |
| Isolated bootstrap | First separate draft failed `No module named research_lab` before any network/reservation. Explicit pinned `app_root` added before imports. Failed draft retained. | Actual v1.1 VPS prepare/ready/no-GO execution; isolated `python -I` subprocess regression |
| Service could kill protection | Old draft `TimeoutStartSec=120` could terminate an already accepted entry while protecting it. New inert oneshot templates use `TimeoutStartSec=infinity`, `Restart=no`; existing pre-dispatch budgets stay enforced. | Actual `systemd-analyze verify` exit 0 for correctly named entry/manager services and timers, no stderr; protection/restart/timeout tests |

These changes do not change selector/ranking, risk, stop floor, caps, fee schedule or strategy mathematics. A definitive broker 422, uncertain POST/PATCH/DELETE, partial fill or unknown ownership retains the original fail-closed/scoped recovery behavior.

## Actual installed checks and replay

- Initial installed capture at Oct14 14:52:42.894 UTC: all original package pins match; account flat/open orders 0; NET asset eligible; original HALT present; no Dynamic LIVE runtime DB; source intents 0 / attempts 0. This dated broker state is not tomorrow's state.
- Corrected control actually ran `--prepare` → `STATIC_PREPARED` and `--ready` → `READY_TO_DISPATCH`. These metadata states grant **no operational/order authority**. No GO/session intake/reservation was created.
- `--entry` with no GO returned `BLOCKED_DATA: SEPARATE_EXACT_OWNER_GO_REQUIRED` before publisher/network/source-book writes.
- `--rehearse` on the retained Oct14 source at its actual time returned `NOT_SELECTION_WINDOW`, correctly. It did not pretend October14 was October15.
- Separate explicitly counterfactual-clock RAM replay exercised the exact **unchanged** Oct15 intent and installed source book. Retained price $349.82 produced qty **0.325167779**, notional **$113.75019244978**, reference stop **$316.28**, distance **$33.54**, modeled risk **$10.90612730766**. $349.83 rejected `FIRST_INTENT_PRICE_CAP` before writing. No future-price claim, real GO, reservation or broker call. Book bytes/HALT bytes and counts remained unchanged. [RAM receipt](evidence/alpaca_oct15_final_preflight_20261014/ram_replay_receipt.json).
- Actual retained entry/re-arm/exit/activity/cash payloads were replayed OFFLINE again: `PAPER_EXECUTION_PASS`, actual fees **$0.03**, net **−$4.535524745824**, raw files unchanged. Timestamp precision/source metadata comparator preserves the entire raw payload and rejects material identity/fill/ownership differences. [Actual payload replay](evidence/alpaca_oct15_final_preflight_20261014/real_payload_replay.json).
- Final installed readback at Oct14 **16:17:02.993 UTC /19:17 Cyprus**: original37 and all53 control static pins match; original HALT/native empty ledger/crontab unchanged; source intents/attempts 0; no runtime DB, GO or session directory. All four proposed Oct15 units `not-found`, no activation. Production Bybit PID1648585, web1623208, ATT11584802, NRestarts0 unchanged. This final check had **no broker query**.
- Targeted verification: **279 passed / 0 failed**, including a synthetic whole control path with one reservation, one BUY, full STOP and duplicate refusal. Synthetic permits/broker writes exist only in pytest temporary fixtures. Prior non-green full suite was not rerun and is not represented as green.

## Post-GO path and failure boundaries

| Stage | Actual code / outcome |
|---|---|
| 1. Explicit owner GO | Existing `intent_permit` requires exactly the first-intent GO schema/account/endpoint/session/intent/static binding/text. A declaration, old monthly GO or generic `--apply` cannot authorize this entry. |
| 2. Operational arm, before opening | External human-approved operator creates exact GO JSON, archives only this original HALT under the original writer lock and registers/arms only the four prepared units below. No automatic HALT clear exists in the driver/runtime. |
| 3. Static custody | `control.load_spec` checks actual files before import; `OpeningDispatcher` compares prepared policy/checks/source-book/static pins; drift blocks before market/plan writes. |
| 4. One-session opening | Existing controller checks prepared/ready, no previous terminal/adapter invocation/source reservation, known calendar and remaining budget. Latest start is **strictly before 13:32:25 UTC /16:32:25 Cyprus**, not 16:35. |
| 5. Fresh publisher | GET account/cash/liabilities, positions/open orders, NET asset and raw quote CTS; use pinned protocol/calendar/gates. Unknown, stale/future, changed survivor, fee/cash conflict or source truncation blocks. |
| 6. Exact preview and reservation | `preview_snapshot`: original `_propose` in RAM → unchanged `compile_intake` → `check_first_intent`. Only valid exact external GO + absent HALT + original account lock allows `DynamicBook.propose` and exclusive session export. Compare the actual plan to preview. |
| 7. Durable adapter boundary | Controller persists `invoking_adapter.json` before the sole invocation. A crash/restart does not invoke the entry adapter again. |
| 8. Runtime source/GO/lock | `run_once`: custody, exact active plan and binding, external GO, original writer lock, durable LIVE state, original profile/account. Recheck clock/window, asset, positions/orders, cash/liability/gross/slot/session/client IDs, raw CTS. |
| 9. BUY and readback | Persist exact dispatch before POST; quantity LIMIT/DAY only. No uncertain resend. Terminal no-fill gives `LIVE_NO_FILL_TERMINAL`; proven partial entry cancels remainder once and protects exactly the proven fill. |
| 10. Immediate protection | Freeze fill-relative cent-rounded stop using unchanged risk distance. Persist pending native lineage; exact STOP/DAY fractional quantity; readback/ownership/floor/remaining validation. Definitive 422 uses existing scoped emergency unwind. Unknown response is not called protection PASS and is not blindly resent. |
| 11. Owned management | Same account lock/runtime/GO/lineage; full remaining quantity, HWM/floor monotonicity, native ratchet. Original HALT blocks new entries but does not disable owned management. |
| 12. DAY re-arm | Actual broker clock/session; proven old terminal unfilled stop only; deterministic per-day cid; same accepted floor. Below floor/definitive 422 uses scoped unwind; uncertainty requires source reconciliation, no lowered stop/retry. |
| 13. Exit/kill | Only the owned quantity/IDs. Cancel only proven owned stop; wait for terminal cancellation; no market sell while replacement/stop/cancel status is unknown; exact remaining quantity, no second exit. |
| 14. Finality | Exact actual exit orders and source-pinned fees/cash/liabilities; flatness is not cost finality. Exit pending finality is explicit; source late arrival does not create another order. |

**Complete matrix:** [late_blocker_matrix.csv](evidence/alpaca_oct15_final_preflight_20261014/late_blocker_matrix.csv) and [branch_inventory.json](evidence/alpaca_oct15_final_preflight_20261014/branch_inventory.json): **318 explicit fail-closed/reject sites across114 reachable functions**, exact file/function/line/condition/reason, materiality, STATIC/FRESH_ONLY/FUTURE_ORDER_EVENT/OWNER_ACTION, status and test references. Parameterized reasons are retained rather than silently collapsed. Generic exceptions, OS/SQLite/network failures route to the recorded outer BLOCKED boundary; this is not a claim that every possible machine failure was injected or every branch achieved coverage. Direct literal tests and subsystem checks are distinguished. Unused monthly main/PAPER sender/selector/judge paths are outside this launch graph; the base HTTP implementation overridden by DynamicLiveClient is excluded.

Known representational differences in the old PAPER JSON are already resolved by the versioned REG/execution comparator. They are not new trading blockers. Material ID, symbol, side, qty, fill, type/status, ownership, cap or causal-time changes still block.

## Finite checks requiring Oct15 state

No more static build/research work is scheduled. Only these existing conditions remain:

1. **Owner action:** separate exact human GO after the fresh bounded dossier; original HALT remains until that approval. Missing GO means no arm/order.
2. **Fresh operational custody:** pinned files/profile/source book/native ledger, original lock available, competing entry/manager authority still retired, no unexpected writer/unit or booked attempt. Drift must be sourced; no automatic repair in the opening window.
3. **Fresh account:** same LIVE account ACTIVE/unblocked; actual flat/no open orders for this first-entry template; cash/nonmarginable cash, published pending/accrued liabilities and CAT reserve support the actual size. Unknown is not zero.
4. **Fresh NET asset/price:** tradable/fractionable, raw exchange quote CTS and receive lineage within unchanged max age, positive ask, existing earnings/concentration/reentry/protection eligibility. IEX quote is not NBBO. Fresh ask >$349.82 or any envelope/cap/minimum failure rejects this intent; do not change price/risk or choose another ticker.
5. **Actual opening clock/timing/transport:** original session/open flag, broker clock within5s, budgeted fresh/reserve/preflight completion; current source/transport availability. No start at/after16:32:25. No late/date-transferred attempt.

Actual order acceptance, partials, stop ACK, future DAY expiry/re-arm/exit and posted LIVE fees are **future order events**, not a new pre-entry PAPER/statistical gate. Their handlers have been checked; their future outcomes cannot be certified today.

## Oct15 operational runbook — existing code, no coding in the window

**Before16:15 Cyprus:** one bounded fresh read-only preflight of the above sources; read the fixed control spec by its pin. Show the owner NET, actual current CTS/ask, provisional unchanged-planner sizing and all envelope bounds. A projected-clock RAM preview must be labeled provisional; only opening data creates the actual source plan. No rescan/retune. Today's prepared/ready receipts already exist; **do not rerun `--prepare`** (its timestamp is immutable).

After direct human approval, the exact required text is:

```text
GO ALPACA_DYNAMIC_FIRST_INTENT_V1 198903481c94357e3ae76d11688aa23f9a8740f2515062a64c7c267f0600f2fd
```

This text has **not** been received. Do not execute the activation recipe below until the direct human approval and fresh preflight are present. Copy its provenance into the private operational receipt, not into a generated self-approval.

The exclusive private `CONTROL/session/owner-go.json` must contain exactly these values from the pinned `first-intent.json`:

```python
owner_go = dict(
    schema='ALPACA_DYNAMIC_FIRST_INTENT_OWNER_GO_V1',
    account_id=intent['account_id'], endpoint=intent['endpoint'],
    intent_sha256=intent['intent_sha256'],
    static_binding_sha256=intent['static_binding_sha256'],
    session=intent['session'],
    owner_go_text='GO ALPACA_DYNAMIC_FIRST_INTENT_V1 '+intent['intent_sha256'])
```

There is no `native_manager_source_sha256` field in this GO record; that pin is already checked inside the intent. Use the existing `write_new`/canonical JSON helpers, mode0600/O_EXCL, and preserve the approval receipt. Never overwrite/reissue a GO for another session. No session intake/binding is manually fabricated: the original planner/compiler assembles them at opening.

**Arm procedure after GO, completed before16:29:** reuse `control.load_spec` and the existing runtime `account_lock(binding)` with the original lock path. Under that lock, recheck the original HALT scope/pin, current LIVE flat/no-orders, empty native ledger and unused source/runtime books. Create the exclusive GO file; install only the fixed templates with the following mapping; daemon-reload and verify the new units remain disabled/inactive before final arming. The old monthly cron stays retired, old profile stays unchanged, and no old manager is activated.

| Inert source under CONTROL | Exact target in `/etc/systemd/system/` |
|---|---|
| `entry.service` | `alpaca-oct15-first-entry.service` |
| `activation-entry.timer` | `alpaca-oct15-first-entry.timer` |
| `manager.service` | `alpaca-oct15-owned-manager.service` |
| `manager.timer` | `alpaca-oct15-owned-manager.timer` |

These exact source templates were syntax-checked together under the target basenames with `systemd-analyze verify`. Do not use the old generic `alpaca-dynamic-live-*` templates, the failed v1 draft, or direct `run_alpaca_dynamic_live_v1.py` entry: they do not load this corrected control overlay.

Archive the original HALT **only after GO and the locked fresh checks**, retaining its bytes/hash/provenance in the private session custody. This is the separately owner-approved activation step, not something `--entry` automatically performs. Never edit its account/reason to impersonate another state. Enable/start only `alpaca-oct15-first-entry.timer` and `alpaca-oct15-owned-manager.timer`, then immediately read back their exact unit pins, next elapse, active state and ownership. The entry timer has `OnCalendar=2026-10-15 13:30:00 UTC`, `Persistent=false`; manager runs at existing5-minute cadence. **Do not manually start the entry service while arming.** If arming fails or misses the deadline before any entry, stop only this entry timer, restore this scoped HALT, preserve the partial receipt and return BLOCKED; no automatic activation retry or date transfer. No stopped account-wide lock/manager/guard is replaced by another authority.

Arming is an operational action after owner GO; its success is not claimed in this static report. Today no unit has been registered/started and HALT has not been archived/cleared.

**16:30:** the timer invokes exactly:

```text
/root/by-bot/.venv/bin/python -B /opt/bybot-research/alpaca-dynamic-live-20261013/control/oct15-first-entry-v1-1/control-v1.py --spec /opt/bybot-research/alpaca-dynamic-live-20261013/control/oct15-first-entry-v1-1/spec.json --entry --owner-go /opt/bybot-research/alpaca-dynamic-live-20261013/control/oct15-first-entry-v1-1/session/owner-go.json
```

Opening critical path: mandatory fresh GETs≤30s → exact preview/reserve/export≤5s → original runtime final preflight allowance120s → one BUY → protection/readback. No document reading, source reconstruction, broad tests, helper coding or model review. Actual step times/receipts are persisted by OpeningDispatcher. Once an entry has been accepted, no opening/systemd hard deadline aborts its protection.

**After the attempt:** read `CONTROL/dispatch/{fresh,reserve,invoking_adapter,terminal}.json`, private session intake/binding, durable `binding.runtime/live.sqlite`, native ledger and exact broker orders. `OPENING_PATH_COMPLETED` alone is not a filled/protected LIVE claim: inspect `execution.status`. Report ENTRY_PROTECTED / NO_FILL / exact BLOCKED. Never restart/reinvoke the entry service after uncertain dispatch. Owned recovery is the manager path using the same GO/intake/binding and original lock.

**Owned maintenance / kill** (after an actual owned entry; never for legacy holdings):

```text
/root/by-bot/.venv/bin/python -B CONTROL/control-v1.py --spec CONTROL/spec.json --maintenance --owner-go CONTROL/session/owner-go.json
/root/by-bot/.venv/bin/python -B CONTROL/control-v1.py --spec CONTROL/spec.json --kill --owner-go CONTROL/session/owner-go.json
```

Substitute `CONTROL` only with the pinned v1.1 directory above. `--kill` uses existing scoped cancellation/unwind, not account-wide flatten. Keep owned manager active through uncertainty/HALT and until terminal exit/cost reconciliation. If an unknown stop/replacement/cancel exists, preserve HALT and obtain authoritative readback; no blind POST/PATCH/DELETE or downward floor change.

**Actual LIVE cost closure after an owned terminal:** use the existing `scripts/run_alpaca_dynamic_live_v1.py --maintenance --cost-finality <actual source-pinned closure> --apply --owner-go <same GO> --first-intent <same intent>` interface, bootstrapped through `control.load_spec` first so it uses the corrected runtime overlay. Do not invoke the old CLI directly in a fresh process without this bootstrap. The entry/maintenance driver intentionally does not synthesize or supply a fee closure. No fee is inferred from flatness. Exact prewritten bootstrap (after terminal, not opening):

```python
import importlib.util, sys
from pathlib import Path
control_root = Path('/opt/bybot-research/alpaca-dynamic-live-20261013/control/oct15-first-entry-v1-1')
x = importlib.util.spec_from_file_location('pinned_control', control_root/'control-v1.py')
control = importlib.util.module_from_spec(x); x.loader.exec_module(control)
spec = control.load_spec(control_root/'spec.json')
from scripts.run_alpaca_dynamic_live_v1 import main
main(['--policy', spec['policy'], '--binding', str(control_root/'session/binding.json'),
      '--intake', str(control_root/'session/intake.json'), '--live-profile', spec['live_profile'],
      '--first-intent', spec['intent'], '--owner-go', str(control_root/'session/owner-go.json'),
      '--maintenance', '--apply', '--cost-finality', sys.argv[1]])
```

`sys.argv[1]` must be the independently source-pinned actual account/day finality file. The existing runtime checks exact orders/raw pins/cash/liabilities before releasing final net accounting. This is the already required terminal accounting path, not an additional entry gate.

**Rollback:** before a fill, disable/stop only the Oct15 entry timer and restore the scoped HALT; no alternate entry. After a fill, first block entries, preserve lock/GO/intake/ledger/book and keep owned maintenance; do not stop the manager or restore the old monthly manager while a position is unprotected/uncertain. Use the existing owned kill path if the approved safety action requires exit. Disable this manager timer only after proven flat/no open owned orders and retained terminal receipt; posted costs remain explicit until their actual source closes.

**No GO / fresh rejection / expired window:** no order. Preserve the terminal reason and spend no new PAPER/research cycle on it. This intent is not transferred to another session.

## Verification command and freeze

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -q tests/test_alpaca_first_entry_control_v1.py tests/test_alpaca_first_entry_assembly_v1.py tests/test_alpaca_live_observation_clock.py tests/test_alpaca_dynamic_live_runtime_v1.py tests/test_alpaca_dynamic_first_intent_v1.py tests/test_alpaca_dynamic_live_intake_v1.py tests/test_alpaca_open_dispatch_v2.py tests/test_alpaca_live_readiness_v1.py tests/test_alpaca_fee_to_live_closure_v1.py tests/test_alpaca_execution_identity_v1.py tests/test_alpaca_posted_fee_reg_v3.py tests/test_alpaca_protective_exit_manager.py
```

279 PASS. Root review only; no independent reviewer quota replacement. Source contract pins code and installed custody, not a promised future market result. From this point code is frozen until the Oct15 fresh preflight. Claude's checkout/processes, KITY sources/timing, ATT1 and Liquidation were not changed. No new strategy, judge or money authority.
