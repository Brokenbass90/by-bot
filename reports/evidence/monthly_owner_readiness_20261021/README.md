# Reproduction and evidence boundary

`timing-diagnostic.json`:20real server read-path samples, raw unit/process hashes
and operational verdict excluded. Natural load only; not a financial retirement
receipt or broker latency benchmark.

`legacy-transition-repro.json`: synthetic late-legacy-cost rejection. Reproduce:

```sh
.venv/bin/python -I -B reports/evidence/monthly_owner_readiness_20261021/repro_legacy_transition.py
```

`pump4-source-replay.json`:65fixed-source signal/geometry matches,1unavailable,
input prefixes checked and research files unchanged. This is not executor parity,
new research/PnL or real trading acceptance. `replay-negative-checks.json` records
ambient-PF and altered-fixture rejection before output. Reproduce to a NEW local
output path outside the research checkout:

```sh
.venv/bin/python -I -B reports/evidence/monthly_owner_readiness_20261021/pump4_source_replay.py \
  --research-root /ABSOLUTE/PATH/TO/bybit-bot-clean-v28 \
  --fixtures /ABSOLUTE/PATH/TO/published-pump4-fixtures.json \
  --output /ABSOLUTE/PATH/TO/NEW-local-replay.json
```

Fixture source is the exact publishedb138735 blob
`research_lab/results/pump4_fixtures_v1_20261020.json` with SHA
f6badf311e888fab05a3d4131559f98152f8589d49b35c7b034e306617726ca4.
Both frozen strategy/signals source hashes are enforced. Historical candle JSONs
come from the already existing research data/oos_bybit_h1_20261020 cache; missing
or changed prefixes fail closed. No fetching, judge/simulator, funding estimate,
research-file write or actual broker call is part of this script.

Private actual broker replies/quantities/account IDs/ledger/unit state, profile
and unit hashes, owner budget/risk proposal and personal exit repin envelope
are intentionally excluded from Git publication. Actual financial scope/config
pins are not yet frozen; the private file is a REVIEW_PROPOSAL, not executable GO.
