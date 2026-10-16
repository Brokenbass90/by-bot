# Alpaca NET protection incident and strategy parity — October16

CURRENT: **ALPACA_STRATEGY_PARITY_BLOCKED**. More urgent, actual NET protection
is **UNPROTECTED_DAY_EXPIRED_MANAGER_BLOCKED** at the last completed GETs.
Owner notified immediately and chose to restore the existing stop personally;
completion/readback is still pending. Do not report LIVE_PROTECTED from yesterday.

## Actual safety finding

ACCOUNT=LIVE |2026-10-16 16:05:05.686UTC /19:05Cyprus |NET0.325167779
@311.222, broker mark293.6397, unrealized−5.717198USD |open orders0.
Original native STOP277.69 has status expired, filled0. Durable native accepted
floor277.69 and HWM315.505 remain unchanged. Manager exit2:
`ENTRY_FILL_SOURCE_CHANGED`. Journal first retained failure06:40:01UTC,
116 failures through16:15:01. Regular-session DAY re-arm therefore did not run.
[Incident](evidence/alpaca_parity_repair_20261016/protection_incident.json).
Followup16:15:36UTC again found open orders0. Owner's intent to restore is not
broker confirmation. Agent made zero broker writes/position changes.

Root cause: original filled_at `2026-10-15T13:30:06.234131481Z` later read as
`2026-10-15T13:30:06.234131Z`. Source metadata changed null→access_key.
ID, symbol, side, type, quantities, fill price/status and ownership match.
String equality blocked maintenance before protection recovery. This is an
execution defect, independent of strategy loss/selection quality.

## Narrow repair prepared, NOT activated

Runtime now reuses existing strict `execution_identity_v1` on the complete raw
orders. It preserves original JSON/hashes, accepts only existing nanosecond→
microsecond rounding/access_key addition; material differences still block.
Regression reproduces next-day expired stop, one re-arm at the unchanged floor,
duplicate/restart safety and price/qty/status/timestamp/source conflicts.
**112 targeted PASS** including human-only restored-stop scope validation.

Inert VPS repair:
`/opt/bybot-research/alpaca-dynamic-live-20261013/repairs/oct16-entry-identity-v2`.
All original53source pins retained plus patched runtime/controller/identity
module, **56 pins verified by actual GET-only owned_snapshot**.
[Read-only proof](evidence/alpaca_parity_repair_20261016/identity_repair_readonly.json).
Runtime SHA `a0710690e43ffbb4a96329de33ec8f65edf1d4c4ab11e549ed9b1911249548e4`;
spec SHA `8f392da86c16fd8edfa7959786aadca89445c86b723bf42dd27a32786a4dbf69`.
Original app/spec/controller/unit/ledger remain unchanged. Initial inert-v1
missing dependency was caught by actual read-only replay and preserved; v2
explicitly pins/loads the existing identity implementation before runtime.
The repair controller rejects every mode except maintenance before source I/O.

Human-only helper `research_lab/alpaca_owned_stop_repair_v1.py` is prepared and
staged, default no-network. Exact hash
`62a73c7a37c1a3d649fc24df53bbd17429157e3eca250c10356da0d6151ad452`.
It permits exactly one personally restored full NET STOP/DAY277.69, or no active
order with the exact original expired STOP, unchanged position/fill, original
entry identity and original unit/source pins. The original manager owns re-arm
and scoped emergency unwind, never a new entry. It proposes
binding first; after personal execution only, an exclusive claim/receipt precedes
native ownership binding if needed and replacement of this one manager's ExecStart.
It preserves HWM/floor/quantity/HALT and the existing timer; no new entry path.
It then starts existing owned maintenance. **Agents must NEVER execute the
owner activation flag, launcher or systemctl start of this monetary manager.**
Private launcher prepared/syntax checked and offered for PERSONAL execution;
agent has NOT executed it:
`.private/alpaca_parity_20261016/owner-bind-manager-once.sh`.
Actual GET-only recovery-v2 helper check returned OWNED_STOP_RECOVERY_READONLY_READY
with ORIGINAL_EXPIRED_STOP_REARM; no broker/native/service writes. One concrete
human activation command was provided; completion/readback pending.
Never silently adopt a manually added order without this explicit binding.

Entry HALT already existed: checked under original account lock and preserved
byte-for-byte per owner's instruction. It never inhibits owned maintenance.
[Receipt](evidence/alpaca_parity_repair_20261016/entry-halt-receipt.json).
No halt clear, new money GO, new PAPER, stop widening or risk increase.

## Strategy reference and exact discrepancies

Reference: `ALPACA_AGENT_BRIEF.md` at commit
`9e1cff1a9f324aae9926b857039514e11f7ae1c2`, §3,
Strategy ID `ALPACA-BASELINE-c78b78dd7e68ef75`.
Actual file retained in sibling `alpaca-wt-20260907`; its historical `.git`
link is broken, not repaired. File/code hashes recorded independently in
[reference inventory](evidence/alpaca_parity_repair_20261016/reference_inventory.json).
Canonical selector engine `backtest/alpaca_honest_portfolio.py` SHA
`21c83fe9bff1659990a869a40bd2f62b8f8c3a359f88d4b398291b4096f978b8`;
existing diagnostic runner SHA
`1d14dd1dd1dda5e258a0a510c83215d91a9a393267730ea6eb16c060bd1bdca8`.

| Contract | Measured fact | Parity |
|---|---|---|
| Monthly last-session selection, next open | Owner-approved Oct6 Dynamic policy uses first-session-of-week ranking and later replacement opens | MISMATCH; preserve separate version, no silent reference substitution |
| One next-session signal | SignalOct9/intendedOct12/actualOct15; no Oct14 full revalidation | STALE against requested reference |
| Correct entry-date ATR20 | Live used Oct9 ATR20=16.771206665045003/raw2ATR33.54241333009, cent-derived33.54 reused | Current Oct14 ATR/qualification UNKNOWN; no source in packet |
| Stop from actual fill | Actual311.222−cent-distance, ceil→277.69 | Actual-fill anchoring EXISTS; stale distance remains the defect |
| Original ratchet formula | +3.5% activation/3.5% trail/+0.5% lock/10bps market ceiling, monotonic | Numeric rule matches; daily proxy cannot prove intraday parity |
| Observation cadence | LIVE5min, historical proxy daily-close (comments describe15min LIVE) | Exact sampling parity NOT_PROVEN |
| Entry/quote provenance | CTS/source and input receipts exist, but dated old signal/ATR | Needs unified future strategy receipt |
| Strategy ID | Native26f7ff663dc98e87 vs briefc78b78dd7e68ef75 | Do not relabel current trade as baseline |

Additional reference ambiguity is recorded, not guessed: original diagnostic
config/default proxy uses signal_close stop anchor; later brief/fill-gate prereg
requires entry_fill. Before full parity certification pin the exact selected
baseline runner invocation/config proving entry_fill. No historical outcome run
was performed to manufacture a match. Known ratchet giveback is not retuned.

Saved Oct9 source replay reproduced **exact selector picks and regime gate**:
NET only, weight0.6. Thus no selector-formula corruption is shown.
[Replay](evidence/alpaca_parity_repair_20261016/selection-replay.json).
This proves Oct9 selection only; it does not prove NET qualified Oct14 or that
ATR increased after the decline. No new ticker substitution off-cycle permitted.
Rejection naming for future stale revalidation: `STALE_SIGNAL_RESELECT_FAIL`.

## Evidence classification and remaining work

- Oct12–13 NET PAPER: **OPERATIONAL_VALIDATION**, forced/planned lifecycle exit;
  not strategy evidence regardless of signal age.
- Oct15 NET LIVE: **OFF_PROTOCOL_STALE_SIGNAL / OFF_PROTOCOL_RISK_REFERENCE**
  relative to validated monthly baseline; quarantined from edge comparisons.
  This does not rewrite its money journal or deny the separate Dynamic approval.
- Oct7 XOM zero-size and Oct9 reserved/retired nondispatch intents: no actual
  strategy trade/outcome; retain original source/retirement evidence.
- Oct1 CRWD/AMD/META and older PAPER intents: **UNKNOWN pending complete source
  lineage audit**. Latest all-order read hit100, so ALL-history coverage is not
  claimed. Prior attractive results are not automatically baseline evidence.

P0: personal source-pinned maintenance-only repair (adopt exact manual stop or
re-arm expired original) → actual protected/restart/next DAY readback. Then finish
future entry parity and complete old intent inventory from declared source books.
No new entries before ALPACA_STRATEGY_PARITY_PASS. Current manager/stop formula
must not be changed to improve strategy economics during this repair.
KITY batch/WS, Elder HEDGE and Reporting follow after safety; no money cap350 or
other KITY boundary change has been approved/applied.
