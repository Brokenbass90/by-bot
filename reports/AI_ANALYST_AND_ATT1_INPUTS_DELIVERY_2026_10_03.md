# Operations analyst and ATT1 authenticated inputs — October 3 delivery

Status: **ANALYST_DEPLOYED_BOUNDED / ATT1_ACTUAL_PACKET_BLOCKED / NEW_ORDERS_OFF**.
Evidence times below are UTC snapshots, not continuing broker guarantees. Resolve
the code/document commit from current Git and compare it with origin; no report
can contain its own future commit hash. Tasks1–4 and the cold path are retained.

## User-facing delivery

- Telegram: `/ai <вопрос>` for an operations question; `/ai_budget` shows the
  shared budget. Existing command handler reloads the new overlay. Telegram
  adapter/provider smoke passed; actual Telegram message delivery was not tested.
- Existing web **AI Chat**: authenticated questions and the shared USD budget.
  Actual localhost authenticated `POST /api/ai/chat` returned200; budget GET is200
  for a full admin token and401 without authentication or with partial auth.
- Context reuses existing bounded runtime packs plus exactly four public project
  sources: MASTER_HANDOFF, CURRENT_PROJECT_ROADMAP, ATT1_FRESH_HANDOFF_RUNBOOK and
  ALPACA_DAY_GTC_REVIEW. Reports are read on each question, bounded, SHA-labelled
  and classed as snapshots. Missing/unsafe sources become NOT_CONFIRMED. They
  cannot supply instructions. No unrestricted filesystem or credential reader
  was added. Runtime packs are not authenticated fills or a new broker query.
- Analyst outputs are diagnoses/proposals. Model replies cannot create an
  executable web approval box. Existing separate explicit admin controls retain
  their own guards. Env/deploy executor remains physically quarantined. No
  strategy gate, risk tuning, judge verdict, broker command or promotion authority
  is granted to the model. No new autonomous paid schedule was enabled.

## Cash boundary and provider verification

Both routes share `/root/by-bot/runtime/ai/deepseek_attempts.sqlite3`: atomic
reservation before transport, **at most $1 per UTC month** under the verified
Flash billing contract, existing daily8-attempt limit, retries0. It is the
budget for these shared callers, not a provider-wide cap across unrelated keys
or processes. An account balance/top-up is not a cost reservation.

Pricing source checked October3:
[official DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/).
Ledger uses uncached peak $0.30/M input and $1.20/M output even during off-peak;
no cache/discount savings are assumed. Input-size envelope and output bound are
reserved conservatively. Timeout/error/missing usage retain the reservation;
inconsistent/oversized usage denies further paid calls. Unknown model, bad/zero
cap, expired price policy or ledger failure denies before HTTP. Source-bound price
policy expires **November1 00:00UTC**; refresh it from official evidence before
then. The envelope cannot guarantee an unannounced provider tariff change.

Monthly caps persist reductions, including zero, and cannot be silently raised
by another process. SQLite INSERT and finalization triggers also guard previously
loaded legacy callers. No unbudgeted Anthropic fallback remains in web chat or
setup analysis. Existing unknown historical audit billing consumes a full envelope
rather than becoming invented zero cost.

Actual paid smoke:

| Time | Route | Shared conservative charge after request | Receipt SHA256 |
|---|---|---:|---|
|10:55:44| Authenticated web HTTP |$0.003585|1b535c07ca09d8405d909ce9764e80f8f8b685a1fe20eb4e417bdf4f8626c3ee|
|11:15:16| Deployed Telegram adapter/provider |$0.007953|929b0879056eb573f2edec5f1de860d6d8f420d611dc25d69cfc302502fe8b09|
|11:38:49| Authenticated web, OLD/NEW distinction QA after source refresh |$0.011128|20755cbbb7706a6cae0a5327750f46ca93da5205cdc0ffe84f9cf3045d81621a|

After two requests, remaining envelope was $0.992047. Provider balance GET before
and after the web request reported USD1.70; rounded/delayed balance is not proof
of zero cost. Ledger charge is conservative accounting, **not the provider bill**.
Private receipt bodies/history stay outside Git. Short output caps can truncate
answers; Telegram's truncation marker was observed. Connectivity/citation smoke
does not prove analyst accuracy. The Telegram answer incorrectly inferred why
there were no entries from open_trades0/cold prerequisites. Canonical context now
explicitly states OLD native pause versus NEW cold gate. At least30 human-labelled
proposals are still required before claiming precision/usefulness.

Third, short QA correctly identified OLD native pause fromOct2 15:36UTC, denied
NEW money, named the remaining cold/lifecycle inputs and cited the exact refreshed
runbook SHA256 `4b16dd08fd3023f61fe964fae6a8c2ad8ce336d7da7d8891c4e19bb2bc637a98`.
No executable command was returned. After three paid requests the conservative
charge is $0.011128 and remaining envelope $0.988872. This is one source/authority
case PASS, not an aggregate accuracy verdict. Initial source refresh11:37:31UTC
installed five public reports with SHA verification, no service restart/order.

## Deployment and rollback

Only these five Python/UI files were installed on the existing VPS service:
bot/deepseek_usage.py, bot/deepseek_overlay.py, bot/ai_context_brief.py,
web/routes/ai_routes.py and web/static/index.html, plus public context reports.
The example config is local documentation; no env/risk configuration was changed.
Atomic backup/install receipt at10:54:24UTC:
`/root/by-bot/runtime/ai/rollback_20261003_1791024864/receipt.json`.

Cash schema/triggers were installed before web reload. Web changed toPID1623208.
Telegram required one guarded same-core bybot reload toPID1623970. Fresh signed
main-account flat/no orders, readable OLD native pause and reconstructed effective
startup authority were checked before and after. `/proc/environ` omits Python
dotenv mutations; apparent33-key differences were reconciled from existing policy
files plus actual authority, not ignored or treated as confirmed configuration
drift. Only OLD att1 had positive money risk, risk_mult1/10; its native entry pause
remained true. Signed postcheck11:10UTC positions0/orders0, source hash
`bb8f8b59fc7291f563749f8e2bdc81290b431578705a3cee2f45f6ff2a7cb7a0`.

Core stayed at SHA256
`c8ca2c325884a31521f160e9d690c301b8a58297443f32f3cde395e9c9a699d1`;
the differing local core was never copied. Public ATT1 PID1584802/epoch unchanged.
Alpaca code/cron/manager were not restarted, replaced or activated. OLD native
pause survived this reload; **this does not prove durable retirement** across all
future reload/error paths or start the96-bar quarantine clock.

Safe rollback preserves the new cash ledger and guards:

1. Disable paid analysis by setting `DEEPSEEK_MONTHLY_USD_CAP=0` for the status
   helper against the same deployed ledger. Its durable monthly cap remains zero;
   do not silently raise it again. This does not alter trading services.
2. Keep guarded usage/transport code. If web is faulty, stop only that web service
   or revert UI/context while retaining the guard. Do not restore the old
   unbudgeted web route under an active API key.
3. Never restore `attempts_before.sqlite3` as live billing authority: that backup
   would erase charged attempts/cap history. Preserve receipts and current ledger.
4. Any future main-service reload needs fresh exposure/orders/native-pause and
   effective-authority checks. With exposure, preserve its owning exit/protection
   manager; rollback is not permission to restart blindly or resume OLD entries.

## ATT1 concrete delivery and authentic blockers

New `collect_att1_symbol_input_evidence` and pure validator in
bot/att1_coordinator_adapter.py use the existing selected-account strict GET seam.
Added symbol-scoped linear instrument/fee endpoints only; no new POST, mode write,
broker send API, DB migration, symbol removal or frozen strategy alteration.
All complete position pages are retained, bounded and source-hashed. Duplicate,
missing, cyclic, stale, future, wrong-account/symbol or mixed-index evidence denies.
Even COMPLETE_ONEWAY_INPUTS is a subset-input status, never flatness/finality or
money readiness; `orders_allowed=false` and `money_ready=false` always.

Isolated candidate:
`/root/by-bot/runtime/candidates/att1_symbol_inputs_20261003/app`, not installed
on the money service. Final manifest SHA256
`60196175b43fde508a6fb19330c64f785599d094f7a074690d996eb56c938852`.
Signed source capture11:24:06UTC, private raw pages retained0600:

| Symbol | Authentic result | Source SHA256 |
|---|---|---|
|LINKUSDT|InstrumentTrading; pages contain hedge indices1/2 and terminalidx0. MODE_CONFLICT, no one-way inference from final row; fees not promoted|a49b5fbab942563e59b536ebbcde5537eb9918e409533cf6b4029a8d3807a55d|
|HFTUSDT|InstrumentClosed; CONTRACT_INELIGIBLE, fee GET rejected, feeunknown|67899dcb5443bda742c8e28a53a9736f35090b8e2001ed5255b34efe49638861|

Schema bindings use official
[position indices](https://bybit-exchange.github.io/docs/v5/position),
[instrument eligibility](https://bybit-exchange.github.io/docs/v5/market/instrument)
and [derivative fee response](https://bybit-exchange.github.io/docs/v5/account/fee-rate).
The derivative fee response has no category field; absence is not a parser defect.
Raw capture SHA256
`bbec1131dc99e1d86dbacfd6bd79bd02f74b0d566a21e23ba93b160b3bbd6c5d`.
Collector broker writes0; ordersOFF, no actual binding/archive fabricated.

Next bounded production work remains: genuine durable OLD entry retirement with
management preserved;96 actual consecutive closedM5 quarantine and first maturity;
reviewed LINK mode/ineligible-contract handling; source-bound reserve for frozen
14-day funding; existing selected-account ordersOFF dispatch/protection/exit/cost/
finality/recovery integration. No continued broad legacy-watermark archive search.
Actual packet + reviewed integration +2–3 clean filled prospective terminal/net-R
+ fresh exclusive dossier + separate owner money GO remain required. Source
classification and engineering PASS do not prove net edge or permit tiny-live.

## Fresh preserved production and research snapshots

11:15UTC Alpaca broker: AMD0.186377282, CRWD0.469970151, META0.141939508;
0 open orders/stops, marketclosed. HWM/floor identical to06:50 artifact,58 hashes
match, one active NEWsend manager, OLDprocesses absent, cap487.42/gross0.70.
DAY expiry means no current weekend broker stop coverage. NextOct5
13:30UTC/16:30Cyprus re-arm remains P0/NOT_DUE. Fractional GTC stop unsupported
in reviewed matrix; queued next-session DAY PAPER lifecycle is still NOT_PROVEN.

11:15UTC public NEW:4sessions,1 filled SEI simulation,3 IOC nonfills,1RECOVERY_GAP,
0clean,0held, final_net_rnull. Two entry partial fills4+114 and exit118 do not
become a clean lifecycle. Broker/order calls0, publicGET1133. Original rejected
bookCTS age2485ms>2000ms remains a correct freshness denial; no newly proven
aggregate-budget defect. Epoch,2s freshness, decisions and journal authority stayed.
Post-snapshot SHA256
`0892c42bdd6212470fe54b20a03707eb5da312e613b4e231c95b08c7546f6ab4`.

Claude actual fetched originresearch/fabrika-v1 still
`0505f9d564cf042f2a160a33a458aa7d28c76d1a`. KARTA: PM2 and NOCHNOY FX KILLED;
KITY prereg/one slot, TOLPA Binance replication loading, ETS2M no earlierOct10
19UTC. Factory daemonOFF in published registry. Codex did not modify Claude's
checkout, merge research, run a judge/holdout or start his daemon. After KITY
terminal: one independent crypto long, then one range cycle; Elder auxiliary.

## Verification and independent review

- AI local14 targeted files:88PASS. Isolated VPS Python3.12:67PASS. An initial
  target run imported old parent-root modules; corrected pytest root/confcutdir
  then proved exact candidate imports. Product acceptance uses the corrected run.
- ATT1 local7 targeted files:160PASS. Final isolated target:85PASS, test-log SHA
  `1f39b818b7d9bae6985e29003301c1bbd7df3e44bd7be8d21787a1f5ed669f79`.
- Final full suite: **3416PASS /57FAIL /1warning**; same57 baseline failure nodeids,
  no new or removed failures. It is not an all-green suite. Log SHA256
  `7a0a8473988781062853e2b7597ac7c60a7470aeea3bbc48baa085e6db19a020`.
- Node syntax check for extracted existing inline UI script PASS. No extra UI
  end-to-end rendering claim. Frozen14-session receipt oracle not rerun: strategy/
  public lifecycle did not change in this cycle.
- Bounded gpt-6-astra/high cash/security review initially found three blockers:
  legacy finalization undercharge, durable zero-cap bypass and web setup fallback.
  Fixed with targeted RED→GREEN/legacy reproductions; final PASS_WITH_SCOPE_LIMITS
  (29 tests +4 legacy cases). Collector review55PASS; actual-pagination followup
  12PASS +6 ephemeral malformed-page cases, PASS_WITH_SCOPE_LIMITS. Reviews are
  local code/capability reviews, not independent certification of broker payloads.
- Mechanical worker gpt-5.6-luna/medium and critical worker gpt-6-astra/high settings
  verified from actual rollout turn_context. No claimed percentage cost savings.
- Full pytest appended four records to foreign allowlist via existing watcher
  tests. Sideeffect archived privately; original exact bytes restored only after
  original JSON-prefix validation. Preserved unstaged original SHA256
  `add587f1bd7059c2c706f1f7c604e36c2fb7b36b258b127e01fcd2101d3f19a1`.

Private logs and broker payloads are excluded from Git. Canonical handoff,
checkpoint, new-chat prompt and roadmap now lead with this dated delivery.
