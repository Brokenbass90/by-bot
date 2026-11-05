# V2 writer transition and Monthly precision comparison — 5 November 2026

## V2 transition accepted; existing evidence preserved

Actual read-only observation: 2026-11-05 06:00:45.790607 UTC / 08:00:45 Cyprus.
Current manifest PID1879/start05:58:57UTC/startcount115 matches producer
0f7e5f9dbc2e409ec634f2d6f8ea127feadbf06d4605bc54b11a55ec58f306fa and
shared module bd9175ee7ccd10791f71d214376d03322eef4d9ff94100894de57ada5fb908ff.
Latest history entry matches manifest exactly with first new line116. Existing
selected consumer binding accepts it without a code change, repin or guard waiver.
All eight selected bundle files and thin launcher match their existing manifest.
Claimed writer PID exists; this check did not independently reacquire/test its lock.

Complete journal prefix:115 rows/115 unique IDs/no partial tail; all100 existing
own prefix anchors and their saved source bytes match current prefix exactly.
No old rows, measurements or outcomes were edited/replayed by this check.

Existing automatic hook at05:58:58UTC accepted V2 (PRODUCER_DRIFT absent):
measured0/joined4/blocked3. Three old previously-unobserved rows correctly got
PREVIOUS_PRODUCER_UNOBSERVED_NO_REPLAY. These are preserved historical exclusions,
not new opportunities. Four joins concern prior captured measurements, not four
independent trades or fills. Aggregate hook status UNKNOWN due to these exclusions;
V3 was PENDING_OUTCOME. Mixed-resolution schema compatibility remains OPEN.
No extra cycle, network GET, producer restart, hook or runtime edit was performed
by this verification. Broker requests/writes0, money authority false.

[Verified transition](evidence/poly_v2_transition_20261105/verified-transition.json).

## Monthly: precision differs, but cents are not an established repair

| Successful/rejected path | Amount/quantity serialization | Evidence limit |
|---|---|---|
| AMD1Oct successful market BUY/day | notional formatted to2dp | Deployed source+execution receipt; not original raw wire |
| NET15Oct successful limit BUY/day | qty and2dp limit_price | Different order type; not comparable market-notional request |
| LLY3Nov rejected market BUY/day | notional string101.413902261, exactly9dp | Reconstructed from durable intent+pinned serializer, not raw wire |

Prior bounded native-log/intent/observation investigation found no saved original
HTTP422 body or request ID; reconstructed audit still explicitly records
actual_response_body_available=false. Thus actual code42210000 and the proposed
message have NOT been observed for LLY. No broker rejection is invented.
Fresh connected-mail search found only the earlier support auto-ack, no substantive
response. Private mailbox/request identifiers and metadata are not exported here.

Primary Alpaca references checked5Nov:
- [Fractional order support](https://alpaca.markets/support/how-can-i-pass-a-fractional-order): both qty and notional accept up to9 decimal places.
- [Alpaca staff precision explanation](https://forum.alpaca.markets/t/notional-increment-does-not-fulfill-minimum-pricing-criteria/12844): the quoted notional42210000 example used11 decimal places; staff advised at most9, not cents. This is a primary staff explanation, not a promise about our missing response.
- [Trading order documentation](https://docs.alpaca.markets/us/v1.1/docs/orders-at-alpaca): code42210000/increment wording also appears for invalid limit_price and stop_price. Field and full message matter; code alone is not specific to notional.

Therefore9dp vs AMD2dp is a confirmed difference, not proof of a precision defect.
No rounding, new keys, manual BUY, retry of spent intent, date transfer or financial
runtime installation was performed. If broker logs establish a notional precision
rejection for the actual request, prepare the minimum field-specific fix and a new
bounded dated packet with separate owner GO. Existing local error-capture repair
remains NOT_DEPLOYED and is not by itself a422 repair. Old3Nov window stays expired.

References to existing evidence: MONTHLY_MAIL_REVIEW_2026_11_04.md,
MONTHLY_HTTP422_DIAGNOSIS_2026_11_03.md and
reports/evidence/monthly_http422_20261103/reconstructed-request-audit.json.
No application code changed; no repeated full test suite is warranted for this
read-only evidence/documentation update.
