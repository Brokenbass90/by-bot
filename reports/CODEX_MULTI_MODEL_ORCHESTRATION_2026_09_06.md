# Codex multi-model orchestration — 2026-09-06

## Current verified state

September 7 continuation evidence:
`research_lab/results/codex_orchestration_20260906/runtime_children_20260907.json`
confirms Alpaca mechanical work on Luna/medium, L3 implementation on Terra/high
and independent financial review on Astra/high in both runtime metadata and
rollout contexts. Two Luna follow-ups hit usage-limit errors after useful work;
they were not retried or replaced by an expensive mechanical worker. The root
independently checked the patches and closed integration/documentation. This
does not establish the billing reason for the errors; no reset was consumed.

The local Codex app/runtime supports stable `multi_agent_v2`: app
`26.901.51231`, build `8109`, CLI `0.153.4`. The feature is enabled by the
scoped project configuration for the parent workspace and canonical
repository. The canonical repository was explicitly trusted; the parent
workspace was already trusted, and other global configuration was preserved.

The final runtime receipt is
`research_lab/results/codex_orchestration_20260906/runtime_verification_final.json`.
It verifies explicit dispatch of Luna with medium effort and Terra with high
effort in SQLite thread metadata and rollout `turn_context`. This is local
runtime/rollout evidence, not billing-level attestation; measured savings are
not available. The root model remained unchanged. Explicit model/effort
overrides are verified; the parent was not restarted, so hot reload of defaults
is not proven.

The post-config child verification receipt is
`research_lab/results/codex_orchestration_20260906/post_config_child_verification.json`.
The specified child thread is recorded in SQLite as `gpt-5.6-luna` with
`medium` effort, and its rollout context records the same dispatch. The parent
was not restarted, so this proves explicit per-spawn runtime dispatch and does
not prove hot reload of persisted defaults.

The official configuration references used for the project-loading/defaults
interpretation are [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic)
and [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents).

The superseded `runtime_verification.json` recorded the feature as disabled/not
loaded because the canonical repository was not yet trusted; the binary already
supported stable v2. That configuration/trust
history is separate from the first onsite evaluator receipt, whose
`FAIL_CLOSED` result was caused by the UTC alias bug. Both prior receipts remain
preserved. The alias is now fixed and the evaluator has 34 passing evaluator
tests; neither history is erased or rewritten.

## Scope and authority

This update concerns orchestration evidence only. It does not change the
ATT1/ETS2S deployed release, VPS files, service, configuration, risk, orders,
money authority or shadow behavior. The synthetic L2 exposure core is
implemented and critically reviewed with no slice blockers; see
`reports/ATT1_ETS2S_L2_EXPOSURE_CORE_2026_09_06.md`. Full L2/L3 parity and L2
PASS remain unclaimed.

## Evidence files

- Runtime/config receipt:
  `research_lab/results/codex_orchestration_20260906/runtime_verification_final.json`
- Corrected aggregate-only onsite receipt:
  `research_lab/results/att1_ets2s_burnin_20260906/onsite_receipt_20260906T141756Z.json`
- Post-config child verification:
  `research_lab/results/codex_orchestration_20260906/post_config_child_verification.json`
