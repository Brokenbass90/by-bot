# Event Universe V2r2 — corrected local launch status

The corrected spec was frozen at `2026-07-21T18:18:02Z`, before this run root
existed. Launch started at `1784657998535` ms and the first public source as-of was
`1784658002796` ms, so preregistration precedes both launch and observation.

- screen: `event_universe_v2r2_20260721`
- run root: `runtime/research/event_universe_v2r2_20260721_public1`
- deadline at ms: `1785262798535` (seven-day hard bound)
- spec canonical payload SHA-256: `e12e201b2a3b383dafd8c6d01190bbbf49c089e57d1f7f583fd378e39ba02798`
- spec file SHA-256: `d5c4ec835e86bd85e050ed593e215f47aa48d223ee758f0d8e4004256003102a`
- launch self-hash: `0423342b537df8426b548c51570aa47a00a8fe5aa00d52954803fe59c28b6096`
- launch file SHA-256: `f8348bed0684499b5744a537b0ccfac2506cae03bde72e6b6c5b595d5540bd88`

First corrected observation:

- sequence: 1
- universe/prefetch/scored: 752/100/100
- advisory candidates: 17
- symbol errors: 0
- immutable symbols tracked: 100
- snapshot SHA-256: `357a01c16d4c3cfe1a7dd6da40a9018d77a185906c49784f0d2c3754b0e6a8ea`
- snapshot contract revision: `v2r2_timestamp_corrected`

The original V2 screen is stopped and absent. Its root and one snapshot remain
preserved under an explicit invalidation receipt; they must never be combined with
V2r2. The corrected collector remains public GET-only, research-only, no-keys,
non-executable, and terminal fail-closed on a cross-snapshot bar revision.

Verification before launch: 34 focused V1/scorer/V2/V2r2 tests passed, plus Python
compile and shell syntax checks. Safe command is
`bash scripts/launch_event_universe_v2r2.sh`; it refuses a duplicate screen.
