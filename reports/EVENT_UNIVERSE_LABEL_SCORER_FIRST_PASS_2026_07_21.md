# Event Universe V1 label scorer — first pass

## Verdict

`BLOCKED_BY_SOURCE_FINALITY`; no return label was calculated and no performance
claim is permitted.

The preregistered scorer froze snapshots 1–957 and validated the immutable
snapshot/replay chain. It then failed closed at the first cross-snapshot M5
conflict:

- symbol: `BANKUSDT`
- M5 start: `1784440200000`
- first observed row: close `0.11218`, base volume `651790.0`, quote turnover
  `73032.0437`
- later row for the same start: close `0.11218`, base volume `651840.0`, quote
  turnover `73037.6527`
- deterministic failure receipt:
  `reports/research/event_universe_v1_labels/event_universe_label_failure_s000957_018d26e5718e_edaef07ec1d2.json`

A diagnostic scan found 11 revisions, all in `BANKUSDT`. Later conflicts also
changed the stored close, not only volume. The individual replay objects and their
stored score hashes are internally valid; the problem is that a Bybit M5 bar was
accepted immediately after its nominal close and the public endpoint revised it
in a later poll. Therefore the source is good enough for prospective discovery
cards, but the current run is not an immutable outcome tape.

## What this means

This is a useful data-quality finding, not a negative strategy result. The scorer
did exactly what was preregistered: it did not silently keep the first row, take
the last row, discard the symbol after seeing it fail, or publish returns from an
unstable path. Selected episodes and 1h/4h/24h performance remain unknown.

## Required repair (new source version, never mutate V1)

1. Freeze a V2 collector/spec/root. A bar is eligible only after one additional
   complete M5 settlement interval: `bar_start + 10m <= source_as_of` rather than
   `bar_start + 5m <= source_as_of`.
2. Preserve the existing hash/delta replay chain and add the same cross-snapshot
   immutable-bar assertion online. Any later revision stops V2 immediately.
3. Run the repaired collector prospectively for at least 48 hours before an
   interim 1h/4h/24h label pass; keep the planned seven-day run for a less sparse
   receipt.
4. Reuse the already-frozen label semantics unchanged. If V2 still observes a
   revision after the settlement lag, preregister a two-poll confirmation rule in
   V3 instead of choosing rows after looking at returns.

No live service, API key, order, account, allocator, or risk setting was touched
by this pass.
