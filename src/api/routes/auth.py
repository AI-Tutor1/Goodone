"""Login / logout / me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from src.api.auth import (
    Session,
    hash_password,
    issue_session,
    verify_password,
)
from src.api.dependencies import SESSION_COOKIE, require_session
from src.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    user_id: str
    role: str


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginPayload, response: Response) -> LoginResponse:
    """Bootstrap-CFO login.

    Phase 5 stores the CFO password as an Argon2 hash of the value in
    ``CFO_PASSWORD`` env var. There is exactly one user; multi-user lands
    when the FA / department-head personas wake up post-Phase 6.
    """
    settings = get_settings()
    if payload.username != settings.cfo_username:
        raise HTTPException(status_code=401, detail="invalid credentials")
    expected_hash = hash_password(settings.cfo_password.get_secret_value())
    if not verify_password(expected_hash, payload.password):
        raise HTTPException(status_code=401, detail="invalid credentials")

    token = issue_session(user_id=settings.cfo_username, role="cfo")
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="lax",
        max_age=settings.session_lifetime_hours * 3600,
    )
    return LoginResponse(user_id=settings.cfo_username, role="cfo")


@router.post("/logout")
def logout(response: Response) -> dict[str, str]:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": "true"}


@router.get("/me", response_model=LoginResponse)
def me(session: Session = Depends(require_session)) -> LoginResponse:
    return LoginResponse(user_id=session.user_id, role=session.role)
