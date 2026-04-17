#!/usr/bin/env bash
# Run the trading journal web interface.
#
# Usage:
#   bash scripts/run_web.sh              # production mode, port 8765
#   WEB_DEV_MODE=1 bash scripts/run_web.sh  # dev mode (CORS allows localhost:3000)
#   WEB_ENABLE_DOCS=1 bash scripts/run_web.sh  # enable /docs (Swagger UI)
#
# In production, put nginx in front:
#   location /trading/ {
#       proxy_pass http://127.0.0.1:8765/;
#       proxy_set_header Host $host;
#       proxy_set_header X-Forwarded-Proto https;
#   }
#
# Then set WEB_COOKIE_SECURE=1 so cookies are HTTPS-only.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

source .venv/bin/activate

# Required: set a real secret in production
export WEB_JWT_SECRET="${WEB_JWT_SECRET:-change-me-use-openssl-rand-hex-32}"

# Optional: restrict to HTTPS cookies when behind nginx
export WEB_COOKIE_SECURE="${WEB_COOKIE_SECURE:-0}"

HOST="${WEB_HOST:-127.0.0.1}"
PORT="${WEB_PORT:-8765}"

echo "[web] Starting Trading Journal on http://${HOST}:${PORT}"
echo "[web] To set up a user: python3 web/setup_totp.py --email you@example.com"
echo "[web] JWT secret: ${WEB_JWT_SECRET:0:8}... (first 8 chars)"

exec uvicorn web.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info \
    --no-access-log
