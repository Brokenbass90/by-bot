# PUMP4 full-chain read throughput — bounded plan

Goal: reduce CPU on actual H1 publication while preserving every journal/strategy/
fsync/ownership/60s check. Four postpatch hours:2PASS/2late; no stablePASSclaim.

Use one DATA-only LifecycleJournal subclass overriding _load only. Strict JSON
already produces JSON-native objects: skip only redundant _event JSON roundtrip
and reuse exact canonical eventbytes for both eventSHA and identity lookup. Keep
all originalbounds, ASCII/_pairs/_constant, sequence/schema/eventID checks, full
hashchain and canonical-line comparison on EVERY read. No cache/partial-prefix
trust/financial-parser changes. Base _locked/_append/_event/fync remain untouched.
Bootstrap injects only pump4_closed_bar_intake_v1.LifecycleJournal; originalsource
files/modules/epochs remainimmutable. Versionedmanifest records physicaldecoder.

1. RED redundant JSON-decode count on a realtwo-record journal; add original/new
   acceptance/error A/B corpus and Pythonappend/restart/drift/fsync guards.
2. Minimal subclass; localtargeted tests and copiedBTCbyte/decision/stateparity.
3. One bounded criticalreview of finalsubclass/injection; fix confirmedissues only.
4. ExactVPSnetworkdeniedtests andsamepublicprefixbenchmark. Benchmark isnotactualH1.
5. Only ifaccepted/measured: distinctquietDATAhandoff fromcurrentwarmunit/PID,
   existingfinancialowner/scopes unchanged; no replayoldclaims orloosen60s.
   ActualfutureH1receipt requiredbeforecallingSOURCEPASS. NoMoneyGOimplied.
