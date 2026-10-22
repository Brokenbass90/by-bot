# KITY Bybit C2, 22 October: actual signal parity

**C2_PASS_MATCH_ONLY**, not money readiness, C1/C3 or economic PASS.

Used the existing frozen calculator (`cb47f0e` research identity), with no
research evaluator, outcome, PnL, strategy rewrite or weekly executor. Acquired
50Bybit public trade archives for21October (564,046,129compressed bytes) and
50closed-daily candle captures. Reconstructed independently, then sealed the
result before opening the research signal/flow. Compared exact immutable local
copies and verified original external files still had the same hashes.

| Check | Result |
|---|---|
| Independent features / archive hashes | 50 /50match |
| Ineligible in original top50 | 0 |
| Maximum feature difference | 4.995506040494924e−7; below frozen1e−6 tolerance |
| LONG set | GRASSUSDT, XAUTUSDT, XAGUSDT, MNTUSDT, DOTUSDT |
| SHORT set | LTCUSDT, MSTRUSDT, SOXLUSDT, XAUUSDT, WLDUSDT |
| Frozen snapshot | 21Oct23:50:51UTC, inside accepted23:50–23:59 window |
| Actual monetary order quantities | Not present in research signal; NOT_PROVEN |
| Broker writes / research writes | 0 /0 |

The snapshot filename containing2355 is not proof of an exact23:55capture;
the actual timestamp above is preserved. A1/C1 timely-publication evidence was
not verified by this C2 job. Historical public archives do not create new
prospective observations. Numeric sizing, real account, execution, C3 and edge
remain separate gates; prior KITY one-shot authority stays SPENT/ORDERS_OFF.

Independent receipt:
`a7274c16a4d63cb8a27d557c7b3a49d19417fd6249e661f6361b791338a79394`.
Comparison receipt:
`c01c4c9e55bafcc0ed2937c451006da849d14bfcdbea905cd242e1cead899003`.

[Inspectable receipt](evidence/kity_bybit_c2_20261022/receipt.json).
Raw archives, complete feature reconstruction, external-input seals and
invocation logs remain in `.private/kity_bybit_c2/2026-10-22/`.
Two preliminary path-custody invocation errors are retained; corrected absolute
paths passed. No failed output was overwritten or promoted to a new gate.
