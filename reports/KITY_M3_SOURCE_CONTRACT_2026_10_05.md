# KITY M3 frozen source contract probe — 2026-10-05

The frozen files were copied from `bybit-bot-clean-v28` commit `d6ed8126c041969de0bc6191e39fefe4a1272d5b` into `.private/kity_m3_20261005/source/`. `SOURCE_MANIFEST.json` records each Git blob pin and SHA-256. Git blob IDs and SHA-256 values are intentionally both recorded: they are different hash domains.

The throwaway fixture command was:

```text
python3 .private/kity_m3_20261005/probe_contract.py
```

It executed the frozen paper module with `exec` under a non-`__main__` namespace, replaced `get`, `instrumenty`, `oi_2355`, `svechi`, `utc`, and sleep with synthetic stubs, and installed a forbidden `urlopen` guard. Result: `network_calls: 0`.

Observed synthetic cases:

- `n=30 -> 3 long / 3 short`, `n=40 -> 4 / 4`, `n=50 -> 5 / 5`; this is the implementation’s `k = len(rows)//10` behavior. The prereg/runbook’s intended 50-name case is 5/5. This probe did not retune or run the judge.
- A six-leg synthetic filled list with every `lot_ok`, known prices, and `sverka.ok=true` produced `PAPER_WEEK_OPERATIONAL_PASS`. The implementation does not enforce the runbook’s 10-leg manager requirement, so this is a synthetic contract finding only.
- With no 23:55 OI observation, mocked `oi_2355` returned the last in-window 23:50 value (`23.0`).
- An existing stale/tampered `signal.json` was returned verbatim without validation or recomputation.
- Sixty duplicate kline rows were accepted because `svechi` filters closed rows; the surrounding signal path checks only length and the last date.

Static limitations remain: this probe saved no raw OI/kline responses, used no current exchange filters or prices, cannot establish float min-lot correctness, and does not create a provenance chain for mocked responses. No raw discovery archives were read, no judge was run, and there is no `CANARYPASS` claim.

Primary clarification: the frozen prereg/judge expressly allow n//10 for n≥30. The smaller basket is faithful to research, while the ten-leg production brief requires an explicit BLOCKED_EXECUTION reason when n<50. No 5+5 selector replacement is approved. Static source reading also confirms the forward writer discards raw OI and kline response bytes and saves derived mappings/arrays instead; a hash of those derived files is not raw wire provenance.
