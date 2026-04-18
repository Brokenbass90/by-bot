#!/usr/bin/env python3
"""One-time TOTP + password setup for a new web user.

Usage:
    python3 web/setup_totp.py --email you@example.com

This script:
  1. Prompts for a password (entered twice, never echoed)
  2. Generates a TOTP secret and prints the QR code URL
  3. Asks you to confirm a test TOTP code before saving
  4. Writes the user entry to configs/web_config.json

Run again to update an existing user's password or TOTP secret.
Run with --revoke to remove a user.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

import pyotp
import qrcode  # optional — prints ascii QR if unavailable

# Ensure we can import web.auth from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
from web.auth import hash_password, get_totp_uri, _CONFIG_PATH, _load_config, _save_config


def setup_user(email: str) -> None:
    email = email.strip().lower()
    print(f"\n=== Setting up user: {email} ===\n")

    # Password
    while True:
        pw1 = getpass.getpass("Enter password: ")
        pw2 = getpass.getpass("Confirm password: ")
        if pw1 == pw2:
            break
        print("Passwords do not match. Try again.")

    hashed = hash_password(pw1)

    # TOTP
    secret = pyotp.random_base32()
    uri = get_totp_uri(email, secret)
    print(f"\nTOTP secret: {secret}")
    print(f"\nScan this URI with Google Authenticator:")
    print(f"  {uri}")
    print()

    # Try to show ASCII QR code if qrcode package is available
    try:
        import qrcode as qr
        qr_obj = qr.QRCode()
        qr_obj.add_data(uri)
        qr_obj.make(fit=True)
        qr_obj.print_ascii()
    except ImportError:
        print("(Install 'qrcode' package for ASCII QR display)")

    # Confirm with a live code
    print("\nOpen Google Authenticator, add the account, then enter a 6-digit code to confirm.")
    import pyotp as _p
    totp = _p.TOTP(secret)
    while True:
        code = input("Enter TOTP code: ").strip()
        if totp.verify(code, valid_window=1):
            print("✓ TOTP code verified.\n")
            break
        print("Invalid code. Try again (make sure the clock is correct).")

    # Save
    cfg = _load_config()
    if "users" not in cfg:
        cfg["users"] = {}
    users = cfg["users"]
    existing = users.get(email, {})
    is_first_user = len(users) == 0
    cfg["users"][email] = {
        "hashed_password": hashed,
        "totp_secret": secret,
        "enabled": True,
        "is_admin": bool(existing.get("is_admin", is_first_user)),
    }
    _save_config(cfg)
    print(f"User '{email}' saved to {_CONFIG_PATH}")
    print("\nKeep the TOTP secret safe. If you lose access to Google Authenticator,")
    print("run this script again to regenerate a new secret.")


def revoke_user(email: str) -> None:
    email = email.strip().lower()
    cfg = _load_config()
    users: dict = cfg.get("users", {})
    if email not in users:
        print(f"User '{email}' not found.")
        return
    del users[email]
    cfg["users"] = users
    _save_config(cfg)
    print(f"User '{email}' revoked.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage web interface users (TOTP + password)")
    parser.add_argument("--email", required=True, help="User email address")
    parser.add_argument("--revoke", action="store_true", help="Remove user instead of adding")
    args = parser.parse_args()

    if args.revoke:
        revoke_user(args.email)
    else:
        setup_user(args.email)


if __name__ == "__main__":
    main()
