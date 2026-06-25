# CODEX HANDOFF — 2026-06-25

Читать вместе с `CODEX_HANDOFF_2026_06_20.md`, `reports/STATE_AND_MIGRATION_2026_06_22.md`
и `reports/CLAUDE_AUDIT_2026_06_22.md`.

## 1. Git / сохранённая работа

- Branch: `codex/dynamic-symbol-filters`.
- Pushed commits:
  - `22f7c34` — `breakdown_retest_v3`, `spike_fade_v3`, `hedge_pairing`,
    fail-closed `evaluate_crypto_promotion.py`, package/hedge/alpaca runners,
    Claude audit/state reports and tests.
  - `9a43566` — `backtest/midterm_efficiency_run.py`.
  - `49a4ad0` — streaming/checkpointed package and midterm runners plus
    `candidate_shortlist.py` maker/taker shortlist.
  - `51a0828` — this handoff file before later OOM notes; if this paragraph is
    visible in git, a later handoff update was also saved.
- Local full suite before commit: `423 passed`.
- Server research-copy targeted tests: `18 passed`.
- Still dirty locally but not part of this save: generated
  `reports/PROOF_OF_LIFE_latest.txt`, `reports/PROOF_OF_LIFE_telegram.txt`,
  plus many historical untracked docs/reports/config candidates. Continue to
  stage only explicit paths; never `git add .`.

## 2. Live crypto state — checked 2026-06-25 10:53 UTC

- `bybot.service`: active.
- Last service restart: `Sat 2026-06-20 04:58:02 UTC`.
- Bybit open positions: `0`.
- `trade_on=true`, `dry_run=false`, regime `bear_chop`.
- Real non-zero crypto risk:
  - `flat` / ARF1: `risk_mult=0.3`.
- Enabled but zero-risk / scan-shadow:
  - `range=0.0`, `att1=0.0`, `breakdown=0.0`, `ivb1=0.0`,
    `midterm=0.0`, `bounce1=0.0`.
- Disabled:
  - `asb1_slope_break=false`, `hzbo1=false`, `elder=false`
    (heartbeat still shows elder risk field `0.05`, but enabled is false).
- After the 2026-06-20 stop-loss cluster there were no new Bybit trades in the
  checked journal. Realized since 2026-06-20: `range -0.7292 USDT`, 5 losses.

### OOM incident and fix — checked/applied 2026-06-25 12:04 UTC

- A full `package_efficiency_run.py` research process on the same 1GB VPS
  caused memory pressure and `bybot.service` was killed by the kernel OOM killer
  at `2026-06-25 11:00 UTC`.
- The live service did restart automatically, but the unit was configured with
  `OOMScoreAdjust=500`, making the trading bot more likely to be killed than
  research. That is wrong for production.
- Applied server-side persistent unit change while Bybit was flat:
  - `/etc/systemd/system/bybot.service`
  - `OOMScoreAdjust=-900`
  - `MemoryMax=700M`
  - `systemctl daemon-reload && systemctl restart bybot.service`
- Post-restart check:
  - Bybit open positions: `0`;
  - `bybot.service` active;
  - process `/proc/<pid>/oom_score_adj=-900`;
  - heartbeat fresh.
- Heavy research on this VPS must not run unbounded again. Use a separate
  research server, local machine with caffeinate, or transient systemd units with
  strict `MemoryMax/CPUQuota` and small symbol/strategy shards.

## 3. Why the candle bug reappeared

It was not one line reverting; it was duplicated live data paths. Some newer
adapters already used `strategies/live_kline_utils.fetch_closed_klines`, but
legacy Range and the monolith stores for IVB1/Elder bypassed that helper and
could see the currently forming candle. Known live paths are now wired to closed
candles and covered by tests. A permanent guard still needs to be added to
`system_integrity_gate`: fail if a live strategy adapter calls raw `fetch_klines`
without the closed-candle wrapper.

## 4. Why the bot is quiet

Live counters show silence is mostly expected under current safety settings:

- Most sleeves have `risk_mult=0.0`.
- ATT1: many `no_signal`, mostly `trendline` / cooldown.
- Breakdown: mostly `structure_idle`.
- IVB1: many `no_signal`, mostly no completed impulse/volume condition.
- Flat/ARF1: only live-risk sleeve, but touch/range/regime filters are strict.
- Range: risk is `0.0` and loss-cooldown is actively blocking repeats after the
  stop cluster.

Do not increase risk just to make the bot trade. Next risk comes only after a
fresh current-code replay, monthly/WF stability and shadow/canary evidence.

## 5. Research status

Completed server evidence:

- ARS1 Wilder recheck: 64/64 variants failed. Best was r061 with PF `1.897`,
  net `4.72%`, DD `2.37`, but too few trades (`29`), net below gate and too many
  red months/streaks. ARS1 is not production income.
- Old `+89%/+120%` baseline remains invalid as a current trading claim. Latest
  known exact rerun was around `+11.24%`, PF `1.148`, DD `8.77%`.

Earlier active server-side screens, started in isolated research copy
`/root/by-bot-research-20260625-22f7c34-archive`, were stopped after the OOM
finding because the full 12-symbol package runner was too heavy for the live VPS.

New safer research copy:

- `/root/by-bot-research-20260625-49a4ad0`
- source: local `git archive` of commit `49a4ad0`;
- data cache symlinked to `/root/by-bot/data_cache`;
- targeted tests: `18 passed`.

Transient research unit:

- `safe_small_research_20260625.service`
- `MemoryMax=360M`, `CPUQuota=60%`, `Nice=10`;
- log: `/root/by-bot-research-20260625-49a4ad0/logs/safe_small_research_20260625.log`;
- tasks: `midterm_efficiency_run.py`, then IVB1 package on `BTCUSDT ETHUSDT SOLUSDT`,
  then `candidate_shortlist.py`.

Old stopped/unsafe queue for reference:

- `research_queue_20260625_22f7c34`
  - running full `backtest/package_efficiency_run.py` on 12 symbols with
    `PKG_COST_R=0.12`;
  - then queued: midterm efficiency, hedge pairing, Alpaca leverage probe.
- `quick_research_20260625_22f7c34`
  - running `hedge_pairing_run.py --step 3`, then Alpaca leverage probe.
  - first command attempted midterm before the file was copied and skipped it.
- `midterm_efficiency_20260625`
  - running `backtest/midterm_efficiency_run.py`.
- `bybit_liquidations_collector_20260616`
  - still collecting liquidation data.

Useful server check command:

```bash
ssh -i ~/.ssh/by-bot root@64.226.73.119 'cd /root/by-bot-research-20260625-49a4ad0 && systemctl status safe_small_research_20260625 --no-pager -l | head -40 && tail -220 logs/safe_small_research_20260625.log'
```

For full package, output is currently buffered; use:

```bash
ssh -i ~/.ssh/by-bot root@64.226.73.119 'cd /root/by-bot-research-20260625-22f7c34-archive && screen -S research_queue_20260625_22f7c34 -X hardcopy logs/research_queue_20260625_22f7c34.hardcopy 2>/dev/null || true; tail -120 logs/research_queue_20260625_22f7c34.hardcopy; tail -120 logs/research_queue_20260625_22f7c34.screenlog'
```

## 6. Alpaca paper — checked 2026-06-25 10:53 UTC

- Mode: Alpaca paper.
- Equity: `$100,219.81`, cash `$99,523.93`.
- Open positions:
  - AAPL: market value about `$256`, PnL `-5.41` (`-2.1%`).
  - JPM: market value about `$255`, PnL `+3.39` (`+1.3%`).
  - UNH: market value about `$185`, PnL `+1.42` (`+0.8%`).
- Dry-run manager check confirmed broker stop orders:
  - AAPL stop `279.58`;
  - JPM stop `317.43`;
  - UNH stop `388.79`.
- `adaptive_v1` baseline remains the paper order driver.
- `lively_config()` remains shadow/no-orders. Latest lively shadow picked
  UNH, LLY, JPM, AAPL, KO, but does not trade.
- Real Alpaca capital still gated until after the formal post-close review on
  2026-06-26: ownership, fills, duplicate orders, broker stops, realized/unreal
  PnL and trailing behavior.

## 7. Next order of work

1. Wait for server research screens to finish; extract:
   package ranking, midterm ranking, hedge `improved=True/False`, Alpaca leverage
   table.
2. If package ranking finds a positive sleeve, run real next-open/monthly/WF
   with fees and the fail-closed promotion gate.
3. IVB1 remains the first serious crypto candidate from prior evidence, but must
   be revalidated after closed-candle fixes and with risk scaled under DD limit.
4. v3 family (`inplay_retest_v3`, `breakdown_retest_v3`, `spike_fade_v3`) is now
   saved and ready for sweeps/monthly/WF.
5. Build `system_integrity_gate` before any next live promotion: tests, secrets,
   closed candles, live/backtest parity, broker positions/stops, stale data,
   promotion provenance, strategy risk consistency.
6. Keep crypto live defensive: ARF1 only canary risk; Range/ATT1/Breakdown/IVB1/
   Midterm remain zero-risk until evidence says otherwise.
