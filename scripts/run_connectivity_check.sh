#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f ".venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

HOST="${BYBOT_SSH_HOST:-root@64.226.73.119}"
KEY="${BYBOT_SSH_KEY:-$HOME/.ssh/by-bot}"
BYBIT_BASE="${BYBIT_BASE:-https://api.bybit.com}"
TIMEOUT_SEC="${CONNECT_TIMEOUT_SEC:-8}"

echo "=== CONNECTIVITY CHECK ==="
echo "time_utc=$(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "host=${HOST}"
echo "bybit=${BYBIT_BASE}"
echo "timeout_sec=${TIMEOUT_SEC}"
echo ""

echo "--- local dns ---"
python3 - <<'PY' || true
import socket
host = "api.bybit.com"
try:
    ip = socket.gethostbyname(host)
    print(f"dns_ok {host} -> {ip}")
except Exception as e:
    print(f"dns_fail {host}: {e}")
PY

echo ""
echo "--- local bybit http ---"
set +e
curl -sS --max-time "$TIMEOUT_SEC" "${BYBIT_BASE%/}/v5/market/time" >/tmp/bybot_conn_local_bybit.json
RC=$?
set -e
if [[ $RC -eq 0 ]]; then
  echo "bybit_http_ok"
  sed -n '1,1p' /tmp/bybot_conn_local_bybit.json
else
  echo "bybit_http_fail rc=$RC"
fi

echo ""
echo "--- local ssh ---"
set +e
ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout="$TIMEOUT_SEC" "$HOST" "echo ssh_ok host=\$(hostname) time=\$(date -u '+%F %T UTC')" >/tmp/bybot_conn_ssh.txt 2>/tmp/bybot_conn_ssh.err
SSH_RC=$?
set -e
if [[ $SSH_RC -eq 0 ]]; then
  cat /tmp/bybot_conn_ssh.txt
else
  echo "ssh_fail rc=$SSH_RC"
  sed -n '1,3p' /tmp/bybot_conn_ssh.err
fi

if [[ $SSH_RC -eq 0 ]]; then
  echo ""
  echo "--- server bybit http ---"
  set +e
  ssh -i "$KEY" -o BatchMode=yes -o ConnectTimeout="$TIMEOUT_SEC" "$HOST" \
    "curl -sS --max-time ${TIMEOUT_SEC} '${BYBIT_BASE%/}/v5/market/time'" >/tmp/bybot_conn_server_bybit.json 2>/tmp/bybot_conn_server_bybit.err
  SRV_RC=$?
  set -e
  if [[ $SRV_RC -eq 0 ]]; then
    echo "server_bybit_http_ok"
    sed -n '1,1p' /tmp/bybot_conn_server_bybit.json
  else
    echo "server_bybit_http_fail rc=$SRV_RC"
    sed -n '1,3p' /tmp/bybot_conn_server_bybit.err
  fi
fi

echo ""
echo "connectivity check done"
