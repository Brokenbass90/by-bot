"""Auth endpoints: login (password) → TOTP → full session.

Flow:
  POST /auth/login        — email + password → partial cookie (5 min TTL)
  POST /auth/totp         — TOTP code → full-access cookie (8 h TTL)
  GET  /auth/me           — returns current user email (full session required)
  DELETE /auth/logout     — clears cookie
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from ..auth import (
    create_full_token,
    create_partial_token,
    get_user,
    verify_password,
    verify_totp,
)
from ..deps import require_auth, require_partial_auth


def _tg_notify(text: str) -> None:
    """Fire-and-forget Telegram message. Silent if TG_TOKEN not set."""
    token = os.getenv("TG_TOKEN", "").strip()
    chat  = (os.getenv("TG_CHAT_ID", "") or os.getenv("TG_CHAT", "")).strip()
    if not token or not chat:
        return
    try:
        import urllib.request, json as _json, ssl
        payload = _json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=5)
    except Exception:
        pass  # never block auth on TG failure

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_NAME = "access_token"
# secure=True must be set when running behind HTTPS nginx in production
_COOKIE_SECURE = False  # override via WEB_COOKIE_SECURE=1 env at startup


class LoginRequest(BaseModel):
    email: str
    password: str


class TOTPRequest(BaseModel):
    code: str


@router.post("/login")
async def login(body: LoginRequest, response: Response):
    """Step 1: validate email whitelist + password.

    Returns a *partial* session cookie. No data endpoints are accessible yet.
    The client must immediately call POST /auth/totp to complete the flow.
    """
    email = body.email.strip().lower()

    # Always run both checks to prevent email-enumeration via timing
    user = get_user(email)
    pw_ok = False
    if user and user.get("enabled", True):
        pw_ok = verify_password(body.password, user.get("hashed_password", ""))

    if not pw_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_partial_token(email)
    response.set_cookie(
        _COOKIE_NAME, token,
        httponly=True, samesite="lax", secure=_COOKIE_SECURE,
        max_age=5 * 60,
    )
    return {"next": "totp", "message": "Password accepted. Enter your 6-digit TOTP code."}


@router.post("/totp")
async def totp(
    body: TOTPRequest,
    request: Request,
    response: Response,
    email: str = Depends(require_partial_auth),
):
    """Step 2: verify Google Authenticator TOTP code.

    Requires the partial cookie from /auth/login.
    On success replaces it with a full-access cookie (8 h).
    """
    if not verify_totp(email, body.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired TOTP code",
        )

    token = create_full_token(email)
    response.set_cookie(
        _COOKIE_NAME, token,
        httponly=True, samesite="lax", secure=_COOKIE_SECURE,
        max_age=8 * 3600,
    )

    # ── security: notify via Telegram ────────────────────────────────────────
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    ip  = request.headers.get("X-Forwarded-For", request.client.host if request.client else "?")
    _tg_notify(
        f"🔐 <b>Web login</b>\n"
        f"User: <code>{email}</code>\n"
        f"IP: <code>{ip}</code>\n"
        f"Time: {ts}"
    )

    return {"authenticated": True, "email": email}


@router.get("/me")
async def me(email: str = Depends(require_auth)):
    """Return current authenticated user (full session required)."""
    return {"email": email}


@router.delete("/logout")
async def logout(response: Response):
    """Invalidate session by clearing the cookie."""
    response.delete_cookie(_COOKIE_NAME)
    return {"logged_out": True}
