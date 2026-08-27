# ATT1 on BTC and ETH — frozen pre-sealed diagnostic

**Decision:** `DESCRIPTIVE_ONLY_NO_PROMOTION`.

This is a post-hoc attribution of the already-frozen live-native ATT1 ledger for
`[2024-03-01, 2025-10-01)`. It did not retune parameters, call a broker, alter an
order, or decode any row from the reserved `[2025-10-01, 2026-07-01)` window.

| Cohort | Base N | Base sum R / PF | Stress sum R / PF | Interpretation |
| --- | ---: | ---: | ---: | --- |
| BTC only | 12 | `+5.911 / 3.643` | `+4.443 / 2.871` | positive but too small and single-symbol for promotion |
| ETH only | 17 | `-3.620 / 0.680` | `-4.142 / 0.643` | negative in both halves; portability warning |
| BTC + ETH | 29 | `+2.291 / 1.169` | `+0.301 / 1.022` | almost no stressed edge; BTC offsets ETH |
| Major-8 excluding BTC/ETH | 63 | `+12.930 / 1.487` | `+11.290 / 1.417` | stronger cohort, but first half is negative in base |
| Major-8 all | 92 | `+15.220 / 1.379` | `+11.591 / 1.282` | below frozen PF gate and DD above 10R |

## What this changes

The claim "ATT1 is structurally broken on Bitcoin" is not supported by this
live-native frozen cohort. Bitcoin was the strongest of the two majors here, but
`N=12` is not enough to infer a stable BTC-specific edge.

The ETH concern is real enough to preregister, not strong enough to remove ETH
post hoc. ETH is negative in base and stress and in both chronological halves.
The correct next question is fixed before new evidence is read:

> Does the exact ATT1 contract transfer to ETH, and does a fixed universe with
> ETH included beat the same universe with ETH excluded under the unchanged
> execution and exposure contract?

The already-frozen reserved diagnostic does not contain this arm and must not be
changed now. The comparison belongs in a new prospective preregistration only. It
must not become a search for ETH-only parameters.

## What this does not change

- live risk, symbol universe, geometry, slots, and money authority remain unchanged;
- the reserved window remains unopened in this work;
- the result cannot override the full frozen gates;
- BTC and ETH need not share future strategy families: trend-continuation and
  medium-term hypotheses may be designed separately, but require their own
  causal contracts and evidence.

Canonical machine receipt:
`research_lab/results/att1_btc_eth_presealed_diagnostic_v1_20260827/receipt.json`.

The frozen input ledgers were read from the preserved legacy workbench
`bybit-bot-clean-v28/research_lab/results/att1_sbr1_actual_adapter_parity_presealed_v1_20260823`.
They are bound by the three SHA-256 values in the receipt. The runner requires
that directory explicitly through `--input`; it does not silently select another
worktree or regenerate the evidence.
