"""Simple password-gate authentication."""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Shared secret used to sign session tokens.
_SECRET = os.getenv("APP_SESSION_SECRET", "change-me-in-production")
_APP_USERNAME = os.getenv("APP_USERNAME", "admin")
_APP_PASSWORD = os.getenv("APP_PASSWORD", "")
# Set to "localhost" in local dev so the session cookie is visible to Next.js (port 3000)
# and the API (port 8000). Leave unset in production (host-only cookie).
_COOKIE_DOMAIN = os.getenv("APP_COOKIE_DOMAIN") or None
_SESSION_DAYS = 30


def _session_cookie_kwargs() -> dict:
    kwargs: dict = {"key": "session", "path": "/"}
    if _COOKIE_DOMAIN:
        kwargs["domain"] = _COOKIE_DOMAIN
    return kwargs


def _sign(payload: str) -> str:
    return hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def _make_token() -> str:
    """Create a signed session token: random_nonce.expiry_ts.signature."""
    nonce = secrets.token_hex(16)
    expires = int((datetime.now(timezone.utc) + timedelta(days=_SESSION_DAYS)).timestamp())
    payload = f"{nonce}.{expires}"
    sig = _sign(payload)
    return f"{payload}.{sig}"


def verify_token(token: str) -> bool:
    """Verify a session token is valid and not expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False
        nonce, expires_str, sig = parts
        payload = f"{nonce}.{expires_str}"
        if not hmac.compare_digest(sig, _sign(payload)):
            return False
        if int(expires_str) < int(datetime.now(timezone.utc).timestamp()):
            return False
        return True
    except Exception:
        return False


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    """Validate username/password and set session cookie."""
    if not _APP_PASSWORD:
        raise HTTPException(status_code=500, detail="APP_PASSWORD not configured on server")
    if not hmac.compare_digest(request.username, _APP_USERNAME) or not hmac.compare_digest(request.password, _APP_PASSWORD):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = _make_token()
    response.set_cookie(
        **_session_cookie_kwargs(),
        value=token,
        httponly=True,
        samesite="lax",
        max_age=_SESSION_DAYS * 86400,
    )
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    """Clear session cookie."""
    response.delete_cookie(**_session_cookie_kwargs())
    return {"ok": True}


@router.get("/check")
async def check(request: Request):
    """Check if the current session is valid."""
    token = request.cookies.get("session", "")
    if verify_token(token):
        return {"authenticated": True}
    raise HTTPException(status_code=401, detail="Not authenticated")
