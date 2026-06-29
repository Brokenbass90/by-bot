# Density (HVN) confluence — test spec for GPT (2026-06-29)

Claude wired volume-at-price density (HVN) confluence into the bounce legs.
Default OFF (additive). GPT: add tests covering the new behavior. Existing tests
(`test_alt_support_bounce_v2.py`, `test_alt_channel_bounce_v1.py`,
`test_market_context.py`) already pass and must stay green.

## What was added
- `bot/market_context.py`: `nearest_dist_atr(level, points, atr) -> float`
  (min |level-point|/atr; +inf if no points / bad atr).
- `alt_support_bounce_v2` (ASB2): cfg `require_hvn`(False), `hvn_bins`(24),
  `hvn_top_n`(6), `hvn_confluence_atr`(0.7). Env: `ASB2_REQUIRE_HVN`,
  `ASB2_HVN_*`. When `require_hvn=True`, signal is rejected with
  `no_hvn_confluence_<dist>` if the support is farther than
  `hvn_confluence_atr` (in ATR) from the nearest HVN. `reason` now includes `hvn=`.
- `alt_channel_bounce_v1` (ACB1): same cfg/env (`ACB1_*`). Confluence checked on
  the touched edge (lower line for long, upper for short).

## Tests to add
1. `nearest_dist_atr`: known points -> exact ATR distance; empty/zero-atr -> inf.
2. ASB2 `require_hvn=True`: build a bounce fixture where support COINCIDES with a
   high-volume node (give those bars big volume) -> signal still fires, reason has
   `hvn=`. Then move volume away from support -> `no_hvn_confluence_*`, no signal.
3. ASB2 `require_hvn=False` (default): density never blocks (regression).
4. ACB1 `require_hvn=True`: long at lower edge with HVN at lower line -> fires;
   HVN absent near edge -> `no_hvn_confluence_*`. Same for short at upper edge.
5. ACB1 `require_hvn=False`: regression, density never blocks.

## Fixture hint
HVNs come from `volume_hvns(rows, bins, top_n)` = price bins with most volume.
To place an HVN at a level, give the bars trading at that level much higher
volume than the rest. Use small `hvn_bins` (e.g. 8) in tests for predictable bins.
