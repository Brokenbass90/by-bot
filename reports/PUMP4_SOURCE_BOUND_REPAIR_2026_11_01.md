# PUMP4 archive bound incident / current-hour repair —1Nov2026

**CODE_AND_PUBLIC_SOURCE_PARSER_PASS / NOT_SELECTED.** No LIVE source/config/unit,
GO, risk or epoch was changed. The deployed legacy reader remains blocked.
This is a bounded execution-source repair, not a new strategy or TINY-2 activation.

## Actual failure and signals

Existing TrustedSources.candidate scans every observations/*.json and rejects a
count above20000. Fresh1Nov public-source GET counted25671files. The already
existing ws-hours/<hour>/published index remains available (134current files in
the observed hour). The failure occurs before candidate/account admission; it
is not a key-expiration error. No archive was deleted/moved or source epoch reset.

Public source receipt census:87H1receipts,11692timely symbol observations,5raw frozen
signals: HYPEUSDT30Oct18UTC; ESPUSDT/XPLUSDT31Oct10UTC; HEIUSDT31Oct11UTC;
GWEIUSDT1Nov02UTC. Three hour receipts were not fully passing, so this is not a
complete opportunity census. Census begins at the first whole H1 in the scope
window, not proof that GO existed at each source time. All five positive examples
are after the recorded28Oct activation. Signals are not executed trades, account
admission, missed profit or economic PASS. No outcomes/judge/PnL was run.

[Source census](evidence/pump4_current_hour_20261101/source-signal-census.json).

## Minimal repair

New explicit runner config option candidate_source=CURRENT_H1_PUBLICATIONS_V1
reads only the existing current H1 publication index, max137files; it does not
scan the growing archive. Publication must bind frozen source pins, deterministic
decision ID, exact current bar/symbol/file, source mode, actual availability /
publication times, no money authority and exact immutable original observation.
Then the ORIGINAL eligibility/cooldown, frozen journal + fresh HTTPS causal replay,
sizing, native stop, single-owner and send-once admission still apply.

Both publication and original-observation identities are retained/rechecked before
and after HTTPS. Outside the original <=60s entry window, no historical entry is
created. Missing current publication does not fall back to an archived positive.
NO_NEW_SIGNAL is only a no-eligible-candidate tick, never a full-hour opportunity
census. Historical/no-opportunity receipts cannot prove profitable trading.

Legacy configs retain the original legacy mode/guard. A typed opt-in and new exact
source/config envelope are required for selection; old GO cannot silently accept
changed source bytes. No new producer, universal engine, cleanup or mtime-based
causal inference was introduced.

## Evidence and review

**196 local / same196 VPS PASS**, not392independent checks. VPS tests ran without
network in the isolated193-file candidate. Includes actual20001archive-file RED
reproduction, current positive without archive scanning, wrong/future/changed/
missing/symlinked publication rejection, no late or negative signal admission,
and selected owner+original account lease+fresh GET+restart/no duplicate OFF E2E.

One gpt-6-astra/high bounded review; actual runtime metadata verified, session
01a19676-d17a-7ec3-8f3f-7dfea67ebcce. OneP2 publication read race reproducedRED;
fixed with retained/rechecked file identities. Both during-read/during-HTTPS race
regressions pass. Initial independent13tests; final196checkedbyprimary, no second
independent signoff or financial deployment approval.

Real immutable public-source parser replay checked134publications in EACH of the
four hours containing the five signals, matching symbols above. Historical cutoff
is explicit; no financial owner, credentials, network or strategy execution.
This is source-parser acceptance, NOT actual financial ORDERS_OFF or a new timely
LIVE decision. No prospective credit for replay.

Candidate `/opt/bybot-research/pump4-current-hour-repair-20261101/candidate-badb0d4afd158e3a/app`.
Manifest SHA256badb0d4afd158e3a0a8321a36b84de6acf28f79c3d5d5388168874ca3c272e6c.
[Delivery](evidence/pump4_current_hour_20261101/delivery.json),
[review](evidence/pump4_current_hour_20261101/review.json),
[local tests](evidence/pump4_current_hour_20261101/local-tests.txt),
[VPS tests](evidence/pump4_current_hour_20261101/vps-tests.txt),
[real parser replay](evidence/pump4_current_hour_20261101/real-public-parser-replay.json).

## API/authentication: fresh broker truth

1Nov09:47:07.850UTC bound existing credential loader + GET-only transport,
fixed old config byteSHAfa0b3b2e…53014a / scopefec235e3…fcf794 verified. query-api
HTTP200/retCode0: CURRENT KEY VALID. GET complete USDT positions/open orders:
0open positions,0open orders. No financial owner or lease constructed, no secrets
published and no broker writes. This is current flat proof, NOT complete historical
no-trade/final-fee proof. Pagination count was not recorded; published request
count is labelled minimum, not an exact telemetry claim.

Key expiredAt **2026-11-06T08:43:37Z /10:43:37Cyprus**. Current PUMP new-entry GO
ends **1Nov19:26:32.774UTC /21:26:32.774Cyprus**, unchanged. These are different
clocks. Given168hmaximum hold, a NEW entry on1Nov could require custody after key
expiry. Before new pilot financial approval, provide a sufficiently long-lived
key or an accepted controlled rotation/custody plan. Do not replace the active
credential file ad hoc: its hash/key fingerprint is part of the accepted envelope.
[Sanitized API/account receipt](evidence/pump4_current_hour_20261101/bound-api-check.json).

## Exact next gate / new chat continuation

The FINANCIAL source-repair envelope is NOT PREPARED / NOT APPLIED. Next bounded
work: prepare exact replacement runner/source/config/scope/unit hashes and owner
procedure using the existing selected-owner handoff and original lock818853.
Retain old scopes/claims/barriers/loss state and prove no pending ownership/custody
before switching; current flat GET is not perpetual proof. No second writer.
Include rollback without reviving spent GO. Original50/30/20, one entry/position,
risk and expiry cannot be expanded by this source repair. If expiry arrives,
stop new entries as authorized; do not extend automatically or replay old GO.
A changed financial source/config envelope needs its exact review/owner authority
before selection; no personal command is issued from code-only PASS.

Then finish serial TINY-2 cost-release policy + actual-account OFF/handoff and new
financial packet, accounting for API lifetime. Earlier cumulative accounting /
selected OFF code in2efcd79 remains accepted; do not redo it or its unchanged tests.
Monthly2Nov operational P0 remains independent: accepted standing scope400/280/40,
conditional entry/CASH14:30UTC/16:30Cyprus; no reactivation or strategy change.
Brain learning/native Mac DATA transport remain later P1; no new research family.
