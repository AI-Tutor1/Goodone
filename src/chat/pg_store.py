"""Postgres-backed chat session store.

Replaces ``InMemorySessionStore`` in production so chat history survives
API restarts. Sessions and messages live in ``audit.chat_sessions`` and
``audit.chat_messages`` (created by migration 0002).

The interface intentionally mirrors ``InMemorySessionStore`` but each method
takes an optional ``db`` (SQLAlchemy Session). In-memory callers pass
``db=None``; production callers always pass the request-scoped DB session.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text

from src.chat.models import ChatMessage, ChatSession

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class PostgresChatSessionStore:
    """DB-backed session store. Thread-safe via Postgres transactions."""

    def create(self, *, user_id: str, db: "Session") -> ChatSession:
        sid = uuid.uuid4().hex[:12]
        db.execute(
            text(
                "INSERT INTO audit.chat_sessions (session_id, user_id) VALUES (:sid, :uid)"
            ),
            {"sid": sid, "uid": user_id},
        )
        db.commit()
        return ChatSession(id=sid)

    def get(self, sid: str, *, db: "Session") -> ChatSession | None:
        row = db.execute(
            text(
                "SELECT session_id, created_at FROM audit.chat_sessions WHERE session_id = :sid"
            ),
            {"sid": sid},
        ).one_or_none()
        if row is None:
            return None

        msg_rows = db.execute(
            text(
                """
                SELECT role, content, tool_name, tool_input, created_at
                FROM audit.chat_messages
                WHERE session_id = :sid
                ORDER BY msg_id
                """
            ),
            {"sid": sid},
        ).all()

        messages = [
            ChatMessage(
                role=r.role,
                content=r.content,
                tool_name=r.tool_name,
                tool_input=r.tool_input,
                created_at=r.created_at,
            )
            for r in msg_rows
        ]
        return ChatSession(id=row.session_id, created_at=row.created_at, messages=messages)

    def append(self, sid: str, msg: ChatMessage, *, db: "Session") -> None:
        import json
        db.execute(
            text(
                """
                INSERT INTO audit.chat_messages
                    (session_id, role, content, tool_name, tool_input)
                VALUES (:sid, :role, :content, :tool_name, :tool_input::jsonb)
                """
            ),
            {
                "sid": sid,
                "role": msg.role,
                "content": msg.content,
                "tool_name": msg.tool_name,
                "tool_input": json.dumps(msg.tool_input) if msg.tool_input else None,
            },
        )
        db.commit()

    def list_ids(self, *, db: "Session") -> list[str]:
        rows = db.execute(
            text(
                "SELECT session_id FROM audit.chat_sessions ORDER BY created_at DESC LIMIT 100"
            )
        ).all()
        return [r.session_id for r in rows]

    def list_sessions(self, *, db: "Session") -> list[dict]:
        rows = db.execute(
            text(
                """
                SELECT s.session_id, s.user_id, s.created_at,
                       COUNT(m.msg_id) AS message_count,
                       MAX(m.created_at) AS last_message_at
                FROM audit.chat_sessions s
                LEFT JOIN audit.chat_messages m ON m.session_id = s.session_id
                GROUP BY s.session_id, s.user_id, s.created_at
                ORDER BY s.created_at DESC
                LIMIT 50
                """
            )
        ).all()
        return [
            {
                "session_id": r.session_id,
                "user_id": r.user_id,
                "created_at": r.created_at.isoformat(),
                "message_count": r.message_count,
                "last_message_at": r.last_message_at.isoformat() if r.last_message_at else None,
            }
            for r in rows
        ]


_pg_store: PostgresChatSessionStore | None = None


def get_pg_store() -> PostgresChatSessionStore:
    global _pg_store
    if _pg_store is None:
        _pg_store = PostgresChatSessionStore()
    return _pg_store
