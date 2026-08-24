# ATT1 fixed-51 raw-decision shadow — atomic default-off deploy plan

**Not executed.** This bundle has no order, account, private-API, sizing,
promotion, admitted-evidence, performance, or final-N authority. The money
universe remains major-8. The fixed-51 stream is raw decision telemetry only.

## Frozen identities

- authority: `zero_risk_public_att1_fixed51_evidence_no_orders_no_money_no_promotion`;
- fixed-51 universe SHA-256: `fa5c61703cac5c72218022f15d92ee46d6fa577df84c9cfcbf8cc005893bfe19`;
- preregistration SHA-256: `5e856b01940248e1adf784d6a1e53562543e7a5cc60765f3739694e5fe42cac4`;
- source closure SHA-256: `fe788a5e63344ca1e6bffcc0b975ce6e25b65799dca166b10a44fbe04c00ffaf`;
- canonical manifest SHA-256: `0f664417d4ff1d650f48a0e82e7f6c3efe775c82e2cfe21f81378a11c2f61880`;
- raw manifest-file SHA-256: `1d419ceaacce7d7575f6f2477d0c01485ee91f8e0ebf29e40a0f0b5448a9074e`;
- default-off config-file SHA-256: `612228824a9abf62ab064d5d78770a4c8dd45d912ca516ccdf7aa8f2a023af6f`.

`HFTUSDT` remains a frozen member and is expected to be stale/unavailable. It
may not be replaced. Any unknown symbol gap makes the service run fail partial;
zero successful evaluations fail closed. An expected HFT-only gap is explicit
and exits successfully so systemd does not manufacture a false outage.

## Offline gates

Run from the exact staged tree using the target server Python dependency set:

```sh
python3 -m pytest -q tests/test_att1_fixed51_shadow.py tests/test_att1_sbr1_live_wrappers.py tests/test_live_native_regime_gate.py
python3 -m py_compile bot/att1_fixed51_shadow.py scripts/run_att1_fixed51_zero_risk_shadow.py
python3 scripts/run_att1_fixed51_zero_risk_shadow.py
git diff --check
```

The no-network preflight must report `RESEARCH_ONLY_DISABLED`,
`measurement_authority=raw_decision_only`, and all three of
`evidence_admitted`, `performance_authority`, and `final_n_eligible` false.

## Atomic host procedure preserving runtime

First inventory the actual Python path, service user, unit state, and current
runtime path. The paths below are a template and not a claim about the host.

```sh
STAMP=20260824T____Z
LIVE=/opt/bybot-research/att1-fixed51-raw-shadow
STAGE=/opt/bybot-research/.att1-fixed51-raw-shadow-$STAMP
BACKUP=/opt/bybot-research/att1-fixed51-raw-shadow-backup-$STAMP

sudo systemctl stop att1-fixed51-raw-shadow.timer att1-fixed51-raw-shadow.service
sudo mkdir "$STAGE"
# Copy only the reviewed manifest closure, preregistration, config and units.
sudo rsync -a ./bot ./strategies ./scripts ./configs ./research_lab/prereg ./deploy "$STAGE"/

# Preserve the append-only runtime while no writer is active.
if sudo test -d "$LIVE/runtime"; then
  sudo rsync -a "$LIVE/runtime/" "$STAGE/runtime/"
fi

# Create a server-only config copy and change only enabled:false -> true.
# Retain both file hashes in the receipt. Never edit the repository default.
sudo mkdir -p "$STAGE/runtime/config"
sudo cp "$STAGE/configs/att1_fixed51_zero_risk_shadow_v1.json" \
  "$STAGE/runtime/config/att1_fixed51_zero_risk_shadow.json"

# Run the no-network preflight before the atomic swap. Then run one public
# cycle only if the staged server config has been explicitly enabled.
sudo /root/by-bot/.venv/bin/python \
  "$STAGE/scripts/run_att1_fixed51_zero_risk_shadow.py" \
  --root "$STAGE" \
  --config "$STAGE/runtime/config/att1_fixed51_zero_risk_shadow.json"

if sudo test -e "$LIVE"; then sudo mv "$LIVE" "$BACKUP"; fi
sudo mv "$STAGE" "$LIVE"
sudo cp "$LIVE/deploy/systemd/att1-fixed51-raw-shadow.service" /etc/systemd/system/
sudo cp "$LIVE/deploy/systemd/att1-fixed51-raw-shadow.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start att1-fixed51-raw-shadow.timer
```

The timer is not enabled by the repository and runs at `H1 + 2m20s` UTC with a
300-second freshness ceiling. The oneshot is fail-closed at
`TimeoutStartSec=150`, before that freshness window expires. Deploy between H1
decision windows. If a raw
event already exists for the current H1, do not change config/source identity
until the next H1; the journal correctly treats that as a conflict.

## Post-start receipt

Retain: host, UTC, staged/backup paths, Git SHA, server Python version, every
file SHA, repository/server config SHA, preflight stdout, timer/unit hashes,
first service status, journal mode/owner, journal event and chain hashes,
cycle status, exact failed/expected-unavailable symbols, and explicit zeros for
orders/private/broker/money/promotion authority.

## Rollback without losing evidence

Stop timer and service first. Never delete the failed tree. If it wrote newer
runtime events, validate and copy that entire runtime to the rollback stage
before restart. If schemas or chains cannot be reconciled mechanically, retain
both trees and remain stopped; do not truncate or rewrite either journal.
