# SBR1 fixed-51 public evidence-shadow switch — deploy plan and receipt template

**Scope:** SBR1 public zero-risk evidence shadow only. This plan does not
change ATT1, XAU/MT5, money risk, slots, geometry, allocator, or promotion
authority. It has not been executed from this recovery checkout.

## Pinned identities

- Evidence universe: fixed-51;
- Evidence-universe SHA-256: `fa5c61703cac5c72218022f15d92ee46d6fa577df84c9cfcbf8cc005893bfe19`;
- Money universe: major-8 (`BTCUSDT, ETHUSDT, SOLUSDT, ADAUSDT, LINKUSDT, LTCUSDT, DOTUSDT, SUIUSDT`);
- Source preregistration SHA-256: `dffa60b17b785b9182560b1bace7105eef9d715488866dd665df77825cac7b68`;
- Evidence manifest SHA-256: `597154e23c592c6db5fcb2eca2b5e5f9559526646f0a9444a1ccfd22bb100624`;
- Expected authority: `zero_risk_public_shadow_no_orders_no_money_no_promotion`.

The frozen lists overlap on five symbols, not eight. Therefore the runtime
evaluation union is 54 symbols: fixed-51 plus major-8-only LINK/LTC/DOT. All
major-8 symbols keep the existing lifecycle. The other 46 fixed-51 members are
raw pre-parity observations only. HFT remains in fixed-51 and is recorded as an
expected structural gap; it is never replaced. No fixed-51 receipt is eligible
for final N or promotion before caller/filter/lifecycle parity.

## Offline gates before any host mutation

Run from the staged release directory and retain stdout/stderr:

```sh
python3 -m pytest -q tests/test_sbr1_fixed51_universe.py tests/test_sbr1_zero_risk_shadow.py tests/test_sbr1_shadow_random_control.py
python3 scripts/run_sbr1_zero_risk_shadow.py --config configs/sbr1_zero_risk_shadow_v1.json
python3 -m py_compile bot/sbr1_universe.py bot/sbr1_zero_risk_shadow.py scripts/run_sbr1_zero_risk_shadow.py
git diff --check
```

The no-argument runner must return `RESEARCH_ONLY_DISABLED`, `network_calls=false`,
`writes=false`, `orders_allowed=false`, `private_api_allowed=false`,
`money_authority=false`, and the pinned evidence/money hashes. Any identity,
preregistration, source-closure, or authority drift is a hard stop.

## Recommended atomic host commands (not run)

Use a new timestamped staging directory outside the live root. Reconcile the
source bundle and its complete dependency closure before copying. Preserve the
existing server-side enabled config, runtime journal, random-control journal,
permissions, and ownership as independent artifacts. Do not enable the unit
until the staged no-network preflight is captured. Do not use `rsync --delete`
against either the live tree or a directory containing runtime evidence.

```sh
STAMP=20260824T____Z
LIVE=/opt/bybot-research/sbr1-zero-risk-shadow
STAGE=/opt/bybot-research/.sbr1-fixed51-$STAMP
BACKUP=/opt/bybot-research/sbr1-zero-risk-shadow-backup-$STAMP
SERVER_CONFIG=/opt/bybot-research/.release-input/sbr1-zero-risk-shadow-$STAMP.json

sudo systemctl stop sbr1-zero-risk-shadow.timer
sudo systemctl stop sbr1-zero-risk-shadow.service
sudo mkdir "$STAGE"
# Copy only the reviewed immutable source closure into an empty stage.
sudo rsync -a ./bot ./configs ./deploy ./research_lab/prereg ./scripts "$STAGE"/
# Prepare SERVER_CONFIG from the reviewed release config. The only permitted
# host overrides are enabled=true and the already-inventoried relative journal
# path. Diff it against both the release config and the old host config.
sudo install -m 0600 "$SERVER_CONFIG" \
  "$STAGE/configs/sbr1_zero_risk_shadow_v1.json"
# Runtime is not part of the source stage and is never deleted.
sudo -u bybot-research python3 "$STAGE/scripts/run_sbr1_zero_risk_shadow.py" \
  --root "$STAGE" --config "$STAGE/configs/sbr1_zero_risk_shadow_v1.json"
sudo sha256sum "$STAGE/configs/sbr1_zero_risk_shadow_v1.json" \
  "$STAGE/configs/research/sbr1_fixed51_evidence_manifest_v1.json"
sudo mv "$LIVE" "$BACKUP"
sudo mv "$STAGE" "$LIVE"
# The stopped old tree remains an immutable rollback backup. Copy (do not move)
# its runtime into the new tree so both the rollback and new release retain the
# exact pre-switch journal. Verify event count and chain tip before start.
sudo cp -a "$BACKUP/runtime" "$LIVE/runtime"
sudo chown -R bybot-research:bybot-research "$LIVE/runtime"
sudo systemctl daemon-reload
sudo systemctl start sbr1-zero-risk-shadow.timer
sudo systemctl start sbr1-zero-risk-shadow.service --no-block
```

The actual host command must use the deployment account and paths proven by a
fresh host inventory; the commands above are a template, not authorization to
deploy. The reviewed public 54-symbol cycle at `2026-08-24T18:57Z` completed in
`22.71s`; it was intentionally outside the H1 decision window and therefore
returned degraded status while still proving 50/51 public coverage, one
expected HFT structural gap, and zero order/private/broker authority.
`RuntimeMaxSec=120` is pinned in the service: more than five times this observed
runtime and below the three-minute retry boundary. A timeout fails closed and
lets the retry run; it never widens the evidence contract. There is no broker
rollback because this unit has no execution surface.

## Receipt template

- Change decision/owner approval: `________________`;
- Host and UTC timestamp: `________________`;
- Source commit/SHA: `________________`;
- Stage path and backup path: `________________`;
- Config SHA-256: `________________`;
- Fixed-51 manifest SHA-256: `________________`;
- Fixed-51 universe SHA-256: `fa5c61703cac5c72218022f15d92ee46d6fa577df84c9cfcbf8cc005893bfe19`;
- Major-8 money universe SHA-256: `c9e0e9ff37725938c25a30e1bdcd25e615092f89e330111612a214a458c90940`;
- Preregistration SHA-256: `dffa60b17b785b9182560b1bace7105eef9d715488866dd665df77825cac7b68`;
- Focused test result: `________________`;
- No-network preflight result: `________________`;
- Public cycle result: `________________`;
- `orders_created_or_changed`: `0`;
- `private_api_calls`: `false`;
- `broker_calls`: `false`;
- `money_authority`: `false`;
- `release_or_promotion_authority`: `false`;
- `evidence_role`: `preparity_raw_not_final_n`;
- `fixed51_final_n_eligible`: `false`;
- Coverage expected / observed / error / unavailable: `________________`;
- Preserved config SHA-256 before/after: `________________`;
- Preserved journal tip and event count before/after: `________________`;
- Measured cycle runtime and selected `RuntimeMaxSec`: `________________`;
- Rollback verification and operator: `________________`.

## Atomic rollback (if required)

```sh
sudo systemctl stop sbr1-zero-risk-shadow.timer sbr1-zero-risk-shadow.service
sudo mv /opt/bybot-research/sbr1-zero-risk-shadow \
  /opt/bybot-research/sbr1-zero-risk-shadow-failed-$STAMP
sudo mv /opt/bybot-research/sbr1-zero-risk-shadow-backup-$STAMP \
  /opt/bybot-research/sbr1-zero-risk-shadow
sudo systemctl daemon-reload
sudo systemctl start sbr1-zero-risk-shadow.timer
```

Retain the failed tree and all receipts. Do not delete evidence or rewrite the
preregistration. Raw non-major fixed-51 signals can never be admitted; the old
major-8 lifecycle remains the only admission surface in this bounded release.
