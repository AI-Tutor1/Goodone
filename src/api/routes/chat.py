"""CFO chat endpoints.

* ``POST /chat/sessions`` — start a new conversation, returns ``{id}``.
* ``GET  /chat/sessions``     — list all sessions for the current user (DB-backed in production).
* ``POST /chat/sessions/{id}/messages`` — send a user message, get the assistant's reply back.
* ``GET  /chat/sessions/{id}`` — full message history for re-render.
* ``GET  /chat/tools`` — list the read-only tools wired into the service.

In production (APP_ENV=production) sessions are persisted to PostgreSQL via
``PostgresChatSessionStore`` so history survives API restarts. In other
environments the process-local ``InMemorySessionStore`` is used (tests too).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.dependencies import db_session, require_session
from src.chat import (
    ChatService,
    ChatTurnRequest,
    ChatTurnResponse,
    get_chat_provider,
    get_default_store,
)
from src.chat.models import ChatMessage
from src.chat.pg_store import get_pg_store
from src.core.config import get_settings

router = APIRouter(prefix="/chat", tags=["chat"])


def _use_pg() -> bool:
    return get_settings().app_env == "production"


def _service(db: Any = None) -> Any:
    if _use_pg():
        from src.chat.pg_service import PgChatService

        return PgChatService(provider=get_chat_provider(), pg_store=get_pg_store())
    return ChatService(provider=get_chat_provider(), store=get_default_store())


@router.get("/tools")
def list_tools(_session: Any = Depends(require_session)) -> list[dict[str, Any]]:
    return [d.model_dump() for d in _service().tool_descriptors]


@router.get("/sessions")
def list_sessions(
    _session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    """List all chat sessions. In production, returns DB-persisted sessions."""
    if _use_pg():
        return {"sessions": get_pg_store().list_sessions(db=db)}
    store = get_default_store()
    return {
        "sessions": [
            {
                "session_id": sid,
                "message_count": len(_s.messages) if (_s := store.get(sid)) is not None else 0,
            }
            for sid in store.list_ids()
        ]
    }


@router.post("/sessions")
def create_session(
    auth: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, str]:
    if _use_pg():
        sess = get_pg_store().create(user_id=auth.user_id, db=db)
    else:
        sess = get_default_store().create()
    return {"id": sess.id}


@router.get("/sessions/{sid}")
def get_session(
    sid: str,
    _session: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> dict[str, Any]:
    sess = get_pg_store().get(sid, db=db) if _use_pg() else get_default_store().get(sid)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"unknown chat session: {sid}")
    return {
        "id": sess.id,
        "created_at": sess.created_at.isoformat(),
        "messages": [_message_payload(m) for m in sess.messages],
    }


@router.post("/sessions/{sid}/messages", response_model=ChatTurnResponse)
def post_message(
    sid: str,
    body: ChatTurnRequest,
    auth: Any = Depends(require_session),
    db: Session = Depends(db_session),
) -> ChatTurnResponse:
    if _use_pg():
        from src.chat.pg_service import PgChatService

        svc = PgChatService(provider=get_chat_provider(), pg_store=get_pg_store())
        try:
            return svc.turn(session_id=sid, user_message=body.message, db=db)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
    try:
        return ChatService(provider=get_chat_provider(), store=get_default_store()).turn(
            session_id=sid, user_message=body.message, db=db
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


def _message_payload(m: ChatMessage) -> dict[str, Any]:
    return {
        "role": m.role,
        "content": m.content,
        "tool_name": m.tool_name,
        "tool_input": m.tool_input,
        "created_at": m.created_at.isoformat(),
    }
