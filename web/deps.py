"""FastAPI dependency helpers for authentication."""

from __future__ import annotations

from fastapi import Cookie, HTTPException, status
from typing import Optional

from .auth import get_email_from_token, is_admin_user


def require_auth(
    access_token: Optional[str] = Cookie(default=None),
) -> str:
    """FastAPI dependency. Returns email of authenticated user or raises 401."""
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    email = get_email_from_token(access_token, require_full=True)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )
    return email


def require_partial_auth(
    access_token: Optional[str] = Cookie(default=None),
) -> str:
    """For TOTP endpoint: accept partial (password-only) session."""
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    email = get_email_from_token(access_token, require_full=False)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid",
        )
    return email


def require_admin(
    access_token: Optional[str] = Cookie(default=None),
) -> str:
    """Require a full authenticated session and admin privileges."""
    email = require_auth(access_token=access_token)
    if not is_admin_user(email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return email
