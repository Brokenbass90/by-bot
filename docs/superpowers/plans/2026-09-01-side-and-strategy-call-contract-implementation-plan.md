# Side and Strategy Call Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make direction and strategy-call contracts explicit and fail-closed, then recompute GS1 with an auditable receipt.

**Architecture:** A pure `bot.side_contract` owns internal/exchange direction conversion. A pure research invocation helper owns the `store` versus `symbol` decision and is consumed by both the generic adapter and `research_machine`; GS1 emits canonical internal directions at the source.

**Tech Stack:** Python 3.12, dataclasses, inspect, pytest, JSON receipts.

**Spec:** `docs/superpowers/specs/2026-09-01-side-and-strategy-call-contract-design.md`

## Global Constraints

- Canonical internal directions are exactly `long` and `short`.
- Exchange aliases are accepted only through an explicit normalizer; unknown values fail closed.
- Symbol-first dispatch is selected only when the bound parameter is named `symbol`; unknown names fail closed.
- No live configuration, risk, orders, positions, services, private APIs, money authority, or sealed inputs.
- Existing GS1/PUMP4 evidence is not promoted by this repair.

---

### Task 1: Pure direction vocabulary

**Files:**
- Create: `bot/side_contract.py`
- Create: `tests/test_side_contract.py`

**Interfaces:**
- Produces: `normalize_side(value: object) -> Literal["long", "short"]`
- Produces: `to_exchange_side(value: object) -> Literal["Buy", "Sell"]`
- Produces: `SideContractError(ValueError)`

- [ ] **Step 1: Write failing table-driven tests**

Use literal expectations for `long`, `LONG`, `Buy`, `sell`, and `short`, plus
unknown/empty/non-string rejection and exact `Buy`/`Sell` conversion.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest -q tests/test_side_contract.py`

Expected: collection/import failure because `bot.side_contract` does not exist.

- [ ] **Step 3: Implement the pure contract**

Use an explicit alias dictionary and raise `SideContractError` for every value
outside it. Do not use a fallback branch.

- [ ] **Step 4: Run GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_side_contract.py`

- [ ] **Step 5: Commit**

```bash
git add bot/side_contract.py tests/test_side_contract.py
git commit -m "feat: define fail-closed side contract"
```

### Task 2: Enforce direction contract at consumers

**Files:**
- Modify: `bot/risk_sizing_contract.py`
- Modify: `bot/tpsl_policy.py`
- Modify: `backtest/engine.py`
- Modify: `tests/test_risk_sizing_contract.py`
- Modify: `tests/test_tpsl_policy.py`
- Create: `tests/test_backtest_side_contract.py`

**Interfaces:**
- Consumes: `normalize_side()` from Task 1.
- Produces: wrong-side stops reject for both internal and exchange aliases; unknown sides reject or raise at their pure boundary.

- [ ] **Step 1: Add failing behavior tests**

Cover `Buy` with a stop above entry, `Sell` with a stop below entry, unknown
side rejection, equal long/Buy slippage, equal short/Sell slippage, and TP/SL
policy parity across vocabularies.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest -q tests/test_risk_sizing_contract.py tests/test_tpsl_policy.py tests/test_backtest_side_contract.py`

Expected: current absolute-distance fallback accepts invalid geometry and
`Buy` receives short slippage.

- [ ] **Step 3: Replace fallbacks with explicit normalization**

`calculate_risk_size` converts aliases and returns `unknown_side` on
`SideContractError`. `_apply_slippage` normalizes before branching.
`planned_tpsl_after_fill` and `protective_stop_is_live` normalize before their
geometry checks and preserve current non-numeric fallback behavior.

- [ ] **Step 4: Run GREEN and existing focused regressions**

Run: `.venv/bin/python -m pytest -q tests/test_side_contract.py tests/test_risk_sizing_contract.py tests/test_tpsl_policy.py tests/test_backtest_side_contract.py`

- [ ] **Step 5: Commit**

```bash
git add bot/risk_sizing_contract.py bot/tpsl_policy.py backtest/engine.py tests/test_risk_sizing_contract.py tests/test_tpsl_policy.py tests/test_backtest_side_contract.py
git commit -m "fix: enforce side geometry across consumers"
```

### Task 3: Repair GS1 at the signal source

**Files:**
- Modify: `strategies/grid_smart_v1.py`
- Modify: `tests/test_new_strategy_contracts.py`

**Interfaces:**
- Consumes: internal vocabulary `long` / `short`.
- Produces: every non-null GS1 `TradeSignal` validates before leaving the strategy.

- [ ] **Step 1: Add a failing deterministic GS1 signal test**

Use a controlled store/config fixture that reaches one long and one short
signal path. Assert canonical side and `TradeSignal.validate()`.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest -q tests/test_new_strategy_contracts.py`

Expected: current GS1 emits `Buy` or `Sell`, so validation fails.

- [ ] **Step 3: Change GS1 internal comparisons and emitted side**

Use `long` / `short` throughout the chosen-side branch. Do not alter the
entry, stop, target, regime, cooldown, or level geometry.

- [ ] **Step 4: Run GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_new_strategy_contracts.py tests/test_backtest_side_contract.py`

- [ ] **Step 5: Commit**

```bash
git add strategies/grid_smart_v1.py tests/test_new_strategy_contracts.py
git commit -m "fix: emit canonical GS1 sides"
```

### Task 4: Explicit store-versus-symbol invocation contract

**Files:**
- Create: `research_lab/strategy_call_contract.py`
- Modify: `research_lab/strategy_adapter.py`
- Modify: `research_lab/research_machine.py`
- Create: `tests/test_strategy_call_contract.py`
- Create: `tests/test_research_machine_strategy_calls.py`

**Interfaces:**
- Produces: `first_signal_argument(obj: object) -> Literal["store", "symbol"]`
- Produces: `invoke_ohlcv_signal(obj, *, store, symbol, ts_ms, o, h, l, c, v)`
- Consumed by: generic adapter convention detection/caller and `research_machine`.

- [ ] **Step 1: Add failing contract tests**

Use real `PumpFadeV4RStrategy` and one store-first strategy plus a deliberately
ambiguous fixture. Prove PUMP4 receives a string symbol, store-first receives
the store identity, and ambiguity raises instead of guessing.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/python -m pytest -q tests/test_strategy_call_contract.py tests/test_research_machine_strategy_calls.py`

Expected: missing module and current adapter labels PUMP4 simply `ohlcv`.

- [ ] **Step 3: Implement and wire the contract**

Add explicit `symbol_ohlcv`, `symbol_last_price`, and async equivalents to the
generic adapter. Replace the direct call in `research_machine` with
`invoke_ohlcv_signal`; keep exception accounting visible rather than silently
classifying every exception as no signal.

- [ ] **Step 4: Run GREEN and adapter consumers**

Run: `.venv/bin/python -m pytest -q tests/test_strategy_call_contract.py tests/test_research_machine_strategy_calls.py tests/test_strategy_liveness_probe.py tests/test_collect_inplay_prospective_shadow.py`

- [ ] **Step 5: Commit**

```bash
git add research_lab/strategy_call_contract.py research_lab/strategy_adapter.py research_lab/research_machine.py tests/test_strategy_call_contract.py tests/test_research_machine_strategy_calls.py
git commit -m "fix: dispatch strategy calls by explicit signature"
```

### Task 5: GS1 invalidation and recomputation receipt

**Files:**
- Create: `reports/receipts/GS1_SIDE_CALL_CONTRACT_RECOMPUTE_2026_09_01.json`
- Create: `reports/GS1_SIDE_CALL_CONTRACT_RECOMPUTE_2026_09_01.md`
- Preserve: `research_lab/passport_gs1.json` pre-fix identity in the receipt.

**Interfaces:**
- Consumes: Tasks 1–4 and `research_lab/data/h1/*.npz`.
- Produces: fail-closed result with exact source/config/data/output identities; never promotion authority.

- [ ] **Step 1: Hash the pre-fix passport, data manifest, strategy source, and config**

Record literal SHA-256 values before the run.

- [ ] **Step 2: Run the bounded recomputation without sealed inputs**

Run `research_machine.py` against `research_lab/data/h1` and a temporary output
root. If runtime exceeds the bounded session, launch it as a named local
research job and record PID/log/output paths; do not fabricate a result.

- [ ] **Step 3: Compare GS1 before/after and audit PUMP4 call parity**

Report trade/cell counts, PF/R/DD only when produced by the corrected contract.
Keep PUMP4 at its existing multiple-testing verdict.

- [ ] **Step 4: Validate the receipt**

Run JSON parse, self-hash verification, `git diff --check`, focused tests, and a
secret scan limited to staged files.

- [ ] **Step 5: Commit**

```bash
git add reports/receipts/GS1_SIDE_CALL_CONTRACT_RECOMPUTE_2026_09_01.json reports/GS1_SIDE_CALL_CONTRACT_RECOMPUTE_2026_09_01.md
git commit -m "research: recompute GS1 after contract repair"
```

