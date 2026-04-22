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
_DEFAULT_SECRET_MARKERS = {
    "change-me-in-production-use-openssl-rand-hex-32",
    "change-me-use-openssl-rand-hex-32",
    "",
}

# Default to pbkdf2_sha256 for portability. Keep bcrypt as a legacy verifier
# so older hashes still work if they already exist in config.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def _looks_like_default_secret(secret: str) -> bool:
    return secret.strip() in _DEFAULT_SECRET_MARKERS


def _default_runtime_root() -> Path:
    return Path(__file__).parent.parent / "runtime"


def _looks_like_local_dev_runtime() -> bool:
    host = os.getenv("WEB_HOST", "127.0.0.1").strip().lower()
    dev_mode = os.getenv("WEB_DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
    cookie_secure = os.getenv("WEB_COOKIE_SECURE", "0").strip().lower() in {"1", "true", "yes", "on"}
    runtime_root = Path(os.getenv("WEB_RUNTIME_ROOT", str(_default_runtime_root())))
    local_host = host in {"127.0.0.1", "localhost", "::1"}
    return dev_mode or (local_host and not cookie_secure and runtime_root == _default_runtime_root())


def enforce_runtime_security() -> None:
    """Fail fast if web auth is about to run with unsafe production settings."""
    if _looks_like_local_dev_runtime():
        return
    if _looks_like_default_secret(_SECRET_KEY) or len(_SECRET_KEY.strip()) < 32:
        raise RuntimeError(
            "WEB_JWT_SECRET is still default/weak. Set a strong secret before starting web outside local dev."
        )
    if os.getenv("WEB_COOKIE_SECURE", "0").strip().lower() not in {"1", "true", "yes", "on"}:
        raise RuntimeError(
            "WEB_COOKIE_SECURE must be enabled before starting web outside local dev."
        )


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


def is_admin_user(email: str) -> bool:
    """Return True only for explicit admins.

    Migration-safe bootstrap rule:
      - if `is_admin` is explicitly set on the user record, honor it
      - otherwise, allow the sole configured user to act as bootstrap admin
    """
    cfg = _load_config()
    users: dict = cfg.get("users", {})
    email = email.strip().lower()
    user = users.get(email)
    if not user:
        return False
    if "is_admin" in user:
        return bool(user.get("is_admin"))
    return len(users) == 1


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
