# Deep equities handoff — 2026-09-28

Status: **COPY VERIFIED / DATA ACCEPTANCE BLOCKED**.

Separate research checkout path: `research_lab/data/alpaca_pit_daily_deep_20260925/`.
All **965 files / 961 bar files / 2,032,108 bars** match source and manifest.
Original research archive (1,006 files), source archive and Factory queue are unchanged.
Copied manifest, quality and per-file hashes are in
`research_lab/pakety/CODEX_DEEP_EQUITY_HANDOFF_20260928/` in `bybit-bot-clean-v28`.
No repeated download, old dataset replacement, queue edit or acceptance flag change.

## Existing integrity blockers

- **SPCX identity reuse confirmed by provider reference GETs**: on 2024-11-20,
  The SPAC and New Issue ETF, type ETF, FIGI BBG00YJ8L8T5; on 2026-06-12,
  Space Exploration Technologies Corp. Class A Common Stock, type CS,
  FIGI BBG000NQF3Z5, list_date 2026-06-12. Raw receipts are preserved privately;
  sanitized identities/hashes are in `EQUITY_DEEP_HANDOFF_RECEIPT_2026_09_28.json`.
  Ticker text is not a stable security identity. The positive-volume/zero-VWAP
  source bar is also retained. No repair by replacing a value or deleting an
  interval was performed.
- **XTKG**: all 23 observations after the frozen 2026-04-02 delisting date have
  v=n=vw=0. They do not prove post-delisting trades. Existing integrity rules
  still reject them; raw and normalized records remain untouched.
- **Historical universe**: the frozen pool was selected partly using current
  liquidity. Extending bars to 2016 does not establish historical PIT membership
  or remove survivorship bias. Claude independently rejected the dataset on
  2026-09-28; his exact review hash is in the receipt.

The frozen `P_AKC_OSTATOCHNYY_MOMENT` remains BLOCKED_DATA and was not run.
No sealed evidence was consumed. Required next data artifact: historical
membership/security identity for the intended dates, including delisted
securities, plus documented resolution of existing integrity conflicts.
Setting `promotion_authorized=true` cannot substitute for these artifacts.
Research acceptance does not authorize broker orders or LIVE activation.

Claude branch `research/fabrika-v1` was pushed and verified at
`4acaa850c03ca606c6e80907ca38976f53fb25b5`. The dirty checked-out branch was untouched.
