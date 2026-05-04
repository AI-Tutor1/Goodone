"""Authentication helpers.

Argon2 password hashing + signed-cookie sessions via :mod:`itsdangerous`.
TOTP scaffolding (pyotp) is wired but not enforced; the dashboard can opt
in by sending an OTP code on login. There's exactly one admin / CFO user
in Phase 5 — bootstrapped via an env-driven password.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# Session cookies
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Session:
    user_id: str
    role: str
    expires_at: int  # unix seconds


def _serializer() -> URLSafeSerializer:
    settings = get_settings()
    return URLSafeSerializer(settings.secret_key.get_secret_value(), salt="cfo-session")


def issue_session(*, user_id: str, role: str = "cfo") -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "uid": user_id,
        "role": role,
        "exp": int(time.time()) + settings.session_lifetime_hours * 3600,
    }
    return _serializer().dumps(payload)


def parse_session(token: str | None) -> Session | None:
    if not token:
        return None
    try:
        raw = _serializer().loads(token)
    except BadSignature:
        return None
    if raw.get("exp", 0) < time.time():
        return None
    return Session(user_id=str(raw["uid"]), role=str(raw["role"]), expires_at=int(raw["exp"]))


# Add a session_lifetime_hours pull-through so tests can monkey-patch.
def _ensure_settings_field() -> None:
    """Guard for older Settings that don't expose session_lifetime_hours."""
    settings = get_settings()
    if not hasattr(settings, "session_lifetime_hours"):
        # Pydantic Settings reload wouldn't have this — fall back to 8.
        settings.session_lifetime_hours = 8


_ensure_settings_field()
