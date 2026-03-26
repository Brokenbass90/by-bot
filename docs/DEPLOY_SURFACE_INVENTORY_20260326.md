# Deploy Surface Inventory 2026-03-26

This is an inventory for safe cleanup, not a deletion order.

## Current Canonical Paths
- Local working secrets: `.env`
- Server working secrets: `/root/by-bot/.env`
- Redacted reference: `configs/server.env.example`
- Live service: `bybot.service`
- Live app dir: `/root/by-bot`

## Active Deploy Entry Points

### Primary Local Deploy
- `scripts/deploy_session10.sh`
- Purpose:
  - patches `/root/by-bot/.env`
  - copies current bot files directly over SSH/SCP
  - enables DeepSeek and live strategy flags
- Status: keep as current canonical local deploy helper

### Full Bot File Push
- `scripts/deploy_all_latest.sh`
- Purpose:
  - pushes a broad set of bot/core files to `/root/by-bot`
  - good for controlled syncs after local fixes
- Status: keep, but use carefully because it is broader than `deploy_session10.sh`

### Targeted DeepSeek Patch
- `scripts/deploy_deepseek_audit.sh`
- Purpose:
  - targeted DeepSeek/TG hardening deploy
- Status: keep as targeted maintenance helper

### Server-Side Recovery / Clean Restart
- `scripts/clean_deploy_server.sh`
- Purpose:
  - stop old processes
  - refresh code on server
  - restart bot cleanly
- Status: keep, but treat as server-side recovery tool, not default daily deploy

## Historical / One-Off Deploy Scripts

These are not automatically wrong, but they are no longer the best first choice.

- `scripts/deploy_session9.sh`
- `scripts/deploy_full_20260318.sh`
- `scripts/deploy_live_evening_20260319.sh`
- `scripts/deploy_sloped_atom_canary_20260318.sh`
- `scripts/deploy_to_server.sh`

## Why They Are Legacy-Like
- they encode older rollout assumptions
- some rely on GitHub pull flows while the current live flow often uses direct file copy
- some are single-date rollout scripts for one specific canary or evening patch

## Near-Term Cleanup Actions
1. Keep `deploy_session10.sh` as the default documented local deploy path for now.
2. Keep `deploy_all_latest.sh` only as a broader manual sync helper.
3. Mark dated one-off scripts as historical in docs before deleting anything.
4. Do not remove server recovery scripts until live status and env flow are fully stable.

## Not Safe To Delete Yet
- Any deploy script that still contains unique env patch logic
- Any server recovery script used during a live outage
- Any dated deploy script that documents a live rollout we may need to reproduce
