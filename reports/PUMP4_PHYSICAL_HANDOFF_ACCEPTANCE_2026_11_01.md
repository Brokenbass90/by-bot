# PUMP4 physical handoff acceptance — 1 November 2026

The installer, generated health observer, immutable packet builder and independent
acceptance are complete. **Actual VPS verify-only is BLOCKED_PREFLIGHT:
KEY_EXPIRES_DURING_CUSTODY.** This is the one observed operational blocker before
requesting a separate exact financial GO; it is not READY_FOR_OWNER_GO or a LIVE
repair. No financial apply, key change, restart or new permission was performed.

## What is accepted

- Continue aef951d: the accepted194-file reader candidate05f89618 and its210local /
  same210VPS tests remain unchanged. No new reader or strategy was developed.
- New scripts: pump4_source_handoff_v1.py, pump4_source_repair_health_v1.py and
  build_pump4_source_handoff_v1.py. Default does nothing financially; verify-only
  reads state. Apply requires a new exact packet GO and complete acceptance.
- Original account lock818853, observer lock819480, old anchors and unused money
  root are checked. Under the observer lock, selected-owner/root/snapshot are
  checked again before claim/revoke/stop; after stop they are checked under the
  account lock. No copying/reset of spent claims, risk/loss history or old GO.
- Exact source/config/unit/wrapper/health binding, same account UID and key-life
  guard; only a separately pinned credential source can select another key.
  The current env is never hot replaced. DATA and Monthly units are preserved.
- Before any new start, a failed handoff restores old custody with entries
  revoked. After any new start attempt, ambiguity is readback-only. Revocation
  keeps selected custody; no retry or automatic rollback of a possibly trading
  owner. No order API is implemented in this installer.
- Generated health distinguishes PENDING_SOURCE from verified coverage and
  source failure. Normal pending does not alert. Receipt scan streams without
  an arbitrary200000-file cutoff. Optimized Python is rejected before I/O;
  the derived unit forces PYTHONOPTIMIZE=0 and wrapper hashes use explicit checks.

## Verification and independent review

**50 tests locally PASS (2.52s), the same50 on VPS PASS (13.13s).** These are not100
independent tests. They exercise temporary fake operations, actual temporary
flocks and production-shaped nonsecret configuration. VPS acceptance ran with
network denied and systemctl/systemd-run/systemd-analyze stubbed. No broker calls
or live SystemOps apply occurred. VPS stage202files manifest:
`ce31eb411e347c8a8a92061e69f3e31c2af14962b79b612f6ac541e5c7c6f460`.
The first copied pytest environment lacked `_pytest._argcomplete` before tests;
acceptance then used the existing root/by-bot pytest environment also used for
prior210. This was a test-harness failure, not a successful test or runtime defect.

Independent final review: gpt-6-astra/high, runtime session
`01a197ee-baf5-79c2-a40a-a75ce96dcab1`, actual model/effort verified.
Original review found one P2 optimized-Python bypass; primary additionally found
an owner-change-before-lock race. Both have RED evidence and targeted fixes.
Final targeted review16:42:04UTC: PASS, unresolved important0;14 targeted tests
are a subset, not added to50. Reviewer financial readiness prose predates packet
sealing; the subsequent sealed receipts bind the same unchanged material SHA.

## Real preflight and unchanged production

Actual verify-only observed **1Nov17:13:38.248UTC /19:13:38.248Cyprus**:
13 authenticated GETs, broker writes0; flat=true, full pilot history_empty=true,
allocation50 available. Actual key fingerprint/account UID match the original
binding. All preceding physical/source/account gates passed; the next check
returned KEY_EXPIRES_DURING_CUSTODY. This does not prove fee finality or future
flatness. Raw broker balance is retained mode0600 privately, not in public evidence.

After-check17:23:37.609UTC: original financialPID3198429 and DATAPID3152955 running,
0restarts, unchanged unit SHA; proposed runtime and handoff claim absent. Monthly
unit hashes unchanged, timer active/waiting. An inactive oneshot service between
ticks is not a failure. This check returned no last-cycle journal lines, so no new
Monthly actual-cycle acceptance is inferred from it.

The old owner is still the legacy SOURCE_BLOCKED contour; the repaired candidate
is staged, not selected. Old entry GO still ends1Nov19:26:32.774UTC /21:26Cyprus.
At this report's17:30UTC observation that deadline is future. Existing read-only
monitor must use a fresh post-expiry GET/full history before NO_TRADE; current
pre-expiry empty history is insufficient. No automatic extension or release.

## Exact staged proposal, not an authorization

Local `.private/pump4_physical_handoff_20261101/owner-packet-v5` and VPS
`/opt/bybot-research/pump4-current-hour-repair-20261101/owner-packet-v5`.
Packet SHA256:
`5dcdcb20abb1220f066a4819c3f93e9a341658b8cd28dcfd42424ceb8f6bb9fe`.
Financial material SHA256:
`d3c3b7325b91f97281cfe23e4206204f0624c9b91dd31ba979272a4d20453611`.
The packet and receipts are immutable/staged, not installed or activated.

Proposed new entries1Nov19:26:32.774UTC–8Nov19:26:32.774UTC; allocation50USDT,
max gross30, reserve20, scenario risk1, one entry/one position. This is a separate
single-entry source-repair pilot, **not serial TINY-2**. Cross margin remains;
50 is not isolated and1 is not a guaranteed loss bound. No scope is extended.

## Sole current blocker and owner action

Actual API key expires **6Nov08:43:37UTC /10:43:37Cyprus**. The proposed latest entry
plus168h custody and24h reconciliation requires access through
**16Nov19:26:32.774UTC /21:26Cyprus**, or independently verified no-fixed-expiry
metadata with exact VPS IP binding. Current key is valid now; this is a custody
lifetime problem, not evidence that all API access has stopped.

Owner action: arrange sufficient same-account Bybit contract-trading access,
without withdrawal permission, and retain the old key/current env until handoff.
First inspect whether the existing key can safely obtain sufficient lifetime via
its supported IP-binding settings; current exact_vps_ip=false does not establish
that it has no IP binding. Do not change a shared key blindly. Alternatively stage
a dedicated same-UID key in a separate0600 VPS file bound to64.226.73.119. Send no
key/secret through chat or Git. Codex must not change keys itself.

A separately staged key changes credential pins and therefore requires rebuilding
and sealing a replacement exact envelope using the accepted builder; do not patch
this immutable packet. Same-key lifetime change still needs fresh metadata and
verify-only. After actual key/source/account gates pass, present the final exact
packet and request separate new financial GO. Never execute or repeat the old GO.
No unready financial launch command is provided here.

One attempted broad snapshot was rejected by automatic approval review before
execution. It was replaced with metadata-only stat/hash inspection and existing
nonsecret local configs; no credential bytes were exported and this is no longer
a blocker. The rejected script must not be run.

## Monthly and subsequent work

Monthlyv6 remains400/280/40, existing timer enabled.30Oct DATA diagnostic
LLY36.2193% /LMT38.1308% /INTU25.6499%, core200 QA PASS; first local import was late
1Nov09:27UTC, not a timely30Oct night import. This is not a BUY/fill receipt.
Existing conditional execution window: **2Nov14:30UTC /16:30Cyprus**.

One bounded postwindow read-only follow-up `monthly-2` is scheduled2Nov16:40Cyprus.
It checks native observations plus independently pinned GET-only Alpaca helper,
actual fills/positions/protection and identity; missing/partial evidence=>UNKNOWN.
It cannot activate/replay orders, alter services or infer CASH from empty account.
It deletes only itself after its single check. Future market execution is PENDING;
existing data/legacy preflight monitors and native Monthly timer are preserved.

After key readiness and separately approved physical repair, return to existing
TINY-2 actual-account OFF/cost-release work; do not reimplement serial components,
expand Brain/Factory or alter Monthly. Historic five raw signals are not five
proved admissible trades or missed profits; historic durable index timing remains
UNKNOWN.

Evidence: [directory](evidence/pump4_physical_handoff_20261101/), with exact source
hashes, RED/GREEN outputs, both reviews, public packet/proof manifests, safe before/
after metadata and sanitized actual preflight. Private credentials/config payloads
and raw broker balances are excluded.
