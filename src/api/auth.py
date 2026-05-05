"""Authentication helpers.

Argon2 password hashing + signed-cookie sessions via itsdangerous.
TOTP (pyotp) is enforced when TOTP_ENFORCED=true in settings.

Two-step login when TOTP is enforced:
  Step 1: POST /auth/login  → validates password → returns HTTP 202 with a
          short-lived "totp_pending" token (5 min, not a full session).
  Step 2: POST /auth/totp   → validates OTP code → issues full session cookie.

When TOTP_ENFORCED=false (dev default), step 1 issues the full session directly.

Password hash:  computed once at module load via _get_cfo_hash() so Argon2's
                expensive KDF is not re-run on every login request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, URLSafeSerializer

from src.core.config import get_settings

_HASHER = PasswordHasher()


def hash_password(plain: str) -> str:
    return _HASHER.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    try:
        _HASHER.verify(stored_hash, plain)
        return True
    except VerifyMismatchError:
        return False


@lru_cache(maxsize=1)
def _get_cfo_hash() -> str:
    """Compute the CFO password hash once at startup instead of per-request."""
    return hash_password(get_settings().cfo_password.get_secret_value())


@lru_cache(maxsize=1)
def _get_fa_hash() -> str | None:
    """Compute the FA password hash once at startup. Returns None if FA not configured."""
    settings = get_settings()
    if not settings.fa_password:
        return None
    return hash_password(settings.fa_password.get_secret_value())


def check_credentials(username: str, password: str) -> str | None:
    """Validate username+password. Returns role ('cfo' or 'fa') on success, None on failure."""
    settings = get_settings()
    if username == settings.cfo_username and verify_password(_get_cfo_hash(), password):
        return "cfo"
    if (
        settings.fa_username
        and username == settings.fa_username
        and _get_fa_hash() is not None
        and verify_password(_get_fa_hash(), password)  # type: ignore[arg-type]
    ):
        return "fa"
    return None


# ---------------------------------------------------------------------------
# Session cookies
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Session:
    user_id: str
    role: str
    expires_at: int  # unix seconds


def _serializer(salt: str = "cfo-session") -> URLSafeSerializer:
    settings = get_settings()
    return URLSafeSerializer(settings.secret_key.get_secret_value(), salt=salt)


def issue_session(*, user_id: str, role: str = "cfo") -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "uid": user_id,
        "role": role,
        "exp": int(time.time()) + settings.session_lifetime_hours * 3600,
    }
    return _serializer().dumps(payload)


def issue_totp_pending_token(*, user_id: str, role: str) -> str:
    """Short-lived (5 min) token used during the TOTP verification step."""
    payload: dict[str, Any] = {
        "uid": user_id,
        "role": role,
        "exp": int(time.time()) + 300,  # 5 minutes
        "pending": True,
    }
    return _serializer(salt="totp-pending").dumps(payload)


def parse_totp_pending_token(token: str) -> tuple[str, str] | None:
    """Returns (user_id, role) if token is valid and unexpired, else None."""
    try:
        raw = _serializer(salt="totp-pending").loads(token)
    except BadSignature:
        return None
    if raw.get("exp", 0) < time.time():
        return None
    if not raw.get("pending"):
        return None
    return str(raw["uid"]), str(raw["role"])


def parse_session(token: str | None) -> Session | None:
    if not token:
        return None
    try:
        raw = _serializer().loads(token)
    except BadSignature:
        return None
    if raw.get("exp", 0) < time.time():
        return None
    if raw.get("pending"):
        return None  # pending tokens are NOT full sessions
    return Session(user_id=str(raw["uid"]), role=str(raw["role"]), expires_at=int(raw["exp"]))
