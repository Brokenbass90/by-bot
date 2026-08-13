#!/usr/bin/env python3
"""Reset an existing web user's password without rotating TOTP or role.

The password is accepted only through an interactive hidden prompt.  It is
never accepted as a command-line argument, so it cannot leak through shell
history or the process list.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web import auth


MIN_PASSWORD_LENGTH = 12


def reset_user_password(email: str, password: str) -> dict[str, object]:
    """Replace only ``hashed_password`` for an existing enabled user."""
    normalized = str(email or "").strip().lower()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must contain at least {MIN_PASSWORD_LENGTH} characters")

    cfg = auth._load_config()
    users = cfg.get("users")
    if not isinstance(users, dict) or normalized not in users:
        raise KeyError(f"configured web user not found: {normalized}")
    existing = users.get(normalized)
    if not isinstance(existing, dict):
        raise ValueError(f"invalid web user record: {normalized}")
    if existing.get("enabled") is False:
        raise ValueError(f"web user is disabled: {normalized}")
    if not existing.get("totp_secret"):
        raise ValueError("TOTP is missing; use web/setup_totp.py instead")

    old_totp = str(existing["totp_secret"])
    old_role = bool(existing.get("is_admin"))
    new_hash = auth.hash_password(password)
    existing["hashed_password"] = new_hash
    users[normalized] = existing
    cfg["users"] = users
    auth._save_config(cfg)

    stored = auth._load_config().get("users", {}).get(normalized, {})
    if not auth.verify_password(password, str(stored.get("hashed_password") or "")):
        raise RuntimeError("password reset verification failed")
    if not hmac.compare_digest(str(stored.get("totp_secret") or ""), old_totp):
        raise RuntimeError("TOTP changed during password-only reset")
    if bool(stored.get("is_admin")) != old_role:
        raise RuntimeError("user role changed during password-only reset")

    return {
        "email": normalized,
        "totp_preserved": True,
        "role_preserved": True,
        "hash_fingerprint": hashlib.sha256(new_hash.encode("utf-8")).hexdigest()[:12],
    }


def _prompt_password() -> str:
    while True:
        first = getpass.getpass("New web password: ")
        second = getpass.getpass("Confirm new web password: ")
        if first != second:
            print("Passwords do not match. Try again.")
            continue
        if len(first) < MIN_PASSWORD_LENGTH:
            print(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters.")
            continue
        return first


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset an existing web password while preserving TOTP and role",
    )
    parser.add_argument("--email", required=True)
    args = parser.parse_args()

    try:
        receipt = reset_user_password(args.email, _prompt_password())
    except (KeyError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        "Password reset complete: "
        f"email={receipt['email']} "
        f"totp_preserved={str(receipt['totp_preserved']).lower()} "
        f"role_preserved={str(receipt['role_preserved']).lower()} "
        f"hash_fingerprint={receipt['hash_fingerprint']}"
    )
    print("Use the new password plus the existing Authenticator code to log in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
