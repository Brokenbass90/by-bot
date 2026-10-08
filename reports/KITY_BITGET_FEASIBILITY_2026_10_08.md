# KITY Bitget exact-basket audit — October 8, 2026

**Bitget: BLOCKED_EXECUTION. Current frozen eight-leg basket cannot be executed
exactly. Strict signal intake independently remains BLOCKED_DATA. No canary GO.**

Owner preference: Bybit first, Bitget as an alternative, MEXC later; Binance is
deprioritized. This audit tests the existing Bitget account and exact October8
basket, without adding a venue, credentials or an order path to the KITY candidate.
Machine evidence: `KITY_BITGET_FEASIBILITY_2026_10_08.json`.

## Actual Bitget result

One bounded read-only SSH invocation performed **39 allowlisted GETs** from
**09:38:08.013 to09:38:13.888UTC /12:38Cyprus**. All HTTP200/API00000 and raw-body
hash checks pass. No retry, POST, mode/leverage/key change, funding transfer,
remote write or order call. Raw account identifiers stay in the private archive.

Complete documented Classic USDT-FUTURES contracts response: **816 unique
symbols**, no duplicate symbol rows. Seven frozen legs exist as normal USDT
perpetuals; **币安人生USDT is absent**. A census search of underlying fields for
币安/binancelife/bianrensheng returns no hits. No authoritative alias mapping
is established. This is a USDT-perpetual check, not a claim about all Bitget
products. Do not drop, substitute or fill the missing eighth leg elsewhere.

| Frozen side | Symbol | Quantity step | Min notional USDT | Account leverage | Funding interval |
|---|---|---:|---:|---:|---:|
| LONG | SANDUSDT | 1 | 5 | 10 | 8h |
| LONG | BTWUSDT | 1 | 5 | 5 | 4h |
| LONG | TRXUSDT | 1 | 5 | 10 | 8h |
| LONG | AEROUSDT | 1 | 5 | 10 | 4h |
| SHORT | DOGEUSDT | 1 | 5 | 10 | 8h |
| SHORT | TRUMPUSDT | 0.1 | 5 | 10 | 4h |
| SHORT | 币安人生USDT | — | — | — | — |
| SHORT | FILUSDT | 0.1 | 5 | 10 | 8h |

Existing leverage is observed configuration, **not approved canary leverage**.
All seven signed symbol-account responses: crossed margin, hedge_mode,
single-asset, available/equity0USDT. Existing Classic futures account likewise
available/equity0USDT; separately queried spot USDT available **0.05067355**.
Thus the manager's ~$50 is a hypothetical budget, not authenticated funding.
Spot cash is not futures margin and no transfer was attempted. Other wallet
products/assets were not audited; do not claim the entire exchange account is empty.

Existing key account-info GET returns ten authority codes, retained in JSON.
An authoritative code-to-derivatives-trade mapping was not verified: **trade
permission UNKNOWN**. Successful account reads alone do not establish it.
Current USDT futures position response is an empty list. Normal orders and all
three trigger categories return successful **null lists/null cursors**, no rows
reported. Retain that exact schema; it is not exclusive ownership, future-order
absence, cash finality or a validated unwind contract.

All seven signed fee endpoints: maker0.0002/taker0.0006. Constant-notional
taker entry+exit is **12bps**, excluding spread, slippage and funding. Real exit
notional may change. This is actual fee evidence, not a change to research costs.
Current funding rates/intervals/bounds are retained separately; none establishes
a seven-day liability reserve. No candidate funding policy was approved.

Seven raw scale0 books have non-crossed ordered depth. Official Bitget docs define
their ts as matching-engine milliseconds. Two server-time GETs bracket stable
VPS clock offset at[-124,+200]ms during this six-second capture; common local use
time09:38:13.532UTC yields bounded ages11–823ms. **Seven received books pass the
unchanged2s check at that captured time only**. The full eight-leg check is blocked;
quiet/continuity, present-market freshness and production compatibility are unproven.

Individual diagnostic minimums fit visible depth: SAND69, BTW4, TRX15, AERO7,
DOGE57, TRUMP2.7, FIL4.7. Their top-of-book notionals sum36.15971USDT. This is
**seven separate minimums, not an equal-notional portfolio**, not a substitute
basket, admitted quantities, collateral requirement or smallest canary. Full
eight-leg equal-notional size/gross/margin+reserve and whether$50suffices are
**NOT_ESTABLISHED**. Do not extrapolate Binance's43.73889gross to Bitget.

## Strategy queue and next action

KITY ranks closed Binance d-1 taker-buy ratios within the frozen exact23:55OI
universe: higher-ratio decile LONG, lower-ratio decile SHORT, equal notional,
seven-day hold, k=n//10. October8 n49 gives4+4. Research READY_FOR_BUILD is not
actual-account readiness; diagnostic independent signal parity is not proof of
independent profitability. Filtering venue eligibility **before ranking changes
the strategy** and needs a separately preregistered KITY challenger. It is not a
configuration shortcut for the frozen signal.

Research ref verified against origin: **cf904086a2d887a96ac2be3324a3d78433e1a94b**.
KARTA's newer research verdict rows govern candidate status; its old production
rows and October2 counter table are stale. No judge/outcome was run or consumed.

| Candidate | Verified current gate | Earliest next evidence |
|---|---|---|
| KITY_M3 | Only new crypto READY_FOR_BUILD; strict GAIB/external provenance/accepted seal/packet-size BLOCKED_DATA. Current exact Bybit and Bitget baskets BLOCKED_EXECUTION; Binance key futures disabled and owner deprioritized | Source contract closure and a future exact basket feasible on the chosen venue, then account/caps/reserve/unwind/finality dossier and separate GO. No promised LIVE date |
| NEW ATT1 | Orders OFF; OLD new-entry authority retired. Oct6 terminal public snapshot17sessions/10gaps/1clean ADA/0held, not fresh October8 counts | Reviewed continuity/reserve work, 2–3 clean filled terminals/net-R, actual dossier and GO. The one clean ADA net-R was negative; operational clean is not edge |
| ETS2M | Armed existing one-shot; original900cohort identity mismatch, not READY | Oct10 19UTC /22Cyprus; exact original-source recovery or honest BLOCKED_DATA, no early judge/re-pinning |
| PEREGREV/C8 | Execution baseline only, prospective family evidence pending | Frozen future event/day/cost gates; no canary promise |
| TOLPA family | Weekly L1 KILLED after Binance replication; daily cheap-screen SURVIVED is not independent confirmation or readiness | Existing forward evidence only, no combining family results |
| New crypto long/range/basis/event | No additional accepted money sleeve. Current long/range attempts include terminal KILLs; design/data collection and historical adapter modules are not strategies | Claude-owned independent preregistered mechanism through WIP1 Factory, no Codex retuning or revival |

Do not spend this signal on venue shopping or funding an unavailable basket.
Next money-engineering priority remains the already scheduled **Alpaca one-XOM
PAPER window16:30–16:35Cyprus**, conditional on fresh account/fee/cash/quote/minimum/
exclusive ownership. Actual DAY re-arm if held is October9opening. Existing LIVE
HALT is preserved; no CRWD/META rebuy or activation. This audit did not query Alpaca
or production service PIDs; earlier broker/service facts retain their timestamps.
ATT1 completed original probes/deadline, ETS2M one-shot, Claude and OS2 unchanged.

## Reproduction and preservation

Private raw archive, mode0400:
`.private/kity_bitget_intake_20261008/bitget_raw_archive.json`, SHA256
`c78bca6dc958160d7a27c2f9060faece7ebe0a994d631afd929531d9b8d1257b`.
Reproducible GET-only source and offline projection are retained under
`reports/evidence/kity_bitget_intake_20261008/`. Re-run only the offline projector
against that retained archive; a new network audit is a new dated snapshot.
All39source hashes/method bounds and per-leg decimal/depth/clock assertions pass.
No product code changed, so no product/full-suite test claim is made.

Queue worker runtime: gpt-5.6-luna/medium, independently verified in its actual
turn_context. Its stale OLD-LIVE and16-session summaries were corrected using
the later retired-entry and terminal17-session receipt. One independent
gpt-6-astra/high review, also runtime-verified: **PASS_WITH_LIMITATIONS**. It
reconciles39hashes, missing leg, minima/depth/fees/clock arithmetic, identifier
redaction and no broker mutation. Stable-clock/snapshot limits remain explicit;
other-service preservation and old source-intake blockers are context, not
independently established by this Bitget archive.

Official endpoint semantics: [contract config and merge depth](https://www.bitget.com/docs/catalog/classic-contract-market/classic-contract-market),
[signed fee rates](https://www.bitget.com/docs/catalog/classic-common-public/classic-common),
[Classic positions](https://www.bitget.com/docs/catalog/classic-contract-position/classic-contract-position),
[trigger-order query](https://www.bitget.com/docs/catalog/classic-contract-plan/classic-contract-plan),
[Classic account endpoint mapping](https://www.bitget.com/docs/classic/uta-api-upgrade-guide).
No UTA upgrade was performed or proposed as an automatic fix.
