"""Orchestrates a single chat turn.

Flow per turn:

1. Append the user's message to the session.
2. Ask the provider for intent (text or tool calls) given history + tool list.
3. If the provider asked for tool calls, run each one against the GL
   (read-only — see ``src/chat/tools.py``), append a ``role="tool"`` row
   per result, then ask the provider to continue with those results.
4. Return the final assistant text in a ``ChatTurnResponse``.

The service does **not** persist sessions across process restarts in
Phase 6. ``InMemorySessionStore`` is the default; swap it for a Postgres
implementation when retention becomes a requirement.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from threading import Lock
from typing import TYPE_CHECKING, Any

from src.chat.models import ChatMessage, ChatSession, ChatTurnResponse
from src.chat.provider import ChatProvider, ProviderTurn
from src.chat.tools import Tool, builtin_registry

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------


class InMemorySessionStore:
    """Process-local session store. Thread-safe via a single lock."""

    def __init__(self) -> None:
        self._sessions: dict[str, ChatSession] = {}
        self._lock = Lock()

    def create(self) -> ChatSession:
        sess = ChatSession(id=uuid.uuid4().hex[:12])
        with self._lock:
            self._sessions[sess.id] = sess
        return sess

    def get(self, sid: str) -> ChatSession | None:
        with self._lock:
            return self._sessions.get(sid)

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())

    def append(self, sid: str, msg: ChatMessage) -> None:
        with self._lock:
            sess = self._sessions.get(sid)
            if sess is None:
                msg_err = f"unknown chat session: {sid}"
                raise KeyError(msg_err)
            sess.messages.append(msg)


_default_store: InMemorySessionStore | None = None


def get_default_store() -> InMemorySessionStore:
    """Process-wide singleton. Tests should call ``reset_default_store``."""
    global _default_store
    if _default_store is None:
        _default_store = InMemorySessionStore()
    return _default_store


def reset_default_store() -> None:
    global _default_store
    _default_store = None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


# Hard cap on tool-call rounds per turn — prevents a buggy provider from
# getting stuck in a loop and burning through DB connections / API quota.
MAX_TOOL_ROUNDS = 3


class ChatService:
    """Glue between the provider, the tool registry, and the session store."""

    def __init__(
        self,
        *,
        provider: ChatProvider,
        store: InMemorySessionStore,
        tools: dict[str, Tool] | None = None,
    ) -> None:
        self._provider = provider
        self._store = store
        self._tools = tools if tools is not None else builtin_registry()

    @property
    def tool_descriptors(self) -> list[Any]:
        return [t.descriptor() for t in self._tools.values()]

    def create_session(self) -> ChatSession:
        return self._store.create()

    def turn(self, *, session_id: str, user_message: str, db: Session) -> ChatTurnResponse:
        sess = self._store.get(session_id)
        if sess is None:
            msg = f"unknown chat session: {session_id}"
            raise KeyError(msg)

        user_msg = ChatMessage(role="user", content=user_message)
        self._store.append(session_id, user_msg)

        tool_messages: list[ChatMessage] = []
        for _round in range(MAX_TOOL_ROUNDS):
            sess = self._store.get(session_id)  # refresh after append
            assert sess is not None
            intent = self._provider.turn(
                history=sess.messages,
                tools=self.tool_descriptors,
            )
            if not intent.tool_calls:
                return self._finalise(session_id, intent, tool_messages)
            tool_results = self._run_tool_calls(intent, db, tool_messages, session_id)
            sess = self._store.get(session_id)
            assert sess is not None
            intent = self._provider.continue_with_tool_results(
                history=sess.messages,
                tools=self.tool_descriptors,
                tool_results=tool_results,
            )
            if not intent.tool_calls:
                return self._finalise(session_id, intent, tool_messages)
        # Safety valve: too many rounds → return whatever we have plus a note.
        fallback = ProviderTurn(
            text="(stopped after too many tool rounds — narrow your question and try again)",
        )
        return self._finalise(session_id, fallback, tool_messages)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _run_tool_calls(
        self,
        intent: ProviderTurn,
        db: Session,
        sink: list[ChatMessage],
        session_id: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        results: list[tuple[str, dict[str, Any]]] = []
        for call in intent.tool_calls:
            tool = self._tools.get(call.name)
            if tool is None:
                payload = {"error": f"unknown tool: {call.name}"}
            else:
                try:
                    payload = tool.fn(db, call.input)
                except Exception as exc:
                    payload = {"error": f"{type(exc).__name__}: {exc}"}
            results.append((call.name, payload))
            tool_msg = ChatMessage(
                role="tool",
                content=str(payload),
                tool_name=call.name,
                tool_input=call.input,
            )
            self._store.append(session_id, tool_msg)
            sink.append(tool_msg)
        return results

    def _finalise(
        self,
        session_id: str,
        intent: ProviderTurn,
        tool_messages: Iterable[ChatMessage],
    ) -> ChatTurnResponse:
        assistant = ChatMessage(role="assistant", content=intent.text or "(no answer)")
        self._store.append(session_id, assistant)
        return ChatTurnResponse(
            session_id=session_id,
            assistant=assistant,
            tool_calls=list(tool_messages),
        )
