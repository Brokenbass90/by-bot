# Monthly production entrypoint: bounded independent review

Date: 2026-10-20. Base: `230106b7c4ee9b3cf3f65d91ad0c991181283758`.
Verdict: **no unresolved Critical/Important finding in the narrowed entrypoint commit scope after the direct fixes**. This is engineering review for ORDERS_OFF delivery, not financial activation or full unattended-lifecycle acceptance.

Scope: entire uncommitted change in `scripts/run_alpaca_monthly_cycle_v1.py`, `scripts/run_alpaca_dynamic_live_v1.py`, `research_lab/alpaca_monthly_release_v1.py`, `scripts/rehearse_alpaca_monthly_cycle_v1.py`, and new `tests/test_alpaca_monthly_production_runner_v1.py`, plus directly relevant existing custody/dispatcher/transport/notification interfaces. The prior accepted 274-test component was not re-audited. No tracked files edited by reviewer.

## Important finding reproduced and fixed

**P1: a dispatch failure after an actual broker write falsely reported zero writes.** Original `main()` exception handler at lines 175–177 reused the disabled CLI receipt's unconditional `broker_writes=0`. A final `DISPATCH_TICK` receipt write failure can occur after maintenance has submitted an owned DAY stop.

Independent offline reproduction used the real CLI, dispatcher, native maintenance and restricted transport with memory-only HTTP: one stop POST occurred during the tick, then the injected final receipt OSError produced `MONTHLY_CYCLE_BLOCKED` with `broker_writes: 0`. Reproducer and original evidence are private `test_review_failures.py` and `failure-repros.log` retained in the local audit directory. That historical repro intentionally asserts the old defect; do not count it as a current green test.

Root's direct fix tracks dispatch start, emits `broker_writes: null` and `broker_write_count_source: EXISTING_OWNED_DISPATCH_JOURNAL` on dispatch failure, and retains known-zero receipts before dispatch/default mode. Independently re-ran public regression `test_dispatch_record_failure_after_write_never_claims_zero`; it passed in the post-fix targeted suite.

Root also identified invalid owner-GO failures reaching notification configuration before authentication. Reviewed the direct fix: CLI captures `trusted_notifications` only after `runner_authority` succeeds for dispatch. Independently re-ran `test_unapproved_dispatch_cannot_use_notification_configuration`; passed. Finding attribution remains root's, not an independent reviewer discovery.

## Reviewed boundaries

- Disabled/default and source schemas remain false-authority. `--dispatch` needs the distinct runner schema, exact implementation closure, owner scope/GO and separately bound operational configuration. Changing authority paths does not create a scope/spec hash cycle; operational manager, source, profile, native binding, costs and notification inputs are covered by the runner-config digest.
- Complete standing custody checks for account/book/runtime, original lock identity, strategy/code pins and limits precede production profile loading/transport construction. Expiry/revocation remain entry-only checks so unchanged owned maintenance can continue.
- The runner reuses `MonthlyManager.tick`, its dispatch lock, existing book/native journals, original account lock, recovery, maintenance and automatic cost producer. Maintenance precedes cost/source callback failure. There is no added retry loop, ownership migration or legacy NET adoption path.
- Original profile directory, exact LIVE endpoint and account lock checks remain in the shared profile loader. Its optional Monthly contract selects the existing restricted serializer; the default Dynamic contract is unchanged. Per-write exact permits and actual account checks remain in existing native paths.
- Normal applying receipts use the existing journal as the write-count authority. Notification results retain unknown delivery and durable no-retry semantics; claims/receipts are not removed or retried by the new CLI.
- Unit templates retain a disabled source service and one manager service. Dispatch uses its separate pinned spec only when explicitly supplied. No install/enable/mutation code was added. Existing rollback rejects exposure, pending dispatch or accounting uncertainty.

## OPEN handoff acceptance before LIVE

Per the owner's narrowed first-commit scope, fresh proof that the legacy Alpaca manager and its timer have relinquished ownership is a separate **OPEN handoff/activation gate**. The account lock serializes operations and foreign-exposure checks reject adoption; neither proves a legacy scheduler cannot run again later. This entrypoint commit must not be described as complete autonomous activation or full single-manager handoff acceptance. Exact legacy-service/timer retirement proof, NET flat/identity handling, rollback continuity and bounded standing owner packet remain required before LIVE. No such production proof was collected in this review.

## Reproducible verification

Commands from repository root:

```sh
.venv/bin/python -B -m pytest -q tests/test_alpaca_monthly_production_runner_v1.py tests/test_alpaca_monthly_release_v1.py tests/test_alpaca_monthly_notifications_v1.py -k 'not full_frozen'
```

Post-fix result: **15 passed, 1 deselected in 8.24s**, `targeted-tests-after-fixes.log`. Original pre-fix suite: 13 passed, 1 deselected in 5.61s, `targeted-tests.log`; these overlap and must not be added.

```sh
.venv/bin/python -B -m pytest -q tests/test_alpaca_monthly_standing_v1.py tests/test_alpaca_monthly_account_transport_v1.py -k 'expiry_or_revocation_keeps_owned_maintenance or any_revocation_marker_blocks_buy or original_account_lock_prevents_second_writer or existing_transport_can_explicitly_select_monthly_wire_without_relaxing_default or monthly_live_custody_scope_cannot_be_reused_or_changed or legacy_live_approval_cannot_activate_monthly'
```

Result: **13 passed, 47 deselected in 5.44s**, `targeted-boundary-tests.log`. These are targeted existing boundary regressions, not a repeat of the accepted base suite. `git diff --check` passed.

The full frozen58 actual-CLI/default-loader E2E was deliberately excluded to avoid duplicate heavy work. Parent reports PASS in 264.07s; this reviewer read its fixture wiring but did not execute that E2E or independently attest the parent's receipt. No network, real profile/credentials, broker/VPS calls, financial activation, systemctl or runtime unit changes. Unrelated allowlist and PUMP4 files untouched. Runtime model/effort verification belongs to root; this report makes no self-attested model claim.

## Reviewed file hashes (SHA-256)

```text
967f55921ad64c271481d32744887bdc6ef0b671d72ae82332290fcb35ac0fcc  scripts/run_alpaca_monthly_cycle_v1.py
c90d120a43044d00c0a47e101e428eb0aef75474b321c192b5514addeecb3522  scripts/run_alpaca_dynamic_live_v1.py
b36c3c3a4e925423107e2b1884a0470128e2b69555e3ab3d88d7623b61c12e57  research_lab/alpaca_monthly_release_v1.py
de7bff9172027e2d76baa3ad5b5fcddc7a67608f5d9d8fb471d85bb046589c3e  scripts/rehearse_alpaca_monthly_cycle_v1.py
6bdd81ac0c7a3db0746b3ea8e8c409f736980248f53bedf24c20e4f0a01978f6  tests/test_alpaca_monthly_production_runner_v1.py
```

Root evidence update: five profile/default-alert boundary test cases were added
after the source review without changing the reviewed runtime bytes. Final exact
local/server results are reported separately, not attributed to the reviewer.
