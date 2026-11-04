# Polymarket fresh snapshot inputs — implementation plan

> For agentic workers: use superpowers:executing-plans task-by-task. Existing checkout/measurement module; no new framework.

Goal: feed actual full REST books for both existing-market outcomes and captured
Gamma feeSchedule into the existing ORDERS_OFF measurement. Owner-approved4Nov
P1; independent of the winning research model. No strategy/order/risk authority.

Architecture: one pure normalizer plus bounded public-GET CLI. Exactrawresponse
bytes/hash, request/receive times, endpoint/token/condition identity and explicit
snapshot scope. Full REST response is a single observed snapshot, not continuous
WS coverage. Existing VPS WS collectors/selection/delivery and Claude stay intact.
Tech: Python3.12 stdlib; existing polymarket_v2_orders_off_v1.measure.
Spec: current ROADMAP_SELF_IMPROVING.md and owner4Nov P1 request.

Constraints: maxprice .985/model100 remain measurement-only; no wallet/key/POST/
financialconstructors/Brain/judge/outcome runs. No defaultfee or base_fee mapping.
Recognize Gamma feesEnabled + feeSchedule(rate,exponent=1,takerOnly=true); unknown
schedule/exponent/version→UNKNOWN. Feesdisabled explicitly maymean0, missingdoesnot.
Old V2 economicFAIL preserved; no assumption freshquote is qualifyingtrade/fill.
No newservice/WSproducer. Boundedrepeat3 proves repeatablemeasurements, not24x7.

Files: new research_lab/polymarket_v2_snapshot_inputs_v1.py (pureinputvalidation),
new scripts/measure_polymarket_snapshot_v1.py (GET-onlyboundedcapture/call),
modify research_lab/polymarket_v2_orders_off_v1.py (explicitfullRESTsnapshot scope
inreceipt; existingVERIFIED/GAP semantics stay), newtests fornormalizer+CLIguards.

Review focus: mismatchedtoken/condition; stale/future response; duplicate/nonfinite
JSON; unsupported fee/exponent/protocol; caller-supplied signal not verified by
measurement; twooutcomes notsimultaneous/independentopportunities; streamcontinuity
not inferred from REST. Sourcehashes alwaysraw bytes, not reserializedobjects.

- [x] RED exactGammafeeSchedule overrideslegacybase_fee; unknowndoesnotbecome0.
- [x] RED fullRESTpair identities/freshness/captureSHA/scope; sourceerrorfailsclosed.
- [x] Minimalnormalizer + receiptbasis, runnewtests+existing23measurementtests.
- [x] BoundedCLI fixedGETallowlist, raw0600createexclusive/fsync, repeat1..3,
      suppliedsignalordistinctNON_STRATEGIC_PROBE; noorderflags/keys/WS.
- [x] Oneboundedreview, targetedfixesonly; actualfreshpair/repeatedmeasurements.
- [x] RecordremainingWSruntime/Claude-signalcomparison gaps, no economicPASSclaim.

Primary sources checked4Nov: docs.polymarket.com/trading/fees,
/market-data/market-details, /market-data/prices-order-books. Gamma captured3Nov
had feeSchedule rate.05/exponent1/takerOnlytrue despite legacybase_fee1000.

Delivered4Nov:56focusedPASS; two critical-review regressions fixed/rechecked.
Actual final-source3pair snapshots07:59UTC; report POLY_FRESH_SNAPSHOT_MEASUREMENT_2026_11_04.md.
Regular hook/causal Claude signal join remains OPEN; output22resolvedrows lacks IDs/times.
