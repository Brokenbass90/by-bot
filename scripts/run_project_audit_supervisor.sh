#!/usr/bin/env bash
# One read-only/project-runtime audit cycle, optionally repeated on the Mac.
# Recommended background mode:
#   bash scripts/run_project_audit_supervisor.sh --with-model --full-first --loop
# `--full-first` refreshes the expensive all-strategy liveness table once; later
# loop iterations run only the cheap deterministic/model layers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WITH_MODEL=0
FULL=0
FULL_FIRST=0
AUTO_FULL=0
SYNC_LIVE=0
LOOP=0
INTERVAL_SEC=21600
while [ "$#" -gt 0 ]; do
  case "$1" in
    --with-model) WITH_MODEL=1 ;;
    --full) FULL=1 ;;
    --full-first) FULL=1; FULL_FIRST=1 ;;
    --auto-full) AUTO_FULL=1 ;;
    --sync-live) SYNC_LIVE=1 ;;
    --loop) LOOP=1 ;;
    --interval-sec) shift; INTERVAL_SEC="${1:?missing interval}" ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

mkdir -p runtime/project_audit logs

run_cycle() (
  local lock="runtime/project_audit/run.lock"
  if ! mkdir "$lock" 2>/dev/null; then
    local old_pid=""
    if [ -r "$lock/pid" ]; then
      read -r old_pid < "$lock/pid" || true
    fi
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
      echo "audit cycle already running: $lock (pid=$old_pid)"
      return 0
    fi
    # A killed terminal/tool process can bypass EXIT traps.  Recover only this
    # exact audit lock and only after proving that its owner is no longer alive.
    [ ! -e "$lock/pid" ] || rm -f "$lock/pid"
    if ! rmdir "$lock" 2>/dev/null || ! mkdir "$lock" 2>/dev/null; then
      echo "cannot recover stale audit lock: $lock" >&2
      return 1
    fi
  fi
  printf '%s\n' "$$" > "$lock/pid"
  trap 'rm -f "$lock/pid"; rmdir "$lock" 2>/dev/null || true' EXIT INT TERM HUP

  if [ "$SYNC_LIVE" = "1" ]; then
    bash scripts/sync_web_live_mirror.sh || true
  fi

  if [ "$AUTO_FULL" = "1" ]; then
    if [ ! -r runtime/liveness_table.txt ] \
      || ! grep -q '^LIVENESS_SWEEP_COMPLETE ' runtime/liveness_table.txt \
      || ! find runtime/liveness_table.txt -mmin -2160 -print -quit | grep -q .; then
      FULL=1
    else
      FULL=0
    fi
  fi

  python3 scripts/build_tech_registry.py --quiet

  if [ "$FULL" = "1" ]; then
    python3 research_lab/continuous_audit.py --full
  else
    python3 research_lab/continuous_audit.py
  fi

  if [ "$WITH_MODEL" = "1" ]; then
    python3 research_lab/ai_auditor.py --with-model
  else
    python3 research_lab/ai_auditor.py
  fi
  python3 research_lab/audit_registry.py
  python3 research_lab/negative_outcome_registry.py || true
  python3 research_lab/audit_health.py || true

  AUDIT_WITH_MODEL="$WITH_MODEL" AUDIT_FULL="$FULL" python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path
p = Path("runtime/project_audit/supervisor_status.json")
registry_path = Path("runtime/project_audit/registry.json")
try:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
except (OSError, ValueError):
    registry = {}
p.write_text(json.dumps({
    "schema_id": "project_audit_supervisor_status_v1",
    "last_success_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "proposal_only": True,
    "live_mutation": False,
    "with_model": os.environ.get("AUDIT_WITH_MODEL") == "1",
    "full_liveness": os.environ.get("AUDIT_FULL") == "1",
    "registry_summary": registry.get("summary", {}),
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
)

while :; do
  run_cycle 2>&1 | tee -a logs/project_audit_supervisor.log
  [ "$LOOP" = "1" ] || break
  if [ "$FULL_FIRST" = "1" ]; then
    FULL=0
    FULL_FIRST=0
  fi
  sleep "$INTERVAL_SEC"
done
