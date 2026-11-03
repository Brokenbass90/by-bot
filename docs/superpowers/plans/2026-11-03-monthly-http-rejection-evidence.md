# Monthly HTTP rejection evidence — bounded repair plan

Goal: retain safely bounded broker rejection details through the existing transport
and Monthly observation path. No change to payload precision, risk, ownership,
reservation semantics, retry behavior or active VPS code. Original422 body lost:
this repair cannot manufacture its reason or retrospectively declare it known.

Files: research_lab/alpaca_dynamic_live_runtime_v1.py (HTTPError capture only),
research_lab/alpaca_monthly_cycle_v1.py (attach safe evidence to existing issue),
tests/test_alpaca_http_rejection_evidence_v1.py. Existing clients/journals reused.

1. RED real urllib HTTPError fixture through actual exact monthly permit/serializer;
   no real HTTP. Preserve status/code/requestID/boundedbodyhash/sanitizedmessage and
   exactwirepayloadSHA. Never retain headers/keys/account balances or rawHTML.
2. GREEN minimal helper in existing runtime; generic exception string unchanged,
   one-usepermit remains consumed and no retry added. Failed bodyread cannotmask
   the original status. UnknownJSON fields omitted; bodylimit8192bytes.
3. Attach sanitized response to existing Monthly issue so observation persists it.
   Fixture verifies reservation/state staysblocked and no duplicate send.
4. Targeted transport/Monthly lifecycle/regression suite and bounded criticalreview.
   Local candidate only; new source identity needs separate accepted handoff/GO.
5. GET-only actualaccount/asset/configuration/CID proof and exactsavedrequest audit.
   CurrentGETs are not historicalproof of originalopeningconditions. No APIvalidate
   flag invented, no POST to reproduce a lost response, no reservation cleanup.

ActualPUMP15H confirmedPASS134/134within60,last58.750s,0rawsignals; onehouronly,
1.250sheadroom. One-shotmonitorremoved, nativeunits/scopes retained. Original
Monthly125expired3Nov14:35UTC, no newentryauthority implied bydiagnosticrepair.
