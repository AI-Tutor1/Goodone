"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Cookie, Depends, HTTPException

from src.api.auth import Session, parse_session
from src.core.db import get_engine

SESSION_COOKIE = "tuitional_session"


def require_session(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Session:
    s = parse_session(session_cookie)
    if s is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return s


def require_cfo(session: Session = Depends(require_session)) -> Session:
    """Restrict to the CFO role.

    Phase 5 has only the CFO persona; this is here so future roles slot in
    without rewriting every route.
    """
    if session.role != "cfo":
        raise HTTPException(status_code=403, detail="cfo role required")
    return session


def db_session() -> Iterator:
    """Yield a transactional SQLAlchemy session bound to the app engine."""
    from sqlalchemy.orm import Session as _Session

    engine = get_engine()
    with _Session(bind=engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
