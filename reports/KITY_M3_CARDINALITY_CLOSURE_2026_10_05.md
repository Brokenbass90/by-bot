# KITY M3 — compatibility closure, orders OFF

Owner explicitly approved correction to the actual frozen `k=n//10` rule.
This supersedes the initial ten-leg compatibility restriction; it changes no
research rule, universe, ranking, seven-day hold or historical cost model.
Production verdict remains **BLOCKED_DATA / IMPLEMENTED_LOCAL_ORDERS_OFF**.

The assessor now accepts exact6/8/10-leg baskets, k3/4/5 on each side. No padding,
substitution or omitted leg. Execution minimum floor, book census, external
forward comparison and synthetic finality/rotation use the actual basket size.
All books still pass the common2000ms clock together; missing/stale legs reject
whole baskets. CJK venue identifiers remain exact, with bounded public URL
encoding; unavailable Bybit symbols block portability, never disappear silently.

All **251 Claude signal-only vectors PASS**:216*k4 and35*k5. Source refs97493bb
and28e4b48 contain the same Git blob1505db049f13cb9e4f559980834a75c5985d9299;
fixture SHA25667b9db28738b6d89d6cf621b041126b880e58fea2fff556778fccf6be227e3d1.
Both exact source bytes were independently compared in the sibling Git objects.
Actual local/origin research ref8c83196 was checked read-only; no checkout/merge.
Research refd6ed812 remains the original signal contract pin; later artifacts
supply its compatibility correction and vectors. Judge never rerun.

Vectors provide **eight-decimal features**, not original PIT OI or candles.
A synthetic raw-wire adapter feeds those independent features into the actual
reconstructor; expected baskets never build inputs. This proves selection
compatibility at supplied precision, not historical raw provenance or net edge.
Synthetic k3/4/5, ties, minimums, missing/stale legs and lifecycle tests complement
it.25 weeks exposed CJK names rejected by the earlier ASCII-only validator.
No future signal slot was sealed and no prospective credit earned.

Final targeted **380 PASS** includes KITY369 and isolated ETS2M launcher11.
Full suite **3893 PASS /57 exact baseline failures**, no added/removed failures;
full collection preceded the11 ETS2M tests, which passed separately. Failure
names/log hashes are in the JSON receipt. One bounded6-astra/high KITY critical
review approved this local correction. The distinct ETS2M review found a source
terminal-duplicate issue, fixed/tested by primary; no second signoff claimed.
Actual child routing was verified from rollout turn_context, not self-report.
Known suite appends to foreign allowlist were checked and restored byte-exactly;
foreign SHAadd587f1…f19a1 remains untracked/unstaged.

## Money gates still open

1. October8 unseen exact23:55 OI/cutoff census/closed d−1 raw captures, independent
   basket reconstruction, atomic timely seal and external Claude parity.
2. Actual6–10 basket symbols, chosen venue and simultaneous depth/minimums/costs;
   Bybit additionally needs explicit signal/price/funding portability.
3. Authenticated selected-account fees/cash/margin/mode and ownership.
4. Smallest equal-notional feasible size, exact gross/margin/reserve capital,
   fixed absolute per-leg/portfolio/daily caps, rounding tolerance and liability.
5. Partial-basket failure/unwind, protection/exit/finality/restart/kill dossier;
   current synthetic lifecycle is not a deployed money runner.
6. Separate owner GO only after READY_FOR_CANARY. $100/leg/$1000 are examples,
   not approved caps. Historical~24% basket drawdown/severe short tail remain
   explicit risk inputs, not guaranteed loss bounds. No directional short-stop
   retune; a strategy-changing exit requires a separate challenger.

October15 is an earliest candidate, October22 an alternative; evidence decides.
First paper close-reference entry is available October9 00:05UTC, exit October16
00:05UTC. Close references are not executable broker fills.

Reproduce:

```sh
.venv/bin/python -m pytest -q tests/test_kity_m3_orders_off.py tests/test_kity_m3_orders_off_cli.py tests/test_kity_m3_test_vectors.py tests/test_ets2m_unattended_verdict.py
```

No credentials, order path, KITY deployment or LIVE changes were added.
