"""Authentication: email whitelist + bcrypt password + TOTP (Google Authenticator).

Security model:
  1. Only emails in ALLOWED_EMAILS (web_config.json) can ever log in.
  2. Correct password alone gives a *partial* session (TOTP pending).
  3. A valid TOTP code promotes the session to full access.
  4. All tokens are short-lived JWT (8h), stored in httpOnly cookies.
  5. No other entry path exists.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import pyotp
from jose import JWTError, jwt
from passlib.context import CryptContext

# ── config ────────────────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent.parent / "configs" / "web_config.json"
_SECRET_KEY = os.getenv("WEB_JWT_SECRET", "change-me-in-production-use-openssl-rand-hex-32")
_ALGORITHM = "HS256"
_ACCESS_TOKEN_EXPIRE_SECONDS = 8 * 3600   # 8 hours
_PARTIAL_TOKEN_EXPIRE_SECONDS = 5 * 60    # 5 minutes to complete TOTP

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── config loader ─────────────────────────────────────────────────────────────

def _load_config() -> dict:
    """Load web_config.json. Returns empty dict if missing."""
    if not _CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return {}


def _save_config(cfg: dict) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(_CONFIG_PATH)


# ── user lookup ───────────────────────────────────────────────────────────────

def get_user(email: str) -> Optional[dict]:
    """Return user record from config or None if not found / not allowed."""
    cfg = _load_config()
    users: dict = cfg.get("users", {})
    email = email.strip().lower()
    return users.get(email)


def is_email_allowed(email: str) -> bool:
    return get_user(email) is not None


# ── password helpers ──────────────────────────────────────────────────────────

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


# ── TOTP helpers ──────────────────────────────────────────────────────────────

def verify_totp(email: str, code: str) -> bool:
    """Verify a 6-digit TOTP code against the user's stored secret."""
    user = get_user(email)
    if not user:
        return False
    secret = user.get("totp_secret")
    if not secret:
        return False
    totp = pyotp.TOTP(secret)
    # valid_window=1 allows ±30s clock drift
    return totp.verify(str(code).strip(), valid_window=1)


def get_totp_uri(email: str, secret: str, issuer: str = "TradingBot") -> str:
    """Return the otpauth:// URI to display as a QR code."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=email, issuer_name=issuer)


# ── JWT helpers ───────────────────────────────────────────────────────────────

def _create_token(data: dict, expire_seconds: int) -> str:
    payload = dict(data)
    payload["exp"] = int(time.time()) + expire_seconds
    return jwt.encode(payload, _SECRET_KEY, algorithm=_ALGORITHM)


def create_partial_token(email: str) -> str:
    """Token issued after correct password, before TOTP is verified."""
    return _create_token({"sub": email, "stage": "partial"}, _PARTIAL_TOKEN_EXPIRE_SECONDS)


def create_full_token(email: str) -> str:
    """Full-access token issued after TOTP is verified."""
    return _create_token({"sub": email, "stage": "full"}, _ACCESS_TOKEN_EXPIRE_SECONDS)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT. Returns payload dict or None on any error."""
    try:
        return jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
    except JWTError:
        return None


def get_email_from_token(token: str, require_full: bool = True) -> Optional[str]:
    """Return email if token is valid (and full-access if require_full=True)."""
    payload = decode_token(token)
    if not payload:
        return None
    if require_full and payload.get("stage") != "full":
        return None
    email = payload.get("sub")
    if not email or not is_email_allowed(email):
        return None
    return email
