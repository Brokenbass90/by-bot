# Current handoff — 2026-08-12 11:55 UTC

Это единственная короткая точка входа после паузы или перехода в новый чат.
Сначала читать этот файл, затем
`reports/PROJECT_STATE_AND_RESEARCH_REPORT_20260812.md`, затем
`reports/CURRENT_PROJECT_ROADMAP.md`.

## Git truth

- branch: `codex/dynamic-symbol-filters`;
- functional commits pushed:
  - `206c6cf` — Alpaca LIVE/PAPER truth + GTC standalone protection;
  - `df51ed6` — passported dirty-candidate batch + wide public-data runner;
- остальные сотни Claude/user dirty paths не staged, не удалены и не попали в
  эти commits;
- GitHub CLI отсутствует, поэтому draft PR не открыт; branch push подтверждён.

## Direct live truth

- Bybit server checker в этой сессии: `retCode=0`, open positions `0`;
- ATT1 post-release clean cohort: `1/20` на последней ledger-сверке, risk
  `0.10`; повышение только после exact parity + clean cohort gates;
- Alpaca GET-only LIVE: account `ACTIVE`, equity `$485.91`, cash `$391.27`,
  ABBV/SCHW, broker stop coverage `2/2`;
- SCHW current stop `96.47` имеет `DAY`; прежний raised stop `105.32` был
  отменён/rearmed ниже. Local fix `GTC` запушен, но не deployed; текущие ордера
  не изменялись.

## Research completed now

- Alpaca PIT download `1000/1000`, failures `0`;
- validator full pool: `FAIL_CLOSED`; `24` post-delist ticker conflicts + `14`
  empty, quarantined `38`; clean research-only subset `962`, promotion `false`;
- TPB1 ETH rejected: `247` trades, PF `0.828`, `-0.046R/trade`;
- RMR1 major8 rejected: `733` trades, PF `0.789`, `-0.209R/trade` at 16 bps;
  8 bps remains negative, PF `0.892`, `-0.106R/trade`;
- sealed `2025-10..2026-06` holdout was not read; passports and independent
  validation receipts are saved.

## Research continuity

- local supervisor: `6/6 healthy`, no live order authority;
- Inplay ETH prospective: public-only, zero risk, current `N=0`;
- funding dynamic/frozen: each has `3` open, `0` closed shadow trials;
- alt24 L2: more than `35k` observations, `24` symbols, disk guard healthy;
- dirty audit after first adopted batch: `166` code candidates; process only in
  batches of 5–10, no mass cleanup.

## Exact next actions

1. Review and stage the generated wide-RMR + Alpaca PIT evidence together with
   this handoff/roadmap; run focused tests and push one evidence commit.
2. Prepare, but do not silently deploy, a protection-only Alpaca GTC bundle;
   require server-Python smoke and an owner-approved order-safe window.
3. Build exact Alpaca base/stress live-contract replay on clean subset `962`;
   keep current-liquidity selection bias and promotion fail-closed.
4. Leave Inplay parameters frozen; issue first 7-day cadence card. Continue
   funding until closed net trials exist.
5. Next dirty batch: strategy adapter, sweep/reclaim, backtest auditor; each
   through passport → reproduction → accept/reject.

## Promotion gates

- ATT1 `0.10 → 0.25`: clean N20, netR `>=+2`, PF `>=1.20`, drawdown `<=5R`,
  zero unresolved execution conflicts, exact backtest/live lifecycle parity.
- Alpaca: clean-subset exact replay + base/stress + daily MTM + exit parity;
  then tiny new-selection canary, never automatic scale.
- Any research/shadow status is zero capital unless a separate receipt grants
  explicit money authority.
