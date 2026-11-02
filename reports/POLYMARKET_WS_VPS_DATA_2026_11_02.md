# Polymarket: VPS DATA capture and verified Mac archive — 2 November 2026

**VPS_DATA_LIVE_PASS — both canonical WS streams, native delivery and verified cache eviction accepted.**
This is DATA engineering acceptance, not an economic PASS, executable opportunity,
order executor, Brain learning result or permission to trade Polymarket.

## What is actually installed

One public Sports WS producer and one public CLOB worker are enabled on the VPS.
A separate public Gamma catalogue refreshes every 30 minutes. Both old Mac WS
producers are stopped; the existing minute monitor and unrelated research jobs
remain. Original WS logs, source files and DATA-lock inodes/modes are preserved.

The native Mac LaunchAgent `com.bybot.poly-ws-consumer-20261102` holds the original
`sportsws`/`clobws` DATA locks and runs the pinned importer periodically. The normal
existing launcher refused both duplicate roles using a harmless `/usr/bin/true`
probe. No AI invocation is required for capture, delivery or verified cache eviction.
This is normal-launcher exclusivity, not protection against a deliberate direct
manual bypass. Mac login/launchd restarts are supported; a physical sleep/reboot
was not performed during acceptance.

Frozen prototype selection is reused unchanged: top 1,000 Gamma events, at most
150 selected markets, and the existing CLOB question/time filter. Both outcome
tokens are captured for each eligible selected market. This is **not all sports
markets**. A local unpublished prototype intake is explicitly distinguished from
published research acceptance; source inputs are preserved under `inputs/`.
No Claude checkout code, judge, preregistration or economic threshold was changed.

Final independent file/receipt readback **14:06:23.728 UTC /16:06:23.728 Cyprus**:
**284segments**, all284hash/seal/import-receipt/first-mtime matches against VPS
ACKs,0local-only files. Mac archive:238catalogue,40Sports and6CLOB segments;
Sports809RECV, CLOB61RECV including4book snapshots for2assets. These are messages,
not trades or independent opportunities. Current native delivery exit0/warnings[].
Latest DATA aggregate peak **135,086,080bytes (~128.8MiB)**, below192MiB hard cap.
Proof: [actual acceptance](evidence/polymarket_ws_data_20261102/actual-acceptance.json)
and [selected packages](evidence/polymarket_ws_data_20261102/deployment-selection.json).

## Exact selected packages

| Function | Immutable candidate / source manifest SHA256 |
| --- | --- |
| WS workers/catalogue | `candidate-b79fcd827bea31cc` / `b79fcd827bea31ccaf21217ab1e590f3024d971813ccdc5f124bc748d7791eca` |
| Native Mac delivery and isolated VPS export/ACK helper | `candidate-0f337c1798e06975` / `0f337c1798e0697523422c429c398d86327fe8f4e288f4bd96edca48db6f167a` |

VPS base `/opt/bybot-research/polymarket-ws-data-20261102`; shared DATA runtime
`/var/lib/bybot-polydata-20261102`; epoch `poly-ws-data-20261102`.
Mac archive `/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28/research_lab/data/poly_ws_vps_v1`.
Full selection/spec/packet pins: [evidence](evidence/polymarket_ws_data_20261102/).
Earlier candidates and spent installation/cutover claims remain historical;
**do not repeat their applying commands**. A consumer-only update does not replace
or silently repin the independently selected WS services.

## Actual acceptance and measured limits

- Both public DATA services physically activated **13:24:08.358 UTC**; all preserved
  financial unit hashes, owner PID3669955, DATA PID3152955, original account lock
  inode818853 and two LIQ PIDs matched before/after.
- Real Sports game messages reached sealed files and the Mac archive. A DATA-only
  restart at **13:34:18.553 UTC** changed the Sports session/PID while preserving
  prior completed files. The interrupted partial remains untouched; missing
  messages across the interruption remain `UNKNOWN`.
- A separately labelled public CLOB transport probe at **13:32:52.837 UTC** received
  both outcome books for market5977784: depth72bids/9asks and9bids/72asks.
  Venue timestamp1793626371773, local receive1793626371813. The40ms clock difference
  is not an independently calibrated one-way latency or proof of an exploitable
  price. That probe was outside frozen eligibility and is excluded from canonical
  strategy observations.
- At **13:44:08.802 UTC**, all174 local segments matched their VPS eviction ACKs,
  including compressed/raw hashes, immutable import receipts and first local
  mtimes. They comprise158catalogue,15Sports and1CLOB process-start segments.
  Sports contained361RECV rows; the CLOB process-start is not a quote observation.
- Native deliveries completed **13:41:23.325 UTC** (4segments) and
  **13:46:46.219 UTC** (6segments), exit0/current warnings empty. Neither is a trade.
  The status's `error_type` retains the earlier timeout classification; current
  health is determined by latest `last_pull_exit`, timestamp and current warnings.
- Aggregate measured DATA memory peak **128,249,856 bytes (~122.3MiB)**. The slice
  enforces192MiB RAM and30%of one CPU core in total, including all export/ACK helpers;
  individual workers have10%CPU/128MiB, transfer helpers10%CPU/96MiB. DynamicUser,
  no capabilities, ProtectHome and strict filesystem protection are selected.
  No credential files or financial runtime imports are needed by these services.

Canonical CLOB started naturally on the frozen eligible market6388992 at
**14:00:04.835 UTC**. Its two initial books were received **14:00:04.853 UTC**,
venue book timestamp1793628002466: one outcome0bids/48asks, the other48bids/0asks.
Both original outcome IDs and empty sides are preserved. This is canonical quote
capture, **not a two-sided executable market or economic opportunity**. The venue
book-state timestamp is not assumed to be a message-send timestamp. Final Mac
copy/ACK verification passed in the284-segment acceptance receipt.

## Storage and cleanup: implemented, bounded, no paid service

| Location | Rule |
| --- | --- |
| VPS Sports / CLOB / catalogue |128 /512 /128MiB role budgets; 2GiB free-space stop threshold, with bounded in-flight writes |
| Early warning |75%role budget, VPS free below3GiB, delivery backlog older than1h, stale/stopped/reconnecting source |
| Mac archive |20GiB hard cap and10GiB free floor for new files; warning at15GiB archive or less than15GiB free |
| Detailed VPS eviction ACKs |7days, then recoverable daily hash digests; complete Mac files/seals/import receipts retained |

Flow: seal+fsync on VPS → exclusive Mac import → verify compressed/raw hashes,
seal and immutable receipt → fsync directory ancestry → ACK → delete **only the
acknowledged new source cache files** and retain the eviction proof. Conflicts
are not overwritten. Source partials, old research data, financial records and
unrelated files are never selected for deletion. Local cache cleanup cannot be
mistaken for research outcome/judge consumption.

Two actual catalogue captures produced **45,396,932 compressed bytes**, about
22.7MB/capture. At the30minute schedule this alone projects roughly1.09GB/day
on Mac; this is a storage estimate, not a measured full day. CLOB busy-match rate
still requires real observation. The catalogue's128MiB queue therefore holds only
about2–3hours at this observed rate, less after retained ACK overhead. A long Mac
sleep/offline period can stop catalogue capture at quota, and later stale
catalogue blocks CLOB. This protects disk and preserves honest gaps; **unlimited
continuous capture while Mac is offline is not proven**. Native services retry
once/minute and resume after verified ACK cleanup frees space.

After cache eviction the Mac is the principal full archive. There is no claimed
second independent backup. Do not delete Mac originals to make room without a
separate verified archival decision. No cloud subscription, VPS upgrade or
indiscriminate server cleanup was installed.

## Failures found on the actual path and resolved

1. The first catalogue start rejected a real10.1MB Gamma page because the original
   bound was4MiB. A new immutable candidate allows at most16MiB/page and preserves
   exact response bytes in1MiB chunks with a full-body SHA. Segment/import bounds
   remain8MiB; partial source never becomes an accepted catalogue. Two regressions.
2. `screen quit` removed the two WS screens but left their exact Python children
   alive. The spent cutover was not repeated. After fresh PID/cwd/source checks,
   only those two children were terminated; locks and the native consumer were
   independently reconciled. No production trading process was targeted.
3. Per-file SSH transfer timed out on the158-segment initial catalogue backlog.
   The delivery-only candidate now exports up to16segments/8MiB compressed per
   bounded request, verifies each independently and ACKs each batch immediately.
   Initial backlog timeouts are preserved; a subsequent82.49s catch-up delivered
   42segments, freed10,899,959source bytes and reported no warnings. The two later
   successful native cycles, not fixture tests, demonstrate resumed delivery.
4. Seven unrelated tracked local PUMP4/DATA scripts were unexpectedly absent.
   Owner reported no intentional deletion. Only absent paths were restored from
   exact HEAD bytes with create-exclusive writes; no concurrent file was replaced
   and none was executed. Cause is unknown; no blame or deletion approval inferred.

## Verification and preserved production

**43local / same43VPS PASS**, VPS network denied. The original39-test candidate
also passed `systemd-analyze verify`. One actual Astra/high independent review
found1P1/3P2; each was reproduced RED and corrected. Later actual-response/batch
corrections have primary review and targeted regressions; no second independent
review or financial signoff is claimed. Full suites were not repeated.

Independent existing pinned PUMP4 `--readback` at **13:38:35.369 UTC** returned
`LIVE_ARMED_HEALTHY`, same scope2de0b6ec…d0970/configf715e676…62daa,
actual_entry_executed=false,134publications/3unavailable/0raw/coverage_complete.
It does not prove a trade, profit or actual-position protection. No activation,
GO, risk, key, financial unit, Monthly configuration or broker mutation was run.

### New P0 found during closeout — do not call PUMP4 currently healthy

The second pinned readback **14:08:36.808UTC** returned
`OWNER_ACTION_REQUIRED / SUPERVISOR_SOURCE_BLOCKED`; supervisor receipts continue
`BLOCKED_NEW_INPUTS / PUMP4_RUNTIME_SOURCE_CURRENT_HOUR_COVERAGE_UNVERIFIED`.
The owner process is still active PID3669955/NRestarts0, but healthy source
coverage is **not** confirmed. This supersedes the13:38 healthy snapshot.

Original14:00UTC census:134/134complete pairs,3unavailable, only127/134published
within60s; hour_pass=false. C98,ENA,MSFT,NBIS,PAXG,TSLA,WLFI publications took
60.051–62.742s. Six local receive timestamps also exceed60s; NBIS received59.822s
and published60.051s. These timestamps do not independently distinguish exchange
lag from handler queue/CPU/IO. No disconnection was recorded. The source receipt
contains0rawsignals, so no profitable missed trade is inferred.

The existing pinned observer already collected a complete broker capture at
**14:18:05.154UTC**. Pure file classification under the accepted source pins
confirmed positions_flat=true/open_orders_empty=true/admitted_lifecycle absent.
The classification used the capture's original timestamp, not a retimed current
GET; balances/keys remain private. This establishes account flatness as of that
capture, not a healthy signal source or future finality. This position/order
flatness applies to the captured Bybit linear USDT scope, not other account products.

[Incident evidence](evidence/polymarket_ws_data_20261102/pump4-source-incident.json).
No PUMP4/collector restart, cutoff relaxation, old-signal replay or new order was
performed. Resource interaction with the new DATA load is **not ruled out**;
cause remains OPEN. Next P0 is bounded source timing investigation and fresh H1
verification under the unchanged60s gate. Preserve the imminent Monthly window;
do not silently install another reader or expand scope based on this report.

Monthly remains personally armed v6,400/280/40, with the separate **2Nov14:30UTC /
16:30Cyprus** conditional execution window. `monthly-2` remains ACTIVE for16:40Cyprus
pinned read-only BUY/CASH/NO_ADMISSION/protection reconciliation. At this engineering
acceptance the window is future; diagnostic picks are not orders or fills.

`brain-context-shadow.service` remains failed; it was not restarted or extended.
That stopped worker is separate from the Claude Mac advisor and does not demonstrate
continuous Brain learning since30October. Its investigation is a separate next stage.

## Research consumer and causality boundary

The new compressed raw corpus is separate from the legacy Mac WS journals.
Existing research judges were not repointed or run. Claude needs a versioned
read-only adapter to this corpus before attributing new nightly results to the
VPS feeds; otherwise the old input paths can appear stale. No original log is
silently appended with a new source or schema.

`received_ms` records the local receive observation. Only the completed fsynced
seal establishes completed artifact publication. A timestamp written before
fsync is not an independent historical durability witness or a prospective
trading decision. Transport events, warmup and later research replay must retain
these distinctions.

## Next decision

Use these original streams through a versioned research adapter to measure executable
sports opportunities under an explicit economic protocol. Data capture is now
physically present; it does not establish Polymarket profitability. No trading
executor or new universal Brain/Factory engine is justified by transport PASS.


## Коротко для менеджера

Polymarket DATA физически перенесена на VPS: оба WS, исходные сообщения и два
исхода, native-доставка на Mac и очистка только после проверки архива.284сегмента
сверены полностью;43проверки локально/наVPS. Это готовность данных, не прибыльный
Polymarket. Старые judges ещё требуют версионного адаптера нового корпуса.

При финальной сверке обнаружен отдельный P0 PUMP4:14H1получен полностью, но7из134
публикаций вышли за60с; источник блокирует новые входы. Счёт по уже записанному
GET14:18UTC вlinearUSDT безпозиций/открытыхордеров; API/GO не переактивировались. Нужна диагностика
задержек без ослабления cutoff; вклад новой DATA-нагрузки ещё не исключён.
Monthly16:30Кипр и read-onlyконтроль16:40сохранены. Brain — отдельный следующий
этап после этих операционных P0, не новый универсальный движок прямо сейчас.
