# Polymarket public WS DATA-only implementation plan

> Use superpowers:executing-plans, inline implementation plus ONE final Astra/high review.

Goal: continuously preserve two public WS sources with safe bounded VPS ownership
and immutable Mac delivery. Spec: ../specs/2026-11-02-polymarket-ws-data-design.md.
Reuse dedicated recovery checkout. No financial/R&D/judge/Claude edits. No broad
baseline suites or installation into current LIVE Python environment.

## Task 1 — source and durable bounded collector
Files research_lab/polymarket_ws_data_v1.py, scripts/run_polymarket_ws_data_v1.py,
tests/test_polymarket_ws_data_v1.py; frozen prototype inputs under evidence.
Interfaces SegmentStore(root,role,config), append(payload), seal(); catalogue
selection from pinned existingASTfunctions, currentcatalog with both tokens;
worker(role,config) fixedpublicWS+allowlist+rawclocks/reconnectgap.
- [ ] RED quota/partialrestart/sealhash/duplicate/exclusivewriter/clockseparation,
  frozen catalogue eligibility, bothsides, staleness, GET/send scope.
- [ ] Implement minimal fixedtransport/store/catalogue; GREEN affected suite; commit.

## Task 2 — DATA pull and exact isolated units/handoff
Files scripts/pull_polymarket_ws_data_v1.py, deploy/systemd/poly-ws-data-* and
bounded evidence install/cutover script. Interfaces immutable manifests to exclusive
Macdataset; no oldfileoverwrite; periodic nativeMacpull. Threeonlyunits/fixedsource.
- [ ] RED traversal/hashconflict/idempotency/missingpartial/defaultnoaction.
- [ ] Implement/test resourceandcredentialisolation, handoff/refusal/rollbackproof;
  no live stop or research judge. One final critical review+targetedfixes; commit.

## Task 3 — physical acceptance and publication
- [ ] FreshreadonlyVPSresources/livepins/Macexactprocesses; immutableunselectedstage;
  VPSnetworkdeniedtests/systemdverify and constrainedpublicprobe.
- [ ] Apply only acceptedDATAmigration once, normalMaclaunchrefusal, actualWSframes,
  recover newservices only, nativepull/idempotentimport. Recordunknowncoverage/gaps.
- [ ] Verifyfinancialunits/owner/locksunchanged, preserveMonthlypostwindowP0,
  report/checkpoint/roadmap/managerbrief+commit/push. No additional LIVEauthority.

Review: hostpaths/secretleak; resourceorbudgetexhaustion; stale/partialcatalogue;
recv-vs-venueclock; duplicateproducer/cutover; partialtailneverrepair; no implicit
researchPASS. Selfreview: task1seals feed task2import; unitsinvoke exacttask1CLI;
installation afterfinalreview; source-onlytests no historicaloutcomeconsumption.
