# Brain V2 A5/A6: single historical filter terminated, permission spent

Terminal result: **BLOCKED_DATA / realized_capital_nonpositive**. One permitted
historical run was started and terminated; **no retry remains authorized**.
The complete four-fold comparison is unavailable. This is neither a developing
PASS nor a completed STOP_V1 verdict, and grants no policy or money authority.

## What was implemented and frozen before outcomes

Owner-supplied A5/A6 were verified and the existing research ref published as
`e2d668ce415c82c1c22c44454df84e168a8c5f7d`, without checkout edits or merge.

- A5: `c07cf7964f4013b98c696633ac2b46bdc55cdfce0756f51b33a26cd0ada6e84a`.
- A6: `19a177e2a4b9e096e049552642b9ea49f51f8a5ce70630403dcc298f766e4441`.
- The original 17 control pins and all four previously published train tables
  remained unchanged. No generator rerun, B3 judge or new holdout entries.
- Separate `brain_v2_develop.py` implements continuous $100,000 model capital,
  carried positions/equity, entry-time fold attribution, release-first 15m ticks,
  historical **DD_ENV**, frozen caps/scoring and A6 archive-calendar/cold-start.
- `brain_v2_develop_run.py` verifies pins before an exclusive start marker,
  writes separate paired/tick/three closed ledgers, and rejects any second run.
  A failed/crashed output directory remains spent. No credentials/order path.
- 278 local targeted tests passed before publication/run: 24 new developing/
  one-shot tests and 254 preserved Brain/source/OS2 tests. Root review reproduced
  and fixed mutable funding-input aliasing RED→GREEN. Independent financial
  review remains unavailable due to the prior quota failure; no retry/signoff.
  Full-suite historically NOT_GREEN and not rerun; no VPS tests/operations.

Pre-run code commit **55b04e02d435678b332212f234a0676dd2581646** was pushed and
actual remote verified before outcome consumption. The published pre-run manifest
SHA is **476fc7ba3c00264ca11e8d79dbd90ba424c8a8a3495f77c2df05c1dd1c68721c**.
This manifest includes implementation/addenda/source/table pins and all permissions.

## Actual attempt and retained evidence

Authoritative directory:
`reports/evidence/brain_v2_develop_20261012/run_a5_a6/`.

- `STARTED.json`: 2026-10-12 **06:59:57.761967 UTC**, attempts permitted 1.
- `TERMINAL.json`: **07:00:16.745535 UTC**, `filter_runs=1`,
  `run_permission_consumed=true`, `exception_type=BrainBlocked`, exact reason above.
- Five compressed hash-chained journals and `ARTIFACTS.json` survived the exception.
  **115,721 records**, **14,157,521 compressed bytes**, all hashes/chains/counts pass.
- Last persisted historical tick: **2025-04-07 14:45 UTC**, 62,076 consecutive
  ticks from July 1, 2023. 44,837 opportunity decisions were recorded. Fourth
  entry window remains incomplete; no release-only tail or full filter verdict.
- Closed ledger counts RAW_SAFE **3,221**, FOUNDATION **2,714**, BRAIN_DET **2,873**.
  These are virtual closed positions, not actual broker executions or independent
  prospective evidence. No current strategy profitability claim follows.

The engine applies releases, then raises on nonpositive capital before returning
the next packet. Therefore the failing **15:00 tick itself was not journaled**.
It is not represented as a recovered persisted engine state. Source-bound cash
arithmetic below explains that first unsaved tick without starting an allocator.

## Exact cause: admitted SF3 GRASS notional is unbounded by stop-risk caps

The existing SF3 stream SHA
`7739e7a4619bf238097de04afc8b41303b74718c64cc25a4022436296010fe45`
contains this exact already-admitted row:

```json
{"leg":"SF3","sym":"GRASSUSDT","side":"short","ts":1744033500000,"R":-199.072,"hours":1,"lev":165060.0}
```

Opportunity ID:
`19eb416494e6d322218295b33f2eb4cfb411cf90c21d0e357e8b44813b135aa0`.
Signal bar opens April 7 **13:45 UTC**, `t_available`/entry **14:00**, release **15:00**.
All three arms admitted it under the unchanged frozen caps. `lev` is the stream's
notional-to-risk multiplier, **not evidence of a broker allowing 165,060x leverage**.
Its inverse stop-distance is approximately **0.060584 bps**. This creates notional
far beyond the model's capital although the nominal stop-risk passes its caps.

| Arm | Last recorded capital, USD | GRASS risk, USD | GRASS notional, USD | GRASS net loss, USD | Capital after due releases, USD |
|---|---:|---:|---:|---:|---:|
| RAW_SAFE | 118,984.75 | 594.92 | 98,198,112.86 | −157,711.90 | −39,320.64 |
| FOUNDATION | 79,803.57 | 399.02 | 65,861,886.55 | −105,778.04 | −25,974.47 |
| BRAIN_DET | 77,870.22 | 363.32 | 59,969,757.22 | −96,314.93 | −18,829.93 |

The last column includes the other EPIC release for RAW_SAFE/BRAIN_DET; FOUNDATION
did not hold that EPIC opportunity. It is **forensic arithmetic, not a saved tick**.

For GRASS the archive covers the holding interval under A6, but there is no
settlement strictly after entry through release. Funding is demonstrably zero for
this covered interval, not substituted for missing data. SHA of the funding file:
`92c15fd2f446074b0c42254bf911e5ce5a0356b66b44c702bbd008e8bac85bc9`.
The frozen cash calculation is therefore:

`net = risk × (−199.072) − 0.0004 × (risk × 165060) = −265.096 × risk`.

The source R numerically equals `−1 − 0.0012 × 165060`; the latter is the frozen
6bps/side commission scale. This algebra is **not independent proof of the
original simulator's stop path or raw price/ATR correctness**. No strategy was
resimulated to explain it. The additional 2bps/side slippage contributes **66.024R**;
no second commission charge was added by the new runner.

Every saved equity tick reconciles exactly to initial capital plus previously
recorded known closed cash at Decimal precision 50. Thus the traced failure is
consistent with the unchanged source row, sizing and cost contract, rather than
an observed double-fee or recorded cash-transfer mismatch. Raw market/source
validity and economic feasibility of that SF3 normalization remain a separate
research issue, not resolved by ledger integrity.

Recorded UNKNOWN counts before the unsaved tick were RAW_SAFE 59/3221,
FOUNDATION 48/2714, BRAIN_DET 58/2873 (all below 5% **at that partial boundary**).
Missing HFT and insufficient history remain recorded. The actual abort reason
was capital, not a final funding-coverage gate. No final coverage PASS is claimed.

## Reconciliation and next action

Inspect `run_a5_a6/PARTIAL_CAPITAL_RECONCILIATION.json`; the reproducible forensic
reader is `reports/evidence/brain_v2_develop_20261012/reconcile_spent_run.py`.
It reads recorded journals and source rows for already-admitted positions only;
**allocator_runs=0, judge_runs=0, no new decisions**. It checks each chain, each
recorded cash formula, every saved tick's realized capital, and the due releases.
It never calls `DevelopEngine`, advances the historical simulation, admits a new
position, or manufactures a completed four-fold report.

Do not rerun the filter, truncate/winsorize R/lev, remove GRASS/SF3, clamp capital,
alter fees, raise risk or change this input manifest to obtain a nicer result.
Keep all original markers, compressed ledgers, source/table pins and raw funding.

The next research handoff is narrow: **Claude should verify the already-consumed
SF3 GRASS normalization/source and specify a separately versioned execution-feasible
notional/margin/cost contract before any new comparison**. A stop-risk cap alone
does not bound traded gross or transaction losses. This report authorizes neither
a V1 rescue nor another outcome run. Frozen V1 has no policy/money authority.

Independent P0 remains the original **NET Alpaca PAPER** session October 12
13:30–13:35 UTC / 16:30–16:35 Cyprus. This Brain cycle performed **zero SSH, broker,
service, order or LIVE operations**. It does not confirm today's PAPER outcome or
runtime health; preserve the server opener/guard, LIVE HALT/caps and separate GO.
VPS Bounce remains terminal BLOCKED_DATA, Codex BOUNCE1_8 cancelled, Claude Mac
bounce_ten.py separate. KITY/ATT1 and spent B3 remain untouched.
