"""Login / logout / me + TOTP 2-step authentication."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from src.api.auth import (
    Session,
    check_credentials,
    issue_session,
    issue_totp_pending_token,
    parse_totp_pending_token,
)
from src.api.dependencies import SESSION_COOKIE, require_session
from src.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


class TotpPayload(BaseModel):
    pending_token: str
    otp_code: str


class LoginResponse(BaseModel):
    user_id: str
    role: str


@router.post("/login")
def login(payload: LoginPayload, response: Response) -> Any:
    """Step 1 of authentication.

    When TOTP is not enforced: issues a full session cookie and returns HTTP 200.
    When TOTP is enforced: validates password only, returns HTTP 202 with a
    short-lived pending token — the client must complete step 2 via POST /auth/totp.
    """
    settings = get_settings()
    role = check_credentials(payload.username, payload.password)
    if role is None:
        raise HTTPException(status_code=401, detail="invalid credentials")

    if settings.totp_enforced and settings.cfo_totp_secret is not None:
        pending = issue_totp_pending_token(user_id=payload.username, role=role)
        response.status_code = 202
        return {"requires_totp": True, "pending_token": pending}

    # TOTP not enforced — issue full session immediately.
    token = issue_session(user_id=payload.username, role=role)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_lifetime_hours * 3600,
    )
    return LoginResponse(user_id=payload.username, role=role)


@router.post("/totp", response_model=LoginResponse)
def verify_totp(payload: TotpPayload, response: Response) -> LoginResponse:
    """Step 2 — validate the TOTP code and issue a full session cookie."""
    import pyotp

    settings = get_settings()
    if not settings.totp_enforced or settings.cfo_totp_secret is None:
        raise HTTPException(status_code=400, detail="TOTP is not enforced on this server")

    result = parse_totp_pending_token(payload.pending_token)
    if result is None:
        raise HTTPException(status_code=401, detail="invalid or expired pending token")

    user_id, role = result
    secret = settings.cfo_totp_secret.get_secret_value()
    if not pyotp.TOTP(secret).verify(payload.otp_code, valid_window=1):
        raise HTTPException(status_code=401, detail="invalid OTP code")

    token = issue_session(user_id=user_id, role=role)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_lifetime_hours * 3600,
    )
    return LoginResponse(user_id=user_id, role=role)


@router.get("/totp-setup")
def totp_setup(session: Session = Depends(require_session)) -> dict[str, Any]:
    """Return the provisioning URI for scanning into an authenticator app.

    Only CFO can call this. Returns the otpauth:// URI and the raw base32 secret.
    """
    import pyotp

    settings = get_settings()
    if settings.cfo_totp_secret is None:
        raise HTTPException(status_code=404, detail="CFO_TOTP_SECRET not configured")
    secret = settings.cfo_totp_secret.get_secret_value()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(session.user_id, issuer_name="Tuitional Finance")
    return {"provisioning_uri": uri, "secret": secret}


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": "true"}


@router.get("/me", response_model=LoginResponse)
def me(session: Session = Depends(require_session)) -> LoginResponse:
    return LoginResponse(user_id=session.user_id, role=session.role)
