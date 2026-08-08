# Research station, LTC audit and FX smart-grid result — 2026-08-08

## Outcome first

- The Mac research station is installed as `com.tradingstation.research-station`
  with `RunAtLoad` and `KeepAlive`. It owns five research-only loops and has no
  broker/order authority.
- The public Bybit liquidation collector is moved from an orphanable VPS
  `screen` session into `liquidation-collector.service` with automatic restart.
  It uses no API key and has no order authority.
- A false-green defect was found and fixed: GNU screen's `(Dead ???)` sockets
  were previously counted as live processes. Regression coverage now rejects
  dead sockets; the frozen-funding and project-audit loops were materially
  restarted after the repair.
- Telegram allowlist digests now default to `live_only`. Inactive/shadow sleeve
  changes remain in `configs/allowlist_change_log.json` but do not alert the
  owner. `all` and `off` remain explicit modes.
- The 2026-08-08 LTC ATT1 trade used about `$95.80` notional, lost `$0.42053235`
  after fees, and was protected by the exchange stop. This is already roughly
  `$100` notional; it is not `$100` at risk.
- The deployed ATT1 reason did not persist pivot anchors, so the exact line
  cannot be audited from the entry receipt. The current committed local ATT1
  does serialize anchors. Deploy that logging-only parity change separately;
  do not promote the uncommitted minimum-distance challenger.
- A new non-martingale FX smart-grid diagnostic failed: best stress PF `0.8783`,
  net `-2914.38 bps`, `0/4` positive chronological folds over `2232` trades.
  The 3-layer form was less bad than the matching single entry, but still has no
  executable edge. Do not run it in demo/live.

## Verification

Double-click `CHECK_RESEARCH_STATION.command`, or run:

```bash
launchctl print gui/$(id -u)/com.tradingstation.research-station
.venv/bin/python scripts/local_research_station.py --status-only
```

Healthy means both a live process and a fresh evidence artifact. A process by
itself is never green.

## FX grid contract

The new diagnostic is `research_lab/fx_smart_grid_v1.py`:

- public Dukascopy M5 aggregated to complete H1;
- range efficiency and width gates;
- equal-size layers, no martingale;
- range-break kill and UTC session flatten before overnight financing;
- base and doubled-stress spread/commission assumptions;
- four chronological folds;
- a mandatory comparison with the matching one-entry range fade.

The cost contract is expired for promotion, which is explicitly recorded in
the receipt. That limitation cannot rescue the result because every time fold
is already negative.

## Next event family

`configs/preregistered/consolidation_level_impulse_v1_20260808.json` freezes the
owner's distinct hypothesis: first bounded impulse out of a real consolidation
at a meaningful horizontal or validated sloped level. It is not XSEC. Required
controls separate compression, level location, breakout direction, retest,
entry lateness, PIT universe and doubled executable costs.
