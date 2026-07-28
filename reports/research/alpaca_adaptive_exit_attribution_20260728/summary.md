# Alpaca Adaptive V1 exit attribution

Date: 2026-07-28  
Verdict: `EXIT_BINDING / RESEARCH_ONLY`

At 5 bps per side, with the selector and SPY gate unchanged:

| exit | 2022 proxy | recent proxy | combined arithmetic |
|---|---:|---:|---:|
| shared default | -1.61% | -3.58% | -5.19% |
| wide same-shape | -2.67% | +15.25% | +12.58% |
| 22-session calendar hold | -0.38% | +54.29% | +53.91% |

The current shared exit is the binding historical defect.  It stopped 33 of
43 gated trades across the two windows and converted a strongly positive
recent selector proxy into a loss.

The calendar-hold number is not a forecast: the universes are survivor-only,
and the arm has no acceptable broker catastrophe stop.  It identifies the
repair direction—monthly holding with a distant safety stop—rather than a
live-ready implementation.
