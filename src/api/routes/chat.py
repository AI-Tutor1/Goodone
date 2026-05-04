"""CFO chat endpoints.

* ``POST /chat/sessions`` — start a new conversation, returns ``{id}``.
* ``POST /chat/sessions/{id}/messages`` — send a user message, get the
  assistant's reply (and any tool-call traces) back in one response.
* ``GET  /chat/sessions/{id}`` — full message history for re-render.
* ``GET  /chat/tools`` — list the read-only tools wired into the
  service (handy for debugging / for the frontend to render
  capability hints).

Sessions live in a process-local store (``InMemorySessionStore``); see
``src/chat/service.py``. Provider selection comes from
``Settings.chat_provider`` (``stub`` by default).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.api.dependencies import db_session, require_session
from src.chat import (
    ChatService,
    ChatTurnRequest,
    ChatTurnResponse,
    get_chat_provider,
    get_default_store,
)
from src.chat.models import ChatMessage

router = APIRouter(prefix="/chat", tags=["chat"])


def _service() -> ChatService:
    return ChatService(provider=get_chat_provider(), store=get_default_store())


@router.get("/tools")
def list_tools(_session=Depends(require_session)) -> list[dict]:
    return [d.model_dump() for d in _service().tool_descriptors]


@router.post("/sessions")
def create_session(_session=Depends(require_session)) -> dict[str, str]:
    return {"id": _service().create_session().id}


@router.get("/sessions/{sid}")
def get_session(sid: str, _session=Depends(require_session)) -> dict:
    sess = get_default_store().get(sid)
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
    _session=Depends(require_session),
    db=Depends(db_session),
) -> ChatTurnResponse:
    try:
        return _service().turn(session_id=sid, user_message=body.message, db=db)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


def _message_payload(m: ChatMessage) -> dict:
    return {
        "role": m.role,
        "content": m.content,
        "tool_name": m.tool_name,
        "tool_input": m.tool_input,
        "created_at": m.created_at.isoformat(),
    }
