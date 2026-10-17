# IBIT/BTC DATA-ONLY — initial ORDERS_OFF contract check

LATEST: published07438fc v1.1 resolves these intake questions. The saved-source
adapter is implemented/39targetedPASS; see
[data/shadow delivery](TRADING_OS_DATA_SHADOW_DELIVERY_2026_10_17.md).
Actual network collector and10-session acceptance remain pending. The original
intake findings below are retained as dated history, not current blockers.

**Status: CONTRACT_INTAKE_COMPLETE / SOURCE_SEMANTICS_OPEN.** Independent P1,
behind KITY execution and Alpaca operational readiness. No implementation,
source daemon, financial transport, strategy/evaluator run or ten-session PASS
is claimed by this initial check. No LIVE source/config/authority was changed.

## Frozen input

User supplied research commit `5a23fc3ddeb490af95826e54ae17fd1509b32164`.
Its actual repository path includes the prefix:
`research_lab/dosie/KONTRAKT_ISTOCHNIK_IBIT_DATA_ONLY_2026_10_17.md`.
SHA256 of exact file bytes:
`f62caa602140aaba25333f4b956731223da8e8eece589bd1fdb762192cd8d3b0`.
The commit is an ancestor of fetched published research `54c6675`; the original
contract is untouched. The abbreviated user path `dosie/...` is relative to
`research_lab/`, not the repository root.

Purpose: a reproducible per-NYSE-session IBIT close / Binance and Bybit BTC
reference source, actual receive/decision timestamps, freshness, independent
cross-check, fail-closed missing data, append-only session identity and recovery.
It cannot submit orders or grant a trading permit. It must not change the frozen
ETF_PREMIYA_BTC signal, KITY/Alpaca/NET, or consume CONFIRM outcomes.

## Reuse existing research components

Read these from the pinned research ref, never from Claude's dirty checkout:

- `research_lab/PREREG_ETF_PREMIYA_2026_10_17.md`: frozen signal and source assumptions.
- `research_lab/fabrika/etf_premiya_sobytiya.py`: existing event/premium/z calculation.
- `research_lab/fabrika/etf_vpered.py`: existing grouped IBIT daily source,
  local `polucheno_ms`, Binance hourly retrieval and session decision append.
- `research_lab/fabrika/etf_premiya_sessiya.py`: existing session helpers;
  file-derived dates are not a broker calendar.
- `research_lab/data/etf_premiya/MANIFEST.json`: pinned source identities.
- `research_lab/dosie/DOSIE_ETF_PREMIYA_BTC_V1.md`: DRAFT dossier/source-availability gap.

This check read code/contracts only, not forward outcome files. Existing
forward shadow remains Claude-owned and was not restarted or edited.

## Material source questions — do not guess or retune

| Finding | Evidence / engineering consequence | Narrow clarification for Claude |
|---|---|---|
| Raw IBIT timestamp differs from contract wording | Contract requests a daily bar but places `ibit_close_src_ts` at/after session close and prohibits a later price. Alpaca labels daily bars by the start of their New York day. A date label is not an official auction timestamp. | Define raw provider timestamp, effective interval end/official close provenance and permitted feed/adjustment separately. Never overwrite raw timestamp with16:00 and call it source truth. |
| Early-close reference conflicts with current producer | Contract says12:00–13:00 ET for half days. Existing frozen shadow uses fixed15:00–16:00 ET/Binance and does not implement broker-calendar early closes or Bybit. | Versioned source-contract clarification of early-close parity with frozen rule; preserve signal formula. No autonomous change to shadow/reference hour. |
| Hash identity is underspecified | Output requires `rule_sha`/`source_sha`; current shadow has prereg/truncated code identities and manifest pins. | Name exact bytes/canonical fields hashed and comparison identity; retain full source payload hashes separately. |
| Deferred cross-check/recovery semantics need an explicit state | Massive may appear after first IBIT receive/decision, while contract allows one decision per session and append-only storage. Missing cross-check is not PASS. | Define PENDING/UNKNOWN vs DEFECT, later append-only QA attachment without a second decision, first-receipt immutability, and the ten-session window/cohort start. |

Alpaca's official [Market Data FAQ](https://docs.alpaca.markets/us/docs/market-data-faq)
documents interval-start bar timestamps and distinct IEX/SIP feeds. Therefore
the timestamp/official-close mapping above needs an explicit input contract;
it cannot be inferred from the daily `t` field. This is an engineering inference,
not a modification of the strategy.
[Bybit kline documentation](https://bybit-exchange.github.io/docs/v5/market/kline)
also identifies candles by startTime and warns that an unclosed candle's close
is the last traded price. Both BTC providers must prove the exact closed interval,
using IANA New York conversion and actual broker calendar.

## Queue and acceptance

1. Resolve the four source/identity points against the frozen contract. This is
   not a request for new financial GO and does not block any Money Lane P0.
2. Build an isolated DATA-ONLY GET adapter around the existing calculation;
   immutable raw payloads/first receive time, explicit feed, calendar interval,
   full hashes, durable unique-session decision, append-only QA attachments.
3. Targeted counterexamples: wrong/future/partial bar, holiday and half day,
   DST, BTC deviation>0.2%, IBIT cross-check>0.5%, unavailable Massive,
   missing session, duplicate/concurrent write, crash/partial-tail recovery,
   source revision after restart and no order-host/method path.
4. Engineering fixtures/replays prove implementation only. The contract's
   actual10 consecutive sessions/noMISSING-orDEFECT/≥80%FRESH and100% event/sign
   parity, z±0.01, remain separate sourced acceptance. No invented historical
   first-observed timestamps or backfilled prospective PASS.

No data-source subscription/entitlement, deployment, actual receive latency,
ten-session coverage or source parity was verified in this check. Prefer existing
components; no new framework, model or financial boundary is needed.

## Status delta prepared for Claude

```text
CODEX DELTA 17.10:
P0 remains KITY micro + Alpaca Monthly operational readiness by30.10.
Fresh installed MonthlyV3 default-OFF verify PASS;47 targeted source/book/native
tests PASS. Full57+SPY source service + monthly/daily schedules remain engineering OPEN.
IBIT/BTC DATA-ONLY P1 accepted at5a23fc3; exact contract SHA256 f62caa60...cd8d3b0.
Initial ORDERS_OFF contract check complete, SOURCE_SEMANTICS_OPEN:
clarify (1) daily raw timestamp vs official close/feed, (2) early-close ref hour
vs frozen shadow, (3) rule/source hash identity, (4) deferred Massive QA and
immutable first-receipt/one-decision recovery semantics.
No source daemon/orders/strategy changes/CONFIRM consumption/10-session PASS.
ElderV1.1 adapter source closure retained; real prospective parity still OPEN.
Please reflect these distinct statuses in KARTA_PROEKTA.md.
```

Prepared for the user to pass on; not sent to another chat or external person.
