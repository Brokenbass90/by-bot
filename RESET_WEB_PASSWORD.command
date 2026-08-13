#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/nikolay.bulgakov/Documents/Work/bot-new/bybit-bot-clean-v28"
SSH_KEY="/Users/nikolay.bulgakov/.ssh/by-bot"
SERVER="root@64.226.73.119"
REMOTE_DIR="/root/by-bot"
OWNER_EMAIL="brokenbass1990@gmail.com"

echo "Resetting only the web password. TOTP and trading services are preserved."
echo "The password will be hidden and will not be sent to Codex or shell history."
echo

scp -q -i "$SSH_KEY" "$PROJECT_DIR/web/reset_password.py" "$SERVER:$REMOTE_DIR/web/reset_password.py"
LOCAL_SHA="$(shasum -a 256 "$PROJECT_DIR/web/reset_password.py" | awk '{print $1}')"
REMOTE_SHA="$(ssh -i "$SSH_KEY" "$SERVER" "sha256sum '$REMOTE_DIR/web/reset_password.py' | awk '{print \$1}'")"
if [[ "$LOCAL_SHA" != "$REMOTE_SHA" ]]; then
  echo "ERROR: uploaded reset utility hash mismatch"
  exit 1
fi
echo "Verified reset utility sha256=$LOCAL_SHA"
ssh -t -i "$SSH_KEY" "$SERVER" \
  "cd '$REMOTE_DIR' && chmod 700 web/reset_password.py && .venv/bin/python web/reset_password.py --email '$OWNER_EMAIL'"

echo
echo "Done. Log in with the new password and the existing Authenticator code."
read "?Press Enter to close this window."
