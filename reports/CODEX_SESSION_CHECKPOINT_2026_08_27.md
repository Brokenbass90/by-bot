# Codex checkpoint — 2026-08-27

## Outcome

This session preserved the live system, did not change money/risk/orders, and
turned the next ATT1/SBR1 release step into a fail-closed, reviewable package.
Reserved market rows were not decoded.

## Completed

1. Corrected reserved-window truth: exact range is `[2025-10-01, 2026-07-01)`,
   273 days, and it is **known contaminated** by prior MPL/XSEC reads. Future use
   is diagnostic, not pristine sealed proof.
2. Added metadata-only preflight with exact candidate/source pins and three honest
   blockers: missing exact M5 manifest, frozen one-shot runner, independent audit.
3. Independent review found a fail-open in the first preflight version. Added
   negative tests, exact path allowlists, mandatory claim/refusal/owner flags,
   metadata-manifest schema validation and implementation SHA. Current preflight
   remains `BLOCKED_FAIL_CLOSED` and reports zero market rows/files read.
4. Added frozen BTC/ETH ATT1 attribution for `[2024-03, 2025-10)`: BTC positive
   but low `N=12`; ETH negative at `N=17`; BTC+ETH stress approximately flat.
   Inputs are now exact SHA-pinned and output is atomic. No symbol was removed.
5. Re-ran secret-free `verify_live_config_gate.py`: fixed-51 evidence contract
   `PASS`, no broker access, zero reserved rows.
6. Direct VPS shadow truth: both timers active; ATT1 has 17 raw/0 admitted signals,
   SBR1 1 raw/0 admitted. No money/order authority. Historical transient errors
   are recorded in `SHADOW_EVIDENCE_STATUS_2026_08_27.md`.
7. Direct Alpaca broker truth: dynamic software ratchet confirmed; SCHW exited
   profitably but through an adverse gap; ABBV full-quantity stop is `257.65`,
   above entry. SAFE_HOLD still blocks buys. Exact restart gates are documented.
8. Verified local research station in the active legacy tree: `6/6` healthy plus
   orderbook/trade collectors. Ollama is proposal-only; `219` is not confirmed
   model bugs. Safe routine boundary documented.
9. Added evidence-driven ten-sleeve phase architecture and a corrected draft for
   Pattern Atlas v2. The atlas draft is not yet a machine preregistration/run.

## Verification

- focused tests: `11 passed`;
- Alpaca focused audit supplied: `64 passed`;
- local fixed-51 live-config verification: `PASS`;
- live mutations/orders in this session: `0`;
- reserved rows decoded: `0`.

## Not completed / do not overstate

- ATT1/SBR1 reserved one-shot is not ready and was not run;
- no live risk, geometry, slots, symbol universe or money authority changed;
- Alpaca entries remain SAFE_HOLD; one protected winner is not selector proof;
- Pattern Atlas v2 is a reviewed draft, not a launched experiment;
- Ollama routine digest is designed, not yet implemented or deployed;
- canonical research runtime still differs from the active `clean-v28` runtime;
- web position chart and unrelated dirty/Claude work were not included.

## Exact next strong-model task

`RESERVED_OOS_RUNNER_CLOSURE`, without opening data:

1. build the exact major-8 M5 identity/materialization manifest under a separately
   authorized no-score operation;
2. implement one-shot runner with atomic claim before decode and refusal on retry;
3. implement independent audit and freeze both SHAs;
4. rerun preflight and stop at `READY_FOR_OWNER_AUTHORIZATION`;
5. only then ask for explicit permission to execute the diagnostic once.

Parallel lighter-model tasks: deterministic Ollama routine digest; Alpaca paper
lifecycle/gap/restart harness; Pattern Atlas v2 machine prereg + feature tests;
XAU/Bullwaves read-only journal; web chart CDN repair with UI tests.

## Local Ollama chat

From the canonical tree:

```bash
python3 scripts/chat_with_local_ai.py --model qwen3:8b
```

Good prompt: "Read only the fresh receipts and heartbeat available in the bounded
project context. List at most three status contradictions, cite the source paths,
and say how each can be falsified. Do not propose live changes."

For reliable daily use, first implement the deterministic timestamped routine
digest described in `reports/OLLAMA_ROUTINE_BOUNDARY_2026_08_27.md`; the chat alone
does not automatically ingest every fresh server receipt.
