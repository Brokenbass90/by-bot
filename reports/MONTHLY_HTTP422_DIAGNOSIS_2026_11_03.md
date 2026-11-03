# Monthly HTTP422 diagnosis and PUMP followthrough —3 November2026

## Actual result and remaining blocker

Original Monthly request remains reserved/UNKNOWN; no automaticresend/claimreset/
newscope/datecarry or broker mutation. Actual18:04:15UTCGET: liveaccountidentity
matches125/manager, positions0/open0/recent0, exactCID404. AccountACTIVE/no trade/
account/userblocks; configurationfractional=true; LLYactive/tradable/fractionable.
These are current facts, NOT historicalproof of14:30conditions orcompletecosthistory.

OriginalHTTP422body andrequestID were notsaved andarenotrecoverablefromexisting
nativeintent/observations. Reconstructed originalpayload fromdurableintent+pinned
serializer passes the unchangedstrictwirecontract: LLY/market/buy/day/notional
101.413902261/oneboundCID. CanonicalpayloadSHA a6ad6a2c8c0e91e2e4592d7d73f841a8ed939c47d119ef2e2f6d09ec4087aa60.
This is reconstruction, NOTa rawwirecapture orproof thebrokeracceptedtheschema.
No FinancialPOST wasmadefor diagnosis. Exactrejectionreason remainsUNKNOWN.

Officialsources checked3Nov: Trading POST/v2/orders hasnotionalstring/market/day,
FractionalTrading explicitlysupports9dp; BrokerAPI FAQ says2dp. Different APIs/
documentation cannot establish our lost rejectionreason. No precision/rulechange
wasmadebasedonthis hypothesis.
https://docs.alpaca.markets/us/reference/postorder
https://docs.alpaca.markets/us/docs/fractional-trading
https://docs.alpaca.markets/eu/docs/broker-api-faq

Private ready-to-send support request withaccount/CID/timestamp/reconstructedpayload
is .private/monthly_http422_20261103/broker-support-request.txt. NOTsent; no secrets.
Brokerlogs or a separatelyauthorizedfutureattempt with repairedcapture are needed
to recover a precise server-side reason. No automaticnextdate orDecemberwaitimposed.
No newGOpacket is READY while olduncertainreservation andadmissionexception remain.

## Concrete localrepair — NOTDEPLOYED / NOTMONTHLY_FIXED

Existing DynamicLiveClient._http nowretains boundedHTTPerror evidence on theexisting
AlpacaAPIError: brokerstatus/code, safe requestID, route/method, exactpayloadSHA/
CIDhash, allowlistednoncredentialpayloadfields, bodyprefixSHA/8192limit/truncation,
JSONmessage withcredentials/identifiers/monetaryamountsredacted. NonJSON/rawheaders/
unknownbodyfields notsaved. Genericexceptionstrunchanged, permitconsumedonce,
no retry, no changedpayload/budget/entryrules. FailedbodyreadcannotmaskHTTPstatus.
Existing MonthlyManager.tick persists safe evidence in itsnormalissue/observation.
No extra financialservice/journal, noorderconstruction outsideexistingcode.

11newtests +198existingtransport/Monthly/lifecycle/standing/source/recovery tests:
**209PASS onfinalsource**. Original6RED observedbeforeimplementation. Onebounded
Astra/highreviewfoundcredential-containingrequestID+monetary-formatredactiongaps;
3then2focusedREDcasesfixed. Reviewerverifiedfinal11/11 andreportedresolved.
Testsuse realurllibHTTPError withsyntheticbytes/fakeendpoint only;0realnetworkPOST.
NoactiveVPSsource/ownerGO/scopes/keys/units/financialstate changedbythisrepair.
Newsourceidentityrequiresacceptedversionedhandoff/ownerGO before LIVEselection.

## PUMP — actualprogress andremainingperformancework

Native15H passed134/134within60,last58.750s;16Hpassed134/134,last56.629s.
17Hfailed:123/134within60,last66.274s.18Hfailed:127/134,last63.500s.
Allfour complete134/nodisconnect/0rawsignals; financialowner3669955NRestarts0,
DATA4126455NRestarts0. No trade/profitclaim. Firstwarmrepairhelpedbutnotstable.
Originaloneshotpump4-data-h1-handoff-v3removedafterconfirmed15H; nativeDATA/owner/
health/journalskeep. NextboundedP0 isfulljournal CPUverification optimization,
no gateexpansion/newstrategy/cache orfinancialauthority. Candidateanalysisonly.

## Owner-supplied researchcontext

OFI/absorption/depth/uncertainty/executableedge canbeClaude researchcandidates;
'nearlyinstantOFIuplift' isunproven. HMM/Kelly/LLMensembles/opensourceexecution
projects are notnewengineeringpriority orpermission toconnectmoney. No foreign
repository/code/data purchases/messages orfrozenjudge/outcomechanges performed.

## Acceptance correction

Codex owns operational defects and lostbrokerresponse evidence. LocaltestPASS is
notbrokeracceptance; sourcePASS is nottrade; a short winningrun is noteconomicPASS.
Report precise deployment/runtime/broker/source/economicstates andstopforecasting
profitdateswithoutedge/capacityproof. This report isnotanexcuse ornewreadinesslabel.
