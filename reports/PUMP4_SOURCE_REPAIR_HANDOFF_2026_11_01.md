# PUMP4 source handoff — 1 November 2026

**SOURCE_COVERAGE_PASS / FINANCIAL_HANDOFF_BLOCKED.** New candidate is staged,
not selected. Existing financial owner remains SOURCE_BLOCKED. This is not
READY_FOR_OWNER_GO and no financial command is issued to the owner.

## Actual result

The repaired bounded reader now distinguishes partial H1 publication prefix,
source-finalization pending and verified closed-hour coverage. A missing/failed
completed source is BLOCKED_NEW_INPUTS, not NO_SIGNAL. Existing selected_tick
still reconciles an admitted lifecycle before candidate reading; a source failure
cannot cancel custody. Legacy config behavior is unchanged.

- WAITING_H1_PUBLICATION_PREFIX: first <=60s, only currently available prefix
  checked; no assertion of full negative coverage.
- WAITING_H1_CENSUS_FINALIZATION: entry window closed, receipt pending through
  +120s. Existing producer collects through +90s and has 3s socket-close timeout.
  This is an explicit health grace, never an extension of entry eligibility.
- ENTRY_WINDOW_CLOSED_COVERAGE_CHECKED: exact137-symbol receipt, current index
  and original observations agree; available/nontrading instruments separate.
- Missing receipt after +120s or invalid coverage/index/bytes: source blocked.

No global archive scan/deletion, new producer, second owner or strategy retuning.
The completed check is bounded by137 and still verifies available public files;
it does not reinterpret unavailable instruments as negative decisions.

**Current actual-source proof:** 1Nov14:29:30.485UTC /16:29:30.485Cyprus, H1hour14UTC,
134 exact publication/observation pairs,3explicitly unavailable,0raw signals,
coverage verified. Network denied, no financial owner/lease construction,
0broker requests/writes. This is current source coverage, not an entry/admission
test or proof of historical index durability.

**210local / same210VPS PASS**, network-denied VPS candidate194files:
`/opt/bybot-research/pump4-current-hour-repair-20261101/candidate-05f89618d8550664/app`.
ManifestSHA `05f89618d8550664cf2d914f000ef9f7b101d32176032adb78a6d7bbbdb03dfd`.
Supersedes badb0d4a source-only candidate for next selection, without overwriting
that earlier package. Existing LIVE/unit/source hashes remain unchanged.

Independent Astra/high source audit completed. Coverage review found2P2:
normal90sproducer finalization and nontrading instrument metadata. Primary fixed
both and added bounded regression checks. Nine missing-coverage tests were RED
before implementation. Final follow-up reviewer hit usage limit; no expensive
fallback/repeated retry and **no final independent financial signoff claimed**.
Runtime model/effort verified in session01a19698-2e1e-7010-8cd3-79cb631a3dec.

## Five raw signals: what is and is not proven

| Source hour UTC | Symbol | Recorded original-observation completion delay |
|---|---|---:|
|30Oct18:00|HYPEUSDT|15.767s|
|31Oct10:00|XPLUSDT|8.286s|
|31Oct10:00|ESPUSDT|30.506s|
|31Oct11:00|HEIUSDT|45.026s|
|1Nov02:00|GWEIUSDT|37.631s|

Exact publication/original observation equality, decision ID, history digest,
canonical prior prefix, frozen pins/universe and scope timestamps verified.
No strategy/judge/outcome run. Actual historical HTTPS parity, next-open, quotes,
interval stop/target touches, filters, fees, funding, account capacity and unspent
claim are UNKNOWN. Maximum1entry cannot become5trades; XPL/ESP compete in one hour.

**Correction to earlier timing shorthand:** publication_completed_ms is sampled
after durable original observation but BEFORE current-index publication. Full
hour receipt has no completion timestamp. These values do not independently prove
when the financial reader could durably see the index. Historical index/window
availability and first SOURCE_BLOCKED time remain UNKNOWN. No lost-profit claim.

## Actual account and unchanged production

Independent GET 1Nov14:31:47.463UTC /16:31:47.463Cyprus: flat positions, no open
orders; paginated linear orders/executions and linearUSDT transaction log return
zero rows from28Octscope start through14:31:44.989UTC.6GET total, all complete.
Old root has no admitted lifecycle/risk/revocation and empty flows/barriers/attempts.
This is a bounded current/history snapshot, **not terminal fee finality**, future
flatness, all-account product census or completed-pilot NO_TRADE.

PUMPowner3198429 and DATA3152955 remain active/0restarts; original lock818853.
Old financial receipt remains BLOCKED_NEW_INPUTS / OBSERVATION_BOUND. Monthly
service/timer hashes unchanged, timer active/waiting. No financial writes by us.

## Precise deployment draft and remaining blockers

Prepared exact review-only config/scope/unit/health/wrapper/notification files:
`.private/pump4_source_repair_20261101/source-envelope-review-v1`.
Review dossier SHA59c105f4bb294f8db0c3a4eb22781d36d4bf1059efa825694bfd5edf3902b2af.
Public artifact contains hashes/constraints only, not credentials.
Proposed scope a989d05bd13f7bad2c275e8dedc96af8d4499ff3ccc7d579beddd8d216a9fd4d;
config7ae4b11b4e80440db006ca5bb845662c5952abd4ec714888097dac130b3c4c75;
unit1d9b5cff6bb04b08810c4fcbcbadae7d474cb21b3a5f570199222dbdbd5e5785.
This is **not an executable activation packet**: no installer or owner-go included,
generated financial-health draft not acceptance-tested. Do not run/install it.

Original50allocation/30gross/20reserve/risk1/max1entry+position, epoch, lock and
original expiry are preserved. No scope extension, no claimed risk release/reset.
Proposed fresh root can ONLY be used after stopped-writer/original-lease proof
that old lifecycle/risk/attempts/barriers/flows are completely unused. Otherwise
STOP and reconcile existing custody; never copy/reset money history as empty.
Old scope/GO/history bytes must remain preserved; old entry must be revoked before
new authority. Existing observer lock and single selected writer must be retained.

1. **KEY_LIFETIME:** authenticated query-api says valid now, expires6Nov08:43:37UTC
   /10:43:37Cyprus. Frozen168hhold can continue until8Nov19:26:32.774UTC after
   latest allowed entry, and reconciliation can last longer. No safe next pilot
   with this expiry without a separately accepted custody/rotation arrangement.
2. **Exact physical handoff not implemented/accepted.** Review draft is not enough:
   source/config/unit/observer CAS, old-entry revocation, unchanged money history,
   fresh before/after account read and single start need offline failure acceptance.
   Never call old activation.py without --readback or repeat old GO.
3. **Final critical review incomplete** after reviewer allowance limit. Primary
   fixes/tests are evidence, not an independent financial approval.

## Key lifetime / rotation runbook

Current key is NOT already expired and is NOT the source-reader defect. Do not
replace active .env, delete current key or send secrets to chat/Git. First secure
sufficient lifetime for custody using the existing-account API settings or a new
IP-bound key. Agent does not change Bybit API permissions here.

For a new key: owner creates it for the same actual Bybit userID/parentUID,
restricted to VPS64.226.73.119, required contract order/position permissions only,
no withdrawal/transfers. Stage through a separate protected local/server file,
not the current bound source. Verify both query-api results, same account identity,
permissions/IP/lifetime, full account and old-state proof before any selection.
Hash/mode0600/credential fingerprint then become part of a NEW exact envelope;
old key-bound draft approval cannot be reused. Original key remains available
through verified custody handoff. No secret is committed or printed.

Bybit documents query-api readOnly/permissions/userID/parentUid and expiredAt;
expiry fields apply to unbound keys or password changes. Do not assume that any
nonempty/epoch expiredAt value always means a new key is required; verify actual
binding and API result. [Official API documentation](https://bybit-exchange.github.io/docs/v5/user/apikey-info).

## Expiry, Monthly and next engineering gate

Current GO ends TODAY1Nov19:26:32.774UTC /21:26:32.774Cyprus. Not yet expired at
this report's14:31UTC readback. Existing6hread-only receipt automation is ACTIVE;
it reports expiry once, preserves custody and cannot extend scope. Post-expiry
NO_TRADE requires another fresh independent GET plus complete empty money history;
otherwise UNKNOWN. Prior14:31 snapshot must not be relabelled post-expiry.
Existing monitor updated (same ACTIVE/6hschedule/thread) to use only pinned
read-only-preflight.py SHA f647a97b66dc9a07473e094e421dd3fd7301e007dcf26ae9113696464c657068
afterexpiry. It verifies all193staticcode pins, uses only the trusted bound-key
loader and six GETs, and cannot create an owner/lease/GO. Confirmed pilot
NO_TRADE/no custody deletes only that monitor, not native workers/history.

Monthly stays v6:2Nov14:30UTC /16:30Cyprus conditional execution, LLY/LMT/INTU
diagnostic selection, same400/280/40. Future BUY/CASH/broker readback remains a
future operational check, not something these source tests have proved.

After source handoff, continue existing TINY2 source accounting/cost-release and
actual-account ORDERS_OFF. Do not reimplement accepted2efcd79 components. The
separate cost-release policy remains NOT_IMPLEMENTED_NOT_APPROVED.

Manager proposal accepted as direction: minimal versioned diagnostic contract,
one contemporaneous source→eligibility→risk trace, then second LIQ SHADOW adapter.
These are next gates, not delivered universal interoperability. See draft
`docs/TRADING_DIAGNOSTICS_CONTRACT_V1.md`; no engine rewrite or research-rule change.

Evidence directory: `reports/evidence/pump4_source_handoff_20261101/`.
